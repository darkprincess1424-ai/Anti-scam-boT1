import os
import logging
import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ========== НАСТРОЙКА ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    sys.exit(1)

ADMIN_ID = 8281804228  # Ваш ID

# База данных
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
    added_date TEXT,
    reason TEXT
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
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    added_by INTEGER,
    added_date TEXT
)''')

conn.commit()
print("✅ База данных готова")

# ========== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРАВ ==========
def is_global_admin(user_id):
    """Проверка, является ли пользователь глобальным администратором"""
    return user_id == ADMIN_ID

def is_admin(user_id):
    """Проверка, является ли пользователь администратором"""
    try:
        if user_id == ADMIN_ID:
            return True
        cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None
    except:
        return False

def can_manage_scammers(user_id):
    """Проверка, может ли пользователь управлять скамерами"""
    return is_global_admin(user_id) or is_admin(user_id)

# ========== КЛАВИАТУРЫ ==========
def get_main_reply_keyboard(user_id=None):
    keyboard = [
        ["👤 Мой профиль", "⭐ Список гарантов"],
        ["🕵️ Слить скамера", "📋 Команды"],
        ["ℹ️ Информация о боте"]
    ]
    if is_admin(user_id):
        keyboard.append(["🔐 Админ панель"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_admin_reply_keyboard():
    keyboard = [
        ["➕ Добавить гаранта", "➖ Удалить гаранта"],
        ["➕ Добавить скамера", "➖ Удалить скамера"],
        ["➕ Добавить админа", "➖ Удалить админа"],
        ["📊 Статистика", "⬅️ На главную"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    welcome_text = (
        "🤩 Anti Scam - начинающий проект, который будет помогать людям не попадатся на скам и на сомнительные услуги.\n\n"
        "⚠️В нашей предложке вы - можете слить скамера или же сообщить о подозрительной личности.\n\n"
        "🔍Чат поиска гарантов| трейдов | просто общения - @AntiScamChata\n\n"
        "🛡Наш бот для проверки на скам - @AntilScamBot.\n\n"
        "✔️Если хотите нас поддержать, то ставьте в ник преписку 'As |  Ас'"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Новостной канал", url="https://t.me/AntiScamLaboratory")],
            [InlineKeyboardButton("🕵️ Слить скамера", url="https://t.me/antiscambaseAS")]
        ])
    )
    
    await update.message.reply_text(
        "Используйте кнопки ниже для навигации:",
        reply_markup=get_main_reply_keyboard(user.id)
    )

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /me и обработчик кнопки 'Мой профиль'"""
    user = update.effective_user
    
    try:
        # Получаем информацию о пользователе
        cursor.execute("SELECT COUNT(*) FROM search_history WHERE user_id = ?", (user.id,))
        search_count = cursor.fetchone()[0] or 0
        
        # Проверяем, является ли скамером
        cursor.execute("SELECT scam_count, reason FROM scammers WHERE user_id = ?", (user.id,))
        scammer = cursor.fetchone()
        
        # Проверяем, является ли гарантом
        cursor.execute("SELECT proof_count FROM garants WHERE user_id = ?", (user.id,))
        garant = cursor.fetchone()
        
        # Проверяем, является ли админом
        admin_status = is_admin(user.id)
        
        # Определяем роль
        if scammer:
            scam_count, reason = scammer
            status_text = f"СКАМЕР ⚠️\nКоличество скамов: {scam_count}\nПричина: {reason or 'Не указана'}"
            status_emoji = "⚠️"
        elif garant:
            proof_count = garant[0]
            status_text = f"ГАРАНТ ✅\nПруфов: {proof_count}"
            status_emoji = "✅"
        elif admin_status:
            status_text = "АДМИНИСТРАТОР 👑"
            status_emoji = "👑"
        else:
            status_text = "ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ"
            status_emoji = "👤"
        
        user_info = (
            f"{status_emoji} Ваш профиль:\n\n"
            f"🆔 ID: {user.id}\n"
            f"📛 Имя: {user.first_name}\n"
            f"📧 Username: @{user.username or 'Нет'}\n"
            f"🔍 Статус: {status_text}\n\n"
            f"👁‍🗨 Вас искали: {search_count} раз\n"
            f"🗓️ Дата проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"🤖 Бот: @AntilScamBot"
        )
        
        await update.message.reply_text(
            user_info, 
            reply_markup=get_main_reply_keyboard(user.id)
        )
        
    except Exception as e:
        logger.error(f"Ошибка в me_command: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при получении профиля",
            reply_markup=get_main_reply_keyboard(user.id)
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
    
    try:
        # Сохраняем историю поиска
        cursor.execute(
            "INSERT INTO search_history (user_id, username, searcher_id, search_date) VALUES (?, ?, ?, ?)",
            (user_id, username, update.effective_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        # Проверяем скамеров
        cursor.execute("SELECT scam_count, proofs, reason FROM scammers WHERE user_id = ?", (user_id,))
        scammer = cursor.fetchone()
        
        # Проверяем гарантов
        cursor.execute("SELECT info_link, proofs_link, proof_count FROM garants WHERE user_id = ?", (user_id,))
        garant = cursor.fetchone()
        
        # Проверяем админов
        admin_status = False
        if user_id == ADMIN_ID:
            admin_status = True
        else:
            cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
            admin_status = cursor.fetchone() is not None
        
        conn.commit()
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if scammer:
            scam_count, proofs, reason = scammer
            response = (
                f"🕵️ᴜsᴇʀ: @{username}\n"
                f"🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...\n"
                f"📍обнᴀᴩужᴇн ᴄᴋᴀʍᴇᴩ\n\n"
                f"ʙᴄᴇ ᴨᴩуɸы нᴀ ᴄᴋᴀʍ ⬇️\n"
                f"{reason or '(ᴄᴄыᴧᴋᴀ нᴀ ᴨᴩуɸы)'}\n\n"
                f"ᴨоᴧьзоʙᴀᴛᴇᴧь ᴄ ᴨᴧохой ᴩᴇᴨуᴛᴀциᴇй❌\n"
                f"дᴧя ʙᴀɯᴇй жᴇ бᴇзоᴨᴀᴄноᴄᴛи ᴧучɯᴇ зᴀбᴧоᴋиᴩоʙᴀᴛь ᴇᴦо✅\n\n"
                f"🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot\n\n"
                f"🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи [{current_time}]"
            )
            
        elif garant:
            info_link, proofs_link, proof_count = garant
            response = (
                f"🕵️ᴜsᴇʀ: @{username}\n"
                f"🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...\n"
                f"💯яʙᴧяᴇᴛᴄя ᴦᴀᴩᴀнᴛоʍ бᴀзы\n\n"
                f"ᴇᴦо [ᴇᴇ] инɸо: {info_link}\n"
                f"ᴇᴦо [ᴇᴇ] ᴨᴩуɸы: {proofs_link}\n"
                f"🔢 Количество пруфов: {proof_count}\n\n"
                f"🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot\n\n"
                f"🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи [{current_time}]"
            )
            
        elif admin_status:
            response = (
                f"🕵️ᴜsᴇʀ: @{username}\n"
                f"🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...\n"
                f"💯яʙᴧяᴇᴛᴄя администратором бᴀзы\n\n"
                f"🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot\n\n"
                f"🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи [{current_time}]"
            )
            
        else:
            response = (
                f"🕵️ᴜsᴇʀ: @{username}\n"
                f"🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...\n"
                f"✅ обычный ᴨоᴧьзоʙᴀᴛᴇᴧь ✅\n\n"
                f"🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot\n\n"
                f"🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи [{current_time}]"
            )
        
        await update.message.reply_text(
            response,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚨 Слить скамера", url="https://t.me/antiscambaseAS")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка в check_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при проверке")

# ========== КОМАНДЫ ДЛЯ АДМИНОВ ==========
async def add_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not can_manage_scammers(user.id):
        await update.message.reply_text("❌ У вас нет прав для добавления скамеров!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /add_scammer @username причина\nПример: /add_scammer @username Скам 1000 руб")
        return
    
    username = context.args[0].replace('@', '')
    reason = ' '.join(context.args[1:])
    user_id = hash(username) % 1000000
    
    try:
        cursor.execute(
            """INSERT OR REPLACE INTO scammers (user_id, username, scam_count, proofs, added_by, added_date, reason) 
            VALUES (?, ?, 1, '', ?, ?, ?)""",
            (user_id, username, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reason)
        )
        conn.commit()
        
        await update.message.reply_text(f"✅ @{username} добавлен в скамеры!\nПричина: {reason}")
        
    except Exception as e:
        logger.error(f"Ошибка в add_scammer_command: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении скамера")

async def del_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный администратор может удалять скамеров!")
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

async def add_garant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный администратор может добавлять гарантов!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_garant @username\nПример: /add_garant @username")
        return
    
    username = context.args[0].replace('@', '')
    user_id = hash(username) % 1000000
    
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO garants (user_id, username, added_by, added_date, info_link, proofs_link) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
             "https://t.me/AntiScamLaboratory", "https://t.me/AntiScamLaboratory")
        )
        conn.commit()
        
        await update.message.reply_text(f"✅ @{username} добавлен в гаранты!")
        
    except Exception as e:
        logger.error(f"Ошибка в add_garant_command: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении гаранта")

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
        await update.message.reply_text(f"✅ @{username} удален из гарантов")
    else:
        await update.message.reply_text(f"❌ @{username} не найден")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный администратор может добавлять админов!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_admin @username")
        return
    
    username = context.args[0].replace('@', '')
    user_id = hash(username) % 1000000
    
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO admins (user_id, username, added_by, added_date) VALUES (?, ?, ?, ?)",
            (user_id, username, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        
        await update.message.reply_text(f"✅ @{username} добавлен как администратор!")
        
    except Exception as e:
        logger.error(f"Ошибка в add_admin_command: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении администратора")

async def del_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_global_admin(user.id):
        await update.message.reply_text("❌ Только главный администратор может удалять админов!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /del_admin @username")
        return
    
    username = context.args[0].replace('@', '')
    user_id = hash(username) % 1000000
    
    cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await update.message.reply_text(f"✅ @{username} удален из администраторов")
    else:
        await update.message.reply_text(f"❌ @{username} не найден")

async def list_garants_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT username, proof_count FROM garants ORDER BY username")
    garants = cursor.fetchall()
    
    if garants:
        response = "⭐ ГАРАНТЫ БАЗЫ:\n\n"
        for garant in garants:
            username, proof_count = garant
            response += f"👤 @{username}\n📊 Пруфов: {proof_count}\n\n"
        response += f"📊 Всего гарантов: {len(garants)}"
    else:
        response = "📭 Список гарантов пуст"
    
    await update.message.reply_text(response)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not can_manage_scammers(user.id):
        await update.message.reply_text("❌ У вас нет прав для просмотра статистики!")
        return
    
    cursor.execute("SELECT COUNT(*) FROM scammers")
    scammer_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM garants")
    garant_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM search_history")
    search_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM admins")
    admins_count = cursor.fetchone()[0]
    
    stats_text = (
        f"📊 Статистика Anti-Scam Bot:\n\n"
        f"🚨 Скамеров в базе: {scammer_count}\n"
        f"⭐ Гарантов в базе: {garant_count}\n"
        f"🔍 Всего проверок: {search_count}\n"
        f"👥 Администраторов: {admins_count + 1}\n\n"
        f"👑 Главный админ: ID {ADMIN_ID}\n"
        f"🔄 Версия: 6.0"
    )
    
    await update.message.reply_text(stats_text)

# ========== ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ==========
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        user = update.effective_user
        
        print(f"📩 Получено сообщение: '{text}' от пользователя {user.id}")
        
        # ВСЕГДА обрабатываем кнопки, независимо от типа чата
        
        if text == "👤 Мой профиль":
            print(f"👤 Пользователь {user.id} нажал 'Мой профиль'")
            await me_command(update, context)
            
        elif text == "⭐ Список гарантов":
            await list_garants_command(update, context)
            
        elif text == "🕵️ Слить скамера":
            await update.message.reply_text(
                "Для слива скамера перейдите по ссылке:\nhttps://t.me/antiscambaseAS",
                reply_markup=get_main_reply_keyboard(user.id)
            )
            
        elif text == "📋 Команды":
            help_text = (
                "🤖 Anti-Scam Bot - Справка\n\n"
                "📌 Основные команды:\n"
                "/start - Начать работу с ботом\n"
                "/check @username - Проверить пользователя\n"
                "/check (в ответ на сообщение) - Проверить отправителя\n"
                "/me - Показать мой профиль\n"
                "/garants - Список гарантов\n\n"
            )
            
            if can_manage_scammers(user.id):
                help_text += (
                    "👑 Команды для администраторов:\n"
                    "/add_scammer @username причина - Добавить скамера\n"
                    "/del_scammer @username - Удалить скамера\n"
                    "/stats - Статистика бота\n\n"
                )
            
            if is_global_admin(user.id):
                help_text += (
                    "🕵️‍♂️ Глобальные админ команды:\n"
                    "/add_admin @username - Добавить администратора\n"
                    "/del_admin @username - Удалить администратора\n"
                    "/add_garant @username - Добавить гаранта\n"
                    "/del_garant @username - Удалить гаранта\n\n"
                )
            
            help_text += "🛠 Разработчик: @SAGYN_OFFICIAL"
            
            await update.message.reply_text(
                help_text,
                reply_markup=get_main_reply_keyboard(user.id)
            )
            
        elif text == "ℹ️ Информация о боте":
            info_text = (
                "🤖 Anti Scam Bot v6.0\n\n"
                "🔍 Бот для проверки пользователей на скам\n\n"
                "📊 ВОЗМОЖНОСТИ:\n"
                "• Показ роли в профиле\n"
                "• Проверка пользователей\n"
                "• Система администраторов\n"
                "• База скамеров и гарантов\n\n"
                "👑 РОЛИ ПОЛЬЗОВАТЕЛЕЙ:\n"
                "• Скамер - причина скама\n"
                "• Гарант - количество пруфов\n"
                "• Администратор - управление ботом\n"
                "• Обычный пользователь\n\n"
                "🛠 Разработчик: @SAGYN_OFFICIAL"
            )
            await update.message.reply_text(info_text, reply_markup=get_main_reply_keyboard(user.id))
            
        elif text == "🔐 Админ панель" and can_manage_scammers(user.id):
            await update.message.reply_text("👑 Админ панель", reply_markup=get_admin_reply_keyboard())
            
        elif text == "➕ Добавить гаранта" and is_global_admin(user.id):
            await update.message.reply_text("Используйте команду: /add_garant @username")
            
        elif text == "➖ Удалить гаранта" and is_global_admin(user.id):
            await update.message.reply_text("Используйте команду: /del_garant @username")
            
        elif text == "➕ Добавить скамера" and can_manage_scammers(user.id):
            await update.message.reply_text("Используйте команду: /add_scammer @username причина")
            
        elif text == "➖ Удалить скамера" and is_global_admin(user.id):
            await update.message.reply_text("Используйте команду: /del_scammer @username")
            
        elif text == "➕ Добавить админа" and is_global_admin(user.id):
            await update.message.reply_text("Используйте команду: /add_admin @username")
            
        elif text == "➖ Удалить админа" and is_global_admin(user.id):
            await update.message.reply_text("Используйте команду: /del_admin @username")
            
        elif text == "📊 Статистика" and can_manage_scammers(user.id):
            await stats_command(update, context)
            
        elif text == "⬅️ На главную":
            await update.message.reply_text(
                "Главное меню:",
                reply_markup=get_main_reply_keyboard(user.id)
            )
            
        else:
            await update.message.reply_text(
                "Используйте кнопки ниже:",
                reply_markup=get_main_reply_keyboard(user.id)
            )
            
    except Exception as e:
        logger.error(f"Ошибка в handle_text_message: {e}")
        print(f"❌ ERROR в handle_text_message: {e}")

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Запуск системы"""
    try:
        print("🚀 Запуск Anti-Scam Bot v6.0...")
        print(f"👑 Главный админ ID: {ADMIN_ID}")
        print("✅ Токен бота найден")
        
        # Создаем приложение Telegram бота
        application = Application.builder().token(TOKEN).build()
        
        # Добавляем обработчики в ПРАВИЛЬНОМ порядке:
        # 1. Сначала текстовые сообщения (кнопки)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        # 2. Потом команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("me", me_command))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("garants", list_garants_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text("Используйте кнопки ниже:", reply_markup=get_main_reply_keyboard(u.effective_user.id))))
        
        # 3. Команды админов
        application.add_handler(CommandHandler("add_scammer", add_scammer_command))
        application.add_handler(CommandHandler("del_scammer", del_scammer_command))
        application.add_handler(CommandHandler("add_garant", add_garant_command))
        application.add_handler(CommandHandler("del_garant", del_garant_command))
        application.add_handler(CommandHandler("add_admin", add_admin_command))
        application.add_handler(CommandHandler("del_admin", del_admin_command))
        
        print("\n" + "="*50)
        print("✅ СИСТЕМА ЗАПУЩЕНА УСПЕШНО!")
        print("="*50)
        print("\n📱 ОТПРАВЬТЕ /start В TELEGRAM")
        print("\n🌟 ОСНОВНЫЕ ВОЗМОЖНОСТИ:")
        print("• Кнопка '👤 Мой профиль' - показывает ваш профиль")
        print("• Кнопка '⭐ Список гарантов' - список гарантов")
        print("• /check @username - проверка пользователя")
        print("• /add_scammer @username причина - добавить скамера (для админов)")
        print("• /add_admin @username - добавить админа (только главный админ)")
        
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
