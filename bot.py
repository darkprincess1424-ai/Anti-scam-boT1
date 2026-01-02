import os
import logging
import sqlite3
import sys
import asyncio
from datetime import datetime
from threading import Thread
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, ChatMemberHandler

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
app = Flask(__name__)

@app.route('/')
def home():
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

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy", 
        "service": "anti-scam-bot",
        "timestamp": datetime.now().isoformat(),
        "bot": "running"
    }), 200

# ========== ТЕЛЕГРАМ БОТ ==========
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    sys.exit(1)

ADMIN_ID = 8281804228

# File ID для фото
PHOTO_START = "AgACAgIAAxkBAANzaVQoJVrivNUbO_0_kp0vYE7j0yoAAuwSaxsh3qFKzfjQ3DqXYecBAAMCAAN5AAM4BA"
PHOTO_REGULAR = "AgACAgIAAxkBAANEaVQhuac6f3ohxbrRLsiQyovlv04AArUSaxsh3qFKgpVFnIrVhA0BAAMCAAN5AAM4BA"
PHOTO_SCAMMER = "AgACAgIAAxkBAAN5aVQoPw9O48N7kKXsxI_oJQ8VECsAAu0Saxsh3qFK3skb3DmGQlkBAAMCAAN5AAM4BA"

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
        "• База для слива скамеров"
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
                "• История проверок\n\n"
                "🛠 Разработчик: @SAGYN_OFFICIAL\n"
                "📅 Версия: 2.0 (Render Edition)"
            )
            await update.message.reply_text(info_text, reply_markup=get_main_reply_keyboard(user.id, chat_type))
        else:
            await update.message.reply_text(
                "Используйте кнопки ниже:",
                reply_markup=get_main_reply_keyboard(user.id, chat_type)
            )
    except Exception as e:
        logger.error(f"Ошибка в handle_text_message: {e}")

# ========== ЗАПУСК ВЕБ-СЕРВЕРА В ОТДЕЛЬНОМ ПОТОКЕ ==========
def run_flask_server():
    """Запуск Flask сервера для Render"""
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Запуск веб-сервера на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ========== ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА ==========
async def run_telegram_bot():
    """Запуск Telegram бота с polling"""
    print("🤖 Запуск Anti-Scam Bot на Render...")
    print(f"👑 Админ ID: {ADMIN_ID}")
    
    # Проверка токена
    if not TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не установлен!")
        sys.exit(1)
    
    print("✅ Токен бота найден")
    
    # ОЧЕНЬ ВАЖНО: Очищаем ВСЕ старые подключения перед запуском
    try:
        from telegram import Bot
        temp_bot = Bot(token=TOKEN)
        
        print("🧹 Очистка старых подключений...")
        # 1. Удаляем webhook если был
        await temp_bot.delete_webhook(drop_pending_updates=True)
        
        # 2. Очищаем ВСЕ обновления вручную
        updates = await temp_bot.get_updates(timeout=1)
        if updates:
            last_update_id = updates[-1].update_id
            # Очищаем все обновления
            await temp_bot.get_updates(offset=last_update_id + 1, timeout=1)
            print(f"✅ Очищено {len(updates)} старых обновлений")
        
        print("✅ Все старые подключения очищены")
        
    except Exception as e:
        print(f"⚠️ Предупреждение при очистке: {e}")
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("me", me_command))
    application.add_handler(CommandHandler("help", help_command))
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
    
    print("✅ Бот настроен и готов к запуску")
    
    # Запускаем polling с ОБЯЗАТЕЛЬНЫМИ параметрами
    print("🔄 Запуск polling...")
    await application.run_polling(
        drop_pending_updates=True,  # ОЧЕНЬ ВАЖНО: игнорируем старые сообщения
        allowed_updates=None,
        close_loop=False
    )

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
def main():
    """Основная функция запуска"""
    try:
        print("🚀 Запуск системы...")
        
        # Запускаем веб-сервер в отдельном потоке
        flask_thread = Thread(target=run_flask_server, daemon=True)
        flask_thread.start()
        print("✅ Веб-сервер запущен")
        
        # Запускаем Telegram бота
        print("🤖 Запуск Telegram бота...")
        asyncio.run(run_telegram_bot())
        
    except Exception as e:
        print(f"🔴 Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
