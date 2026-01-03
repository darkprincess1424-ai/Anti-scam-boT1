import os
import logging
import sqlite3
import sys
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== FLASK ВЕБ-СЕРВЕР ДЛЯ UPTIMEROBOT ==========
web_app = Flask(__name__)

# Переменная для отслеживания состояния бота
bot_status = {
    "status": "running",
    "started_at": datetime.now().isoformat(),
    "last_ping": datetime.now().isoformat(),
    "total_requests": 0
}

@web_app.route('/')
def home():
    """Главная страница для проверки"""
    bot_status["total_requests"] += 1
    return jsonify({
        "status": "online",
        "service": "anti-scam-bot",
        "bot_status": bot_status["status"],
        "uptime": str(datetime.now() - datetime.fromisoformat(bot_status["started_at"])),
        "requests": bot_status["total_requests"],
        "timestamp": datetime.now().isoformat()
    })

@web_app.route('/health')
def health():
    """Health check для Render и UptimeRobot"""
    bot_status["total_requests"] += 1
    bot_status["last_ping"] = datetime.now().isoformat()
    
    return jsonify({
        "status": "healthy",
        "service": "anti-scam-bot",
        "bot": bot_status["status"],
        "last_ping": bot_status["last_ping"],
        "timestamp": datetime.now().isoformat(),
        "message": "🤖 Бот работает нормально"
    }), 200

@web_app.route('/ping')
def ping():
    """Простой ping для UptimeRobot"""
    bot_status["total_requests"] += 1
    bot_status["last_ping"] = datetime.now().isoformat()
    
    return jsonify({
        "status": "pong",
        "timestamp": datetime.now().isoformat()
    }), 200

@web_app.route('/status')
def status():
    """Статус бота"""
    bot_status["total_requests"] += 1
    
    try:
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM scammers")
        scammer_count = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM garants")
        garant_count = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM search_history")
        search_count = cursor.fetchone()[0] or 0
        
        conn.close()
        
        stats = {
            "scammers": scammer_count,
            "garants": garant_count,
            "searches": search_count
        }
    except:
        stats = {"error": "Не удалось получить статистику"}
    
    return jsonify({
        "status": "online",
        "bot": bot_status,
        "database_stats": stats,
        "timestamp": datetime.now().isoformat()
    })

def run_web_server():
    """Запуск веб-сервера в отдельном потоке"""
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Запуск веб-сервера на порту {port}")
    print(f"📊 Health check: http://0.0.0.0:{port}/health")
    print(f"🏓 Ping: http://0.0.0.0:{port}/ping")
    print(f"📈 Status: http://0.0.0.0:{port}/status")
    
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ========== ТЕЛЕГРАМ БОТ ==========
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден в переменных окружения!")
    print("💡 Добавьте BOT_TOKEN в Render Dashboard → Environment")
    sys.exit(1)

ADMIN_ID = 8281804228

print(f"🚀 Запуск Anti-Scam Bot с мониторингом...")
print(f"👑 Админ ID: {ADMIN_ID}")
print("✅ Токен бота найден")

# База данных
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы если их нет
cursor.execute('''
CREATE TABLE IF NOT EXISTS scammers (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    scam_count INTEGER DEFAULT 1,
    proofs TEXT,
    added_by INTEGER,
    added_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS garants (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    added_by INTEGER,
    added_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    searcher_id INTEGER,
    search_date TEXT
)''')

conn.commit()
print("✅ База данных инициализирована")

# File ID для фото (ЗАМЕНИТЕ ЭТИ ID НА СВОИ!)
# Как получить File ID: отправьте фото боту, затем используйте команду /getid
PHOTO_START = "AgACAgIAAxkBAANzaVQoJVrivNUbO_0_kp0vYE7j0yoAAuwSaxsh3qFKzfjQ3DqXYecBAAMCAAN5AAM4BA"
PHOTO_REGULAR = "AgACAgIAAxkBAANEaVQhuac6f3ohxbrRLsiQyovlv04AArUSaxsh3qFKgpVFnIrVhA0BAAMCAAN5AAM4BA"
PHOTO_SCAMMER = "AgACAgIAAxkBAAN5aVQoPw9O48N7kKXsxI_oJQ8VECsAAu0Saxsh3qFK3skb3DmGQlkBAAMCAAN5AAM4BA"
PHOTO_GARANT = "AgACAgIAAxkBAANzaVQoJVrivNUbO_0_kp0vYE7j0yoAAuwSaxsh3qFKzfjQ3DqXYecBAAMCAAN5AAM4BA"  # Фото для гаранта
PHOTO_USER_PROFILE = "AgACAgIAAxkBAANEaVQhuac6f3ohxbrRLsiQyovlv04AArUSaxsh3qFKgpVFnIrVhA0BAAMCAAN5AAM4BA"  # Фото для профиля пользователя
PHOTO_USER_SCAMMER = "AgACAgIAAxkBAAN5aVQoPw9O48N7kKXsxI_oJQ8VECsAAu0Saxsh3qFK3skb3DmGQlkBAAMCAAN5AAM4BA"  # Фото для скамера

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_welcome_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Новостной канал", url="https://t.me/AntiScamLaboratory")],
        [InlineKeyboardButton("🕵️ Слить скамера", url="https://t.me/antiscambaseAS")]
    ])

def get_check_result_inline_keyboard(username):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Слить скамера", url="https://t.me/antiscambaseAS")],
        [InlineKeyboardButton("🔗 Вечная ссылка", callback_data=f"perma_link:{username}")]
    ])

def get_main_reply_keyboard(user_id=None, chat_type="private"):
    if chat_type in ["group", "supergroup", "channel"]:
        return None
    elif chat_type == "private":
        keyboard = [
            ["👤 Мой профиль", "⭐ Список гарантов"],
            ["🕵️ Слить скамера", "📋 Команды"],
            ["ℹ️ Информация о боте"]
        ]
        if user_id == ADMIN_ID:
            keyboard.append(["🔐 Админ панель"])
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    return None

def get_admin_reply_keyboard():
    keyboard = [
        ["➕ Добавить гаранта", "➖ Удалить гаранта"],
        ["➕ Добавить скамера", "➖ Удалить скамера"],
        ["📊 Статистика", "⬅️ На главную"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_type = update.effective_chat.type
    
    welcome_text = (
        "Добро пожаловать в 𝐀𝐧𝐭𝐢 𝐬𝐜𝐚𝐦 🔍\n\n"
        "Если вас обманули, вы можете слить скамера в предложку 🕵️\n\n"
        "⚡️ Возможности:\n"
        "• /check @username - проверка пользователя\n"
        "• /check в ответ на сообщение - проверка отправителя\n"
        "• /me - проверить себя\n"
        "• База для слива скамеров\n\n"
        f"📊 Статус бота: ✅ Онлайн"
    )
    
    try:
        await update.message.reply_photo(
            photo=PHOTO_START,
            caption=welcome_text,
            reply_markup=get_welcome_inline_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке фото: {e}")
        await update.message.reply_text(
            welcome_text,
            reply_markup=get_welcome_inline_keyboard()
        )
    
    if chat_type == "private":
        if user.id == ADMIN_ID:
            await update.message.reply_text(
                "👑 Вы администратор! Доступны специальные команды.",
                reply_markup=get_admin_reply_keyboard()
            )
        else:
            await update.message.reply_text(
                "Используйте кнопки ниже для навигации:",
                reply_markup=get_main_reply_keyboard(user.id, chat_type)
            )
    else:
        await update.message.reply_text(
            "Используйте команды: /check @username, /me, /help"
        )

async def check_user(user_id, username, searcher_id):
    try:
        cursor.execute(
            "INSERT INTO search_history (user_id, username, searcher_id, search_date) VALUES (?, ?, ?, ?)",
            (user_id, username, searcher_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        cursor.execute("SELECT COUNT(*) FROM search_history WHERE user_id = ?", (user_id,))
        search_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT scam_count, proofs FROM scammers WHERE user_id = ?", (user_id,))
        scammer = cursor.fetchone()
        
        cursor.execute("SELECT * FROM garants WHERE user_id = ?", (user_id,))
        garant = cursor.fetchone()
        
        conn.commit()
        
        if scammer:
            scam_count, proofs = scammer
            return {"type": "scammer", "scam_count": scam_count, "proofs": proofs, "search_count": search_count}
        elif garant:
            return {"type": "garant", "search_count": search_count}
        else:
            return {"type": "regular", "search_count": search_count}
    except Exception as e:
        logger.error(f"Ошибка при проверке пользователя: {e}")
        return {"type": "regular", "search_count": 0}

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        username = context.args[0].replace('@', '')
        user_id = hash(username) % 1000000
    elif update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        username = target_user.username or f"id{target_user.id}"
        user_id = target_user.id
    else:
        await update.message.reply_text("Использование: /check @username")
        return
    
    result = await check_user(user_id, username, update.effective_user.id)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if result["type"] == "regular":
        response = (
            f"👤 User: @{username}\n"
            f"🤖 Идет проверка в базе...\n"
            f"🗯 Пользователя нету в базе данных.\n\n"
            f"👁‍🗨 Пользователя искали: {result['search_count']} раз\n\n"
            f"🔝 Проверенно @AntilScam_Bot\n\n"
            f"🗓️ Дата и время проверки [{current_time}]\n\n"
            f"От администрации: прошу не вестись на скам 💕"
        )
        
        try:
            await update.message.reply_photo(
                photo=PHOTO_REGULAR,
                caption=response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
        except Exception as e:
            await update.message.reply_text(
                response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
    
    elif result["type"] == "scammer":
        response = (
            f"👤 User: @{username}\n"
            f"🤖 Идет проверка в базе...\n"
            f"📍 ОБНАРУЖЕН СКАМЕР\n\n"
            f"Количество скамов: {result['scam_count']}\n\n"
            f"Пруфы на скам ⏬\n"
            f"{result['proofs'] or 'Доказательства не указаны'}\n\n"
            f"👁‍🗨 Пользователя искали: {result['search_count']} раз\n\n"
            f"🔝 Проверенно @AntilScam_Bot\n\n"
            f"🗓️ Дата и время проверки [{current_time}]\n\n"
            f"От администрации: прошу не вестись на скам 💕"
        )
        
        try:
            await update.message.reply_photo(
                photo=PHOTO_SCAMMER,
                caption=response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
        except Exception as e:
            await update.message.reply_text(
                response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
    
    else:  # garant
        response = (
            f"👤 User: @{username}\n"
            f"🤖 Идет проверка в базе...\n"
            f"⭐ ЭТО ГАРАНТ\n\n"
            f"👁‍🗨 Пользователя искали: {result['search_count']} раз\n\n"
            f"🔝 Проверенно @AntilScam_Bot\n\n"
            f"🗓️ Дата и время проверки [{current_time}]\n\n"
            f"✅ Этот пользователь проверен и является гарантом"
        )
        await update.message.reply_text(response)

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /me и обработчик кнопки 'Мой профиль' с фото"""
    user = update.effective_user
    result = await check_user(user.id, user.username or f"id{user.id}", user.id)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Определяем какое фото показывать
    if result["type"] == "scammer":
        profile_photo = PHOTO_USER_SCAMMER
        status_text = f"СКАМЕР ⚠️\nКоличество скамов: {result['scam_count']}"
        status_emoji = "⚠️"
    elif result["type"] == "garant":
        profile_photo = PHOTO_GARANT
        status_text = "ГАРАНТ ✅"
        status_emoji = "✅"
    else:
        profile_photo = PHOTO_USER_PROFILE
        status_text = "ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ"
        status_emoji = "👤"
    
    user_info = (
        f"👤 {status_emoji} Ваш профиль:\n\n"
        f"🆔 ID: {user.id}\n"
        f"📛 Имя: {user.first_name}\n"
        f"📧 Username: @{user.username or 'Нет'}\n"
        f"🔍 Статус: {status_text}\n\n"
        f"👁‍🗨 Вас искали: {result['search_count']} раз\n"
        f"🗓️ Дата проверки: {current_time}"
    )
    
    try:
        # Пытаемся отправить фото
        await update.message.reply_photo(
            photo=profile_photo,
            caption=user_info,
            reply_markup=get_main_reply_keyboard(user.id, update.effective_chat.type)
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке фото профиля: {e}")
        # Если не получилось отправить фото, отправляем текст
        await update.message.reply_text(
            user_info, 
            reply_markup=get_main_reply_keyboard(user.id, update.effective_chat.type)
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 Anti-Scam Bot - Справка\n\n"
        "📌 Основные команды:\n"
        "/start - Начать работу с ботом\n"
        "/check @username - Проверить пользователя\n"
        "/check (в ответ на сообщение) - Проверить отправителя\n"
        "/me - Показать мой профиль\n\n"
        "🕵️‍♂️ Админ команды:\n"
        "/add_garant @username - Добавить гаранта\n"
        "/del_garant @username - Удалить гаранта\n"
        "/add_scammer @username доказательства - Добавить скамера\n"
        "/del_scammer @username - Удалить скамера\n\n"
        "📊 Статус бота: /status\n"
        "📸 Получить ID фото: /getid\n"
        "🛠 Разработчик: @SAGYN_OFFICIAL"
    )
    await update.message.reply_text(
        help_text,
        reply_markup=get_main_reply_keyboard(update.effective_user.id, update.effective_chat.type)
    )

# Админ команды
async def add_garant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Только для администратора!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_garant @username")
        return
    
    username = context.args[0].replace('@', '')
    cursor.execute(
        "INSERT OR REPLACE INTO garants (user_id, username, added_by, added_date) VALUES (?, ?, ?, ?)",
        (hash(username) % 1000000, username, ADMIN_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    await update.message.reply_text(f"✅ @{username} добавлен в гаранты")

async def del_garant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Только для администратора!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_garant @username")
        return
    
    username = context.args[0].replace('@', '')
    cursor.execute("DELETE FROM garants WHERE username = ?", (username,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ @{username} удален из гарантов")
    else:
        await update.message.reply_text(f"❌ @{username} не найден")

async def add_scammer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Только для администратора!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /add_scammer @username доказательства")
        return
    
    username = context.args[0].replace('@', '')
    proofs = ' '.join(context.args[1:])
    
    cursor.execute(
        """INSERT INTO scammers (user_id, username, scam_count, proofs, added_by, added_date) 
        VALUES (?, ?, 1, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET 
        scam_count = scam_count + 1,
        proofs = proofs || '\n' || excluded.proofs""",
        (hash(username) % 1000000, username, proofs, ADMIN_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    await update.message.reply_text(f"✅ @{username} добавлен в скамеры")

async def del_scammer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Только для администратора!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_scammer @username")
        return
    
    username = context.args[0].replace('@', '')
    cursor.execute("DELETE FROM scammers WHERE username = ?", (username,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ @{username} удален из скамеров")
    else:
        await update.message.reply_text(f"❌ @{username} не найден")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("perma_link:"):
        username = query.data.split(":")[1]
        await query.edit_message_text(
            f"🔗 Вечная ссылка на профиль: @{username}\n\n"
            f"Ссылка: https://t.me/{username}"
        )

# Команда для проверки статуса бота
async def bot_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус бота"""
    status_text = (
        "🤖 Статус Anti-Scam Bot:\n\n"
        f"📊 Статус: ✅ Онлайн\n"
        f"⏱ Запущен: {bot_status['started_at'][:19]}\n"
        f"🔄 Uptime: {str(datetime.now() - datetime.fromisoformat(bot_status['started_at']))}\n"
        f"📡 Последний пинг: {bot_status['last_ping'][:19]}\n"
        f"🌐 Запросов к API: {bot_status['total_requests']}\n\n"
        f"📈 Health check: /health доступен\n"
        f"🏓 Ping: /ping доступен\n\n"
        f"⚡ Бот работает нормально"
    )
    await update.message.reply_text(status_text)

# Команда для получения ID фото
async def getid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить File ID фото"""
    if update.message.photo:
        photo = update.message.photo[-1]
        response = (
            f"📸 File ID получен!\n\n"
            f"`{photo.file_id}`\n\n"
            f"📏 Размер: {photo.file_size:,} байт\n"
            f"📐 Разрешение: {photo.width}×{photo.height}\n\n"
            f"💡 Скопируйте этот ID и вставьте в код:\n"
            f"PHOTO_XXX = \"{photo.file_id}\""
        )
        await update.message.reply_text(response, parse_mode='Markdown')
    elif update.message.document:
        await update.message.reply_text(
            f"📄 Document ID: `{update.message.document.file_id}`",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ Отправьте фото, чтобы получить его File ID\n\n"
            "📌 Просто отправьте фото в этот чат, и я покажу его ID\n"
            "💡 Используйте этот ID в переменных PHOTO_START, PHOTO_REGULAR и т.д."
        )

# Обработчик текстовых сообщений (кнопок)
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        user = update.effective_user
        chat_type = update.effective_chat.type
        
        if chat_type != "private":
            return
        
        if text == "👤 Мой профиль":
            await me_command(update, context)
        elif text == "⭐ Список гарантов":
            cursor.execute("SELECT username FROM garants LIMIT 50")
            garants = cursor.fetchall()
            if garants:
                garants_list = "\n".join([f"⭐ @{g[0]}" for g in garants])
                response = f"⭐ Список гарантов:\n\n{garants_list}"
            else:
                response = "📭 Список гарантов пуст"
            await update.message.reply_text(response, reply_markup=get_main_reply_keyboard(user.id, chat_type))
        elif text == "🕵️ Слить скамера":
            await update.message.reply_text(
                "Для слива скамера перейдите по ссылке:\nhttps://t.me/antiscambaseAS",
                reply_markup=get_main_reply_keyboard(user.id, chat_type)
            )
        elif text == "📋 Команды":
            await help_command(update, context)
        elif text == "ℹ️ Информация о боте":
            info_text = (
                "🤖 Anti Scam Bot\n\n"
                "🔍 Бот для проверки пользователей на скам\n\n"
                "📊 Возможности:\n"
                "• Проверка пользователей в базе данных\n"
                "• База скамеров и гарантов\n"
                "• История проверок\n"
                "• Мониторинг UptimeRobot\n"
                "• Фото профиля для каждого статуса\n\n"
                "🛠 Разработчик: @SAGYN_OFFICIAL\n"
                "📅 Версия: 3.0 (с фото профиля)"
            )
            await update.message.reply_text(info_text, reply_markup=get_main_reply_keyboard(user.id, chat_type))
        elif text == "🔐 Админ панель" and user.id == ADMIN_ID:
            await update.message.reply_text("👑 Админ панель", reply_markup=get_admin_reply_keyboard())
        elif text == "➕ Добавить гаранта" and user.id == ADMIN_ID:
            await update.message.reply_text("Используйте команду: /add_garant @username")
        elif text == "➖ Удалить гаранта" and user.id == ADMIN_ID:
            await update.message.reply_text("Используйте команду: /del_garant @username")
        elif text == "➕ Добавить скамера" and user.id == ADMIN_ID:
            await update.message.reply_text("Используйте команду: /add_scammer @username доказательства")
        elif text == "➖ Удалить скамера" and user.id == ADMIN_ID:
            await update.message.reply_text("Используйте команду: /del_scammer @username")
        elif text == "📊 Статистика" and user.id == ADMIN_ID:
            cursor.execute("SELECT COUNT(*) FROM scammers")
            scammer_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM garants")
            garant_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM search_history")
            search_count = cursor.fetchone()[0]
            
            stats_text = (
                f"📊 Статистика бота:\n\n"
                f"🚨 Скамеров в базе: {scammer_count}\n"
                f"⭐ Гарантов в базе: {garant_count}\n"
                f"🔍 Всего проверок: {search_count}\n\n"
                f"🌐 Хост: Render.com\n"
                f"📡 Запросов к API: {bot_status['total_requests']}\n"
                f"🔄 Версия: 3.0"
            )
            await update.message.reply_text(stats_text, reply_markup=get_admin_reply_keyboard())
        elif text == "⬅️ На главную":
            await update.message.reply_text(
                "Главное меню:",
                reply_markup=get_main_reply_keyboard(user.id, chat_type)
            )
        else:
            await update.message.reply_text(
                "Используйте кнопки ниже:",
                reply_markup=get_main_reply_keyboard(user.id, chat_type)
            )
    except Exception as e:
        logger.error(f"Ошибка в handle_text_message: {e}")

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Запуск системы"""
    try:
        print("🚀 Запуск системы с мониторингом и фото профиля...")
        
        # Запускаем веб-сервер в отдельном потоке
        web_thread = threading.Thread(target=run_web_server, daemon=True)
        web_thread.start()
        
        print("🌐 Веб-сервер запущен")
        print(f"👑 Админ ID: {ADMIN_ID}")
        
        # Ждем немного для запуска веб-сервера
        time.sleep(2)
        
        # Создаем приложение Telegram бота
        print("🤖 Инициализация Telegram бота...")
        application = Application.builder().token(TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("me", me_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", bot_status_command))
        application.add_handler(CommandHandler("getid", getid_command))
        application.add_handler(CommandHandler("add_garant", add_garant))
        application.add_handler(CommandHandler("del_garant", del_garant))
        application.add_handler(CommandHandler("add_scammer", add_scammer))
        application.add_handler(CommandHandler("del_scammer", del_scammer))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        # Обработчик неизвестных команд
        async def unknown_command(update, context):
            await update.message.reply_text(
                "❌ Неизвестная команда. Используйте /start или /help",
                reply_markup=get_main_reply_keyboard(update.effective_user.id, update.effective_chat.type)
            )
        
        application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
        
        print("✅ Система настроена и готова к работе")
        print("📡 Запуск polling Telegram бота...")
        print("🚀 Система запущена! Отправьте /start в Telegram")
        print("\n📸 Фото профиля добавлены:")
        print("   • Обычный пользователь - PHOTO_USER_PROFILE")
        print("   • Скамер - PHOTO_USER_SCAMMER")
        print("   • Гарант - PHOTO_GARANT")
        print("\n💡 Чтобы получить новые File ID для фото, используйте команду /getid")
        print("\n🔗 Для UptimeRobot используйте эти URL:")
        print(f"   • Monitor URL: https://anti-scam-bot1-7.onrender.com/health")
        print(f"   • Ping URL: https://anti-scam-bot1-7.onrender.com/ping")
        print(f"   • Status URL: https://anti-scam-bot1-7.onrender.com/status")
        
        # Запускаем polling с обработкой ошибок
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=None
        )
        
    except Exception as e:
        print(f"🔴 Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
