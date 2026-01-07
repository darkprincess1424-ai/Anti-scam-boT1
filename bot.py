from flask import Flask, request, jsonify
import logging
import requests
import json
from datetime import datetime
import os
import sqlite3
from functools import wraps

app = Flask(__name__)

# =============== НАСТРОЙКИ БОТА ===============
# ЗАМЕНИТЕ НИЖЕ НА ВАШ ТОКЕН!
BOT_TOKEN = 'ВАШ_ТОКЕН_БОТА_ЗДЕСЬ'
TELEGRAM_API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}'
ADMIN_ID = 8281804228  # Ваш ID для админ панели

# ID фото для разных статусов
PHOTOS = {
    'welcome': 'AgACAgIAAxkBAAMDaV5adx8Oy37acG9cGOEgHbYhv2wAAiMOaxuQvvlKqFGS2DnsF9YBAAMCAANzAAM4BA',
    'scammer': 'AgACAgIAAxkBAAMTaV5df-wUhpGbu_aqFH6_Smuu2zMAAkEOaxuQvvlKUCFRzR1AGyYBAAMCAAN5AAM4BA',
    'garant': 'AgACAgIAAxkBAAMZaV5d0ng4BuFtTjmwQbwAAYBsHktuAAJFDmsbkL75Ssa18PFEpyhEAQADAgADeQADOAQ',
    'user': 'AgACAgIAAxkBAAMbaV5d5EjzLoxlESB0a3aRaO9ENrAAAkgOaxuQvvlKzGwdJxbnZlsBAAMCAAN5AAM4BA',
    'admin': 'AgACAgIAAxkBAAMVaV5dle8QkMo02yTdfGKefimIAAEDAAJEDmsbkL75StvZ04a4hKQJAQADAgADeQADOAQ'
}

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            status TEXT DEFAULT 'user',
            search_count INTEGER DEFAULT 0,
            added_scammers INTEGER DEFAULT 0,
            proof_link TEXT,
            info_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица скамеров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scammers (
            scammer_id INTEGER PRIMARY KEY,
            username TEXT,
            reason TEXT,
            proof_link TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица гарантов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS garants (
            garant_id INTEGER PRIMARY KEY,
            username TEXT,
            proof_link TEXT,
            info_link TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица админов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY,
            username TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица проверок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checks (
            check_id INTEGER PRIMARY KEY AUTOINCREMENT,
            checker_id INTEGER,
            checked_id INTEGER,
            check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Добавляем администратора по умолчанию
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, status) VALUES (?, ?, ?)', 
                  (ADMIN_ID, 'admin', 'admin'))
    cursor.execute('INSERT OR IGNORE INTO admins (admin_id, username, added_by) VALUES (?, ?, ?)',
                  (ADMIN_ID, 'admin', ADMIN_ID))
    
    conn.commit()
    conn.close()

# Функции для работы с базой данных
def get_user_status(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'user'

def get_user_info(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT username, status, search_count, added_scammers, 
                     proof_link, info_link FROM users WHERE user_id = ?''', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'username': result[0],
            'status': result[1],
            'search_count': result[2],
            'added_scammers': result[3],
            'proof_link': result[4],
            'info_link': result[5]
        }
    return None

def register_user(user_id, username, first_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
                  (user_id, username, first_name))
    conn.commit()
    conn.close()

def increment_search_count(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET search_count = search_count + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def add_scammer(scammer_id, username, reason, proof_link, added_by):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''INSERT OR REPLACE INTO scammers 
                     (scammer_id, username, reason, proof_link, added_by) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (scammer_id, username, reason, proof_link, added_by))
    
    cursor.execute('INSERT OR REPLACE INTO users (user_id, username, status) VALUES (?, ?, ?)',
                  (scammer_id, username, 'scammer'))
    
    cursor.execute('UPDATE users SET added_scammers = added_scammers + 1 WHERE user_id = ?',
                  (added_by,))
    
    conn.commit()
    conn.close()

def add_garant(garant_id, username, proof_link, info_link, added_by):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''INSERT OR REPLACE INTO garants 
                     (garant_id, username, proof_link, info_link, added_by) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (garant_id, username, proof_link, info_link, added_by))
    
    cursor.execute('INSERT OR REPLACE INTO users (user_id, username, status) VALUES (?, ?, ?)',
                  (garant_id, username, 'garant'))
    
    conn.commit()
    conn.close()

def get_all_garants():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, proof_link FROM garants ORDER BY username')
    results = cursor.fetchall()
    conn.close()
    return results

# Функции для работы с Telegram API
def send_message(chat_id, text, parse_mode='HTML', reply_markup=None, photo=None):
    if photo:
        url = f'{TELEGRAM_API_URL}/sendPhoto'
        data = {
            'chat_id': chat_id,
            'photo': photo,
            'caption': text,
            'parse_mode': parse_mode
        }
    else:
        url = f'{TELEGRAM_API_URL}/sendMessage'
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
    
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    
    response = requests.post(url, json=data)
    return response.json()

def answer_callback_query(callback_query_id, text):
    url = f'{TELEGRAM_API_URL}/answerCallbackQuery'
    data = {
        'callback_query_id': callback_query_id,
        'text': text
    }
    requests.post(url, json=data)

# Клавиатуры
def get_main_keyboard():
    keyboard = {
        'keyboard': [
            [{'text': 'Мой профиль'}],
            [{'text': 'Список гарантов'}, {'text': 'Команды бота'}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': False
    }
    return keyboard

def get_inline_keyboard_for_welcome():
    keyboard = {
        'inline_keyboard': [
            [
                {'text': 'Слить скамера', 'url': 'https://t.me/antiscambaseAS'},
                {'text': 'Новостной канал', 'url': 'https://t.me/AntiScamLaboratory'}
            ]
        ]
    }
    return keyboard

def get_inline_keyboard_for_profile(username):
    keyboard = {
        'inline_keyboard': [
            [
                {'text': 'Слить скамера', 'url': 'https://t.me/antiscambaseAS'},
                {'text': 'Вечная ссылка', 'url': f'https://t.me/{username}'}
            ]
        ]
    }
    return keyboard

def get_group_admin_keyboard():
    keyboard = {
        'keyboard': [
            [{'text': '/open'}, {'text': '/close'}],
            [{'text': '/warn'}, {'text': '/mut'}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': False
    }
    return keyboard

# Обработчики команд
def handle_start(message):
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    username = message['from'].get('username', '')
    first_name = message['from'].get('first_name', '')
    
    register_user(user_id, username, first_name)
    
    welcome_text = """
Anti Scam - начинающий проект, который будет помогать людям не попадатся на скам и на сомнительные услуги.

⚠️В нашей предложке вы - можете слить скамера или же сообщить о подозрительной личности.

🔍Чат поиска гарантов| трейдов | просто общения - @AntiScamChata

🛡Наш бот для проверки на скам - @AntilScamBot.

✔️Если хотите нас поддержать, то ставьте в ник приписку 'As | Ас'
    """
    
    send_message(chat_id, welcome_text, 
                 photo=PHOTOS['welcome'],
                 reply_markup=get_inline_keyboard_for_welcome())
    
    send_message(chat_id, "Выберите действие:", 
                 reply_markup=get_main_keyboard())

def handle_my_profile(message):
    user_id = message['from']['id']
    username = message['from'].get('username', '')
    
    status = get_user_status(user_id)
    increment_search_count(user_id)
    
    user_info = get_user_info(user_id)
    search_count = user_info['search_count'] if user_info else 1
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    if status == 'scammer':
        photo_id = PHOTOS['scammer']
        text = f"""
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
        
    elif status == 'garant':
        photo_id = PHOTOS['garant']
        info_link = user_info['info_link'] if user_info and user_info['info_link'] else "(ссылка на инфа)"
        proof_link = user_info['proof_link'] if user_info and user_info['proof_link'] else "(ссылка на пруфы)"
        
        text = f"""
🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя ᴦᴀᴩᴀнᴛоʍ бᴀзы

ᴇᴦо [ᴇᴇ] инɸо: {info_link}
ᴇᴦо [ᴇᴇ] ᴨᴩуɸы: {proof_link}

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
        """
        
    elif status == 'admin':
        photo_id = PHOTOS['admin']
        added_scammers = user_info['added_scammers'] if user_info else 0
        
        text = f"""
🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя администратором бᴀзы

Добавленно скамеров - {added_scammers}

🔎ᴨоᴧьзоʙᴀᴛᴧя иᴄᴋᴀᴧи: {search_count}
🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
        """
        
    else:
        photo_id = PHOTOS['user']
        text = f"""
🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
✅ обычный ᴨоᴧьзоʙᴀᴛᴇᴧь ✅

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
        """
    
    send_message(message['chat']['id'], text, 
                 photo=photo_id,
                 reply_markup=get_inline_keyboard_for_profile(username))

def handle_garants_list(message):
    garants = get_all_garants()
    
    if not garants:
        text = "📭 Список гарантов пуст"
    else:
        text = "📋 Список гарантов:\n\n"
        for i, (username, proof_link) in enumerate(garants, 1):
            text += f"{i}. @{username}\n"
            text += f"   🔗 Пруфы: {proof_link}\n\n"
    
    send_message(message['chat']['id'], text)

def handle_bot_commands(message):
    commands_text = """
🤖 Команды бота:

👤 Для всех:
/start - Запустить бота
/check @username - Проверить пользователя
/check me - Проверить себя

🛡 Для гарантов:
/add_garant @username [ссылка_на_био] [ссылка_на_пруфы] - Добавить гаранта
/del_garant @username - Удалить гаранта

⚡ Для администраторов:
/add_admin @username - Добавить администратора
/add_scammer @username [причина] [ссылка_на_пруфы] - Добавить скамера
/del_scammer @username - Удалить скамера

👮 Для админов чатов:
/open - Открыть чат
/close - Закрыть чат
/warn @username [причина] - Выдать предупреждение
/mut @username [время] - Замутить пользователя

📸 Для получения ID фото:
Просто отправьте фото боту, и он покажет все ID
    """
    
    send_message(message['chat']['id'], commands_text)

def handle_check_command(message):
    chat_id = message['chat']['id']
    text = message.get('text', '')
    
    if text == '/check me':
        handle_my_profile(message)
        return
    
    parts = text.split()
    if len(parts) < 2:
        send_message(chat_id, "❌ Использование: /check @username или /check me")
        return
    
    send_message(chat_id, "ℹ️ Функция проверки других пользователей в разработке")

def handle_add_scammer(message):
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    
    if user_id != ADMIN_ID:
        send_message(chat_id, "⛔ У вас нет прав администратора!")
        return
    
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 4:
        send_message(chat_id, "❌ Использование: /add_scammer @username причина ссылка_на_пруфы")
        return
    
    send_message(chat_id, "✅ Скамер добавлен в базу (функция в разработке)")

def handle_add_garant(message):
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    
    if user_id != ADMIN_ID:
        send_message(chat_id, "⛔ У вас нет прав администратора!")
        return
    
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 4:
        send_message(chat_id, "❌ Использование: /add_garant @username ссылка_на_био ссылка_на_пруфы")
        return
    
    send_message(chat_id, "✅ Гарант добавлен в базу (функция в разработке)")

def handle_photo(message):
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    
    if 'photo' in message:
        photos = message['photo']
        
        response_text = "📸 Информация о фотографии:\n\n"
        response_text += f"👤 Отправитель: {message['from'].get('first_name', 'User')}\n"
        
        if 'caption' in message:
            response_text += f"📝 Подпись: {message['caption']}\n\n"
        
        response_text += "Размеры фотографии:\n"
        
        for i, photo in enumerate(photos, 1):
            response_text += f"\n{i}. Размер {photo['width']}×{photo['height']}:\n"
            response_text += f"   📁 ID файла: {photo['file_id']}\n"
            response_text += f"   📦 Размер файла: {photo.get('file_size', 'N/A')} байт\n"
        
        send_message(chat_id, response_text)
        
        with open('photo_ids.txt', 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Пользователь: {message['from'].get('first_name', 'Unknown')} (ID: {user_id})\n")
            for photo in photos:
                f.write(f"Photo ID: {photo['file_id']}\n")
            f.write(f"{'='*50}\n")

# Основной обработчик
@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    
    if 'message' in update:
        message = update['message']
        text = message.get('text', '')
        
        if 'photo' in message:
            handle_photo(message)
        elif text == '/start':
            handle_start(message)
        elif text == 'Мой профиль':
            handle_my_profile(message)
        elif text == 'Список гарантов':
            handle_garants_list(message)
        elif text == 'Команды бота':
            handle_bot_commands(message)
        elif text.startswith('/check'):
            handle_check_command(message)
        elif text.startswith('/add_scammer'):
            handle_add_scammer(message)
        elif text.startswith('/add_garant'):
            handle_add_garant(message)
        elif text.startswith('/add_admin'):
            send_message(message['chat']['id'], "ℹ️ Команда в разработке")
        else:
            send_message(message['chat']['id'], 
                        "ℹ️ Используйте кнопки или команды из меню 'Команды бота'")
    
    return jsonify({'ok': True})

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    webhook_url = 'https://ваш-домен.ру/webhook'
    url = f'{TELEGRAM_API_URL}/setWebhook?url={webhook_url}'
    response = requests.get(url)
    return jsonify(response.json())

@app.route('/')
def index():
    return """
    <h1>🤖 Anti Scam Bot</h1>
    <p>Бот работает! Замените BOT_TOKEN на ваш токен в коде.</p>
    <p>Инструкция:</p>
    <ol>
        <li>Замените 'ВАШ_ТОКЕН_БОТА_ЗДЕСЬ' на ваш токен</li>
        <li>Настройте webhook URL на ваш домен</li>
        <li>Перезапустите приложение</li>
    </ol>
    """

if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("🤖 Anti Scam Bot готов к запуску!")
    print("⚠️  ЗАМЕНИТЕ BOT_TOKEN НА ВАШ ТОКЕН!")
    print("=" * 50)
    app.run(debug=True, port=5000)
