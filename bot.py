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

# File ID для фото
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
    level INTEGER DEFAULT 5,
    added_by INTEGER,
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

def get_admin_level(user_id):
    if user_id == ADMIN_ID:
        return 10  # Уровень главного админа
    cursor.execute("SELECT level FROM admins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

def can_manage_scammers(user_id):
    # Уровень 5 и выше может управлять скамерами
    return get_admin_level(user_id) >= 5

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

def get_main_keyboard(user_id, chat_type="private"):
    """Возвращает клавиатуру в зависимости от типа чата"""
    if chat_type != "private":
        # В группах не показываем кнопки
        return ReplyKeyboardRemove()
    
    keyboard = [["👤 Мой профиль", "⭐ Список гарантов"]]
    if is_admin(user_id):
        keyboard.append(["🔐 Админ панель"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard(user_id):
    """Клавиатура для админ панели"""
    keyboard = []
    
    # Проверяем права админа
    if can_manage_scammers(user_id):
        keyboard.append(["➕ Добавить скамера", "➖ Удалить скамера"])
    
    if is_global_admin(user_id):
        keyboard.append(["➕ Добавить гаранта", "➖ Удалить гаранта"])
        keyboard.append(["➕ Добавить админа", "➖ Удалить админа"])
    
    keyboard.append(["📊 Статистика", "⬅️ На главную"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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
        reply_markup=get_main_keyboard(user.id, chat_type)
    )

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or f"id{user.id}"
    chat_type = update.effective_chat.type
    
    # Определяем роль пользователя
    role = get_user_role(user.id, username)
    
    # Готовим информацию в зависимости от роли
    if role == "global_admin":
        status_text = "👑 ГЛОБАЛЬНЫЙ АДМИНИСТРАТОР"
        status_emoji = "👑"
        photo = PHOTO_ADMIN
        extra_info = (
            "• Управление всеми администраторами\n"
            "• Добавление/удаление гарантов\n"
            "• Полный контроль над ботом\n"
            "• Уровень доступа: 10 (максимальный)"
        )
        
    elif role == "admin":
        level = get_admin_level(user.id)
        status_text = f"🛡 АДМИНИСТРАТОР (Уровень {level})"
        status_emoji = "🛡"
        photo = PHOTO_ADMIN
        
        # Описание прав в зависимости от уровня
        rights = []
        if level >= 5:
            rights.append("• Добавление скамеров в базу")
            rights.append("• Удаление скамеров из базы")
        if level >= 3:
            rights.append("• Просмотр статистики")
        rights.append("• Проверка пользователей")
        
        extra_info = "\n".join(rights)
        
    elif role == "scammer":
        reason = get_scammer_info(user.id)
        status_text = f"⚠️ СКАМЕР"
        status_emoji = "⚠️"
        photo = PHOTO_SCAMMER
        extra_info = f"Причина: {reason or 'Не указана'}\n\n" + \
                    "• Внесен в черный список\n" + \
                    "• Не доверяйте этому пользователю\n" + \
                    "• Рекомендуется заблокировать"
        
    elif role == "garant":
        proof_count = get_garant_info(user.id)
        status_text = f"✅ ГАРАНТ"
        status_emoji = "✅"
        photo = PHOTO_GARANT
        extra_info = f"Количество пруфов: {proof_count}\n\n" + \
                    "• Проверенный и надежный пользователь\n" + \
                    "• Имеет подтвержденные сделки\n" + \
                    "• Рекомендуется для сотрудничества"
        
    else:  # regular
        status_text = "👤 ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ"
        status_emoji = "👤"
        photo = PHOTO_REGULAR
        extra_info = "• Не замечен в скамерах\n" + \
                    "• Нет информации о гарантийных сделках\n" + \
                    "• Будьте осторожны при сделках"
    
    # Получаем статистику
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
    
    # Добавляем статистику для админов
    if role in ["global_admin", "admin"] and added_scammers > 0:
        profile_info += f"<b>📊 Добавлено скамеров:</b> {added_scammers}\n\n"
    
    profile_info += (
        f"<b>📋 Возможности:</b>\n{extra_info}\n\n"
        f"<b>🗓️ Дата проверки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"<b>🤖 Проверено:</b> @AntilScamBot"
    )
    
    try:
        # Пытаемся отправить фото с подписью
        await update.message.reply_photo(
            photo=photo,
            caption=profile_info,
            parse_mode='HTML',
            reply_markup=get_main_keyboard(user.id, chat_type)
        )
    except Exception as e:
        # Если не получилось отправить фото, отправляем текстом
        logger.error(f"Ошибка отправки фото: {e}")
        await update.message.reply_text(
            profile_info,
            parse_mode='HTML',
            reply_markup=get_main_keyboard(user.id, chat_type)
        )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    
    if context.args:
        username = context.args[0].replace('@', '')
        user_id = hash(username) % 1000000000
    elif update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        username = target_user.username or f"id{target_user.id}"
        user_id = target_user.id
    else:
        await update.message.reply_text("Использование: /check @username")
        return
    
    # Определяем роль
    role = get_user_role(user_id, username)
    
    if role == "scammer":
        reason = get_scammer_info(user_id)
        response = (
            f"🕵️ <b>ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            f"<b>👤 Пользователь:</b> @{username}\n"
            f"<b>🔍 Результат:</b> 🚨 <b>СКАМЕР</b>\n"
            f"<b>📝 Причина:</b> {reason or 'Не указана'}\n\n"
            f"<b>⚠️ ВНИМАНИЕ:</b> Не доверяйте этому пользователю!"
        )
    elif role == "garant":
        proof_count = get_garant_info(user_id)
        response = (
            f"🕵️ <b>ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            f"<b>👤 Пользователь:</b> @{username}\n"
            f"<b>🔍 Результат:</b> ✅ <b>ГАРАНТ</b>\n"
            f"<b>📊 Количество пруфов:</b> {proof_count}\n\n"
            f"<b>⭐ РЕКОМЕНДАЦИЯ:</b> Надежный пользователь для сделок"
        )
    elif role in ["admin", "global_admin"]:
        level = get_admin_level(user_id)
        response = (
            f"🕵️ <b>ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            f"<b>👤 Пользователь:</b> @{username}\n"
            f"<b>🔍 Результат:</b> 👑 <b>АДМИНИСТРАТОР</b>\n"
            f"<b>📊 Уровень доступа:</b> {level}\n\n"
            f"<b>🛡️ СТАТУС:</b> Проверенный сотрудник бота"
        )
    else:
        response = (
            f"🕵️ <b>ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            f"<b>👤 Пользователь:</b> @{username}\n"
            f"<b>🔍 Результат:</b> 👤 <b>ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ</b>\n\n"
            f"<b>ℹ️ ИНФОРМАЦИЯ:</b> Пользователь не найден в базах скамеров или гарантов"
        )
    
    await update.message.reply_text(response, parse_mode='HTML')

# ========== АДМИН КОМАНДЫ ==========
async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный администратор может добавлять админов!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /add_admin @username уровень\n"
            "Пример: /add_admin @username 5\n\n"
            "Уровни доступа:\n"
            "• 5 - Может добавлять/удалять скамеров\n"
            "• 10 - Главный администратор (только вы)"
        )
        return
    
    username = context.args[0].replace('@', '')
    level = context.args[1]
    
    if not level.isdigit() or not 1 <= int(level) <= 9:
        await update.message.reply_text("❌ Уровень должен быть числом от 1 до 9!")
        return
    
    level = int(level)
    
    # Генерируем ID из username
    user_id = hash(username) % 1000000000
    
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO admins (user_id, username, level, added_by, added_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, level, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        
        level_info = ""
        if level >= 5:
            level_info = "\n• Может добавлять и удалять скамеров\n• Может просматривать статистику"
        else:
            level_info = "\n• Может просматривать статистику\n• Не может управлять скамерами"
        
        await update.message.reply_text(
            f"✅ @{username} добавлен как администратор!\n\n"
            f"<b>📊 Уровень доступа:</b> {level}\n"
            f"<b>📋 Права:</b>{level_info}\n\n"
            f"<b>👤 Добавил:</b> {user.first_name}",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении администратора!")

async def del_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный администратор может удалять админов!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_admin @username")
        return
    
    username = context.args[0].replace('@', '')
    user_id = hash(username) % 1000000000
    
    cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ @{username} удален из администраторов!")
    else:
        await update.message.reply_text(f"❌ @{username} не найден!")

async def add_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not can_manage_scammers(user.id):
        await update.message.reply_text("❌ У вас нет прав для добавления скамеров!\nТребуется уровень 5 или выше.")
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
        
        # Обновляем статистику админа
        cursor.execute("SELECT COUNT(*) FROM scammers WHERE added_by = ?", (user.id,))
        total_added = cursor.fetchone()[0]
        
        await update.message.reply_text(
            f"✅ @{username} добавлен в скамеры!\n\n"
            f"<b>📝 Причина:</b> {reason}\n"
            f"<b>👤 Добавил:</b> {user.first_name}\n"
            f"<b>📊 Ваш баланс добавлений:</b> {total_added} скамеров",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении!")

async def del_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not can_manage_scammers(user.id):
        await update.message.reply_text("❌ У вас нет прав для удаления скамеров!\nТребуется уровень 5 или выше.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_scammer @username")
        return
    
    username = context.args[0].replace('@', '')
    
    cursor.execute("DELETE FROM scammers WHERE username = ?", (username,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ @{username} удален из скамеров!")
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
    
    # Статистика по уровням админов
    cursor.execute("SELECT level, COUNT(*) FROM admins GROUP BY level ORDER BY level DESC")
    admin_levels = cursor.fetchall()
    
    admin_stats = ""
    for level, count in admin_levels:
        admin_stats += f"• Уровень {level}: {count} чел.\n"
    
    stats_text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"<b>🚨 Скамеров в базе:</b> {scammer_count}\n"
        f"<b>⭐ Гарантов в базе:</b> {garant_count}\n"
        f"<b>👥 Администраторов:</b> {admin_count + 1}\n"
        f"<b>📈 Всего пруфов у гарантов:</b> {total_proofs}\n\n"
        f"<b>📋 Распределение админов по уровням:</b>\n{admin_stats}\n"
        f"<b>👑 Главный админ:</b> {ADMIN_ID}\n"
        f"<b>🤖 Версия бота:</b> 6.0 (система уровней)"
    )
    
    await update.message.reply_text(stats_text, parse_mode='HTML')

# ========== ОБРАБОТЧИК КНОПОК ==========
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    chat_type = update.effective_chat.type
    
    print(f"📩 Сообщение: '{text}' от {user.id} в чате типа {chat_type}")
    
    if text == "👤 Мой профиль":
        await me_command(update, context)
        
    elif text == "⭐ Список гарантов":
        cursor.execute("SELECT username, proof_count FROM garants ORDER BY proof_count DESC")
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
        await update.message.reply_text("👑 Админ панель", reply_markup=get_admin_keyboard(user.id))
        
    elif text == "➕ Добавить скамера" and can_manage_scammers(user.id):
        await update.message.reply_text("Используйте: /add_scammer @username причина")
        
    elif text == "➖ Удалить скамера" and can_manage_scammers(user.id):
        await update.message.reply_text("Используйте: /del_scammer @username")
        
    elif text == "➕ Добавить гаранта" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /add_garant @username [количество_пруфов]")
        
    elif text == "➖ Удалить гаранта" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /del_garant @username")
        
    elif text == "➕ Добавить админа" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /add_admin @username уровень")
        
    elif text == "➖ Удалить админа" and is_global_admin(user.id):
        await update.message.reply_text("Используйте: /del_admin @username")
        
    elif text == "📊 Статистика" and is_admin(user.id):
        await stats_command(update, context)
        
    elif text == "⬅️ На главную":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(user.id, chat_type))
        
    else:
        await update.message.reply_text(
            "Используйте кнопки ниже:",
            reply_markup=get_main_keyboard(user.id, chat_type)
        )

# ========== ЗАПУСК ==========
def run_bot():
    print("🤖 Запуск Telegram бота...")
    print(f"👑 Главный админ ID: {ADMIN_ID}")
    print("📊 Система уровней администраторов:")
    print("• Уровень 5+ - добавление/удаление скамеров")
    print("• Уровень 10 - главный администратор (только вы)")
    
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
    app.add_handler(CommandHandler("add_admin", add_admin_command))
    app.add_handler(CommandHandler("del_admin", del_admin_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
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
