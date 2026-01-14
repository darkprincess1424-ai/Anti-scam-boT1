import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telebot import types
import sqlite3
import threading
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = 8281804428  # Ваш ID админа
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://your-domain.com/')

# Инициализация Flask и бота
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT DEFAULT 'user',
            search_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица скамеров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scammers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            reason TEXT,
            proofs TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица гарантов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS garanty (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            info_link TEXT,
            proofs_link TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица администраторов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица варнов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            reason TEXT,
            warned_by INTEGER,
            warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Добавляем администратора по умолчанию
    cursor.execute('INSERT OR IGNORE INTO admins (user_id, username, added_by) VALUES (?, ?, ?)', 
                  (ADMIN_ID, 'owner', ADMIN_ID))
    
    conn.commit()
    conn.close()

init_db()

# Функции работы с БД
def get_user_role(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Проверяем скамеров
    cursor.execute('SELECT * FROM scammers WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        conn.close()
        return 'scammer'
    
    # Проверяем гарантов
    cursor.execute('SELECT * FROM garanty WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        conn.close()
        return 'garant'
    
    # Проверяем администраторов
    cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        conn.close()
        return 'admin'
    
    conn.close()
    return 'user'

def increment_search_count(user_id, username):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Проверяем, есть ли пользователь
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        cursor.execute('UPDATE users SET search_count = search_count + 1 WHERE user_id = ?', (user_id,))
    else:
        cursor.execute('INSERT INTO users (user_id, username, search_count) VALUES (?, ?, 1)', 
                      (user_id, username))
    
    conn.commit()
    conn.close()

def get_search_count(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT search_count FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_scammers_count(admin_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM scammers WHERE added_by = ?', (admin_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def is_admin(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result

# Клавиатуры
def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton('Мой профиль'))
    keyboard.add(KeyboardButton('Список гарантов'))
    keyboard.add(KeyboardButton('Команды бота'))
    return keyboard

def create_inline_keyboard_profile(role, user_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton('Слить скамера', url='https://t.me/antiscambaseAS')
    )
    
    # Вечная ссылка на профиль
    if role != 'user':
        keyboard.add(
            InlineKeyboardButton('Вечная ссылка', url=f'tg://user?id={user_id}')
        )
    
    return keyboard

def create_inline_keyboard_check(user_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton('💍', callback_data=f'like_{user_id}'),
        InlineKeyboardButton('💔', callback_data=f'dislike_{user_id}')
    )
    return keyboard

# Обработчики команд
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """
Anti Scam - начинающий проект, который будет помогать людям не попадатся на скам и на сомнительные услуги.

⚠️В нашей предложке вы - можете слить скамера или же сообщить о подозрительной личности.

🔍Чат поиска гарантов| трейдов | просто общения - @AntiScamChata

🛡Наш бот для проверки на скам - @AntilScamBot.

✔️Если хотите нас поддержать, то ставьте в ник приписку 'As |  Ас'
    """
    
    # Отправляем фото с приветствием
    try:
        bot.send_photo(
            message.chat.id,
            'AgACAgIAAxkBAAMDaV5adx8Oy37acG9cGOEgHbYhv2wAAiMOaxuQvvlKqFGS2DnsF9YBAAMCAANzAAM4BA',
            caption=welcome_text,
            reply_markup=create_main_keyboard()
        )
        
        # Создаем инлайн кнопки под сообщением
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton('Слить скамера', url='https://t.me/antiscambaseAS'),
            InlineKeyboardButton('Новостной канал', url='https://t.me/AntiScamLaboratory')
        )
        
        bot.send_message(
            message.chat.id,
            'Выберите действие:',
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error sending welcome: {e}")
        bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda message: message.text == 'Мой профиль')
def my_profile(message):
    user_id = message.from_user.id
    username = message.from_user.username or 'Нет username'
    role = get_user_role(user_id)
    
    # Увеличиваем счетчик поисков
    increment_search_count(user_id, username)
    search_count = get_search_count(user_id)
    
    # Текущее время
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    # Определяем фото и текст в зависимости от роли
    if role == 'scammer':
        photo_id = 'AgACAgIAAxkBAAMTaV5df-wUhpGbu_aqFH6_Smuu2zMAAkEOaxuQvvlKUCFRzR1AGyYBAAMCAAN5AAM4BA'
        caption = f"""
🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
📍обнᴀᴩужᴇн ᴄᴋᴀʍᴇᴩ

ʙᴄᴇ ᴨᴩуɸы нᴀ ᴄᴋᴀʍ ⬇️
(пруфы на скам)

ᴨоᴧьзоʙᴀᴛᴇᴧь ᴄ ᴨᴧохой ᴩᴇᴨуᴛᴀциᴇй❌
дᴧя ʙᴀɯᴇй жᴇ бᴇзоᴨᴀᴄноᴄᴛи ᴧучɯᴇ зᴀбᴧоᴋиᴩоʙᴀᴛь ᴇᴦо✅

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
"""
    
    elif role == 'garant':
        photo_id = 'AgACAgIAAxkBAAMZaV5d0ng4BuFtTjmwQbwAAYBsHktuAAJFDmsbkL75Ssa18PFEpyhEAQADAgADeQADOAQ'
        # Получаем информацию о гаранте из БД
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT info_link, proofs_link FROM garanty WHERE user_id = ?', (user_id,))
        garant_info = cursor.fetchone()
        conn.close()
        
        info_link = garant_info[0] if garant_info else "Не указано"
        proofs_link = garant_info[1] if garant_info else "Не указано"
        
        caption = f"""
🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя ᴦᴀᴩᴀнᴛоʍ бᴀзы

ᴇᴦо [ᴇᴇ] инɸо: {info_link}
ᴇᴦо [ᴇᴇ] ᴨᴩуɸы: {proofs_link}

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
"""
    
    elif role == 'admin':
        photo_id = 'AgACAgIAAxkBAAMVaV5dle8QkMo02yTdfGKefimIAAEDAAJEDmsbkL75StvZ04a4hKQJAQADAgADeQADOAQ'
        scammers_added = get_scammers_count(user_id)
        
        caption = f"""
🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя администратором бᴀзы

Добавленно скамеров - {scammers_added}

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}
🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
"""
    
    else:  # обычный пользователь
        photo_id = 'AgACAgIAAxkBAAMbaV5d5EjzLoxlESB0a3aRaO9ENrAAAkgOaxuQvvlKzGwdJxbnZlsBAAMCAAN5AAM4BA'
        caption = f"""
🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
✅ обычный ᴨоᴧьзоʙᴀᴛᴇᴧь ✅

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}
 
🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
"""
    
    try:
        bot.send_photo(
            message.chat.id,
            photo_id,
            caption=caption,
            reply_markup=create_inline_keyboard_profile(role, user_id)
        )
    except Exception as e:
        logger.error(f"Error sending profile: {e}")
        bot.send_message(message.chat.id, caption, reply_markup=create_inline_keyboard_profile(role, user_id))

@bot.message_handler(func=lambda message: message.text == 'Список гарантов')
def list_garants(message):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, proofs_link FROM garanty')
    garants = cursor.fetchall()
    conn.close()
    
    if not garants:
        bot.send_message(message.chat.id, "Список гарантов пуст.")
        return
    
    response = "📋 Список гарантов:\n\n"
    for i, (username, proofs_link) in enumerate(garants, 1):
        response += f"{i}. @{username}\n"
        response += f"   Пруфы: {proofs_link}\n\n"
    
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == 'Команды бота')
def bot_commands(message):
    commands_text = """
🤖 Доступные команды бота:

🔍 Проверка пользователей:
/check @username - Проверить пользователя
/check (в ответ на сообщение) - Проверить пользователя
/check me - Проверить себя

⚠️ Обратите внимание: 
Команды для администрации не отображаются в публичном списке.
Администраторы имеют специальные права через панель управления.
    """
    
    bot.send_message(message.chat.id, commands_text)

# Команда проверки пользователя
@bot.message_handler(commands=['check'])
def check_user(message):
    args = message.text.split()
    
    if len(args) == 1 and not message.reply_to_message:
        bot.send_message(message.chat.id, "Использование:\n/check @username\n/check me\nИли ответьте на сообщение с /check")
        return
    
    user_to_check = None
    
    if len(args) == 2 and args[1].lower() == 'me':
        user_to_check = message.from_user
    
    elif len(args) == 2 and args[1].startswith('@'):
        username = args[1][1:]
        # Здесь должна быть логика получения пользователя по username
        # Для примера используем текущего пользователя
        user_to_check = message.from_user
    
    elif message.reply_to_message:
        user_to_check = message.reply_to_message.from_user
    
    if user_to_check:
        user_id = user_to_check.id
        username = user_to_check.username or 'Нет username'
        role = get_user_role(user_id)
        
        # Увеличиваем счетчик поисков
        increment_search_count(user_id, username)
        search_count = get_search_count(user_id)
        
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        # Создаем текст результата проверки
        if role == 'scammer':
            result_text = f"""
📍 Результат проверки:

Пользователь: @{username}
ID: {user_id}
Статус: ⚠️ СКАМЕР ⚠️

🔍 Проверок: {search_count}
⏰ Время проверки: {current_time}

Рекомендуется избегать взаимодействия с данным пользователем!
"""
        elif role == 'garant':
            result_text = f"""
📍 Результат проверки:

Пользователь: @{username}
ID: {user_id}
Статус: ✅ ГАРАНТ ✅

🔍 Проверок: {search_count}
⏰ Время проверки: {current_time}

Данный пользователь имеет статус гаранта.
"""
        elif role == 'admin':
            result_text = f"""
📍 Результат проверки:

Пользователь: @{username}
ID: {user_id}
Статус: 👑 АДМИНИСТРАТОР 👑

🔍 Проверок: {search_count}
⏰ Время проверки: {current_time}

Данный пользователь является администратором базы.
"""
        else:
            result_text = f"""
📍 Результат проверки:

Пользователь: @{username}
ID: {user_id}
Статус: 👤 ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ 👤

🔍 Проверок: {search_count}
⏰ Время проверки: {current_time}

Нарушений не обнаружено.
"""
        
        bot.send_message(
            message.chat.id,
            result_text,
            reply_markup=create_inline_keyboard_check(user_id)
        )

# Команды для администрации (только для админов)
@bot.message_handler(commands=['add_scammer'])
def add_scammer(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды.")
        return
    
    args = message.text.split(maxsplit=3)
    if len(args) < 4:
        bot.send_message(message.chat.id, "Использование: /add_scammer @username причина пруфы")
        return
    
    username = args[1][1:] if args[1].startswith('@') else args[1]
    reason = args[2]
    proofs = args[3] if len(args) > 3 else "Не указаны"
    
    # Получаем ID пользователя по username (упрощенная версия)
    # В реальном боте нужно использовать API Telegram для получения ID
    user_id = hash(username) % 1000000  # Временное решение
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO scammers (user_id, username, reason, proofs, added_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, reason, proofs, message.from_user.id))
        
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Скамер @{username} добавлен в базу.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()

@bot.message_handler(commands=['add_admin'])
def add_admin_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Только владелец бота может добавлять администраторов.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(message.chat.id, "Использование: /add_admin @username")
        return
    
    username = args[1][1:] if args[1].startswith('@') else args[1]
    
    # Получаем ID пользователя (упрощенная версия)
    user_id = hash(username) % 1000000
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('INSERT OR IGNORE INTO admins (user_id, username, added_by) VALUES (?, ?, ?)', 
                      (user_id, username, message.from_user.id))
        
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Администратор @{username} добавлен.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()

# Просмотр ID фото (только для админов)
@bot.message_handler(content_types=['photo'])
def get_photo_id(message):
    if is_admin(message.from_user.id):
        photo_id = message.photo[-1].file_id
        bot.send_message(message.chat.id, f"🖼 ID фото: {photo_id}")
    else:
        # Игнорируем фото от обычных пользователей
        pass

# Обработчик инлайн кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data.startswith('like_'):
        user_id = call.data.split('_')[1]
        bot.answer_callback_query(call.id, "❤️ Ваш голос учтен!")
        
    elif call.data.startswith('dislike_'):
        user_id = call.data.split('_')[1]
        bot.answer_callback_query(call.id, "💔 Ваш голос учтен!")

# Flask маршруты для вебхука
@app.route('/')
def index():
    return 'Bot is running!'

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Bad request', 400

# Запуск вебхука
def set_webhook():
    time.sleep(1)
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL + '/webhook')
    logger.info("Webhook set to: " + WEBHOOK_URL + '/webhook')

if __name__ == '__main__':
    # Запускаем установку вебхука в отдельном потоке
    threading.Thread(target=set_webhook).start()
    
    # Запускаем Flask сервер
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
