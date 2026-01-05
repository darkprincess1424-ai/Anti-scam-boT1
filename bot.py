import os
import logging
import sqlite3
import sys
import threading
import time
from datetime import datetime
from flask import Flask, jsonify
from telegram import Update, ReplyKeyboardMarkup
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

# File ID для фото (замените на свои File ID)
PHOTO_REGULAR = "AgACAgIAAxkBAAMHaVuXyRaIsterNpb8m4S6OCNs4pAAAkkPaxt7wNlKFbDPVp3lyU0BAAMCAAN5AAM4BA"
PHOTO_SCAMMER = "AgACAgIAAxkBAAMKaVuX0DTYvXOoh6L9-LQYZ6tXD4IAAkoPaxt7wNlKXE2XwnPDiyIBAAMCAAN5AAM4BA"
PHOTO_GARANT = "AgACAgIAAxkBAAMNaVuX0Rv_6GJVFb8ulnhTb9UCxWUAAjwNaxsDaeBK8uKoaFgkFVEBAAMCAAN5AAM4BA"
PHOTO_ADMIN = "AgACAgIAAxkBAAMQaVuX1K1bJLDWomL_T1ubUBQdnVYAAgcNaxsDaeBKrAABfnFPRUbCAQADAgADeQADOAQ"

# База данных
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()

# Таблицы
cursor.execute('''
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    added_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS scammers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    reason TEXT,
    added_by INTEGER,
    added_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS garants (
    username TEXT PRIMARY KEY,
    added_by INTEGER,
    added_date TEXT,
    proof_count INTEGER DEFAULT 0
)''')

conn.commit()
print("✅ База данных готова")

# ========== ФУНКЦИИ ==========
def is_global_admin(user_id):
    return user_id == ADMIN_ID

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def is_scammer(user_id):
    cursor.execute("SELECT 1 FROM scammers WHERE username LIKE ?", (f'%{user_id}%',))
    return cursor.fetchone() is not None

def get_scammer_info(user_id):
    cursor.execute("SELECT reason FROM scammers WHERE username LIKE ?", (f'%{user_id}%',))
    result = cursor.fetchone()
    if result:
        return result[0]
    return None

def is_garant(user_id):
    cursor.execute("SELECT 1 FROM garants WHERE username LIKE ?", (f'%{user_id}%',))
    return cursor.fetchone() is not None

def get_garant_info(user_id):
    cursor.execute("SELECT proof_count FROM garants WHERE username LIKE ?", (f'%{user_id}%',))
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
    elif is_scammer(user_id):
        return "scammer"
    elif is_garant(user_id):
        return "garant"
    else:
        return "regular"

def get_main_keyboard(user_id):
    keyboard = [["👤 Мой профиль", "⭐ Список гарантов"]]
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
        "🤖 Anti-Scam Bot\n\nИспользуйте кнопки ниже:",
        reply_markup=get_main_keyboard(user.id)
    )

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or f"id{user.id}"
    
    # Определяем роль пользователя
    role = get_user_role(user.id, username)
    
    # Готовим информацию в зависимости от роли
    if role == "global_admin":
        status_text = "👑 ГЛОБАЛЬНЫЙ АДМИНИСТРАТОР"
        status_emoji = "👑"
        photo = PHOTO_ADMIN
        extra_info = "• Управление всеми администраторами\n• Добавление/удаление гарантов\n• Полный контроль над ботом"
        
    elif role == "admin":
        status_text = "🛡 АДМИНИСТРАТОР"
        status_emoji = "🛡"
        photo = PHOTO_ADMIN
        extra_info = "• Добавление скамеров в базу\n• Просмотр статистики\n• Проверка пользователей"
        
    elif role == "scammer":
        reason = get_scammer_info(user.id)
        status_text = f"⚠️ СКАМЕР\nПричина: {reason or 'Не указана'}"
        status_emoji = "⚠️"
        photo = PHOTO_SCAMMER
        extra_info = "• Внесен в черный список\n• Не доверяйте этому пользователю\n• Рекомендуется заблокировать"
        
    elif role == "garant":
        proof_count = get_garant_info(user.id)
        status_text = f"✅ ГАРАНТ\nКоличество пруфов: {proof_count}"
        status_emoji = "✅"
        photo = PHOTO_GARANT
        extra_info = "• Проверенный и надежный пользователь\n• Имеет подтвержденные сделки\n• Рекомендуется для сотрудничества"
        
    else:  # regular
        status_text = "👤 ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ"
        status_emoji = "👤"
        photo = PHOTO_REGULAR
        extra_info = "• Не замечен в скамерах\n• Нет информации о гарантийных сделках\n• Будьте осторожны при сделках"
    
    # Получаем статистику поисков
    cursor.execute("SELECT COUNT(*) FROM scammers WHERE added_by = ?", (user.id,))
    added_scammers = cursor.fetchone()[0] or 0
    
    # Информация о профиле
    profile_info = (
        f"{status_emoji} <b>ВАШ ПРОФИЛЬ</b>\n\n"
        f"<b>🆔 ID:</b> <code>{user.id}</code>\n"
        f"<b>📛 Имя:</b> {user.first_name}\n"
        f"<b>📧 Username:</b> @{user.username or 'нет'}\n"
        f"<b>🔑 Роль:</b> {status_text}\n\n"
    )
    
    # Добавляем дополнительную информацию в зависимости от роли
    if role in ["global_admin", "admin"]:
        profile_info += f"<b>📊 Добавлено скамеров:</b> {added_scammers}\n\n"
    
    profile_info += (
        f"<b>📋 Информация:</b>\n{extra_info}\n\n"
        f"<b>🗓️ Дата проверки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"<b>🤖 Проверено:</b> @AntilScamBot"
    )
    
    try:
        # Пытаемся отправить фото с подписью
        await update.message.reply_photo(
            photo=photo,
            caption=profile_info,
            parse_mode='HTML',
            reply_markup=get_main_keyboard(user.id)
        )
    except Exception as e:
        # Если не получилось отправить фото, отправляем текстом
        logger.error(f"Ошибка отправки фото: {e}")
        await update.message.reply_text(
            profile_info,
            parse_mode='HTML',
            reply_markup=get_main_keyboard(user.id)
        )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /check @username")
        return
    
    username = context.args[0].replace('@', '')
    user_id = hash(username) % 1000000000  # Генерируем ID из username
    
    # Проверяем роль
    role = get_user_role(user_id, username)
    
    if role == "scammer":
        reason = get_scammer_info(user_id)
        response = f"🚨 @{username} - <b>СКАМЕР</b>!\n\nПричина: {reason or 'Не указана'}"
    elif role == "garant":
        proof_count = get_garant_info(user_id)
        response = f"✅ @{username} - <b>ГАРАНТ</b>!\n\nКоличество пруфов: {proof_count}"
    elif role in ["admin", "global_admin"]:
        response = f"👑 @{username} - <b>АДМИНИСТРАТОР</b>!"
    else:
        response = f"👤 @{username} - обычный пользователь"
    
    await update.message.reply_text(response, parse_mode='HTML')

# ========== АДМИН КОМАНДЫ ==========
async def add_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ У вас нет прав для добавления скамеров!")
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
        await update.message.reply_text(f"✅ @{username} добавлен в скамеры!")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении!")

async def del_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный администратор может удалять!")
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
        await update.message.reply_text("❌ Только главный администратор может добавлять гарантов!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /add_garant @username [количество_пруфов]")
        return
    
    username = context.args[0].replace('@', '')
    proof_count = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 0
    
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO garants (username, added_by, added_date, proof_count) VALUES (?, ?, ?, ?)",
            (username, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), proof_count)
        )
        conn.commit()
        await update.message.reply_text(f"✅ @{username} добавлен как гарант!")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка!")

async def del_garant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный администратор может удалять гарантов!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_garant @username")
        return
    
    username = context.args[0].replace('@', '')
    
    cursor.execute("DELETE FROM garants WHERE username = ?", (username,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ @{username} удален из гарантов!")
    else:
        await update.message.reply_text(f"❌ @{username} не найден!")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный администратор может добавлять админов!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_admin @username")
        return
    
    username = context.args[0].replace('@', '')
    user_id = hash(username) % 1000000000
    
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO admins (user_id, username, added_date) VALUES (?, ?, ?)",
            (user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        await update.message.reply_text(f"✅ @{username} добавлен как администратор!")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка!")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ У вас нет прав для просмотра статистики!")
        return
    
    cursor.execute("SELECT COUNT(*) FROM scammers")
    scammer_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM garants")
    garant_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM admins")
    admin_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(proof_count) FROM garants")
    total_proofs = cursor.fetchone()[0] or 0
    
    stats_text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"🚨 <b>Скамеров в базе:</b> {scammer_count}\n"
        f"⭐ <b>Гарантов в базе:</b> {garant_count}\n"
        f"👥 <b>Администраторов:</b> {admin_count + 1}\n"
        f"📈 <b>Всего пруфов у гарантов:</b> {total_proofs}\n\n"
        f"👑 <b>Главный админ:</b> {ADMIN_ID}\n"
        f"🤖 <b>Версия бота:</b> 6.0"
    )
    
    await update.message.reply_text(stats_text, parse_mode='HTML')

# ========== ОБРАБОТЧИК КНОПОК ==========
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    
    print(f"📩 Кнопка: '{text}' от {user.id}")
    
    if text == "👤 Мой профиль":
        await me_command(update, context)
        
    elif text == "⭐ Список гарантов":
        cursor.execute("SELECT username, proof_count FROM garants")
        garants = cursor.fetchall()
        if garants:
            list_text = "⭐ <b>ГАРАНТЫ БАЗЫ:</b>\n\n"
            for garant in garants:
                username, proof_count = garant
                list_text += f"• @{username} - {proof_count} пруфов\n"
            list_text += f"\n<b>Всего гарантов:</b> {len(garants)}"
            await update.message.reply_text(list_text, parse_mode='HTML')
        else:
            await update.message.reply_text("📭 Список гарантов пуст")
            
    elif text == "🔐 Админ панель" and is_admin(user.id):
        await update.message.reply_text("👑 Админ панель", reply_markup=get_admin_keyboard())
        
    elif text == "➕ Добавить скамера" and is_admin(user.id):
        await update.message.reply_text("Используйте: /add_scammer @username причина")
        
    elif text == "➖ Удалить скамера" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /del_scammer @username")
        
    elif text == "➕ Добавить гаранта" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /add_garant @username [количество_пруфов]")
        
    elif text == "➖ Удалить гаранта" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /del_garant @username")
        
    elif text == "➕ Добавить админа" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /add_admin @username")
        
    elif text == "📊 Статистика" and is_admin(user.id):
        await stats_command(update, context)
        
    elif text == "⬅️ На главную":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(user.id))
        
    else:
        await update.message.reply_text(
            "Используйте кнопки ниже:",
            reply_markup=get_main_keyboard(user.id)
        )

# ========== ЗАПУСК ==========
def run_bot():
    print("🤖 Запуск Telegram бота...")
    print(f"📸 ID фото для проверки:")
    print(f"• Обычный: {PHOTO_REGULAR[:30]}...")
    print(f"• Скамер: {PHOTO_SCAMMER[:30]}...")
    print(f"• Гарант: {PHOTO_GARANT[:30]}...")
    print(f"• Админ: {PHOTO_ADMIN[:30]}...")
    
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    
    # ОЧЕНЬ ВАЖНО: сначала обработчик кнопок!
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Затем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("check", check_command))
    
    # Админ команды
    app.add_handler(CommandHandler("add_scammer", add_scammer_command))
    app.add_handler(CommandHandler("del_scammer", del_scammer_command))
    app.add_handler(CommandHandler("add_garant", add_garant_command))
    app.add_handler(CommandHandler("del_garant", del_garant_command))
    app.add_handler(CommandHandler("add_admin", add_admin_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    # Запускаем polling с долгим timeout
    print("✅ Бот запускается...")
    app.run_polling(
        drop_pending_updates=True,
        timeout=30,
        pool_timeout=30,
        connect_timeout=30
    )

def main():
    print(f"🚀 Anti-Scam Bot запускается...")
    print(f"👑 Главный админ ID: {ADMIN_ID}")
    
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
        # Пробуем перезапустить через 5 секунд
        time.sleep(5)
        run_bot()

if __name__ == "__main__":
    main()
