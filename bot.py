import os
import logging
import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ChatPermissions
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
        
        cursor.execute("SELECT COUNT(*) FROM chat_admins")
        chat_admins_count = cursor.fetchone()[0] or 0
        
        conn.close()
        
        stats = {
            "scammers": scammer_count,
            "garants": garant_count,
            "searches": search_count,
            "chat_admins": chat_admins_count
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

ADMIN_ID = 8281804228  # Ваш ID

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
    added_date TEXT,
    reason TEXT,
    reporter_id INTEGER
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS garants (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    added_by INTEGER,
    added_date TEXT,
    info_link TEXT,
    proofs_link TEXT,
    proof_count INTEGER DEFAULT 0
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    searcher_id INTEGER,
    search_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS chat_warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    warnings INTEGER DEFAULT 0,
    last_warn_date TEXT
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS chat_admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    added_by INTEGER,
    added_date TEXT,
    added_scammers INTEGER DEFAULT 0,
    UNIQUE(user_id, chat_id)
)''')

# Новая таблица для статистики администраторов
cursor.execute('''
CREATE TABLE IF NOT EXISTS admin_stats (
    admin_id INTEGER PRIMARY KEY,
    added_scammers INTEGER DEFAULT 0,
    added_garants INTEGER DEFAULT 0,
    added_admins INTEGER DEFAULT 0,
    last_action_date TEXT
)''')

conn.commit()
print("✅ База данных инициализирована")

# File ID для фото (ОБНОВЛЕННЫЕ ID!)
PHOTO_START = "AgACAgIAAxkBAAMDaVuXPAZ_gMcF_masVAbsYOKeHzcAAjYNaxsDaeBKo3RQYRT6stkBAAMCAAN5AAM4BA"
PHOTO_REGULAR = "AgACAgIAAxkBAAMHaVuXyRaIsterNpb8m4S6OCNs4pAAAkkPaxt7wNlKFbDPVp3lyU0BAAMCAAN5AAM4BA"
PHOTO_SCAMMER = "AgACAgIAAxkBAAMKaVuX0DTYvXOoh6L9-LQYZ6tXD4IAAkoPaxt7wNlKXE2XwnPDiyIBAAMCAAN5AAM4BA"
PHOTO_GARANT = "AgACAgIAAxkBAAMNaVuX0Rv_6GJVFb8ulnhTb9UCxWUAAjwNaxsDaeBK8uKoaFgkFVEBAAMCAAN5AAM4BA"
PHOTO_USER_PROFILE = "AgACAgIAAxkBAAMHaVuXyRaIsterNpb8m4S6OCNs4pAAAkkPaxt7wNlKFbDPVp3lyU0BAAMCAAN5AAM4BA"
PHOTO_USER_SCAMMER = "AgACAgIAAxkBAAMKaVuX0DTYvXOoh6L9-LQYZ6tXD4IAAkoPaxt7wNlKXE2XwnPDiyIBAAMCAAN5AAM4BA"
PHOTO_ADMIN = "AgACAgIAAxkBAAMQaVuX1K1bJLDWomL_T1ubUBQdnVYAAgcNaxsDaeBKrAABfnFPRUbCAQADAgADeQADOAQ"

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_welcome_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Новостной канал", url="https://t.me/AntiScamLaboratory")],
        [InlineKeyboardButton("🕵️ Слить скамера", url="https://t.me/antiscambaseAS")]
    ])

def get_check_result_inline_keyboard(username):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Слить скамера", url="https://t.me/antiscambaseAS")],
        [InlineKeyboardButton("🔗 Вечная ссылка", callback_data=f"perma_link:{username}")
        ]
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
        if user_id == ADMIN_ID or is_chat_admin(user_id, 0):
            keyboard.append(["🔐 Админ панель"])
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    return None

def get_admin_reply_keyboard():
    keyboard = [
        ["➕ Добавить гаранта", "➖ Удалить гаранта"],
        ["➕ Добавить скамера", "➖ Удалить скамера"],
        ["➕ Добавить админа", "➖ Удалить админа"],
        ["📊 Статистика", "⬅️ На главную"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# ========== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРАВ ==========
def is_global_admin(user_id):
    """Проверка, является ли пользователь глобальным администратором"""
    return user_id == ADMIN_ID

def is_chat_admin(user_id, chat_id):
    """Проверка, является ли пользователь администратором чата"""
    try:
        cursor.execute("SELECT 1 FROM chat_admins WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора чата: {e}")
        return False

def can_manage_chat(user_id, chat_id):
    """Проверка, может ли пользователь управлять чатом"""
    return is_global_admin(user_id) or is_chat_admin(user_id, chat_id)

def add_chat_admin_to_db(user_id, added_by=ADMIN_ID, chat_id=0):
    """Добавить администратора в базу данных"""
    try:
        cursor.execute(
            """INSERT INTO chat_admins (user_id, chat_id, added_by, added_date) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO NOTHING""",
            (user_id, chat_id, added_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении администратора: {e}")
        return False

def remove_chat_admin_from_db(user_id, chat_id=0):
    """Удалить администратора из базы данных"""
    try:
        cursor.execute("DELETE FROM chat_admins WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка при удалении администратора: {e}")
        return False

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ ПРЕДОТВРАЩЕНИЯ ДУБЛИРОВАНИЯ ==========
last_message_time = {}
MESSAGE_COOLDOWN = 1

def check_message_cooldown(user_id):
    current_time = time.time()
    if user_id in last_message_time:
        time_diff = current_time - last_message_time[user_id]
        if time_diff < MESSAGE_COOLDOWN:
            return False
    last_message_time[user_id] = current_time
    return True

def update_admin_stats(admin_id, action):
    """Обновление статистики администратора"""
    try:
        cursor.execute(
            """INSERT INTO admin_stats (admin_id, added_scammers, added_garants, added_admins, last_action_date) 
            VALUES (?, 0, 0, 0, ?)
            ON CONFLICT(admin_id) DO UPDATE SET last_action_date = ?""",
            (admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        if action == "scammer":
            cursor.execute("UPDATE admin_stats SET added_scammers = added_scammers + 1 WHERE admin_id = ?", (admin_id,))
        elif action == "garant":
            cursor.execute("UPDATE admin_stats SET added_garants = added_garants + 1 WHERE admin_id = ?", (admin_id,))
        elif action == "admin":
            cursor.execute("UPDATE admin_stats SET added_admins = added_admins + 1 WHERE admin_id = ?", (admin_id,))
            
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка при обновлении статистики админа: {e}")

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_type = update.effective_chat.type
    
    if not check_message_cooldown(user.id):
        return
    
    welcome_text = (
        "🤩 Anti Scam - начинающий проект, который будет помогать людям не попадатся на скам и на сомнительные услуги.\n\n"
        "⚠️В нашей предложке вы - можете слить скамера или же сообщить о подозрительной личности.\n\n"
        "🔍Чат поиска гарантов| трейдов | просто общения - @AntiScamChata\n\n"
        "🛡Наш бот для проверки на скам - @AntilScamBot.\n\n"
        "✔️Если хотите нас поддержать, то ставьте в ник преписку 'As |  Ас'"
    )
    
    try:
        await update.message.reply_photo(
            photo=PHOTO_START,
            caption=welcome_text,
            reply_markup=get_welcome_inline_keyboard()
        )
    except:
        await update.message.reply_text(
            welcome_text,
            reply_markup=get_welcome_inline_keyboard()
        )
    
    if chat_type == "private":
        await update.message.reply_text(
            "Используйте кнопки ниже для навигации:",
            reply_markup=get_main_reply_keyboard(user.id, chat_type)
        )

async def check_user(user_id, username, searcher_id):
    try:
        cursor.execute(
            "INSERT INTO search_history (user_id, username, searcher_id, search_date) VALUES (?, ?, ?, ?)",
            (user_id, username, searcher_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        cursor.execute("SELECT COUNT(*) FROM search_history WHERE user_id = ?", (user_id,))
        search_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT scam_count, proofs, reason FROM scammers WHERE user_id = ?", (user_id,))
        scammer = cursor.fetchone()
        
        cursor.execute("SELECT info_link, proofs_link, proof_count FROM garants WHERE user_id = ?", (user_id,))
        garant = cursor.fetchone()
        
        # Проверяем, является ли администратором
        cursor.execute("SELECT COUNT(*) FROM chat_admins WHERE user_id = ?", (user_id,))
        is_admin = cursor.fetchone()[0] > 0
        
        if is_admin:
            cursor.execute("SELECT SUM(added_scammers) FROM chat_admins WHERE user_id = ?", (user_id,))
            added_scammers = cursor.fetchone()[0] or 0
        
        conn.commit()
        
        if scammer:
            scam_count, proofs, reason = scammer
            return {"type": "scammer", "scam_count": scam_count, "proofs": proofs, "reason": reason, "search_count": search_count}
        elif garant:
            info_link, proofs_link, proof_count = garant
            return {"type": "garant", "search_count": search_count, "info_link": info_link, "proofs_link": proofs_link, "proof_count": proof_count}
        elif is_admin:
            return {"type": "admin", "search_count": search_count, "added_scammers": added_scammers}
        else:
            return {"type": "regular", "search_count": search_count}
    except Exception as e:
        logger.error(f"Ошибка при проверке пользователя: {e}")
        return {"type": "regular", "search_count": 0}

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_message_cooldown(update.effective_user.id):
        return
    
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
            f"🕵️ᴜsᴇʀ: @{username}\n"
            f"🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...\n"
            f"✅ обычный ᴨоᴧьзоʙᴀᴛᴇᴧь ✅\n\n"
            f"🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {result['search_count']} раз\n\n"
            f"🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot\n\n"
            f"🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи [{current_time}]\n\n"
            f"оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!"
        )
        
        try:
            await update.message.reply_photo(
                photo=PHOTO_REGULAR,
                caption=response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
        except:
            await update.message.reply_text(
                response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
    
    elif result["type"] == "scammer":
        reason_text = f"Причина: {result['reason']}\n" if result.get('reason') else ""
        response = (
            f"🕵️ᴜsᴇʀ: @{username}\n"
            f"🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...\n"
            f"📍обнᴀᴩужᴇн ᴄᴋᴀʍᴇᴩ\n\n"
            f"ʙᴄᴇ ᴨᴩуɸы нᴀ ᴄᴋᴀʍ ⬇️\n"
            f"{reason_text}"
            f"{result['proofs'] or '(ᴄᴄыᴧᴋᴀ нᴀ ᴨᴩуɸы и ᴨᴩичинᴀ)'}\n\n"
            f"ᴨоᴧьзоʙᴀᴛᴇᴧь ᴄ ᴨᴧохой ᴩᴇᴨуᴛᴀциᴇй❌\n"
            f"дᴧя ʙᴀɯᴇй жᴇ бᴇзоᴨᴀᴄноᴄᴛи ᴧучɯᴇ зᴀбᴧоᴋиᴩоʙᴀᴛь ᴇᴦо✅\n\n"
            f"🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {result['search_count']} раз\n\n"
            f"🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot\n\n"
            f"🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи [{current_time}]\n\n"
            f"оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!"
        )
        
        try:
            await update.message.reply_photo(
                photo=PHOTO_SCAMMER,
                caption=response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
        except:
            await update.message.reply_text(
                response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
    
    elif result["type"] == "admin":
        response = (
            f"🕵️ᴜsᴇʀ: @{username}\n"
            f"🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...\n"
            f"💯яʙᴧяᴇᴛᴄя администратором бᴀзы\n\n"
            f"Добавленно скамеров - {result.get('added_scammers', 0)} чел.\n\n"
            f"🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {result['search_count']} раз\n\n"
            f"🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot\n\n"
            f"🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи [{current_time}]\n\n"
            f"оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!"
        )
        
        try:
            await update.message.reply_photo(
                photo=PHOTO_ADMIN,
                caption=response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
        except:
            await update.message.reply_text(
                response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
    
    else:  # garant
        info_link = result.get('info_link', '(ᴄᴄыᴧᴋᴀ нᴀ инɸо)')
        proofs_link = result.get('proofs_link', '(ᴄᴄыᴧᴋᴀ нᴀ ᴨᴩуɸы)')
        proof_count = result.get('proof_count', 0)
        
        response = (
            f"🕵️ᴜsᴇʀ: @{username}\n"
            f"🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...\n"
            f"💯яʙᴧяᴇᴛᴄя ᴦᴀᴩᴀнᴛоʍ бᴀзы\n\n"
            f"ᴇᴦо [ᴇᴇ] инɸо: {info_link}\n"
            f"ᴇᴦо [ᴇᴇ] ᴨᴩуɸы: {proofs_link}\n\n"
            f"🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {result['search_count']} раз\n\n"
            f"🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot\n\n"
            f"🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи [{current_time}]\n\n"
            f"оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!"
        )
        
        try:
            await update.message.reply_photo(
                photo=PHOTO_GARANT,
                caption=response,
                reply_markup=get_check_result_inline_keyboard(username)
            )
        except:
            await update.message.reply_text(
                response,
                reply_markup=get_check_result_inline_keyboard(username)
            )

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /me и обработчик кнопки 'Мой профиль' с фото"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    user = update.effective_user
    result = await check_user(user.id, user.username or f"id{user.id}", user.id)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Определяем роль пользователя
    if result["type"] == "scammer":
        profile_photo = PHOTO_USER_SCAMMER
        status_text = f"СКАМЕР ⚠️\nКоличество скамов: {result['scam_count']}\nПричина: {result.get('reason', 'Не указана')}"
        status_emoji = "⚠️"
    elif result["type"] == "garant":
        profile_photo = PHOTO_GARANT
        status_text = f"ГАРАНТ ✅\nПруфов: {result.get('proof_count', 0)}"
        status_emoji = "✅"
    elif result["type"] == "admin":
        profile_photo = PHOTO_ADMIN
        status_text = f"АДМИНИСТРАТОР 👑\nДобавлено скамеров: {result.get('added_scammers', 0)}"
        status_emoji = "👑"
    else:
        profile_photo = PHOTO_USER_PROFILE
        status_text = "ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ"
        status_emoji = "👤"
    
    user_info = (
        f"{status_emoji} Ваш профиль:\n\n"
        f"🆔 ID: {user.id}\n"
        f"📛 Имя: {user.first_name}\n"
        f"📧 Username: @{user.username or 'Нет'}\n"
        f"🔍 Статус: {status_text}\n\n"
        f"👁‍🗨 Вас искали: {result['search_count']} раз\n"
        f"🗓️ Дата проверки: {current_time}\n\n"
        f"🤖 Бот: @AntilScamBot"
    )
    
    try:
        await update.message.reply_photo(
            photo=profile_photo,
            caption=user_info,
            reply_markup=get_main_reply_keyboard(user.id, update.effective_chat.type)
        )
    except:
        await update.message.reply_text(
            user_info, 
            reply_markup=get_main_reply_keyboard(user.id, update.effective_chat.type)
        )

# ========== КОМАНДЫ ДЛЯ АДМИНИСТРАТОРОВ ==========
async def add_admin_global_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальная команда для добавления администратора (только для главного админа)"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    user = update.effective_user
    
    # Проверяем права
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только глобальный администратор может добавлять админов!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_admin @username\nПример: /add_admin @username123")
        return
    
    target_username = context.args[0].replace('@', '')
    target_user_id = hash(target_username) % 1000000
    
    # Проверяем, не является ли уже админом
    if is_chat_admin(target_user_id, 0):
        await update.message.reply_text(f"❌ @{target_username} уже является администратором!")
        return
    
    # Добавляем в базу
    if add_chat_admin_to_db(target_user_id, user.id, 0):
        # Обновляем статистику
        update_admin_stats(user.id, "admin")
        
        await update.message.reply_text(
            f"✅ @{target_username} добавлен как глобальный администратор!\n\n"
            f"👤 Добавил: {user.first_name}\n"
            f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🛡️ Теперь этот пользователь может:\n"
            f"• Добавлять скамеров (/add_scammer)\n"
            f"• Удалять скамеров (/del_scammer)\n"
            f"• Просматривать статистику (/stats)\n"
            f"• Управлять чатами (/add_chat_admin, /del_chat_admin)"
        )
    else:
        await update.message.reply_text(f"❌ Ошибка при добавлении администратора @{target_username}")

async def del_admin_global_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальная команда для удаления администратора (только для главного админа)"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    user = update.effective_user
    
    # Проверяем права
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только глобальный администратор может удалять админов!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_admin @username\nПример: /del_admin @username123")
        return
    
    target_username = context.args[0].replace('@', '')
    target_user_id = hash(target_username) % 1000000
    
    # Проверяем, является ли админом
    if not is_chat_admin(target_user_id, 0):
        await update.message.reply_text(f"❌ @{target_username} не является администратором!")
        return
    
    # Удаляем из базы
    if remove_chat_admin_from_db(target_user_id, 0):
        await update.message.reply_text(f"✅ @{target_username} удален из администраторов!")
    else:
        await update.message.reply_text(f"❌ Ошибка при удалении администратора @{target_username}")

async def list_admins_global_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех администраторов"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    user = update.effective_user
    
    # Проверяем права
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только глобальный администратор может просматривать список админов!")
        return
    
    try:
        cursor.execute(
            "SELECT user_id, added_by, added_date, added_scammers FROM chat_admins WHERE chat_id = 0 ORDER BY added_date"
        )
        chat_admins = cursor.fetchall()
        
        global_admin_info = f"👑 Глобальный администратор: ID {ADMIN_ID} (@SAGYN_OFFICIAL)\n"
        
        if chat_admins:
            admins_list = []
            for admin in chat_admins:
                user_id, added_by, added_date, added_scammers = admin
                admins_list.append(f"• ID: {user_id} (добавил {added_scammers} скамеров, добавлен {added_date[:10]})")
            
            response = (
                f"📋 Глобальные администраторы бота:\n\n"
                f"{global_admin_info}\n"
                f"👥 Администраторы ({len(chat_admins)}):\n"
                + "\n".join(admins_list) +
                f"\n\n📊 Всего администраторов: {len(chat_admins) + 1}"
            )
        else:
            response = (
                f"📋 Глобальные администраторы бота:\n\n"
                f"{global_admin_info}\n"
                f"👥 Администраторы: Нет\n\n"
                f"📊 Всего администраторов: 1 (только глобальный)"
            )
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Ошибка в list_admins_global_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении списка администраторов!")

# ========== КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ СКАМЕРАМИ (доступны админам) ==========
async def add_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить скамера (доступно админам)"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    user = update.effective_user
    
    # Проверяем права - теперь админы тоже могут добавлять скамеров
    if not can_manage_chat(user.id, 0):
        await update.message.reply_text("❌ У вас нет прав для добавления скамеров!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /add_scammer @username причина_заноса [доказательства]\nПример: /add_scammer @username Скам 1000 руб https://t.me/proofs")
        return
    
    username = context.args[0].replace('@', '')
    reason = context.args[1]
    proofs = ' '.join(context.args[2:]) if len(context.args) > 2 else ""
    
    try:
        cursor.execute(
            """INSERT INTO scammers (user_id, username, scam_count, proofs, added_by, added_date, reason, reporter_id) 
            VALUES (?, ?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
            scam_count = scam_count + 1,
            proofs = COALESCE(proofs, '') || '\n' || excluded.proofs,
            reason = excluded.reason""",
            (hash(username) % 1000000, username, proofs, user.id, 
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reason, user.id)
        )
        
        # Обновляем статистику администратора
        update_admin_stats(user.id, "scammer")
        
        # Обновляем статистику в chat_admins если это админ
        if is_chat_admin(user.id, 0):
            cursor.execute(
                "UPDATE chat_admins SET added_scammers = added_scammers + 1 WHERE user_id = ? AND chat_id = 0",
                (user.id,)
            )
        
        conn.commit()
        
        response = (
            f"✅ @{username} добавлен в скамеры!\n\n"
            f"📝 Причина: {reason}\n"
            f"📎 Доказательства: {proofs or 'Не указаны'}\n\n"
            f"👤 Добавил: {user.first_name}\n"
            f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Ошибка в add_scammer_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при добавлении скамера!")

async def del_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить скамера (доступно админам)"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    user = update.effective_user
    
    # Проверяем права - теперь админы тоже могут удалять скамеров
    if not can_manage_chat(user.id, 0):
        await update.message.reply_text("❌ У вас нет прав для удаления скамеров!")
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
        await update.message.reply_text(f"❌ @{username} не найден в базе скамеров")

async def add_garant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить гаранта (только для главного админа)"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только глобальный администратор может добавлять гарантов!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_garant @username [info_link] [proofs_link] [proof_count]\nПример: /add_garant @user https://t.me/info https://t.me/proofs 5")
        return
    
    username = context.args[0].replace('@', '')
    info_link = context.args[1] if len(context.args) > 1 else "https://t.me/AntiScamLaboratory"
    proofs_link = context.args[2] if len(context.args) > 2 else "https://t.me/AntiScamLaboratory"
    proof_count = int(context.args[3]) if len(context.args) > 3 and context.args[3].isdigit() else 0
    
    cursor.execute(
        "INSERT OR REPLACE INTO garants (user_id, username, added_by, added_date, info_link, proofs_link, proof_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (hash(username) % 1000000, username, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), info_link, proofs_link, proof_count)
    )
    
    # Обновляем статистику администратора
    update_admin_stats(user.id, "garant")
    
    conn.commit()
    
    response = (
        f"✅ @{username} добавлен в гаранты!\n\n"
        f"📊 Информация: {info_link}\n"
        f"📎 Пруфы: {proofs_link}\n"
        f"🔢 Количество пруфов: {proof_count}\n\n"
        f"👤 Добавил: {user.first_name}\n"
        f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}"
    )
    
    await update.message.reply_text(response)

async def del_garant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить гаранта (только для главного админа)"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только глобальный администратор может удалять гарантов!")
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

async def list_garants_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список гарантов"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    cursor.execute("SELECT username, proof_count, proofs_link FROM garants ORDER BY username")
    garants = cursor.fetchall()
    
    if garants:
        response = "⭐ ГАРАНТЫ БАЗЫ:\n\n"
        for garant in garants:
            username, proof_count, proofs_link = garant
            response += f"👤 @{username}\n📊 Пруфов: {proof_count}\n🔗 Канал: {proofs_link}\n\n"
        response += f"📊 Всего гарантов: {len(garants)}"
    else:
        response = "📭 Список гарантов пуст"
    
    await update.message.reply_text(response)

# ========== СТАТИСТИКА ==========
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика бота (доступно админам)"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    user = update.effective_user
    
    # Проверяем права
    if not can_manage_chat(user.id, 0):
        await update.message.reply_text("❌ У вас нет прав для просмотра статистики!")
        return
    
    cursor.execute("SELECT COUNT(*) FROM scammers")
    scammer_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM garants")
    garant_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM search_history")
    search_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM chat_admins WHERE chat_id = 0")
    chat_admins_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(added_scammers) FROM admin_stats")
    total_added_scammers = cursor.fetchone()[0] or 0
    
    # Получаем топ админов по добавлению скамеров
    cursor.execute("SELECT user_id, added_scammers FROM chat_admins WHERE chat_id = 0 ORDER BY added_scammers DESC LIMIT 5")
    top_admins = cursor.fetchall()
    
    top_admins_text = ""
    for idx, (admin_id, added_count) in enumerate(top_admins, 1):
        top_admins_text += f"{idx}. ID {admin_id}: {added_count} скамеров\n"
    
    stats_text = (
        f"📊 Статистика Anti-Scam Bot v6.0:\n\n"
        f"🚨 Скамеров в базе: {scammer_count}\n"
        f"⭐ Гарантов в базе: {garant_count}\n"
        f"🔍 Всего проверок: {search_count}\n"
        f"👥 Администраторов: {chat_admins_count + 1}\n"
        f"📈 Всего добавлено скамеров: {total_added_scammers}\n\n"
        f"🏆 ТОП-5 администраторов:\n{top_admins_text}\n"
        f"👑 Глобальный админ ID: {ADMIN_ID}\n"
        f"🌐 Хост: Render.com\n"
        f"📡 Запросов к API: {bot_status['total_requests']}\n"
        f"🔄 Версия: 6.0 (полное управление ролями)"
    )
    await update.message.reply_text(stats_text)

# ========== КОМАНДЫ ДЛЯ ЧАТОВ ==========
async def add_chat_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить администратора чата"""
    if not check_message_cooldown(update.effective_user.id):
        return
    
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Эта команда работает только в группах!")
        return
    
    if not can_manage_chat(user.id, chat.id):
        await update.message.reply_text("❌ У вас нет прав для добавления администраторов чата!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_chat_admin @username\nПример: /add_chat_admin @user123")
        return
    
    target = context.args[0].replace('@', '')
    user_id = hash(target) % 1000000
    
    if is_chat_admin(user_id, chat.id):
        await update.message.reply_text(f"❌ @{target} уже является администратором этого чата!")
        return
    
    try:
        cursor.execute(
            "INSERT INTO chat_admins (user_id, chat_id, added_by, added_date) VALUES (?, ?, ?, ?)",
            (user_id, chat.id, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        # Обновляем статистики администратора
        update_admin_stats(user.id, "admin")
        
        conn.commit()
        
        response = (
            f"✅ @{target} добавлен как администратор чата!\n\n"
            f"📛 Чат: {chat.title}\n"
            f"👤 Добавил: {user.first_name}\n"
            f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🛡️ Теперь этот пользователь может:\n"
            f"• Управлять чатом (/close, /open)\n"
            f"• Выдавать предупреждения (/warn)\n"
            f"• Заглушать пользователей (/mute)"
        )
        
        await update.message.reply_text(response)
        
    except sqlite3.IntegrityError:
        await update.message.reply_text(f"❌ @{target} уже является администратором!")
    except Exception as e:
        logger.error(f"Ошибка в add_chat_admin_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при добавлении администратора!")

# ========== СПРАВКА ==========
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_message_cooldown(update.effective_user.id):
        return
    
    chat_type = update.effective_chat.type
    user = update.effective_user
    
    help_text = (
        "🤖 Anti-Scam Bot - Справка\n\n"
        "📌 Основные команды:\n"
        "/start - Начать работу с ботом\n"
        "/check @username - Проверить пользователя\n"
        "/check (в ответ на сообщение) - Проверить отправителя\n"
        "/me - Показать мой профиль\n"
        "/garants - Список гарантов\n\n"
    )
    
    if can_manage_chat(user.id, update.effective_chat.id):
        help_text += (
            "👑 Команды для администраторов:\n"
            "/add_scammer @username причина - Добавить скамера\n"
            "/del_scammer @username - Удалить скамера\n"
            "/stats - Статистика бота\n"
            "/list_admins - Список администраторов\n\n"
        )
    
    if is_global_admin(user.id):
        help_text += (
            "🕵️‍♂️ Глобальные админ команды:\n"
            "/add_admin @username - Добавить администратора\n"
            "/del_admin @username - Удалить администратора\n"
            "/add_garant @username - Добавить гаранта\n"
            "/del_garant @username - Удалить гаранта\n"
            "/broadcast - Рассылка сообщения\n\n"
        )
    
    help_text += (
        "📊 Статус бота: /status\n"
        "🛠 Разработчик: @SAGYN_OFFICIAL"
    )
    
    await update.message.reply_text(
        help_text,
        reply_markup=get_main_reply_keyboard(update.effective_user.id, update.effective_chat.type)
    )

# ========== ДРУГИЕ КОМАНДЫ ==========
async def bot_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_message_cooldown(update.effective_user.id):
        return
    
    status_text = (
        "🤖 Статус Anti-Scam Bot:\n\n"
        f"📊 Статус: ✅ Онлайн\n"
        f"⏱ Запущен: {bot_status['started_at'][:19]}\n"
        f"🔄 Uptime: {str(datetime.now() - datetime.fromisoformat(bot_status['started_at']))}\n"
        f"📡 Последний пинг: {bot_status['last_ping'][:19]}\n"
        f"🌐 Запросов к API: {bot_status['total_requests']}\n\n"
        f"⚡ Бот работает нормально"
    )
    await update.message.reply_text(status_text)

# ========== ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ==========
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not check_message_cooldown(update.effective_user.id):
            return
        
        text = update.message.text
        user = update.effective_user
        chat_type = update.effective_chat.type
        
        if chat_type != "private":
            return
        
        logger.info(f"Получено текстовое сообщение: '{text}' от пользователя {user.id}")
        
        if text == "👤 Мой профиль":
            logger.info(f"Пользователь {user.id} нажал 'Мой профиль'")
            await me_command(update, context)
        elif text == "⭐ Список гарантов":
            await list_garants_command(update, context)
        elif text == "🕵️ Слить скамера":
            await update.message.reply_text(
                "Для слива скамера перейдите по ссылке:\nhttps://t.me/antiscambaseAS",
                reply_markup=get_main_reply_keyboard(user.id, chat_type)
            )
        elif text == "📋 Команды":
            await help_command(update, context)
        elif text == "ℹ️ Информация о боте":
            info_text = (
                "🤖 Anti Scam Bot v6.0\n\n"
                "🔍 Бот для проверки пользователей на скам\n\n"
                "📊 НОВЫЕ ВОЗМОЖНОСТИ:\n"
                "• Показ роли в профиле (скамер/гарант/админ/обычный)\n"
                "• Фото профиля для каждой роли\n"
                "• Система статистики администраторов\n"
                "• Причины добавления скамеров\n"
                "• Счетчик пруфов у гарантов\n\n"
                "👑 РОЛИ ПОЛЬЗОВАТЕЛЕЙ:\n"
                "• Скамер - красное фото, причина скама\n"
                "• Гарант - синее фото, количество пруфов\n"
                "• Администратор - золотое фото, статистика\n"
                "• Обычный пользователь - зеленое фото\n\n"
                "🛠 Разработчик: @SAGYN_OFFICIAL\n"
                "📅 Версия: 6.0 (полное управление ролями)"
            )
            await update.message.reply_text(info_text, reply_markup=get_main_reply_keyboard(user.id, chat_type))
        elif text == "🔐 Админ панель" and can_manage_chat(user.id, 0):
            await update.message.reply_text("👑 Админ панель", reply_markup=get_admin_reply_keyboard())
        elif text == "➕ Добавить гаранта" and is_global_admin(user.id):
            await update.message.reply_text("Используйте команду: /add_garant @username [info_link] [proofs_link] [proof_count]")
        elif text == "➖ Удалить гаранта" and is_global_admin(user.id):
            await update.message.reply_text("Используйте команду: /del_garant @username")
        elif text == "➕ Добавить скамера" and can_manage_chat(user.id, 0):
            await update.message.reply_text("Используйте команду: /add_scammer @username причина_скама")
        elif text == "➖ Удалить скамера" and can_manage_chat(user.id, 0):
            await update.message.reply_text("Используйте команду: /del_scammer @username")
        elif text == "➕ Добавить админа" and is_global_admin(user.id):
            await update.message.reply_text("Используйте команду: /add_admin @username")
        elif text == "➖ Удалить админа" and is_global_admin(user.id):
            await update.message.reply_text("Используйте команду: /del_admin @username")
        elif text == "📊 Статистика" and can_manage_chat(user.id, 0):
            await stats_command(update, context)
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
        print("🚀 Запуск Anti-Scam Bot v6.0 с полным управлением ролями...")
        
        # Запускаем веб-сервер в отдельном потоке
        web_thread = threading.Thread(target=run_web_server, daemon=True)
        web_thread.start()
        
        print("🌐 Веб-сервер запущен")
        print(f"👑 Глобальный админ ID: {ADMIN_ID}")
        
        time.sleep(2)
        
        # Создаем приложение Telegram бота
        print("🤖 Инициализация Telegram бота...")
        application = Application.builder().token(TOKEN).build()
        
        # СНАЧАЛА обработчик текстовых сообщений (чтобы перехватывал кнопки)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        # ПОТОМ основные команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("me", me_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", bot_status_command))
        application.add_handler(CommandHandler("garants", list_garants_command))
        application.add_handler(CommandHandler("stats", stats_command))
        
        # Команды администраторов
        application.add_handler(CommandHandler("add_scammer", add_scammer_command))
        application.add_handler(CommandHandler("del_scammer", del_scammer_command))
        application.add_handler(CommandHandler("add_garant", add_garant_command))
        application.add_handler(CommandHandler("del_garant", del_garant_command))
        
        # Команды для управления админами
        application.add_handler(CommandHandler("add_admin", add_admin_global_command))
        application.add_handler(CommandHandler("del_admin", del_admin_global_command))
        application.add_handler(CommandHandler("list_admins", list_admins_global_command))
        
        # Команды для управления чатами
        application.add_handler(CommandHandler("add_chat_admin", add_chat_admin_command))
        
        print("\n" + "="*50)
        print("✅ СИСТЕМА ЗАПУЩЕНА УСПЕШНО!")
        print("="*50)
        print("\n📱 ОТПРАВЬТЕ /start В TELEGRAM")
        print("\n🌟 ОСНОВНЫЕ ВОЗМОЖНОСТИ v6.0:")
        print("1. Полное управление ролями пользователей")
        print("2. Фото профиля для каждой роли")
        print("3. Показ роли при нажатии 'Мой профиль'")
        print("4. Причины добавления скамеров")
        print("5. Статистика администраторов")
        print("\n👑 КОМАНДЫ ДЛЯ АДМИНИСТРАТОРОВ:")
        print("• /add_admin @username - добавить администратора (только главный админ)")
        print("• /del_admin @username - удалить администратора (только главный админ)")
        print("• /add_scammer @username причина - добавить скамера (доступно админам)")
        print("• /del_scammer @username - удалить скамера (доступно админам)")
        print("• /add_garant @username - добавить гаранта (только главный админ)")
        print("• /list_admins - список всех администраторов")
        print("• /stats - статистика бота")
        print("\n📸 ID ФОТО ДЛЯ ПРОВЕРКИ:")
        print(f"• Приветствие: {PHOTO_START[:30]}...")
        print(f"• Администратор: {PHOTO_ADMIN[:30]}...")
        print(f"• Гарант: {PHOTO_GARANT[:30]}...")
        print(f"• Скамер: {PHOTO_SCAMMER[:30]}...")
        print(f"• Обычный: {PHOTO_REGULAR[:30]}...")
        print("\n🔗 ДЛЯ UPTIMEROBOT:")
        print("• Health: https://anti-scam-bot1-7.onrender.com/health")
        print("• Ping: https://anti-scam-bot1-7.onrender.com/ping")
        
        # Запускаем polling
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        print(f"🔴 Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
