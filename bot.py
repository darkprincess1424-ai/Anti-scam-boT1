import os
import logging
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import threading
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = 8281804428  # Ваш ID админа
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')

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

def is_admin(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result

def get_scammers_count(admin_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM scammers WHERE added_by = ?', (admin_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

# Клавиатуры
def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton('👤 Мой профиль'),
        KeyboardButton('⭐ Список гарантов'),
        KeyboardButton('📋 Команды'),
        KeyboardButton('ℹ️ Информация о боте')
    )
    return keyboard

def create_inline_keyboard_profile(role, user_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton('Слить скамера', url='https://t.me/antiscambaseAS')
    )
    
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
    
    try:
        # Отправляем фото
        bot.send_photo(
            message.chat.id,
            'AgACAgIAAxkBAAMDaV5adx8Oy37acG9cGOEgHbYhv2wAAiMOaxuQvvlKqFGS2DnsF9YBAAMCAANzAAM4BA',
            caption=welcome_text,
            reply_markup=create_main_keyboard()
        )
        
        # Создаем инлайн кнопки
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

# Обработчики кнопок клавиатуры
@bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
def my_profile(message):
    user_id = message.from_user.id
    username = message.from_user.username or 'Нет username'
    role = get_user_role(user_id)
    
    increment_search_count(user_id, username)
    search_count = get_search_count(user_id)
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
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
    
    else:
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

@bot.message_handler(func=lambda message: message.text == '⭐ Список гарантов')
def list_garants(message):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, proofs_link FROM garanty')
    garants = cursor.fetchall()
    conn.close()
    
    if not garants:
        bot.send_message(message.chat.id, "📭 Список гарантов пуст.")
        return
    
    response = "⭐ <b>Список гарантов:</b>\n\n"
    for i, (username, proofs_link) in enumerate(garants, 1):
        response += f"{i}. @{username}\n"
        response += f"   🔗 Пруфы: {proofs_link}\n\n"
    
    bot.send_message(message.chat.id, response, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == '📋 Команды')
def bot_commands(message):
    commands_text = """
🤖 <b>Доступные команды бота:</b>

🔍 <b>Проверка пользователей:</b>
/check @username - Проверить пользователя
/check (в ответ на сообщение) - Проверить пользователя
/check me - Проверить себя

ℹ️ <b>Дополнительно:</b>
/start - Перезапустить бота
    """
    
    bot.send_message(message.chat.id, commands_text, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == 'ℹ️ Информация о боте')
def bot_info(message):
    info_text = """
ℹ️ <b>Информация о боте:</b>

🤖 <b>AntiScam Bot</b>
Версия: 1.0
Разработчик: AntiScam Team

⚙️ <b>Функционал:</b>
• Проверка пользователей на скам
• База данных скамеров
• Список проверенных гарантов
• Защита от мошенников

📞 <b>Связь:</b>
Чат: @AntiScamChata
Канал: @AntiScamLaboratory
    """
    
    bot.send_message(message.chat.id, info_text, parse_mode='HTML')

# Команда проверки пользователя
@bot.message_handler(commands=['check'])
def check_user(message):
    args = message.text.split()
    
    if len(args) == 1 and not message.reply_to_message:
        bot.send_message(message.chat.id, 
                        "❓ <b>Использование команды /check:</b>\n"
                        "/check @username - Проверить пользователя\n"
                        "/check me - Проверить себя\n"
                        "Или ответьте на сообщение с /check", 
                        parse_mode='HTML')
        return
    
    user_to_check = None
    check_type = "пользователь"
    
    if len(args) == 2 and args[1].lower() == 'me':
        user_to_check = message.from_user
        check_type = "себя"
    
    elif len(args) == 2 and args[1].startswith('@'):
        username = args[1][1:]
        # Здесь должна быть логика получения пользователя по username
        user_to_check = message.from_user  # Заглушка
        check_type = f"@{username}"
    
    elif message.reply_to_message:
        user_to_check = message.reply_to_message.from_user
        check_type = f"пользователя @{user_to_check.username or 'без username'}"
    
    if user_to_check:
        user_id = user_to_check.id
        username = user_to_check.username or 'Нет username'
        role = get_user_role(user_id)
        
        increment_search_count(user_id, username)
        search_count = get_search_count(user_id)
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        # Отправляем сообщение о начале проверки
        checking_msg = bot.send_message(message.chat.id, f"🔍 <b>Проверяю {check_type}...</b>", parse_mode='HTML')
        
        # Имитация проверки
        time.sleep(1)
        
        result_text = ""
        if role == 'scammer':
            result_text = f"""
🔴 <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

👤 Пользователь: @{username}
🆔 ID: {user_id}
⚠️ <b>СТАТУС: СКАМЕР</b>

📊 Проверок: {search_count}
🕒 Время проверки: {current_time}

🚨 <b>ВНИМАНИЕ!</b>
Данный пользователь находится в черном списке!
Рекомендуется избегать взаимодействия.
"""
        
        elif role == 'garant':
            result_text = f"""
🟢 <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

👤 Пользователь: @{username}
🆔 ID: {user_id}
✅ <b>СТАТУС: ГАРАНТ</b>

📊 Проверок: {search_count}
🕒 Время проверки: {current_time}

✅ Данный пользователь имеет статус гаранта.
Можно доверять при сделках.
"""
        
        elif role == 'admin':
            result_text = f"""
🔵 <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

👤 Пользователь: @{username}
🆔 ID: {user_id}
👑 <b>СТАТУС: АДМИНИСТРАТОР</b>

📊 Проверок: {search_count}
🕒 Время проверки: {current_time}

👑 Данный пользователь является администратором базы.
Имеет права на добавление скамеров.
"""
        
        else:
            result_text = f"""
🟡 <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

👤 Пользователь: @{username}
🆔 ID: {user_id}
👤 <b>СТАТУС: ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ</b>

📊 Проверок: {search_count}
🕒 Время проверки: {current_time}

✅ Нарушений не обнаружено.
Пользователь не находится в черных списках.
"""
        
        # Удаляем сообщение "Проверяю..."
        try:
            bot.delete_message(message.chat.id, checking_msg.message_id)
        except:
            pass
        
        bot.send_message(
            message.chat.id,
            result_text,
            parse_mode='HTML',
            reply_markup=create_inline_keyboard_check(user_id)
        )

# Просмотр ID фото (только для админов)
@bot.message_handler(content_types=['photo'])
def get_photo_id(message):
    if is_admin(message.from_user.id):
        photo_id = message.photo[-1].file_id
        file_info = bot.get_file(photo_id)
        file_path = file_info.file_path
        
        response = f"""
📸 <b>Информация о фото:</b>

🆔 <b>File ID:</b> <code>{photo_id}</code>
📁 <b>File Path:</b> {file_path}
📏 <b>Размеры:</b>
"""
        
        for i, photo in enumerate(message.photo):
            response += f"  • Размер {i+1}: {photo.width}x{photo.height}\n"
        
        bot.reply_to(message, response, parse_mode='HTML')
    else:
        # Для обычных пользователей просто игнорируем
        pass

# Обработчик инлайн кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data.startswith('like_'):
        user_id = call.data.split('_')[1]
        bot.answer_callback_query(call.id, "❤️ Ваш голос 'За' учтен!")
        
    elif call.data.startswith('dislike_'):
        user_id = call.data.split('_')[1]
        bot.answer_callback_query(call.id, "💔 Ваш голос 'Против' учтен!")

# Административные команды
@bot.message_handler(commands=['add_scammer'])
def add_scammer_command(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды.")
        return
    
    bot.send_message(message.chat.id, "⚠️ Команда в разработке")

# Flask маршруты
@app.route('/')
def index():
    return '🤖 AntiScam Bot is running!'

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Bad request', 400

# Настройка вебхука
@app.route('/setwebhook', methods=['GET'])
def set_webhook_route():
    if WEBHOOK_URL:
        bot.remove_webhook()
        time.sleep(1)
        webhook_url = f"{WEBHOOK_URL}/webhook"
        bot.set_webhook(url=webhook_url)
        return f"✅ Webhook set to: {webhook_url}"
    return "❌ WEBHOOK_URL not set"

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

if __name__ == '__main__':
    # Установка вебхука при запуске
    if WEBHOOK_URL:
        threading.Thread(target=lambda: (
            time.sleep(2),
            bot.remove_webhook(),
            time.sleep(1),
            bot.set_webhook(url=f"{WEBHOOK_URL}/webhook"),
            logger.info(f"Webhook set to: {WEBHOOK_URL}/webhook")
        )).start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
