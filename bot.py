from flask import Flask, request, jsonify
import logging
import requests
import json
from datetime import datetime
import os
import sqlite3
from functools import wraps
import time
import re

app = Flask(__name__)

# =============== НАСТРОЙКИ БОТА ===============
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ Токен бота не найден! Добавьте переменную BOT_TOKEN в Environment Variables на Render")

TELEGRAM_API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}'
ADMIN_ID = 8281804228  # Ваш ID

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

# =============== ГЛОБАЛЬНЫЙ КЭШ ДЛЯ СООТВЕТСТВИЙ ===============
# Храним соответствия username -> user_id
username_to_id_cache = {}

# =============== ФУНКЦИИ БАЗЫ ДАННЫХ ===============
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scammers (
            scammer_id INTEGER PRIMARY KEY,
            username TEXT,
            reason TEXT,
            proof_link TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (added_by) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS garants (
            garant_id INTEGER PRIMARY KEY,
            username TEXT,
            proof_link TEXT,
            info_link TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (added_by) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY,
            username TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (added_by) REFERENCES users(user_id)
        )
    ''')
    
    # Добавляем администратора по умолчанию
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, status) VALUES (?, ?, ?)', 
                  (ADMIN_ID, 'admin', 'admin'))
    cursor.execute('INSERT OR IGNORE INTO admins (admin_id, username, added_by) VALUES (?, ?, ?)',
                  (ADMIN_ID, 'admin', ADMIN_ID))
    
    conn.commit()
    conn.close()

# =============== ОСНОВНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ ===============
def get_user_status(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'user'

def is_admin(user_id):
    """Проверить, является ли пользователь администратором"""
    return get_user_status(user_id) == 'admin' or user_id == ADMIN_ID

def get_user_info(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT username, status, search_count, added_scammers, 
                     proof_link, info_link FROM users WHERE user_id = ?''', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'username': result[0] or f"user_{user_id}",
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
    
    # Проверяем, есть ли пользователь с таким username, но другим ID
    cursor.execute('SELECT user_id FROM users WHERE username = ? AND user_id != ?', (username, user_id))
    existing = cursor.fetchone()
    
    if existing and username and not username.startswith('user_'):
        # Если username уже занят другим ID, добавляем суффикс
        new_username = f"{username}_{user_id}"
        cursor.execute('INSERT OR REPLACE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
                      (user_id, new_username, first_name or "User"))
        username_to_id_cache[new_username] = user_id
    else:
        cursor.execute('INSERT OR REPLACE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
                      (user_id, username or f"user_{user_id}", first_name or "User"))
    
    # Сохраняем в кэше
    if username:
        username_to_id_cache[username] = user_id
    
    conn.commit()
    conn.close()

def get_user_id_by_username(username):
    """Получить ID пользователя по username из базы данных"""
    if not username:
        return None
    
    # Сначала проверяем кэш
    if username in username_to_id_cache:
        return username_to_id_cache[username]
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Ищем точное совпадение username
    cursor.execute('SELECT user_id FROM users WHERE username = ?', (username,))
    result = cursor.fetchone()
    
    if not result:
        # Ищем частичное совпадение (если username имеет суффикс _ID)
        cursor.execute('SELECT user_id FROM users WHERE username LIKE ?', (f"{username}_%",))
        result = cursor.fetchone()
    
    conn.close()
    
    if result:
        user_id = result[0]
        username_to_id_cache[username] = user_id
        return user_id
    
    return None

def increment_search_count(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET search_count = search_count + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def increment_added_scammers(user_id):
    """Увеличить счетчик добавленных скамеров"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET added_scammers = added_scammers + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# =============== ФУНКЦИИ ДЛЯ РАБОТЫ СО СКАМЕРАМИ ===============
def add_scammer(scammer_id, username, reason, proof_link, added_by):
    """Добавить скамера в базу данных"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Сначала убедимся, что пользователь существует
        cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
                      (scammer_id, username, "User"))
        
        # Добавляем в таблицу скамеров
        cursor.execute('''
            INSERT OR REPLACE INTO scammers (scammer_id, username, reason, proof_link, added_by) 
            VALUES (?, ?, ?, ?, ?)
        ''', (scammer_id, username, reason, proof_link, added_by))
        
        # Обновляем статус в таблице пользователей
        cursor.execute('UPDATE users SET status = ? WHERE user_id = ?', ('scammer', scammer_id))
        
        conn.commit()
        conn.close()
        
        # Увеличиваем счетчик добавленных скамеров
        increment_added_scammers(added_by)
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении скамера: {e}")
        return False

def remove_scammer(scammer_id):
    """Удалить скамера из базы данных"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Удаляем из таблицы скамеров
        cursor.execute('DELETE FROM scammers WHERE scammer_id = ?', (scammer_id,))
        
        # Возвращаем статус 'user' в таблице пользователей
        cursor.execute('UPDATE users SET status = ? WHERE user_id = ?', ('user', scammer_id))
        
        conn.commit()
        conn.close()
        
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка при удалении скамера: {e}")
        return False

def list_scammers(limit=50):
    """Получить список всех скамеров"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.scammer_id, s.username, s.reason, s.added_at, u.username as added_by_username
        FROM scammers s
        LEFT JOIN users u ON s.added_by = u.user_id
        ORDER BY s.added_at DESC
        LIMIT ?
    ''', (limit,))
    
    scammers = cursor.fetchall()
    conn.close()
    
    return scammers

# =============== ФУНКЦИИ ДЛЯ РАБОТЫ С АДМИНАМИ ===============
def add_admin_by_id(admin_id, added_by):
    """Добавить администратора по ID"""
    try:
        # Получаем информацию о пользователе
        username = get_username_by_id(admin_id)
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Сначала убедимся, что пользователь существует
        cursor.execute('INSERT OR REPLACE INTO users (user_id, username, first_name, status) VALUES (?, ?, ?, ?)',
                      (admin_id, username or f"user_{admin_id}", "User", 'admin'))
        
        # Добавляем в таблицу админов
        cursor.execute('INSERT OR REPLACE INTO admins (admin_id, username, added_by) VALUES (?, ?, ?)',
                      (admin_id, username or f"user_{admin_id}", added_by))
        
        conn.commit()
        conn.close()
        
        # Сохраняем в кэше
        if username:
            username_to_id_cache[username] = admin_id
        
        logger.info(f"Администратор добавлен: ID={admin_id}, username=@{username}, added_by={added_by}")
        return True, f"Пользователь @{username if username else f'user_{admin_id}'} (ID: {admin_id}) добавлен как администратор"
    except Exception as e:
        logger.error(f"Ошибка при добавлении администратора: {e}")
        return False, f"Ошибка при добавлении администратора: {str(e)}"

def remove_admin(admin_id):
    """Удалить администратора"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Удаляем из таблицы админов
        cursor.execute('DELETE FROM admins WHERE admin_id = ?', (admin_id,))
        
        # Меняем статус на 'user' в таблице пользователей (если не скамер и не гарант)
        cursor.execute('''
            UPDATE users 
            SET status = 'user' 
            WHERE user_id = ? 
            AND status = 'admin'
            AND user_id NOT IN (SELECT scammer_id FROM scammers)
            AND user_id NOT IN (SELECT garant_id FROM garants)
        ''', (admin_id,))
        
        conn.commit()
        conn.close()
        
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка при удалении администратора: {e}")
        return False

def list_admins():
    """Получить список всех администраторов"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.admin_id, a.username, a.added_at, u.username as added_by_username
        FROM admins a
        LEFT JOIN users u ON a.added_by = u.user_id
        ORDER BY a.added_at DESC
    ''')
    
    admins = cursor.fetchall()
    conn.close()
    
    return admins

def get_scammer_info(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT reason, proof_link FROM scammers WHERE scammer_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return {'reason': result[0], 'proof_link': result[1]} if result else None

def get_garant_info(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT proof_link, info_link FROM garants WHERE garant_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return {'proof_link': result[0], 'info_link': result[1]} if result else None

# =============== TELEGRAM API ФУНКЦИИ ===============
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
        result = response.json()
        
        if not result.get('ok'):
            logger.error(f"Ошибка отправки: {result.get('description')}")
        
        return result
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return {'ok': False}

def get_username_by_id(user_id):
    """Получить username пользователя по его ID"""
    try:
        # Сначала проверяем базу данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT username FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] and not result[0].startswith('user_'):
            return result[0].replace('@', '')
        
        # Если не нашли в базе, пробуем через Telegram API
        url = f'{TELEGRAM_API_URL}/getChat'
        data = {'chat_id': user_id}
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            user_data = result.get('result', {})
            username = user_data.get('username')
            return username
        else:
            return None
    except Exception as e:
        logger.error(f"Ошибка получения username для ID {user_id}: {e}")
        return None

# =============== ДЕКОРАТОР ПРОВЕРКИ АДМИНА ===============
def admin_required(func):
    """Декоратор для проверки прав администратора"""
    @wraps(func)
    def wrapper(message):
        user_id = message['from']['id']
        if user_id != ADMIN_ID and get_user_status(user_id) != 'admin':
            send_message(message['chat']['id'], "⛔ У вас нет прав администратора!")
            return None
        return func(message)
    return wrapper

# =============== ОСНОВНАЯ ФУНКЦИЯ ПРОВЕРКИ ===============
def check_user_profile(user_id, username, check_self=False):
    """Проверить профиль пользователя"""
    
    # Если передан username, пытаемся найти соответствующий ID
    if username and (user_id is None or user_id == 0):
        found_id = get_user_id_by_username(username)
        if found_id:
            user_id = found_id
            logger.info(f"Найден ID {user_id} для username @{username}")
        else:
            # Если не нашли, создаем временный ID для проверки
            user_id = hash(username) % 1000000000
            logger.info(f"Создан временный ID {user_id} для username @{username}")
    
    # Регистрируем пользователя если его нет
    if user_id and not get_user_info(user_id):
        register_user(user_id, username, "")
    
    status = get_user_status(user_id)
    
    # Увеличиваем счетчик проверок если проверяем не себя
    if not check_self and user_id:
        increment_search_count(user_id)
    
    user_info = get_user_info(user_id)
    search_count = user_info['search_count'] if user_info else 1
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    display_username = user_info['username'] if user_info else username
    
    # Логируем для отладки
    logger.info(f"Проверка: user_id={user_id}, username={username}, status={status}, display_username={display_username}")
    
    if status == 'scammer':
        photo_id = PHOTOS['scammer']
        scammer_info = get_scammer_info(user_id)
        proofs = scammer_info['proof_link'] if scammer_info else "(пруфы на скам)"
        
        text = f"""
🕵️ᴜsᴇʀ: @{display_username}
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
        info_link = garant_info['info_link'] if garant_info else "(ссылка на инфа)"
        proof_link = garant_info['proof_link'] if garant_info else "(ссылка на пруфы)"
        
        text = f"""
🕵️ᴜsᴇʀ: @{display_username}
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
🕵️ᴜsᴇʀ: @{display_username}
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
🕵️ᴜsᴇʀ: @{display_username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
✅ обычный ᴨоᴧьзоʙᴀᴛᴇᴧь ✅

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
        """
    
    return text, photo_id, display_username

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

# =============== ОБРАБОТЧИКИ КОМАНД ===============
def handle_my_profile(message):
    """Обработчик для кнопки '👤 Мой профиль' и команды '/check me'"""
    user_id = message['from']['id']
    username = message['from'].get('username', f"user_{user_id}")
    
    text, photo_id, display_username = check_user_profile(user_id, username, check_self=True)
    
    send_message(message['chat']['id'], text, 
                 photo=photo_id,
                 reply_markup=get_inline_keyboard_for_profile(display_username))

def extract_username(text):
    """Извлечь username из текста"""
    patterns = [
        r'@(\w+)',  
        r'check\s+@(\w+)',  
        r'/check\s+@(\w+)'  
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def handle_check_username(message, username_to_check):
    """Обработчик команды /check @username"""
    chat_id = message['chat']['id']
    
    # Ищем пользователя в базе по username
    target_user_id = get_user_id_by_username(username_to_check)
    
    if not target_user_id:
        # Если не нашли, создаем временный ID
        target_user_id = hash(username_to_check) % 1000000000
        logger.info(f"Пользователь @{username_to_check} не найден в базе, используем временный ID: {target_user_id}")
    
    # Проверяем профиль
    text, photo_id, display_username = check_user_profile(target_user_id, username_to_check, check_self=False)
    
    # Отправляем результат
    send_message(chat_id, text, 
                 photo=photo_id,
                 reply_markup=get_inline_keyboard_for_profile(display_username))

def handle_check_reply(message):
    """Обработчик /check в ответ на сообщение"""
    chat_id = message['chat']['id']
    
    if 'reply_to_message' in message and 'from' in message['reply_to_message']:
        target_user = message['reply_to_message']['from']
        target_user_id = target_user['id']
        target_username = target_user.get('username', f"user_{target_user_id}")
        
        # Проверяем профиль
        text, photo_id, display_username = check_user_profile(target_user_id, target_username, check_self=False)
        
        send_message(chat_id, text, 
                     photo=photo_id,
                     reply_markup=get_inline_keyboard_for_profile(display_username))
    else:
        send_message(chat_id, "❌ Ответьте на сообщение пользователя, чтобы проверить его")

# =============== НОВЫЕ АДМИНСКИЕ КОМАНДЫ (ПО ID) ===============
@admin_required
def handle_add_admin_by_id_command(message):
    """Добавить администратора по ID"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, 
                    "❌ Неверный формат!\n"
                    "Использование:\n"
                    "<code>/add_admin_id user_id</code>\n\n"
                    "Пример:\n"
                    "<code>/add_admin_id 123456789</code>\n\n"
                    "ℹ️ Чтобы получить ID пользователя, можно:\n"
                    "1. Ответить на его сообщение командой /id\n"
                    "2. Использовать команду /add_admin_reply (в ответ на сообщение)",
                    parse_mode='HTML')
        return
    
    try:
        new_admin_id = int(parts[1])
        
        # Нельзя добавить самого себя (если уже админ)
        if new_admin_id == user_id:
            send_message(chat_id, "⚠️ Вы уже администратор!")
            return
        
        # Добавляем администратора
        success, result_message = add_admin_by_id(new_admin_id, user_id)
        
        if success:
            # Получаем username для кэша
            username = get_username_by_id(new_admin_id)
            if username:
                username_to_id_cache[username] = new_admin_id
            
            send_message(chat_id, f"✅ {result_message}")
        else:
            send_message(chat_id, f"❌ {result_message}")
            
    except ValueError:
        send_message(chat_id, "❌ Неверный ID! ID должен быть числом.")

@admin_required
def handle_add_admin_reply_command(message):
    """Добавить администратора в ответ на сообщение"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    
    if 'reply_to_message' not in message:
        send_message(chat_id, "❌ Ответьте на сообщение пользователя, которого хотите сделать администратором")
        return
    
    target_user = message['reply_to_message']['from']
    target_user_id = target_user['id']
    
    # Нельзя добавить самого себя (если уже админ)
    if target_user_id == user_id:
        send_message(chat_id, "⚠️ Вы уже администратор!")
        return
    
    # Добавляем администратора
    success, result_message = add_admin_by_id(target_user_id, user_id)
    
    if success:
        target_username = target_user.get('username', f"user_{target_user_id}")
        username_to_id_cache[target_username] = target_user_id
        
        send_message(chat_id, f"✅ Пользователь @{target_username} (ID: {target_user_id}) теперь администратор!")
    else:
        send_message(chat_id, f"❌ {result_message}")

@admin_required
def handle_remove_admin_command(message):
    """Удалить администратора"""
    chat_id = message['chat']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, 
                    "❌ Неверный формат!\n"
                    "Использование:\n"
                    "<code>/remove_admin user_id</code>\n\n"
                    "Пример:\n"
                    "<code>/remove_admin 123456789</code>",
                    parse_mode='HTML')
        return
    
    try:
        admin_id_to_remove = int(parts[1])
        
        # Нельзя удалить главного администратора
        if admin_id_to_remove == ADMIN_ID:
            send_message(chat_id, "⛔ Нельзя удалить главного администратора!")
            return
        
        # Нельзя удалить себя
        if admin_id_to_remove == message['from']['id']:
            send_message(chat_id, "⚠️ Вы не можете удалить себя! Обратитесь к другому администратору.")
            return
        
        if remove_admin(admin_id_to_remove):
            send_message(chat_id, f"✅ Администратор с ID {admin_id_to_remove} удален")
        else:
            send_message(chat_id, f"❌ Администратор с ID {admin_id_to_remove} не найден")
            
    except ValueError:
        send_message(chat_id, "❌ Неверный ID! ID должен быть числом.")

@admin_required
def handle_list_admins_command(message):
    """Показать список администраторов"""
    chat_id = message['chat']['id']
    
    admins = list_admins()
    
    if not admins:
        send_message(chat_id, "📭 В базе нет администраторов")
        return
    
    text = "👑 <b>Список администраторов:</b>\n\n"
    
    for admin in admins:
        admin_id, username, added_at, added_by_username = admin
        added_date = datetime.strptime(added_at, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
        
        text += f"👤 @{username}\n"
        text += f"🆔 ID: <code>{admin_id}</code>\n"
        text += f"📅 Добавлен: {added_date}\n"
        text += f"👑 Добавил: @{added_by_username if added_by_username else 'unknown'}\n"
        
        # Помечаем главного админа
        if admin_id == ADMIN_ID:
            text += "⭐ <b>Главный администратор</b>\n"
        
        text += "━━━━━━━━━━━━━━━━\n\n"
    
    text += f"\n📊 Всего администраторов: {len(admins)}"
    
    send_message(chat_id, text, parse_mode='HTML')

def handle_get_id_command(message):
    """Показать ID пользователя"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    username = message['from'].get('username', f"user_{user_id}")
    
    text = f"🆔 <b>Ваш ID:</b> <code>{user_id}</code>\n"
    text += f"👤 <b>Username:</b> @{username}\n\n"
    
    # Если это ответ на сообщение, показываем ID того пользователя
    if 'reply_to_message' in message:
        target_user = message['reply_to_message']['from']
        target_id = target_user['id']
        target_username = target_user.get('username', f"user_{target_id}")
        
        text += f"🎯 <b>ID пользователя @{target_username}:</b> <code>{target_id}</code>\n\n"
        
        # Предлагаем добавить как админа
        if is_admin(user_id):
            text += f"📝 <i>Чтобы добавить этого пользователя как администратора, используйте:</i>\n"
            text += f"<code>/add_admin_id {target_id}</code>"
    
    send_message(chat_id, text, parse_mode='HTML')

# =============== ОСНОВНЫЕ КОМАНДЫ ===============
def handle_start(message):
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    username = message['from'].get('username', f"user_{user_id}")
    first_name = message['from'].get('first_name', 'User')
    
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
                 reply_markup={
                     'inline_keyboard': [[
                         {'text': '🚨 Слить скамера', 'url': 'https://t.me/antiscambaseAS'},
                         {'text': '📢 Новостной канал', 'url': 'https://t.me/AntiScamLaboratory'}
                     ]]
                 })
    
    # Проверяем статус пользователя для отображения правильных кнопок
    keyboard = [
        [{'text': '👤 Мой профиль'}],
        [{'text': '📋 Список гарантов'}, {'text': '⚙️ Команды бота'}]
    ]
    
    if is_admin(user_id):
        keyboard.append([{'text': '👑 Админ панель'}])
    
    send_message(chat_id, "🎯 Выберите действие:", 
                 reply_markup={
                     'keyboard': keyboard,
                     'resize_keyboard': True
                 })

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

def handle_admin_panel(message):
    """Обработчик кнопки '👑 Админ панель'"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    
    if not is_admin(user_id):
        send_message(chat_id, "⛔ У вас нет прав администратора!")
        return
    
    admin_text = """
👑 <b>Админ панель</b>

📋 <b>Доступные команды:</b>

👑 <b>Администраторы:</b>
<code>/add_admin_id 123456789</code> - ➕ Добавить админа по ID
<code>/add_admin_reply</code> - ➕ Добавить админа (в ответ на сообщение)
<code>/remove_admin 123456789</code> - ➖ Удалить админа
<code>/list_admins</code> - 📋 Список админов

🆔 <b>Утилиты:</b>
<code>/id</code> - Показать ID пользователя
<code>/id</code> (в ответ) - Показать ID автора сообщения

🔍 <b>Проверка:</b>
<code>/check @username</code>
<code>/check me</code>
<code>/check</code> (в ответ)

📊 <b>Ваш статус:</b> Администратор ✅

⚠️ <i>Все команды работают только с правами администратора.</i>
    """
    
    send_message(chat_id, admin_text, parse_mode='HTML')

def handle_commands(message):
    """Обработчик команды /commands и кнопки '⚙️ Команды бота'"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    
    commands_text = """
🤖 <b>Команды бота:</b>

👤 <b>Для всех пользователей:</b>
/start - 🚀 Запустить бота
/check @username - 🔍 Проверить пользователя
/check me - 👤 Проверить себя
/check (в ответ на сообщение) - 🔍 Проверить автора сообщения
/id - 🆔 Показать свой ID
/id (в ответ) - 🆔 Показать ID пользователя

👑 <b>Для администраторов:</b>
/add_admin_id 123456789 - ➕ Добавить админа по ID
/add_admin_reply - ➕ Добавить админа (в ответ на сообщение)
/remove_admin 123456789 - ➖ Удалить админа
/list_admins - 📋 Список админов

📸 <b>Для получения ID фото:</b>
Просто отправьте фото боту, и он покажет все ID

🔧 <b>Админ-панель:</b>
Нажмите кнопку "👑 Админ панель" для быстрого доступа к командам
    """
    
    send_message(chat_id, commands_text, parse_mode='HTML')

# =============== ОСНОВНОЙ ОБРАБОТЧИК ===============
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        if 'message' in update:
            message = update['message']
            text = message.get('text', '').strip()
            
            # Обработка фото
            if 'photo' in message:
                handle_photo(message)
                return jsonify({'ok': True})
            
            # Обработка кнопки "👑 Админ панель"
            elif text == '👑 Админ панель':
                handle_admin_panel(message)
                return jsonify({'ok': True})
            
            # Обработка команды /check в ответ на сообщение
            elif text == '/check' and 'reply_to_message' in message:
                handle_check_reply(message)
                return jsonify({'ok': True})
            
            # Обработка команды /check me и кнопки "👤 Мой профиль"
            elif text in ['/check me', '/check', '/check@AntilScam_Bot me', '/check@AntilScam_Bot', '👤 Мой профиль']:
                handle_my_profile(message)
                return jsonify({'ok': True})
            
            # Обработка команды /check @username
            elif text.startswith('/check'):
                username = extract_username(text)
                if username:
                    handle_check_username(message, username)
                else:
                    send_message(message['chat']['id'], 
                                "ℹ️ Использование:\n/check me - проверить себя\n/check @username - проверить другого пользователя\n/check (в ответ на сообщение) - проверить автора")
                return jsonify({'ok': True})
            
            # =========== КОМАНДЫ ДЛЯ РАБОТЫ С АДМИНАМИ (ПО ID) ===========
            # Добавить админа по ID
            elif text.startswith('/add_admin_id'):
                handle_add_admin_by_id_command(message)
                return jsonify({'ok': True})
            
            # Добавить админа в ответ на сообщение
            elif text.startswith('/add_admin_reply'):
                handle_add_admin_reply_command(message)
                return jsonify({'ok': True})
            
            # Удалить админа
            elif text.startswith('/remove_admin'):
                handle_remove_admin_command(message)
                return jsonify({'ok': True})
            
            # Список админов
            elif text.startswith('/list_admins'):
                handle_list_admins_command(message)
                return jsonify({'ok': True})
            
            # Показать ID
            elif text.startswith('/id'):
                handle_get_id_command(message)
                return jsonify({'ok': True})
            
            # Обработка команды /start
            elif text == '/start' or text == '/start@AntilScam_Bot':
                handle_start(message)
                return jsonify({'ok': True})
            
            # Обработка команды /commands и кнопки "⚙️ Команды бота"
            elif text == '⚙️ Команды бота' or text.startswith('/commands'):
                handle_commands(message)
                return jsonify({'ok': True})
            
            elif text == '📋 Список гарантов':
                send_message(message['chat']['id'], "📋 Список гарантов будет доступен позже")
                return jsonify({'ok': True})
            
            # Если текст не команда
            elif text and not text.startswith('/'):
                send_message(message['chat']['id'], 
                            "ℹ️ Используйте кнопки или команды:\n/start - начать\n/check me - проверить себя")
        
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return jsonify({'ok': False}), 500

@app.route('/')
def index():
    return f"""
    <h1>🤖 Anti Scam Bot</h1>
    <p>Бот работает на Render!</p>
    <p><strong>Webhook URL:</strong> https://anti-scam-bot1-1-omoy.onrender.com/webhook</p>
    <p><strong>Для настройки webhook:</strong></p>
    <p><a href="https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url=https://anti-scam-bot1-1-omoy.onrender.com/webhook" target="_blank">
        🔗 Настроить Webhook
    </a></p>
    """

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        domain = "https://anti-scam-bot1-1-omoy.onrender.com"
        webhook_url = f'{domain}/webhook'
        
        # Сначала удаляем старый webhook
        delete_url = f'{TELEGRAM_API_URL}/deleteWebhook'
        requests.get(delete_url)
        
        # Устанавливаем новый
        set_url = f'{TELEGRAM_API_URL}/setWebhook?url={webhook_url}'
        response = requests.get(set_url)
        result = response.json()
        
        return f"""
        <h1>{'✅ Webhook установлен!' if result.get('ok') else '❌ Ошибка'}</h1>
        <p>URL: {webhook_url}</p>
        <p>Результат: {result.get('description', 'Неизвестно')}</p>
        <p><a href="/">🏠 На главную</a></p>
        """
    except Exception as e:
        return f"<h1>❌ Ошибка</h1><p>{e}</p>"

if __name__ == '__main__':
    init_db()
    logger.info("=" * 50)
    logger.info("🤖 Anti Scam Bot запущен!")
    logger.info(f"✅ Токен: {BOT_TOKEN[:10]}...")
    logger.info(f"✅ Админ ID: {ADMIN_ID}")
    logger.info("=" * 50)
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
