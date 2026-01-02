import os
import logging
import sqlite3
import sys
import asyncio
from datetime import datetime
from threading import Thread
from flask import Flask, jsonify, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ВЕБ-СЕРВЕР ==========
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
        "webhook_url": "https://anti-scam-bot1-7.onrender.com/webhook"
    }), 200

# ========== ТЕЛЕГРАМ БОТ ==========
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    sys.exit(1)

ADMIN_ID = 8281804228

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

# Глобальная переменная для приложения бота
telegram_app = None

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

# ========== КОМАНДЫ БОТА ==========
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
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_welcome_inline_keyboard()
    )
    
    if chat_type == "private":
        await update.message.reply_text(
            "Используйте кнопки ниже для навигации:",
            reply_markup=get_main_reply_keyboard(user.id, chat_type)
        )

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
    
    # Простая проверка в базе
    cursor.execute("SELECT * FROM scammers WHERE user_id = ?", (user_id,))
    scammer = cursor.fetchone()
    
    cursor.execute("SELECT * FROM garants WHERE user_id = ?", (user_id,))
    garant = cursor.fetchone()
    
    # Добавляем в историю поиска
    cursor.execute(
        "INSERT INTO search_history (user_id, username, searcher_id, search_date) VALUES (?, ?, ?, ?)",
        (user_id, username, update.effective_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    
    if scammer:
        await update.message.reply_text(
            f"⚠️ @{username} - ОБНАРУЖЕН СКАМЕР!\n\n"
            f"Пользователя проверяли ранее.\n"
            f"Рекомендуем быть осторожным!",
            reply_markup=get_check_result_inline_keyboard(username)
        )
    elif garant:
        await update.message.reply_text(
            f"✅ @{username} - ПРОВЕРЕННЫЙ ГАРАНТ!\n\n"
            f"Этот пользователь проверен и является гарантом.",
            reply_markup=get_check_result_inline_keyboard(username)
        )
    else:
        await update.message.reply_text(
            f"👤 @{username} - обычный пользователь\n\n"
            f"Пользователь не найден в базах скамеров или гарантов.\n"
            f"Всегда проверяйте информацию самостоятельно!",
            reply_markup=get_check_result_inline_keyboard(username)
        )

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Получаем статистику
    cursor.execute("SELECT COUNT(*) FROM search_history WHERE user_id = ?", (user.id,))
    search_count = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT * FROM scammers WHERE user_id = ?", (user.id,))
    scammer = cursor.fetchone()
    
    cursor.execute("SELECT * FROM garants WHERE user_id = ?", (user.id,))
    garant = cursor.fetchone()
    
    user_info = (
        f"👤 Ваш профиль:\n"
        f"🆔 ID: {user.id}\n"
        f"📛 Имя: {user.first_name}\n"
        f"📧 Username: @{user.username or 'Нет'}\n"
        f"🔍 Статус: "
    )
    
    if scammer:
        user_info += f"СКАМЕР ⚠️\nКоличество скамов: {scammer[2]}"
    elif garant:
        user_info += "ГАРАНТ ✅"
    else:
        user_info += "ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ"
    
    user_info += f"\n👁‍🗨 Вас искали: {search_count} раз\n"
    user_info += f"🗓️ Дата проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
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

# ========== WEBHOOK ОБРАБОТЧИК ==========
@app.route('/webhook', methods=['POST'])
async def webhook_handler():
    """Получаем обновления от Telegram"""
    if telegram_app is None:
        return "Bot not ready", 503
    
    try:
        data = request.get_json()
        if not data:
            return "No data", 400
        
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        # Все равно возвращаем 200, чтобы Telegram не копил обновления
        return "OK", 200

# ========== НАСТРОЙКА И ЗАПУСК ==========
async def setup_bot():
    """Настройка Telegram бота"""
    global telegram_app
    
    try:
        print("🚀 Запуск Anti-Scam Bot...")
        print(f"👑 Админ ID: {ADMIN_ID}")
        
        from telegram import Bot
        temp_bot = Bot(token=TOKEN)
        
        # 1. Очистка ВСЕГО
        print("🧹 Очистка старых подключений...")
        await temp_bot.delete_webhook(drop_pending_updates=True)
        print("✅ Очищено")
        
        # 2. Ждем
        await asyncio.sleep(1)
        
        # 3. Установка Webhook
        render_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://anti-scam-bot1-7.onrender.com')
        webhook_url = f"{render_url}/webhook"
        
        print(f"🌐 Устанавливаем Webhook: {webhook_url}")
        await temp_bot.set_webhook(
            url=webhook_url,
            max_connections=100,
            allowed_updates=["message", "callback_query"]
        )
        
        print("✅ Webhook установлен")
        
        # 4. Создаем приложение
        telegram_app = Application.builder().token(TOKEN).build()
        
        # 5. Регистрируем обработчики
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("check", check_command))
        telegram_app.add_handler(CommandHandler("me", me_command))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CallbackQueryHandler(button_callback))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        # 6. Обработчик неизвестных команд
        async def unknown(update, context):
            await update.message.reply_text(
                "❌ Неизвестная команда. Используйте /start или /help",
                reply_markup=get_main_reply_keyboard(update.effective_user.id, update.effective_chat.type)
            )
        
        telegram_app.add_handler(MessageHandler(filters.COMMAND, unknown))
        
        # 7. Запускаем бота
        await telegram_app.initialize()
        await telegram_app.start()
        
        print("✅ Бот запущен и готов к работе!")
        print(f"📡 Webhook URL: {webhook_url}")
        
        return telegram_app
        
    except Exception as e:
        print(f"❌ Ошибка настройки: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_flask():
    """Запуск Flask сервера"""
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Запуск веб-сервера на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

async def main():
    """Основная функция"""
    # Настраиваем бота
    bot_app = await setup_bot()
    if not bot_app:
        print("❌ Не удалось настроить бота")
        return
    
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print("✅ Система полностью запущена")
    print("🤖 Отправьте /start в Telegram боту для тестирования")
    
    # Бесконечный цикл
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("\n🛑 Остановка бота...")
        await bot_app.stop()
        await bot_app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
