import os
import logging
import sqlite3
import sys
from datetime import datetime
from threading import Thread
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, ChatMemberHandler

# ========== НАСТРОЙКА БЕЗОПАСНОГО ЛОГИРОВАНИЯ ==========
def filter_sensitive_data(record):
    """Фильтруем токены и другие секреты из логов"""
    import re
    
    # Токены Telegram ботов
    if hasattr(record, 'msg'):
        # Фильтруем токены в формате 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
        record.msg = re.sub(r'\b\d{10}:[A-Za-z0-9_-]{35}\b', '***FILTERED***', record.msg)
        # Фильтруем токены в URL
        record.msg = re.sub(r'bot\d+:[\w\-]+', 'bot***FILTERED***', record.msg)
    
    # API ключи и другие секреты
    if hasattr(record, 'args'):
        new_args = []
        for arg in record.args:
            if isinstance(arg, str):
                arg = re.sub(r'\b[A-Za-z0-9_-]{35,}\b', '***FILTERED***', arg)
            new_args.append(arg)
        record.args = tuple(new_args)
    
    return True

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Применяем фильтр ко всем логгерам
for handler in logging.getLogger().handlers:
    handler.addFilter(filter_sensitive_data)

# Создаем логгер после настройки
logger = logging.getLogger(__name__)

# Применяем фильтр к библиотечным логгерам
for name in ['httpx', 'telegram', 'werkzeug']:
    lib_logger = logging.getLogger(name)
    for handler in lib_logger.handlers:
        handler.addFilter(filter_sensitive_data)

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
web_app = Flask(__name__)

@web_app.route('/')
def home():
    """Главная страница для Render"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 Anti-Scam Bot</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .container {
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                max-width: 600px;
                margin: 0 auto;
            }
            h1 { font-size: 2.5em; }
            .status { 
                background: #4CAF50; 
                padding: 10px 20px;
                border-radius: 50px;
                display: inline-block;
                margin: 20px 0;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Anti-Scam Bot</h1>
            <div class="status">✅ ONLINE</div>
            <p>Бот работает на Render 24/7</p>
            <p>Для использования найдите бота в Telegram</p>
            <p><small>Health check: /health</small></p>
        </div>
    </body>
    </html>
    """

@web_app.route('/health')
def health():
    """Health check для Render"""
    return jsonify({
        "status": "healthy", 
        "service": "anti-scam-bot",
        "timestamp": datetime.now().isoformat()
    }), 200

def run_web_server():
    """Запуск веб-сервера в отдельном потоке"""
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False)

# ========== ТЕЛЕГРАМ БОТ ==========
# КРИТИЧЕСКИ ВАЖНО: Токен должен быть в переменных окружения
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    logger.error("BOT_TOKEN не установлен в переменных окружения!")
    sys.exit("❌ Ошибка: BOT_TOKEN не найден. Установите его в Render Dashboard")

# ID администратора
ADMIN_ID = 8281804228

# File ID для фото
PHOTO_START = "AgACAgIAAxkBAANzaVQoJVrivNUbO_0_kp0vYE7j0yoAAuwSaxsh3qFKzfjQ3DqXYecBAAMCAAN5AAM4BA"
PHOTO_REGULAR = "AgACAgIAAxkBAANEaVQhuac6f3ohxbrRLsiQyovlv04AArUSaxsh3qFKgpVFnIrVhA0BAAMCAAN5AAM4BA"
PHOTO_SCAMMER = "AgACAgIAAxkBAAN5aVQoPw9O48N7kKXsxI_oJQ8VECsAAu0Saxsh3qFK3skb3DmGQlkBAAMCAAN5AAM4BA"

# Создаем базу данных
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы
cursor.execute('''
CREATE TABLE IF NOT EXISTS scammers (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    scam_count INTEGER DEFAULT 1,
    proofs TEXT,
    added_by INTEGER,
    added_date TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS garants (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    added_by INTEGER,
    added_date TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    searcher_id INTEGER,
    search_date TEXT
)
''')

conn.commit()

# Функция для создания инлайн клавиатуры приветствия
def get_welcome_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Новостной канал", url="https://t.me/AntiScamLaboratory")],
        [InlineKeyboardButton("🕵️ Слить скамера", url="https://t.me/antiscambaseAS")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Функция для создания инлайн кнопок для результата проверки
def get_check_result_inline_keyboard(username):
    keyboard = [
        [InlineKeyboardButton("🚨 Слить скамера", url="https://t.me/antiscambaseAS")],
        [InlineKeyboardButton("🔗 Вечная ссылка", callback_data=f"perma_link:{username}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_reply_keyboard(user_id=None, chat_type="private"):
    """Создает клавиатуру в зависимости от типа чата"""
    
    if chat_type in ["group", "supergroup", "channel"]:
        keyboard = [
            ["/check @username", "/me"],
            ["/help", "/start"]
        ]
    elif chat_type == "private":
        keyboard = [
            ["👤 Мой профиль", "⭐ Список гарантов"],
            ["🕵️ Слить скамера", "📋 Команды"],
            ["ℹ️ Информация о боте"]
        ]
        
        if user_id == ADMIN_ID:
            keyboard.append(["🔐 Админ панель"])
    else:
        keyboard = [
            ["/help", "/start"]
        ]
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_admin_reply_keyboard():
    keyboard = [
        ["➕ Добавить гаранта", "➖ Удалить гаранта"],
        ["➕ Добавить скамера", "➖ Удалить скамера"],
        ["📊 Статистика", "⬅️ На главную"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик добавления/удаления бота из чата"""
    try:
        chat_member = update.chat_member
        
        if (chat_member.new_chat_member and 
            chat_member.new_chat_member.user.id == context.bot.id and
            chat_member.new_chat_member.status == "member"):
            
            chat_type = update.effective_chat.type
            chat_title = update.effective_chat.title or "Чат"
            
            if chat_type in ["group", "supergroup"]:
                welcome_message = (
                    f"🤖 Приветствую в группе «{chat_title}»!\n\n"
                    f"Я - Anti-Scam Bot, помогу проверить пользователей на скам.\n\n"
                    f"📌 Основные команды:\n"
                    f"/check @username - проверить пользователя\n"
                    f"/check (в ответ на сообщение) - проверить отправителя\n"
                    f"/me - показать мой профиль\n"
                    f"/help - справка по командам\n\n"
                    f"💡 Совет: Используйте бота в личных сообщениях для полного функционала!"
                )
                
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=welcome_message,
                    reply_markup=get_main_reply_keyboard(chat_type=chat_type)
                )
                
                logger.info(f"Бота добавили в группу: {chat_title}")
                
        elif (chat_member.old_chat_member and 
              chat_member.old_chat_member.user.id == context.bot.id and
              chat_member.new_chat_member.status in ["left", "kicked"]):
            
            logger.info(f"Бота удалили из чата: {update.effective_chat.title}")
            
    except Exception as e:
        logger.error(f"Ошибка в обработчике chat_member_update: {e}")

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
        "• База для слива скамеров"
    )
    
    try:
        await update.message.reply_photo(
            photo=PHOTO_START,
            caption=welcome_text,
            reply_markup=get_welcome_inline_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке фото приветствия: {e}")
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
            "Используйте команды для работы с ботом: /check, /me, /help",
            reply_markup=get_main_reply_keyboard(chat_type=chat_type)
        )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        user = update.effective_user
        chat_type = update.effective_chat.type
        
        if chat_type in ["group", "supergroup", "channel"]:
            if text in ["👤 Мой профиль", "⭐ Список гарантов", "🕵️ Слить скамера", 
                       "📋 Команды", "ℹ️ Информация о боте", "🔐 Админ панель"]:
                await update.message.reply_text(
                    "⚠️ В групповых чатах используйте команды, а не кнопки:\n"
                    "/check @username - проверить пользователя\n"
                    "/me - мой профиль\n"
                    "/help - справка",
                    reply_markup=get_main_reply_keyboard(chat_type=chat_type)
                )
                return
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
                "Для слива скамера перейдите по ссылке:\n"
                "https://t.me/antiscambaseAS",
                reply_markup=get_main_reply_keyboard(user.id, chat_type)
            )
        
        elif text == "📋 Команды":
            commands_text = (
                "📋 Доступные команды:\n\n"
                "/start - Запустить бота\n"
                "/check @username - Проверить пользователя\n"
                "/check (в ответ на сообщение) - Проверить отправителя\n"
                "/me - Проверить свой профиль\n\n"
                "🕵️‍♂️ Для администраторов:\n"
                "/add_garant @username - Добавить гаранта\n"
                "/del_garant @username - Удалить гаранта\n"
                "/add_scammer @username доказательства - Добавить скамера\n"
                "/del_scammer @username - Удалить скамера"
            )
            await update.message.reply_text(commands_text, reply_markup=get_main_reply_keyboard(user.id, chat_type))
        
        elif text == "ℹ️ Информация о боте":
            info_text = (
                "🤖 Anti Scam Bot\n\n"
                "🔍 Бот для проверки пользователей на скам\n\n"
                "📊 Возможности:\n"
                "• Проверка пользователей в базе данных\n"
                "• База скамеров и гарантов\n"
                "• История проверок\n"
                "• Админ-панель для управления\n\n"
                "⚠️ Важно: Всегда проверяйте информацию!\n\n"
                "🛠 Разработчик: @SAGYN_OFFICIAL\n"
                "📅 Версия: 2.0 (Render Edition)"
            )
            await update.message.reply_text(info_text, reply_markup=get_main_reply_keyboard(user.id, chat_type))
        
        elif text == "🔐 Админ панель":
            if user.id == ADMIN_ID:
                await update.message.reply_text(
                    "👑 Админ панель\n\n"
                    "Используйте кнопки ниже или команды:",
                    reply_markup=get_admin_reply_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ Эта панель только для администратора!",
                    reply_markup=get_main_reply_keyboard(user.id, chat_type)
                )
        
        elif text == "➕ Добавить гаранта" and user.id == ADMIN_ID:
            await update.message.reply_text(
                "Для добавления гаранта используйте команду:\n"
                "/add_garant @username",
                reply_markup=get_admin_reply_keyboard()
            )
        
        elif text == "➖ Удалить гаранта" and user.id == ADMIN_ID:
            await update.message.reply_text(
                "Для удаления гаранта используйте команду:\n"
                "/del_garant @username",
                reply_markup=get_admin_reply_keyboard()
            )
        
        elif text == "➕ Добавить скамера" and user.id == ADMIN_ID:
            await update.message.reply_text(
                "Для добавления скамера используйте команду:\n"
                "/add_scammer @username доказательства",
                reply_markup=get_admin_reply_keyboard()
            )
        
        elif text == "➖ Удалить скамера" and user.id == ADMIN_ID:
            await update.message.reply_text(
                "Для удаления скамера используйте команду:\n"
                "/del_scammer @username",
                reply_markup=get_admin_reply_keyboard()
            )
        
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
                f"🔄 Версия: 2.0"
            )
            await update.message.reply_text(stats_text, reply_markup=get_admin_reply_keyboard())
        
        elif text == "⬅️ На главную":
            await update.message.reply_text(
                "Главное меню:",
                reply_markup=get_main_reply_keyboard(user.id, chat_type)
            )
        
        else:
            if chat_type == "private":
                await update.message.reply_text(
                    "Используйте кнопки ниже для навигации.",
                    reply_markup=get_main_reply_keyboard(user.id, chat_type)
                )
    
    except Exception as e:
        logger.error(f"Ошибка в handle_text_message: {e}")
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла ошибка. Попробуйте еще раз.",
                reply_markup=get_main_reply_keyboard(update.effective_user.id, update.effective_chat.type)
            )
        except:
            pass

async def check_user(user_id, username, searcher_id):
    try:
        cursor.execute(
            "INSERT INTO search_history (user_id, username, searcher_id, search_date) VALUES (?, ?, ?, ?)",
            (user_id, username, searcher_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        cursor.execute(
            "SELECT COUNT(*) FROM search_history WHERE user_id = ?",
            (user_id,)
        )
        search_count = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT scam_count, proofs FROM scammers WHERE user_id = ?",
            (user_id,)
        )
        scammer = cursor.fetchone()
        
        cursor.execute(
            "SELECT * FROM garants WHERE user_id = ?",
            (user_id,)
        )
        garant = cursor.fetchone()
        
        conn.commit()
        
        if scammer:
            scam_count, proofs = scammer
            return {
                "type": "scammer",
                "scam_count": scam_count,
                "proofs": proofs,
                "search_count": search_count
            }
        elif garant:
            return {
                "type": "garant",
                "search_count": search_count
            }
        else:
            return {
                "type": "regular",
                "search_count": search_count
            }
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
        await update.message.reply_text(
            "Использование:\n"
            "/check @username - проверка пользователя\n"
            "/check в ответ на сообщение - проверка отправителя"
        )
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
            logger.error(f"Ошибка при отправке фото обычного пользователя: {e}")
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
            logger.error(f"Ошибка при отправке фото скамера: {e}")
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
    user = update.effective_user
    result = await check_user(user.id, user.username or f"id{user.id}", user.id)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    user_info = (
        f"👤 Ваш профиль:\n"
        f"🆔 ID: {user.id}\n"
        f"📛 Имя: {user.first_name}\n"
        f"📧 Username: @{user.username or 'Нет'}\n"
        f"🔍 Статус: "
    )
    
    if result["type"] == "scammer":
        user_info += f"СКАМЕР ⚠️\nКоличество скамов: {result['scam_count']}"
    elif result["type"] == "garant":
        user_info += "ГАРАНТ ✅"
    else:
        user_info += "ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ"
    
    user_info += f"\n👁‍🗨 Вас искали: {result['search_count']} раз\n"
    user_info += f"🗓️ Дата проверки: {current_time}"
    
    await update.message.reply_text(user_info, reply_markup=get_main_reply_keyboard(user.id, update.effective_chat.type))

# Админ команды
async def add_garant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
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
    
    await update.message.reply_text(f"✅ Пользователь @{username} добавлен в гаранты")

async def del_garant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_garant @username")
        return
    
    username = context.args[0].replace('@', '')
    
    cursor.execute("DELETE FROM garants WHERE username = ?", (username,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ Пользователь @{username} удален из гарантов")
    else:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден в гарантах")

async def add_scammer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
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
    
    await update.message.reply_text(f"✅ Пользователь @{username} добавлен в скамеры")

async def del_scammer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_scammer @username")
        return
    
    username = context.args[0].replace('@', '')
    
    cursor.execute("DELETE FROM scammers WHERE username = ?", (username,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ Пользователь @{username} удален из скамеров")
    else:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден в скамерах")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("perma_link:"):
        username = query.data.split(":")[1]
        await query.edit_message_text(
            f"🔗 Вечная ссылка на профиль: @{username}\n\n"
            f"Ссылка: https://t.me/{username}"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда помощи"""
    help_text = (
        "🤖 Anti-Scam Bot - Справка\n\n"
        "📌 Основные команды:\n"
        "/start - Начать работу с ботом\n"
        "/check @username - Проверить пользователя\n"
        "/check (в ответ на сообщение) - Проверить отправителя\n"
        "/me - Показать мой профиль\n\n"
        "ℹ️ В личных сообщениях доступны кнопки меню\n"
        "💬 В группах используйте команды\n\n"
        "🛠 Разработчик: @SAGYN_OFFICIAL"
    )
    
    chat_type = update.effective_chat.type
    await update.message.reply_text(
        help_text,
        reply_markup=get_main_reply_keyboard(update.effective_user.id, chat_type)
    )

# ========== ФУНКЦИЯ ДЛЯ ЗАПУСКА TELEGRAM БОТА ==========
def run_telegram_bot():
    """Запуск Telegram бота"""
    try:
        print("🤖 Запуск Anti Scam Bot на Render...")
        print(f"🌐 Веб-сервер работает на порту {os.environ.get('PORT', 8080)}")
        print(f"👑 Админ ID: {ADMIN_ID}")
        
        # Проверка токена
        if not TOKEN:
            print("❌ ОШИБКА: BOT_TOKEN не установлен в Environment Variables!")
            print("💡 На Render Dashboard добавьте переменную BOT_TOKEN")
            print("🌐 Перейдите: Render Dashboard → ваш сервис → Environment → Add BOT_TOKEN")
            return
        
        # Безопасный вывод информации о токене
        if TOKEN.startswith("82") and ":" in TOKEN:
            token_for_log = TOKEN[:10] + "..." + TOKEN[-4:]
        else:
            token_for_log = "НЕВАЛИДНЫЙ_ФОРМАТ"
        
        print(f"🔐 Токен бота (обрезано): {token_for_log}")
        
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()
        
        # Добавляем обработчик событий чата
        application.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
        
        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("me", me_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("add_garant", add_garant))
        application.add_handler(CommandHandler("del_garant", del_garant))
        application.add_handler(CommandHandler("add_scammer", add_scammer))
        application.add_handler(CommandHandler("del_scammer", del_scammer))
        
        # Обработчик инлайн кнопок
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Обработчик текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        # Обработчик неизвестных команд
        application.add_handler(MessageHandler(filters.COMMAND, lambda u, c: u.message.reply_text(
            "❌ Неизвестная команда. Используйте /start или /help",
            reply_markup=get_main_reply_keyboard(u.effective_user.id, u.effective_chat.type)
        )))
        
        print("🟢 Telegram бот успешно запущен. Ожидание сообщений...")
        print("🌐 Веб-интерфейс доступен по / и /health")
        print("🔒 Токен защищен от логирования")
        
        # Запускаем поллинг
        application.run_polling(
            close_loop=False,
            stop_signals=None
        )
        
    except Exception as e:
        print(f"🔴 Ошибка при запуске бота: {e}")
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
def main():
    """Основная функция запуска"""
    try:
        # Запускаем веб-сервер в отдельном потоке
        web_thread = Thread(target=run_web_server, daemon=True)
        web_thread.start()
        print("✅ Веб-сервер запущен для Render")
        
        # Запускаем Telegram бота
        run_telegram_bot()
        
    except Exception as e:
        print(f"🔴 Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
