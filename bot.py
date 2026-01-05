import os
import logging
import sqlite3
import sys
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 8281804228  # Ваш ID

# Подключаем базу данных
conn = sqlite3.connect('bot_simple.db', check_same_thread=False)
cursor = conn.cursor()

# Простая база данных
cursor.execute('''
CREATE TABLE IF NOT EXISTS scammers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    reason TEXT,
    added_by INTEGER,
    added_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    added_by INTEGER,
    added_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS garants (
    username TEXT PRIMARY KEY,
    added_by INTEGER,
    added_date TEXT
)''')

conn.commit()

# ========== ФУНКЦИИ ПРОВЕРКИ ПРАВ ==========
def is_global_admin(user_id):
    return user_id == ADMIN_ID

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(user_id):
    keyboard = [
        ["👤 Мой профиль", "⭐ Список гарантов"],
        ["🕵️ Слить скамера", "📋 Команды"],
        ["ℹ️ Информация о боте"]
    ]
    if is_admin(user_id):
        keyboard.append(["🔐 Админ панель"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        ["➕ Добавить скамера", "➖ Удалить скамера"],
        ["➕ Добавить гаранта", "➖ Удалить гаранта"],
        ["➕ Добавить админа", "➖ Удалить админа"],
        ["📊 Статистика", "⬅️ На главную"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        "🤖 Anti-Scam Bot - защита от мошенников\n\n"
        "Используйте кнопки ниже для навигации:",
        reply_markup=get_main_keyboard(user.id)
    )

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Проверяем роль
    role = "👤 Обычный пользователь"
    if is_global_admin(user.id):
        role = "👑 Глобальный администратор"
    elif is_admin(user.id):
        role = "🛡 Администратор"
    
    await update.message.reply_text(
        f"👤 Ваш профиль:\n\n"
        f"🆔 ID: {user.id}\n"
        f"📛 Имя: {user.first_name}\n"
        f"📧 Username: @{user.username or 'нет'}\n"
        f"🔑 Роль: {role}\n\n"
        f"🤖 Бот: @AntilScamBot",
        reply_markup=get_main_keyboard(user.id)
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /check @username")
        return
    
    username = context.args[0].replace('@', '')
    
    # Проверяем в базе
    cursor.execute("SELECT reason FROM scammers WHERE username = ?", (username,))
    scammer = cursor.fetchone()
    
    cursor.execute("SELECT 1 FROM garants WHERE username = ?", (username,))
    garant = cursor.fetchone()
    
    if scammer:
        await update.message.reply_text(f"🚨 @{username} - СКАМЕР!\nПричина: {scammer[0]}")
    elif garant:
        await update.message.reply_text(f"✅ @{username} - ГАРАНТ!")
    else:
        await update.message.reply_text(f"👤 @{username} - обычный пользователь")

# ========== АДМИН КОМАНДЫ ==========
async def add_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /add_scammer @username причина")
        return
    
    username = context.args[0].replace('@', '')
    reason = ' '.join(context.args[1:])
    
    try:
        cursor.execute(
            "INSERT INTO scammers (username, reason, added_by, added_date) VALUES (?, ?, ?, ?)",
            (username, reason, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        await update.message.reply_text(f"✅ @{username} добавлен как скамер!")
    except sqlite3.IntegrityError:
        await update.message.reply_text(f"❌ @{username} уже в базе!")
    except Exception as e:
        await update.message.reply_text("❌ Ошибка!")

async def del_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный админ может удалять!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_scammer @username")
        return
    
    username = context.args[0].replace('@', '')
    
    cursor.execute("DELETE FROM scammers WHERE username = ?", (username,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ @{username} удален!")
    else:
        await update.message.reply_text(f"❌ @{username} не найден!")

async def add_garant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный админ!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_garant @username")
        return
    
    username = context.args[0].replace('@', '')
    
    try:
        cursor.execute(
            "INSERT INTO garants (username, added_by, added_date) VALUES (?, ?, ?)",
            (username, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        await update.message.reply_text(f"✅ @{username} добавлен как гарант!")
    except:
        await update.message.reply_text(f"❌ @{username} уже гарант!")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный админ!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_admin @username")
        return
    
    username = context.args[0].replace('@', '')
    user_id = hash(username) % 1000000  # Простой хэш для теста
    
    try:
        cursor.execute(
            "INSERT INTO admins (user_id, username, added_by, added_date) VALUES (?, ?, ?, ?)",
            (user_id, username, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        await update.message.reply_text(f"✅ @{username} добавлен как админ!")
    except:
        await update.message.reply_text(f"❌ @{username} уже админ!")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    cursor.execute("SELECT COUNT(*) FROM scammers")
    scammer_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM garants")
    garant_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM admins")
    admin_count = cursor.fetchone()[0]
    
    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"🚨 Скамеров: {scammer_count}\n"
        f"⭐ Гарантов: {garant_count}\n"
        f"👥 Админов: {admin_count + 1}\n\n"
        f"👑 Главный админ: {ADMIN_ID}"
    )

# ========== ОБРАБОТЧИК КНОПОК ==========
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    
    print(f"🔘 Кнопка: {text} от {user.id}")
    
    # Главные кнопки
    if text == "👤 Мой профиль":
        await me_command(update, context)
        
    elif text == "⭐ Список гарантов":
        cursor.execute("SELECT username FROM garants")
        garants = cursor.fetchall()
        if garants:
            list_text = "⭐ ГАРАНТЫ:\n\n" + "\n".join([f"• @{g[0]}" for g in garants])
            await update.message.reply_text(list_text)
        else:
            await update.message.reply_text("📭 Список гарантов пуст")
            
    elif text == "🕵️ Слить скамера":
        await update.message.reply_text("Для слива скамера:\nhttps://t.me/antiscambaseAS")
        
    elif text == "📋 Команды":
        help_text = (
            "🤖 Команды:\n\n"
            "/start - Начать\n"
            "/check @username - Проверить\n"
            "/me - Мой профиль\n\n"
        )
        if is_admin(user.id):
            help_text += "👑 Админ команды:\n"
            help_text += "/add_scammer @username причина\n"
            help_text += "/stats - Статистика\n"
        if is_global_admin(user.id):
            help_text += "\n🕵️ Главный админ:\n"
            help_text += "/add_admin @username\n"
            help_text += "/add_garant @username\n"
            help_text += "/del_scammer @username\n"
        await update.message.reply_text(help_text)
        
    elif text == "ℹ️ Информация о боте":
        await update.message.reply_text(
            "🤖 Anti-Scam Bot\n\n"
            "Бот для проверки пользователей\n"
            "Разработчик: @SAGYN_OFFICIAL"
        )
        
    elif text == "🔐 Админ панель" and is_admin(user.id):
        await update.message.reply_text("👑 Админ панель", reply_markup=get_admin_keyboard())
        
    # Админ кнопки
    elif text == "➕ Добавить скамера" and is_admin(user.id):
        await update.message.reply_text("Используйте: /add_scammer @username причина")
        
    elif text == "➖ Удалить скамера" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /del_scammer @username")
        
    elif text == "➕ Добавить гаранта" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /add_garant @username")
        
    elif text == "➖ Удалить гаранта" and is_global_admin(user.id):
        await update.message.reply_text("Используйте команду: /del_garant @username")
        
    elif text == "➕ Добавить админа" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /add_admin @username")
        
    elif text == "➖ Удалить админа" and is_global_admin(user.id):
        await update.message.reply_text("Используйте команду: /del_admin @username")
        
    elif text == "📊 Статистика" and is_admin(user.id):
        await stats_command(update, context)
        
    elif text == "⬅️ На главную":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(user.id))
        
    else:
        await update.message.reply_text(
            "Используйте кнопки:",
            reply_markup=get_main_keyboard(user.id)
        )

# ========== ЗАПУСК БОТА ==========
def main():
    print("🚀 Запуск простого Anti-Scam Bot...")
    print(f"👑 Главный админ: {ADMIN_ID}")
    
    app = Application.builder().token(TOKEN).build()
    
    # ВАЖНО: сначала обработчик кнопок!
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    # Потом команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("add_scammer", add_scammer_command))
    app.add_handler(CommandHandler("del_scammer", del_scammer_command))
    app.add_handler(CommandHandler("add_garant", add_garant_command))
    app.add_handler(CommandHandler("add_admin", add_admin_command))
    
    print("\n✅ Бот запущен!")
    print("📱 Отправьте /start в Telegram")
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
