import os
import logging
import sqlite3
import sys
import threading
import time
from datetime import datetime
from flask import Flask, jsonify
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ========== НАСТРОЙКА ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== FLASK APP ==========
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return jsonify({"status": "online", "service": "anti-scam-bot"})

@web_app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

@web_app.route('/ping')
def ping():
    return jsonify({"status": "pong"}), 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Веб-сервер на порту {port}")
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ========== ТЕЛЕГРАМ БОТ ==========
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    sys.exit(1)

ADMIN_ID = 8281804228  # Ваш ID

# База данных
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()

# Таблицы
cursor.execute('''
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    level INTEGER DEFAULT 5,
    added_by INTEGER,
    added_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS scammers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    username TEXT,
    reason TEXT,
    added_by INTEGER,
    added_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS garants (
    user_id TEXT,
    username TEXT,
    added_by INTEGER,
    added_date TEXT,
    proof_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, username)
)''')

conn.commit()
print("✅ База данных готова")

# ========== ФУНКЦИИ ==========
def is_global_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

def is_admin(user_id):
    if str(user_id) == str(ADMIN_ID):
        return True
    cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (str(user_id),))
    return cursor.fetchone() is not None

def get_admin_level(user_id):
    if str(user_id) == str(ADMIN_ID):
        return 10  # Уровень главного админа
    cursor.execute("SELECT level FROM admins WHERE user_id = ?", (str(user_id),))
    result = cursor.fetchone()
    return result[0] if result else 0

def can_manage_scammers(user_id):
    # Уровень 5 и выше может управлять скамерами
    return get_admin_level(user_id) >= 5

def is_scammer(user_id, username=None):
    user_id_str = str(user_id)
    if username:
        cursor.execute("SELECT 1 FROM scammers WHERE user_id = ? OR username LIKE ?", 
                      (user_id_str, f'%{username}%'))
    else:
        cursor.execute("SELECT 1 FROM scammers WHERE user_id = ?", (user_id_str,))
    return cursor.fetchone() is not None

def get_scammer_info(user_id, username=None):
    user_id_str = str(user_id)
    if username:
        cursor.execute("SELECT reason FROM scammers WHERE user_id = ? OR username LIKE ?", 
                      (user_id_str, f'%{username}%'))
    else:
        cursor.execute("SELECT reason FROM scammers WHERE user_id = ?", (user_id_str,))
    result = cursor.fetchone()
    if result:
        return result[0]
    return None

def is_garant(user_id, username=None):
    user_id_str = str(user_id)
    if username:
        cursor.execute("SELECT 1 FROM garants WHERE user_id = ? OR username LIKE ?", 
                      (user_id_str, f'%{username}%'))
    else:
        cursor.execute("SELECT 1 FROM garants WHERE user_id = ?", (user_id_str,))
    return cursor.fetchone() is not None

def get_garant_info(user_id, username=None):
    user_id_str = str(user_id)
    if username:
        cursor.execute("SELECT proof_count FROM garants WHERE user_id = ? OR username LIKE ?", 
                      (user_id_str, f'%{username}%'))
    else:
        cursor.execute("SELECT proof_count FROM garants WHERE user_id = ?", (user_id_str,))
    result = cursor.fetchone()
    if result:
        return result[0]
    return 0

def get_user_role(user_id, username=None):
    """Определяем роль пользователя"""
    if is_global_admin(user_id):
        return "global_admin"
    elif is_admin(user_id):
        return "admin"
    elif is_scammer(user_id, username):
        return "scammer"
    elif is_garant(user_id, username):
        return "garant"
    else:
        return "regular"

def extract_user_info(text):
    """Извлекает информацию о пользователе из текста"""
    # Убираем команду если есть
    if text.startswith('/'):
        parts = text.split(' ', 1)
        if len(parts) > 1:
            text = parts[1]
        else:
            return None, None
    
    # Ищем упоминание @username
    if '@' in text:
        parts = text.split('@', 1)
        if len(parts) > 1:
            username_part = parts[1].split(' ', 1)[0]
            reason = parts[1].split(' ', 1)[1] if len(parts[1].split(' ', 1)) > 1 else ""
            return username_part, reason.strip()
    
    # Ищем просто username без @
    parts = text.split(' ', 1)
    if len(parts) >= 1:
        username = parts[0].replace('@', '')
        reason = parts[1] if len(parts) > 1 else ""
        return username, reason.strip()
    
    return None, None

def get_user_id_from_username(username):
    """Генерирует ID из username (в реальном боте можно получить через API)"""
    return str(abs(hash(username)) % 1000000000)

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_type = update.effective_chat.type
    
    await update.message.reply_text(
        "🤖 Anti-Scam Bot - защита от мошенников\n\n"
        "🔍 Проверяйте пользователей перед сделкой\n"
        "🚨 Сообщайте о скамерах\n"
        "⭐ Находите проверенных гарантов\n\n"
        "Используйте кнопки ниже для навигации:",
        reply_markup=ReplyKeyboardMarkup(
            [["👤 Мой профиль", "⭐ Список гарантов"]],
            resize_keyboard=True
        ) if chat_type == "private" else ReplyKeyboardRemove()
    )

# ========== АДМИН КОМАНДЫ ==========
async def add_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not can_manage_scammers(user.id):
        await update.message.reply_text("❌ У вас нет прав для добавления скамеров!\nТребуется уровень 5 или выше.")
        return
    
    # Получаем полный текст команды
    full_text = update.message.text
    
    # Извлекаем username и причину
    username, reason = extract_user_info(full_text)
    
    if not username:
        await update.message.reply_text(
            "Использование: `/add_scammer @username причина`\n"
            "Или: `/add_scammer username причина`\n\n"
            "Пример: `/add_scammer @scammer123 Обманул на 1000 рублей`\n"
            "Пример: `/add_scammer scammer123 Мошенник, не отдал товар`",
            parse_mode='Markdown'
        )
        return
    
    if not reason:
        await update.message.reply_text(
            "❌ Не указана причина!\n"
            "Формат: `/add_scammer @username причина`\n\n"
            "Пример: `/add_scammer @scammer123 Обманул на 1000 рублей`",
            parse_mode='Markdown'
        )
        return
    
    # Генерируем ID для пользователя
    user_id = get_user_id_from_username(username)
    
    # Проверяем, не добавлен ли уже
    if is_scammer(user_id, username):
        existing_reason = get_scammer_info(user_id, username)
        await update.message.reply_text(
            f"⚠️ Пользователь @{username} уже есть в базе скамеров!\n\n"
            f"📝 Текущая причина: {existing_reason}\n\n"
            f"Используйте `/update_scammer @username новая_причина` для обновления.",
            parse_mode='Markdown'
        )
        return
    
    try:
        cursor.execute(
            "INSERT INTO scammers (user_id, username, reason, added_by, added_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, reason, str(user.id), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        
        # Обновляем статистику админа
        cursor.execute("SELECT COUNT(*) FROM scammers WHERE added_by = ?", (str(user.id),))
        total_added = cursor.fetchone()[0]
        
        response = (
            f"✅ *@{username} добавлен в скамеры!*\n\n"
            f"📝 *Причина:* {reason}\n"
            f"🆔 *ID в базе:* `{user_id}`\n"
            f"👤 *Добавил:* {user.first_name}\n"
            f"📊 *Ваш баланс добавлений:* {total_added} скамеров\n\n"
            f"🕐 *Дата добавления:* {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
        # Логируем добавление
        logger.info(f"Пользователь {username} добавлен в скамеры. Причина: {reason}. Добавил: {user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении скамера: {e}")
        await update.message.reply_text(
            "❌ Ошибка при добавлении в базу данных!\n"
            "Попробуйте еще раз или обратитесь к разработчику."
        )

async def del_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not can_manage_scammers(user.id):
        await update.message.reply_text("❌ У вас нет прав для удаления скамеров!\nТребуется уровень 5 или выше.")
        return
    
    full_text = update.message.text
    username, _ = extract_user_info(full_text)
    
    if not username:
        await update.message.reply_text("Использование: `/del_scammer @username`", parse_mode='Markdown')
        return
    
    user_id = get_user_id_from_username(username)
    
    # Удаляем по user_id или username
    cursor.execute("DELETE FROM scammers WHERE user_id = ? OR username = ?", (user_id, username))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ @{username} удален из скамеров!")
        logger.info(f"Пользователь {username} удален из скамеров. Удалил: {user.id}")
    else:
        await update.message.reply_text(f"❌ @{username} не найден в базе скамеров!")

async def update_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновление причины у скамера"""
    user = update.effective_user
    
    if not can_manage_scammers(user.id):
        await update.message.reply_text("❌ У вас нет прав для обновления скамеров!")
        return
    
    full_text = update.message.text
    username, new_reason = extract_user_info(full_text)
    
    if not username or not new_reason:
        await update.message.reply_text(
            "Использование: `/update_scammer @username новая_причина`\n\n"
            "Пример: `/update_scammer @scammer123 Добавил новые доказательства мошенничества`",
            parse_mode='Markdown'
        )
        return
    
    user_id = get_user_id_from_username(username)
    
    cursor.execute(
        "UPDATE scammers SET reason = ? WHERE user_id = ? OR username = ?",
        (new_reason, user_id, username)
    )
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(
            f"✅ Причина для @{username} обновлена!\n\n"
            f"📝 Новая причина: {new_reason}"
        )
        logger.info(f"Обновлена причина для {username}: {new_reason}. Обновил: {user.id}")
    else:
        await update.message.reply_text(f"❌ @{username} не найден в базе скамеров!")

async def check_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка конкретного пользователя на скамера"""
    full_text = update.message.text
    
    # Пытаемся получить username из аргументов
    if context.args:
        username = context.args[0].replace('@', '')
    else:
        username, _ = extract_user_info(full_text)
    
    if not username:
        await update.message.reply_text(
            "Использование: `/check_scammer @username`\n"
            "Или отправьте команду в ответ на сообщение пользователя.",
            parse_mode='Markdown'
        )
        return
    
    user_id = get_user_id_from_username(username)
    
    if is_scammer(user_id, username):
        reason = get_scammer_info(user_id, username)
        response = (
            f"🚨 *СКАМЕР НАЙДЕН!*\n\n"
            f"👤 *Пользователь:* @{username}\n"
            f"🆔 *ID в базе:* `{user_id}`\n"
            f"📝 *Причина:* {reason}\n\n"
            f"⚠️ *ВНИМАНИЕ:* Не доверяйте этому пользователю!"
        )
    else:
        response = (
            f"✅ *Пользователь чист*\n\n"
            f"👤 *Пользователь:* @{username}\n"
            f"🆔 *ID в базе:* `{user_id}`\n"
            f"📊 *Статус:* Не найден в базе скамеров\n\n"
            f"ℹ️ *Примечание:* Всегда проверяйте репутацию перед сделкой"
        )
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def list_scammers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех скамеров"""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ У вас нет прав для просмотра списка скамеров!")
        return
    
    cursor.execute("SELECT username, reason, added_date FROM scammers ORDER BY id DESC LIMIT 50")
    scammers = cursor.fetchall()
    
    if not scammers:
        await update.message.reply_text("📭 База скамеров пуста")
        return
    
    response = "🚨 *СПИСОК СКАМЕРОВ (последние 50):*\n\n"
    
    for i, (username, reason, added_date) in enumerate(scammers, 1):
        date_str = datetime.strptime(added_date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
        short_reason = reason[:50] + "..." if len(reason) > 50 else reason
        response += f"{i}. @{username}\n"
        response += f"   📝 {short_reason}\n"
        response += f"   📅 {date_str}\n\n"
    
    cursor.execute("SELECT COUNT(*) FROM scammers")
    total = cursor.fetchone()[0]
    response += f"📊 *Всего в базе:* {total} скамеров"
    
    # Если слишком длинное сообщение, разбиваем
    if len(response) > 4000:
        parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode='Markdown')
    else:
        await update.message.reply_text(response, parse_mode='Markdown')

# ========== ОБРАБОТЧИК КНОПОК И СООБЩЕНИЙ ==========
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    
    # Если это команда в формате "/команда @username текст"
    if text.startswith('/add_scammer'):
        await add_scammer_command(update, context)
        return
    elif text.startswith('/del_scammer'):
        await del_scammer_command(update, context)
        return
    
    # Обработка обычных текстовых сообщений
    if text == "👤 Мой профиль":
        await update.message.reply_text("Используйте /me для просмотра профиля")
    elif text == "⭐ Список гарантов":
        await update.message.reply_text("Используйте /garants для просмотра списка гарантов")
    else:
        await update.message.reply_text(
            "Для работы с ботом используйте команды:\n"
            "• /start - начать работу\n"
            "• /check @username - проверить пользователя\n"
            "• /me - мой профиль\n\n"
            "Для админов:\n"
            "• /add_scammer @username причина - добавить скамера\n"
            "• /del_scammer @username - удалить скамера\n"
            "• /list_scammers - список скамеров"
        )

# ========== ЗАПУСК ==========
def run_bot():
    print("🤖 Запуск Telegram бота...")
    print(f"👑 Главный админ ID: {ADMIN_ID}")
    print("📊 Система уровней администраторов активна")
    
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_scammer", add_scammer_command))
    app.add_handler(CommandHandler("del_scammer", del_scammer_command))
    app.add_handler(CommandHandler("update_scammer", update_scammer_command))
    app.add_handler(CommandHandler("check_scammer", check_scammer_command))
    app.add_handler(CommandHandler("list_scammers", list_scammers_command))
    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаем polling
    print("✅ Бот запускается...")
    app.run_polling(
        drop_pending_updates=True,
        timeout=30,
        pool_timeout=30,
        connect_timeout=30
    )

def main():
    print(f"🚀 Anti-Scam Bot запускается...")
    
    # Запускаем Flask в отдельном потоке
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print("🌐 Flask сервер запущен")
    
    # Ждем немного
    time.sleep(2)
    
    # Запускаем бота
    try:
        run_bot()
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
        time.sleep(5)
        run_bot()

if __name__ == "__main__":
    main()
