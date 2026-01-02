import os
import logging
import sqlite3
import sys
import asyncio
from datetime import datetime
from threading import Thread
from flask import Flask, jsonify, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, ChatMemberHandler

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
    <head><title>🤖 Anti-Scam Bot</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>🤖 Anti-Scam Bot</h1>
        <div style="background: #4CAF50; padding: 10px 20px; border-radius: 50px; display: inline-block;">
            ✅ ONLINE
        </div>
        <p>Бот работает на Render</p>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

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
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
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
    
    await update.message.reply_text(welcome_text)
    
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
    
    # Простая проверка
    cursor.execute("SELECT * FROM scammers WHERE user_id = ?", (user_id,))
    scammer = cursor.fetchone()
    
    cursor.execute("SELECT * FROM garants WHERE user_id = ?", (user_id,))
    garant = cursor.fetchone()
    
    if scammer:
        await update.message.reply_text(f"⚠️ @{username} - СКАМЕР!")
    elif garant:
        await update.message.reply_text(f"✅ @{username} - ГАРАНТ!")
    else:
        await update.message.reply_text(f"👤 @{username} - обычный пользователь")

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👤 Ваш профиль:\n"
        f"🆔 ID: {user.id}\n"
        f"📛 Имя: {user.first_name}\n"
        f"📧 Username: @{user.username or 'Нет'}",
        reply_markup=get_main_reply_keyboard(user.id, update.effective_chat.type)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Команды:\n"
        "/start - начать\n"
        "/check @username - проверить\n"
        "/me - мой профиль"
    )

# ========== WEBHOOK ОБРАБОТЧИК ==========
@app.route('/webhook', methods=['POST'])
async def webhook():
    """Получаем обновления от Telegram"""
    if telegram_app is None:
        return "Bot not ready", 503
    
    try:
        data = request.get_json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

# ========== НАСТРОЙКА И ЗАПУСК ==========
async def setup_bot():
    """Настройка Telegram бота"""
    global telegram_app
    
    try:
        print("🔧 Настройка бота...")
        
        # 1. ОЧИСТКА - УДАЛЯЕМ ВСЕ СТАРЫЕ ПОДКЛЮЧЕНИЯ
        from telegram import Bot
        temp_bot = Bot(token=TOKEN)
        await temp_bot.delete_webhook(drop_pending_updates=True)
        print("✅ Очищены старые подключения")
        
        # 2. Получаем URL для Render
        render_url = os.environ.get('RENDER_EXTERNAL_URL')
        if not render_url:
            # Если нет переменной, используем health check для получения хоста
            import socket
            hostname = socket.gethostname()
            render_url = f"https://{hostname}.onrender.com"
        
        print(f"🌐 Render URL: {render_url}")
        
        # 3. Настраиваем Webhook
        webhook_url = f"{render_url}/webhook"
        await temp_bot.set_webhook(webhook_url)
        print(f"✅ Webhook установлен: {webhook_url}")
        
        # 4. Создаем приложение
        telegram_app = Application.builder().token(TOKEN).build()
        
        # 5. Регистрируем обработчики
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("check", check_command))
        telegram_app.add_handler(CommandHandler("me", me_command))
        telegram_app.add_handler(CommandHandler("help", help_command))
        
        # 6. Запускаем бота
        await telegram_app.initialize()
        await telegram_app.start()
        
        print("✅ Бот запущен через Webhook")
        
        # Возвращаем приложение для сохранения
        return telegram_app
        
    except Exception as e:
        print(f"❌ Ошибка настройки: {e}")
        return None

def run_flask():
    """Запуск Flask сервера"""
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

async def main():
    """Основная функция"""
    print("🚀 Запуск Anti-Scam Bot на Render...")
    print(f"👑 Админ ID: {ADMIN_ID}")
    
    # Настраиваем бота
    bot_app = await setup_bot()
    if not bot_app:
        print("❌ Не удалось настроить бота")
        return
    
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print("✅ Веб-сервер запущен")
    print("🤖 Бот готов к работе!")
    
    # Бесконечный цикл (Flask работает в отдельном потоке)
    try:
        while True:
            await asyncio.sleep(3600)  # Спим 1 час
    except KeyboardInterrupt:
        print("\n🛑 Остановка бота...")
        await bot_app.stop()
        await bot_app.shutdown()

if __name__ == '__main__':
    # Запускаем асинхронно
    asyncio.run(main())
