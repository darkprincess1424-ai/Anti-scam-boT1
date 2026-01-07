from flask import Flask, request, jsonify
import logging
import requests
import json
from datetime import datetime
import os
import sqlite3
from functools import wraps
import time

app = Flask(__name__)

# =============== НАСТРОЙКИ БОТА ===============
# Получаем токен из переменных окружения Render (Environment Variables)
# В Render Dashboard добавьте переменную BOT_TOKEN со значением вашего токена
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ Токен бота не найден! Добавьте переменную BOT_TOKEN в Environment Variables на Render")

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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Декоратор для проверки администратора
def admin_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = message['from']['id']
        if user_id != ADMIN_ID:
            send_message(message['chat']['id'], "⛔ У вас нет прав администратора!")
            return None
        return func(message, *args, **kwargs)
    return wrapper

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
    
    # Таблица мутов в группах
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_mutes (
            chat_id INTEGER,
            user_id INTEGER,
            until_timestamp INTEGER,
            reason TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    
    # Таблица варнов в группах
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_warns (
            warn_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            admin_id INTEGER,
            reason TEXT,
            warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица статусов чатов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_status (
            chat_id INTEGER PRIMARY KEY,
            is_open BOOLEAN DEFAULT 1,
            title TEXT
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

def get_user_by_username(username):
    """Найти пользователя по username в базе"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name FROM users WHERE username = ?', (username,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'user_id': result[0],
            'username': result[1],
            'first_name': result[2]
        }
    return None

def add_scammer(scammer_id, username, reason, proof_link, added_by):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''INSERT OR REPLACE INTO scammers 
                     (scammer_id, username, reason, proof_link, added_by) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (scammer_id, username, reason, proof_link, added_by))
    
    cursor.execute('''INSERT OR REPLACE INTO users (user_id, username, status) 
                     VALUES (?, ?, ?)''', (scammer_id, username, 'scammer'))
    
    cursor.execute('UPDATE users SET added_scammers = added_scammers + 1 WHERE user_id = ?',
                  (added_by,))
    
    conn.commit()
    conn.close()
    return True

def remove_scammer(scammer_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM scammers WHERE scammer_id = ?', (scammer_id,))
    cursor.execute('UPDATE users SET status = "user" WHERE user_id = ?', (scammer_id,))
    
    conn.commit()
    conn.close()
    return True

def add_garant(garant_id, username, proof_link, info_link, added_by):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''INSERT OR REPLACE INTO garants 
                     (garant_id, username, proof_link, info_link, added_by) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (garant_id, username, proof_link, info_link, added_by))
    
    cursor.execute('''INSERT OR REPLACE INTO users (user_id, username, status) 
                     VALUES (?, ?, ?)''', (garant_id, username, 'garant'))
    
    conn.commit()
    conn.close()
    return True

def remove_garant(garant_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM garants WHERE garant_id = ?', (garant_id,))
    cursor.execute('UPDATE users SET status = "user" WHERE user_id = ?', (garant_id,))
    
    conn.commit()
    conn.close()
    return True

def add_admin(admin_id, username, added_by):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('INSERT OR REPLACE INTO admins (admin_id, username, added_by) VALUES (?, ?, ?)',
                  (admin_id, username, added_by))
    
    cursor.execute('UPDATE users SET status = "admin" WHERE user_id = ?', (admin_id,))
    
    conn.commit()
    conn.close()
    return True

def remove_admin(admin_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM admins WHERE admin_id = ?', (admin_id,))
    cursor.execute('UPDATE users SET status = "user" WHERE user_id = ?', (admin_id,))
    
    conn.commit()
    conn.close()
    return True

def get_all_garants():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, proof_link FROM garants ORDER BY username')
    results = cursor.fetchall()
    conn.close()
    return results

def get_all_admins():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM admins ORDER BY username')
    results = cursor.fetchall()
    conn.close()
    return [r[0] for r in results]

def get_scammer_info(user_id):
    """Получить информацию о скамере"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT reason, proof_link FROM scammers WHERE scammer_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'reason': result[0],
            'proof_link': result[1]
        }
    return None

def get_garant_info(user_id):
    """Получить информацию о гаранте"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT proof_link, info_link FROM garants WHERE garant_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'proof_link': result[0],
            'info_link': result[1]
        }
    return None

# Функции для работы с группами
def set_group_status(chat_id, is_open, title=None):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    if title:
        cursor.execute('''INSERT OR REPLACE INTO group_status (chat_id, is_open, title) 
                         VALUES (?, ?, ?)''', (chat_id, is_open, title))
    else:
        cursor.execute('''INSERT OR REPLACE INTO group_status (chat_id, is_open) 
                         VALUES (?, ?)''', (chat_id, is_open))
    
    conn.commit()
    conn.close()

def get_group_status(chat_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_open FROM group_status WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else True  # По умолчанию чат открыт

# Функции для работы с Telegram API
def send_message(chat_id, text, parse_mode='HTML', reply_markup=None, photo=None):
    try:
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
        
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        return {'ok': False}

def get_user_id_by_username(username):
    """Получить ID пользователя по username (упрощенная версия)"""
    # В реальном боте нужно использовать другие методы
    # Здесь возвращаем случайный ID для примера
    return hash(username) % 1000000000

# Клавиатуры с эмодзи 🎉
def get_main_keyboard():
    keyboard = {
        'keyboard': [
            [{'text': '👤 Мой профиль'}],
            [{'text': '📋 Список гарантов'}, {'text': '⚙️ Команды бота'}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': False
    }
    return keyboard

def get_inline_keyboard_for_welcome():
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '🚨 Слить скамера', 'url': 'https://t.me/antiscambaseAS'},
                {'text': '📢 Новостной канал', 'url': 'https://t.me/AntiScamLaboratory'}
            ]
        ]
    }
    return keyboard

def get_inline_keyboard_for_profile(username):
    if not username:
        username = ""
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '🚨 Слить скамера', 'url': 'https://t.me/antiscambaseAS'},
                {'text': '🔗 Вечная ссылка', 'url': f'https://t.me/{username}' if username else 'https://t.me'}
            ]
        ]
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
    
    send_message(chat_id, "🎯 Выберите действие:", 
                 reply_markup=get_main_keyboard())

def check_user_profile(user_id, username, first_name=None, check_self=False):
    """Проверить профиль пользователя (общая функция для проверки)"""
    
    # Регистрируем пользователя если его нет
    if not get_user_info(user_id):
        register_user(user_id, username, first_name or "")
    
    status = get_user_status(user_id)
    
    # Увеличиваем счетчик проверок если проверяем не себя
    if not check_self:
        increment_search_count(user_id)
    
    user_info = get_user_info(user_id)
    search_count = user_info['search_count'] if user_info else 1
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    if status == 'scammer':
        photo_id = PHOTOS['scammer']
        scammer_info = get_scammer_info(user_id)
        proofs = scammer_info['proof_link'] if scammer_info else "(пруфы на скам)"
        
        text = f"""
🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
📍обнᴀᴩужᴇн ᴄᴋᴀʍᴇᴩ

ʙᴄᴇ ᴨᴩуɸы нᴀ ᴄᴋᴀʍ ⬇️
{proofs}

ᴨоᴧьзоʙᴀᴛᴇᴧь ᴄ ᴨᴧохой ᴩᴇᴨуᴛᴀциᴇй❌
дᴧя ʙᴀɯᴇй жᴇ бᴇзоᴨᴀᴄноᴄᴛи ᴧучɯᴇ зᴀбᴧоᴋиᴩоʙᴀᴛь ᴇᴦо✅

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
        """
        
    elif status == 'garant':
        photo_id = PHOTOS['garant']
        garant_info = get_garant_info(user_id)
        info_link = garant_info['info_link'] if garant_info and garant_info['info_link'] else "(ссылка на инфа)"
        proof_link = garant_info['proof_link'] if garant_info and garant_info['proof_link'] else "(ссылка на пруфы)"
        
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
    
    return text, photo_id

def handle_my_profile(message):
    user_id = message['from']['id']
    username = message['from'].get('username', '')
    
    text, photo_id = check_user_profile(user_id, username, check_self=True)
    
    send_message(message['chat']['id'], text, 
                 photo=photo_id,
                 reply_markup=get_inline_keyboard_for_profile(username))

def handle_check_user(message, target_user_id=None, target_username=None):
    """Проверить другого пользователя"""
    chat_id = message['chat']['id']
    checker_id = message['from']['id']
    
    if target_user_id and target_username:
        # Проверка по ID и username
        text, photo_id = check_user_profile(target_user_id, target_username)
        
        # Отправляем результат проверки
        send_message(chat_id, text, 
                     photo=photo_id,
                     reply_markup=get_inline_keyboard_for_profile(target_username))
        
        # Отправляем уведомление проверяющему
        checker_username = message['from'].get('username', 'пользователь')
        send_message(checker_id, f"✅ Вы проверили пользователя @{target_username}")
        
    else:
        send_message(chat_id, "❌ Не удалось найти пользователя для проверки")

def handle_check_command(message):
    """Обработчик команды /check"""
    chat_id = message['chat']['id']
    text = message.get('text', '')
    
    # Проверка самого себя
    if text == '/check me' or text == '/check':
        handle_my_profile(message)
        return
    
    # Проверка по username в команде
    if text.startswith('/check @'):
        parts = text.split()
        if len(parts) >= 2:
            username = parts[1].replace('@', '')
            
            # Ищем пользователя в базе
            user_info = get_user_by_username(username)
            if user_info:
                handle_check_user(message, user_info['user_id'], username)
            else:
                # Если пользователя нет в базе, создаем временную запись
                temp_user_id = get_user_id_by_username(username)
                text, photo_id = check_user_profile(temp_user_id, username)
                
                send_message(chat_id, text, 
                           photo=photo_id,
                           reply_markup=get_inline_keyboard_for_profile(username))
        else:
            send_message(chat_id, "❌ Использование: /check @username или /check me")
        return
    
    # Если команда просто /check без параметров
    send_message(chat_id, "ℹ️ Использование:\n/check me - проверить себя\n/check @username - проверить другого пользователя")

def handle_check_reply(message, reply_to_message):
    """Проверка в ответ на сообщение"""
    chat_id = message['chat']['id']
    
    if 'from' in reply_to_message:
        target_user_id = reply_to_message['from']['id']
        target_username = reply_to_message['from'].get('username', '')
        target_first_name = reply_to_message['from'].get('first_name', '')
        
        if not target_username:
            target_username = f"user_{target_user_id}"
        
        handle_check_user(message, target_user_id, target_username)
    else:
        send_message(chat_id, "❌ Не удалось получить информацию о пользователе")

def handle_garants_list(message):
    garants = get_all_garants()
    
    if not garants:
        text = "📭 Список гарантов пуст"
    else:
        text = "📋 Список гарантов:\n\n"
        for i, (username, proof_link) in enumerate(garants, 1):
            text += f"{i}. 👤 @{username}\n"
            text += f"   🔗 Пруфы: {proof_link}\n\n"
    
    send_message(message['chat']['id'], text)

def handle_admins_list(message):
    admins = get_all_admins()
    
    if not admins:
        text = "📭 Список администраторов пуст"
    else:
        text = "👑 Список администраторов:\n\n"
        for i, username in enumerate(admins, 1):
            text += f"{i}. 👑 @{username}\n"
    
    send_message(message['chat']['id'], text)

def handle_bot_commands(message):
    commands_text = """
🤖 Команды бота:

👤 Для всех:
/start - 🚀 Запустить бота
/check @username - 🔍 Проверить пользователя
/check me - 👤 Проверить себя
/check (в ответ на сообщение) - 🔍 Проверить автора сообщения

🛡 Для администраторов (ID: 8281804228):
/add_admin @username - 👑 Добавить администратора
/del_admin @username - ❌ Удалить администратора
/add_scammer @username [причина] [ссылка_на_пруфы] - 🚨 Добавить скамера
/del_scammer @username - ✅ Удалить скамера
/add_garant @username [ссылка_на_био] [ссылка_на_пруфы] - 🛡 Добавить гаранта
/del_garant @username - ❌ Удалить гаранта
/list_admins - 📋 Список администраторов

👮 Для админов чатов:
/open - 🔓 Открыть чат
/close - 🔒 Закрыть чат
/warn @username [причина] - ⚠️ Выдать предупреждение
/mut @username [время] - 🔇 Замутить пользователя

📸 Для получения ID фото:
Просто отправьте фото боту, и он покажет все ID
    """
    
    send_message(message['chat']['id'], commands_text)

# Админские команды
@admin_required
def handle_add_admin_command(message):
    chat_id = message['chat']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, "❌ Использование: /add_admin @username")
        return
    
    username = parts[1].replace('@', '')
    admin_id = get_user_id_by_username(username)
    
    if add_admin(admin_id, username, message['from']['id']):
        send_message(chat_id, f"✅ Администратор @{username} добавлен!")
    else:
        send_message(chat_id, f"❌ Ошибка при добавлении администратора")

@admin_required
def handle_del_admin_command(message):
    chat_id = message['chat']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, "❌ Использование: /del_admin @username")
        return
    
    username = parts[1].replace('@', '')
    admin_id = get_user_id_by_username(username)
    
    if remove_admin(admin_id):
        send_message(chat_id, f"✅ Администратор @{username} удален!")
    else:
        send_message(chat_id, f"❌ Ошибка при удалении администратора")

@admin_required
def handle_add_scammer_command(message):
    chat_id = message['chat']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 4:
        send_message(chat_id, "❌ Использование: /add_scammer @username причина ссылка_на_пруфы")
        return
    
    username = parts[1].replace('@', '')
    reason = parts[2]
    proof_link = parts[3]
    scammer_id = get_user_id_by_username(username)
    
    if add_scammer(scammer_id, username, reason, proof_link, message['from']['id']):
        send_message(chat_id, f"✅ Скамер @{username} добавлен в базу!")
    else:
        send_message(chat_id, f"❌ Ошибка при добавлении скамера")

@admin_required
def handle_del_scammer_command(message):
    chat_id = message['chat']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, "❌ Использование: /del_scammer @username")
        return
    
    username = parts[1].replace('@', '')
    scammer_id = get_user_id_by_username(username)
    
    if remove_scammer(scammer_id):
        send_message(chat_id, f"✅ Скамер @{username} удален из базы!")
    else:
        send_message(chat_id, f"❌ Ошибка при удалении скамера")

@admin_required
def handle_add_garant_command(message):
    chat_id = message['chat']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 4:
        send_message(chat_id, "❌ Использование: /add_garant @username ссылка_на_био ссылка_на_пруфы")
        return
    
    username = parts[1].replace('@', '')
    info_link = parts[2]
    proof_link = parts[3]
    garant_id = get_user_id_by_username(username)
    
    if add_garant(garant_id, username, proof_link, info_link, message['from']['id']):
        send_message(chat_id, f"✅ Гарант @{username} добавлен в базу!")
    else:
        send_message(chat_id, f"❌ Ошибка при добавлении гаранта")

@admin_required
def handle_del_garant_command(message):
    chat_id = message['chat']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, "❌ Использование: /del_garant @username")
        return
    
    username = parts[1].replace('@', '')
    garant_id = get_user_id_by_username(username)
    
    if remove_garant(garant_id):
        send_message(chat_id, f"✅ Гарант @{username} удален из базы!")
    else:
        send_message(chat_id, f"❌ Ошибка при удалении гаранта")

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

# Основной обработчик webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        if 'message' in update:
            message = update['message']
            text = message.get('text', '')
            
            # Проверка фото
            if 'photo' in message:
                handle_photo(message)
            
            # Проверка команды /check в ответ на сообщение
            elif text == '/check' and 'reply_to_message' in message:
                handle_check_reply(message, message['reply_to_message'])
            
            # Обработка других команд
            elif text == '/start':
                handle_start(message)
            elif text == '👤 Мой профиль':
                handle_my_profile(message)
            elif text == '📋 Список гарантов':
                handle_garants_list(message)
            elif text == '⚙️ Команды бота':
                handle_bot_commands(message)
            elif text.startswith('/check'):
                handle_check_command(message)
            elif text.startswith('/add_admin'):
                handle_add_admin_command(message)
            elif text.startswith('/del_admin'):
                handle_del_admin_command(message)
            elif text.startswith('/list_admins'):
                handle_admins_list(message)
            elif text.startswith('/add_scammer'):
                handle_add_scammer_command(message)
            elif text.startswith('/del_scammer'):
                handle_del_scammer_command(message)
            elif text.startswith('/add_garant'):
                handle_add_garant_command(message)
            elif text.startswith('/del_garant'):
                handle_del_garant_command(message)
            elif text.startswith('/open'):
                send_message(message['chat']['id'], "✅ Чат открыт! 🔓")
            elif text.startswith('/close'):
                send_message(message['chat']['id'], "🔒 Чат закрыт!")
            elif text.startswith('/warn'):
                send_message(message['chat']['id'], "⚠️ Варн выдан!")
            elif text.startswith('/mut'):
                send_message(message['chat']['id'], "🔇 Пользователь замучен!")
            elif text and not text.startswith('/'):
                send_message(message['chat']['id'], 
                            "ℹ️ Используйте кнопки или команды из меню '⚙️ Команды бота'")
        
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return jsonify({'ok': False}), 500

# Роут для проверки работы бота
@app.route('/')
def index():
    token_status = "✅ Установлен" if BOT_TOKEN and BOT_TOKEN != 'ВАШ_ТОКЕН_БОТА_ЗДЕСЬ' else "❌ НЕ УСТАНОВЛЕН"
    
    return f"""
    <h1>🤖 Anti Scam Bot</h1>
    <p>Бот работает на Render!</p>
    <p><strong>Статус:</strong> {token_status}</p>
    <p><strong>Webhook URL:</strong> https://anti-scam-bot1-1-omoy.onrender.com/webhook</p>
    <p><strong>Админ ID:</strong> {ADMIN_ID}</p>
    <hr>
    <h3>🎯 Инструкция по настройке:</h3>
    <ol>
        <li>В Render Dashboard перейдите в Environment Variables</li>
        <li>Добавьте переменную: <code>BOT_TOKEN = ваш_токен</code></li>
        <li>Перезапустите приложение</li>
        <li>Настройте webhook по ссылке:</li>
    </ol>
    <p><a href="https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url=https://anti-scam-bot1-1-omoy.onrender.com/webhook" target="_blank">
        🔗 Настроить Webhook
    </a></p>
    """

# Роут для настройки webhook
@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        # Получаем текущий домен
        domain = "https://anti-scam-bot1-1-omoy.onrender.com"
        webhook_url = f'{domain}/webhook'
        
        url = f'{TELEGRAM_API_URL}/setWebhook?url={webhook_url}'
        response = requests.get(url)
        
        result = response.json()
        if result.get('ok'):
            return f"""
            <h1>✅ Webhook установлен!</h1>
            <p><strong>URL:</strong> {webhook_url}</p>
            <p><strong>Статус:</strong> {result.get('description', 'Успешно')}</p>
            <p><a href="/">🏠 Вернуться на главную</a></p>
            """
        else:
            return f"""
            <h1>❌ Ошибка установки webhook</h1>
            <p><strong>Ошибка:</strong> {result.get('description', 'Неизвестная ошибка')}</p>
            <p><a href="/">🏠 Вернуться на главную</a></p>
            """
    except Exception as e:
        return f"""
        <h1>❌ Ошибка</h1>
        <p><strong>Ошибка:</strong> {e}</p>
        <p><a href="/">🏠 Вернуться на главную</a></p>
        """

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'bot': 'running', 'token_set': BOT_TOKEN != 'ВАШ_ТОКЕН_БОТА_ЗДЕСЬ'})

# Функция для автоматической настройки webhook при запуске
def setup_webhook():
    try:
        # Получаем домен из переменных окружения или используем текущий
        domain = os.environ.get('RENDER_EXTERNAL_URL', 'https://anti-scam-bot1-1-omoy.onrender.com')
        webhook_url = f'{domain}/webhook'
        
        logger.info(f"🎯 Настраиваю webhook на URL: {webhook_url}")
        
        url = f'{TELEGRAM_API_URL}/setWebhook?url={webhook_url}'
        response = requests.get(url)
        
        result = response.json()
        if result.get('ok'):
            logger.info(f"✅ Webhook успешно установлен: {result.get('description')}")
        else:
            logger.error(f"❌ Ошибка установки webhook: {result.get('description')}")
    except Exception as e:
        logger.error(f"❌ Ошибка при настройке webhook: {e}")

if __name__ == '__main__':
    # Инициализация базы данных
    init_db()
    
    logger.info("=" * 50)
    logger.info("🤖 Anti Scam Bot запускается...")
    logger.info(f"✅ Токен получен из переменных окружения")
    logger.info(f"✅ Webhook URL: https://anti-scam-bot1-1-omoy.onrender.com/webhook")
    logger.info(f"✅ Админ ID: {ADMIN_ID}")
    logger.info("=" * 50)
    
    # Автоматическая настройка webhook
    setup_webhook()
    
    # Запуск Flask сервера
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
