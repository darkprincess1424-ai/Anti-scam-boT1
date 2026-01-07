from flask import Flask, request, jsonify
import logging
import requests
import json
from datetime import datetime, timedelta
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
username_to_id_cache = {}

# =============== ТЕЛЕГРАМ API ФУНКЦИИ ===============
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

def delete_message(chat_id, message_id):
    """Удалить сообщение"""
    try:
        url = f'{TELEGRAM_API_URL}/deleteMessage'
        data = {
            'chat_id': chat_id,
            'message_id': message_id
        }
        
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка удаления сообщения: {e}")
        return {'ok': False}

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
            user_id INTEGER,
            username TEXT,
            reason TEXT,
            proof_link TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (added_by) REFERENCES users(user_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS garants (
            garant_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            username TEXT,
            proof_link TEXT,
            info_link TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (added_by) REFERENCES users(user_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            username TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (added_by) REFERENCES users(user_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warns (
            warn_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            reason TEXT,
            warned_by INTEGER,
            warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (warned_by) REFERENCES users(user_id)
        )
    ''')
    
    # Добавляем администратора по умолчанию
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, status) VALUES (?, ?, ?)', 
                  (ADMIN_ID, 'admin', 'admin'))
    cursor.execute('INSERT OR IGNORE INTO admins (admin_id, user_id, username, added_by) VALUES (?, ?, ?, ?)',
                  (ADMIN_ID, ADMIN_ID, 'admin', ADMIN_ID))
    
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

def get_username_by_user_id(user_id):
    """Получить username по user_id"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        return result[0]
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
def add_scammer(user_id, username, reason, proof_link, added_by_id):
    """Добавить скамера в базу"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Проверяем, не является ли пользователь уже скамером
        cursor.execute('SELECT scammer_id FROM scammers WHERE user_id = ?', (user_id,))
        existing_scammer = cursor.fetchone()
        
        if existing_scammer:
            conn.close()
            return False, f"⚠️ Пользователь @{username} (ID: {user_id}) уже в списке скамеров!"
        
        # 1. Добавляем в таблицу scammers
        cursor.execute('''
            INSERT INTO scammers (scammer_id, user_id, username, reason, proof_link, added_by) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, user_id, username, reason, proof_link, added_by_id))
        
        # 2. Обновляем статус в таблице users
        cursor.execute('''
            UPDATE users 
            SET status = 'scammer'
            WHERE user_id = ?
        ''', (user_id,))
        
        # 3. Увеличиваем счетчик добавленных скамеров у администратора
        increment_added_scammers(added_by_id)
        
        # 4. Если пользователь был гарантом, удаляем его из гарантов
        cursor.execute('DELETE FROM garants WHERE user_id = ?', (user_id,))
        
        # 5. Если пользователь был админом, удаляем его из админов
        cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Скамер добавлен: ID={user_id}, username=@{username}, reason={reason}, added_by={added_by_id}")
        return True, f"✅ Скамер @{username} (ID: {user_id}) добавлен в базу\n📝 Причина: {reason}"
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении скамера: {e}")
        return False, f"❌ Ошибка при добавлении скамера: {str(e)}"

def remove_scammer(user_id):
    """Удалить скамера из базы"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Получаем информацию о скамере
        cursor.execute('SELECT username FROM scammers WHERE user_id = ?', (user_id,))
        scammer_result = cursor.fetchone()
        
        if not scammer_result:
            conn.close()
            return False, f"❌ Скамер с ID {user_id} не найден в базе"
        
        username = scammer_result[0] or f"user_{user_id}"
        
        # 1. Удаляем из таблицы scammers
        cursor.execute('DELETE FROM scammers WHERE user_id = ?', (user_id,))
        rows_deleted = cursor.rowcount
        
        if rows_deleted == 0:
            conn.close()
            return False, f"❌ Скамер с ID {user_id} не найден"
        
        # 2. Обновляем статус в таблице users на 'user' (если не админ и не гарант)
        cursor.execute('''
            UPDATE users 
            SET status = CASE 
                WHEN user_id IN (SELECT user_id FROM admins) THEN 'admin'
                WHEN user_id IN (SELECT user_id FROM garants) THEN 'garant'
                ELSE 'user'
            END
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
        
        return True, f"✅ Скамер @{username} (ID: {user_id}) удален из базы"
        
    except Exception as e:
        logger.error(f"Ошибка при удалении скамера: {e}")
        return False, f"❌ Ошибка при удаления скамера: {str(e)}"

def is_scammer(user_id):
    """Проверить, является ли пользователь скамером"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT scammer_id FROM scammers WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_scammer_info(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT reason, proof_link FROM scammers WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {'reason': result[0], 'proof_link': result[1]}
    return None

# =============== ФУНКЦИИ ДЛЯ РАБОТЫ С АДМИНАМИ ===============
def add_admin_by_id(target_user_id, added_by_id, username=None, first_name=None):
    """Добавить администратора по ID"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Если username не передан, пробуем получить его из базы
        if not username:
            cursor.execute('SELECT username FROM users WHERE user_id = ?', (target_user_id,))
            user_result = cursor.fetchone()
            if user_result:
                username = user_result[0]
        
        # Если username все еще None, создаем временный
        if not username:
            username = f"user_{target_user_id}"
        
        # Если first_name не передан, используем "User"
        if not first_name:
            first_name = "User"
        
        # Проверяем, не является ли пользователь скамером
        cursor.execute('SELECT scammer_id FROM scammers WHERE user_id = ?', (target_user_id,))
        existing_scammer = cursor.fetchone()
        
        if existing_scammer:
            conn.close()
            return False, f"❌ Нельзя сделать администратором скамера! Сначала удалите его из списка скамеров."
        
        # 1. Добавляем/обновляем пользователя в таблице users
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, status) 
            VALUES (?, ?, ?, ?)
        ''', (target_user_id, username, first_name, 'admin'))
        
        # 2. Проверяем, не является ли пользователь уже администратором
        cursor.execute('SELECT admin_id FROM admins WHERE user_id = ?', (target_user_id,))
        existing_admin = cursor.fetchone()
        
        if existing_admin:
            conn.close()
            return False, f"⚠️ Пользователь @{username} (ID: {target_user_id}) уже является администратором!"
        
        # 3. Добавляем в таблицу admins
        cursor.execute('''
            INSERT INTO admins (admin_id, user_id, username, added_by) 
            VALUES (?, ?, ?, ?)
        ''', (target_user_id, target_user_id, username, added_by_id))
        
        conn.commit()
        conn.close()
        
        # Сохраняем в кэше
        username_to_id_cache[username] = target_user_id
        
        logger.info(f"Администратор добавлен: ID={target_user_id}, username=@{username}, added_by={added_by_id}")
        return True, f"✅ Пользователь @{username} (ID: {target_user_id}) добавлен как администратор"
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении администратора: {e}")
        return False, f"❌ Ошибка при добавлении администратора: {str(e)}"

def remove_admin_by_id(admin_id):
    """Удалить администратора по ID"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Получаем username для сообщения
        cursor.execute('SELECT username FROM admins WHERE user_id = ?', (admin_id,))
        admin_result = cursor.fetchone()
        username = admin_result[0] if admin_result else f"user_{admin_id}"
        
        # 1. Удаляем из таблицы admins
        cursor.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
        rows_deleted = cursor.rowcount
        
        if rows_deleted == 0:
            conn.close()
            return False, f"❌ Администратор с ID {admin_id} не найден"
        
        # 2. Обновляем статус в таблице users (если не скамер и не гарант)
        cursor.execute('''
            UPDATE users 
            SET status = CASE 
                WHEN user_id IN (SELECT user_id FROM scammers) THEN 'scammer'
                WHEN user_id IN (SELECT user_id FROM garants) THEN 'garant'
                ELSE 'user'
            END
            WHERE user_id = ? 
            AND status = 'admin'
        ''', (admin_id,))
        
        conn.commit()
        conn.close()
        
        return True, f"✅ Администратор @{username} (ID: {admin_id}) удален"
        
    except Exception as e:
        logger.error(f"Ошибка при удалении администратора: {e}")
        return False, f"❌ Ошибка при удаления администратора: {str(e)}"

def list_admins():
    """Получить список всех администраторов"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.admin_id, a.user_id, a.username, a.added_at, u.username as added_by_username
        FROM admins a
        LEFT JOIN users u ON a.added_by = u.user_id
        ORDER BY a.added_at DESC
    ''')
    
    admins = cursor.fetchall()
    conn.close()
    
    return admins

# =============== ДЕКОРАТОР ПРОВЕРКИ АДМИНА ===============
def admin_required(func):
    """Декоратор для проверки прав администратора"""
    @wraps(func)
    def wrapper(message):
        user_id = message['from']['id']
        if user_id != ADMIN_ID and get_user_status(user_id) != 'admin':
            # В группах не показываем сообщение об отсутствии прав
            chat_type = message['chat'].get('type', 'private')
            if chat_type == 'private':
                send_message(message['chat']['id'], "⛔ У вас нет прав администратора!")
            return None
        return func(message)
    return wrapper

# =============== ФУНКЦИИ ДЛЯ МОДЕРАЦИИ ЧАТА ===============
def restrict_user(chat_id, user_id, until_date=None):
    """Ограничить пользователя в чате"""
    try:
        url = f'{TELEGRAM_API_URL}/restrictChatMember'
        
        permissions = {
            'can_send_messages': False,
            'can_send_media_messages': False,
            'can_send_polls': False,
            'can_send_other_messages': False,
            'can_add_web_page_previews': False,
            'can_change_info': False,
            'can_invite_users': False,
            'can_pin_messages': False
        }
        
        data = {
            'chat_id': chat_id,
            'user_id': user_id,
            'permissions': json.dumps(permissions)
        }
        
        if until_date:
            data['until_date'] = until_date
        
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        
        return result.get('ok', False)
    except Exception as e:
        logger.error(f"Ошибка при ограничении пользователя: {e}")
        return False

def unrestrict_user(chat_id, user_id):
    """Снять ограничения с пользователя в чате"""
    try:
        url = f'{TELEGRAM_API_URL}/restrictChatMember'
        
        permissions = {
            'can_send_messages': True,
            'can_send_media_messages': True,
            'can_send_polls': True,
            'can_send_other_messages': True,
            'can_add_web_page_previews': True,
            'can_change_info': False,
            'can_invite_users': False,
            'can_pin_messages': False
        }
        
        data = {
            'chat_id': chat_id,
            'user_id': user_id,
            'permissions': json.dumps(permissions)
        }
        
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        
        return result.get('ok', False)
    except Exception as e:
        logger.error(f"Ошибка при снятии ограничений: {e}")
        return False

def get_warns_count(user_id, chat_id):
    """Получить количество предупреждений пользователя в чате"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM warns WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else 0

def add_warn(user_id, chat_id, reason, warned_by):
    """Добавить предупреждение пользователю"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO warns (user_id, chat_id, reason, warned_by) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, chat_id, reason, warned_by))
        
        conn.commit()
        conn.close()
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении предупреждения: {e}")
        return False

def remove_warns(user_id, chat_id):
    """Удалить все предупреждения пользователя в чате"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM warns WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
        conn.commit()
        conn.close()
        
        return cursor.rowcount
    except Exception as e:
        logger.error(f"Ошибка при удалении предупреждений: {e}")
        return 0

# =============== УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ПРОВЕРКИ ===============
def check_user_profile(user_input, check_self=False):
    """Универсальная функция проверки профиля"""
    user_id = None
    username = None
    
    # Определяем тип входных данных
    if isinstance(user_input, dict):  # Сообщение от пользователя
        user_id = user_input['from']['id']
        username = user_input['from'].get('username', f"user_{user_id}")
    elif isinstance(user_input, str):  # Username
        username = user_input.replace('@', '')
        user_id = get_user_id_by_username(username)
        
        if not user_id:
            # Если не нашли пользователя, создаем временный ID
            user_id = hash(username) % 1000000000
            logger.info(f"Пользователь @{username} не найден, создан временный ID: {user_id}")
    elif isinstance(user_input, int):  # User ID
        user_id = user_input
        username = get_username_by_user_id(user_id) or f"user_{user_id}"
    
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

def get_garant_info(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT proof_link, info_link FROM garants WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return {'proof_link': result[0], 'info_link': result[1]} if result else None

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

# =============== ОСНОВНЫЕ ОБРАБОТЧИКИ ===============
def handle_my_profile(message):
    """Обработчик для кнопки '👤 Мой профиль' и команды '/check me'"""
    text, photo_id, display_username = check_user_profile(message, check_self=True)
    
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
    
    text, photo_id, display_username = check_user_profile(username_to_check, check_self=False)
    
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
        
        text, photo_id, display_username = check_user_profile(target_user_id, check_self=False)
        
        send_message(chat_id, text, 
                     photo=photo_id,
                     reply_markup=get_inline_keyboard_for_profile(display_username))
    else:
        send_message(chat_id, "❌ Ответьте на сообщение пользователя, чтобы проверить его")

def handle_start(message):
    """Обработчик команды /start"""
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
    
    # Показываем клавиатуру только в личных сообщениях
    chat_type = message['chat'].get('type', 'private')
    if chat_type == 'private':
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

# =============== МОДЕРАТОРСКИЕ КОМАНДЫ ДЛЯ ЧАТА ===============
@admin_required
def handle_open_command(message):
    """Команда /open - открыть чат (снять мут со всех)"""
    chat_id = message['chat']['id']
    chat_type = message['chat'].get('type', 'private')
    
    # Команда работает только в группах
    if chat_type not in ['group', 'supergroup']:
        send_message(chat_id, "❌ Эта команда работает только в группах!")
        return
    
    send_message(chat_id, "🔓 <b>Чат открыт!</b>\n\nВсе ограничения сняты.")
    logger.info(f"Чат {chat_id} открыт администратором {message['from']['id']}")

@admin_required
def handle_close_command(message):
    """Команда /close - закрыть чат (замутить всех кроме админов)"""
    chat_id = message['chat']['id']
    chat_type = message['chat'].get('type', 'private')
    
    # Команда работает только в группах
    if chat_type not in ['group', 'supergroup']:
        send_message(chat_id, "❌ Эта команда работает только в группах!")
        return
    
    send_message(chat_id, "🔒 <b>Чат закрыт!</b>\n\nТолько администраторы могут писать.")
    logger.info(f"Чат {chat_id} закрыт администратором {message['from']['id']}")

@admin_required
def handle_warn_command(message):
    """Команда /warn - выдать предупреждение"""
    chat_id = message['chat']['id']
    chat_type = message['chat'].get('type', 'private')
    
    # Команда работает только в группах
    if chat_type not in ['group', 'supergroup']:
        send_message(chat_id, "❌ Эта команда работает только в группах!")
        return
    
    # Проверяем, есть ли ответ на сообщение
    if 'reply_to_message' not in message:
        send_message(chat_id, "❌ Ответьте на сообщение пользователя, которому хотите выдать предупреждение!")
        return
    
    target_user = message['reply_to_message']['from']
    target_user_id = target_user['id']
    target_username = target_user.get('username', f"user_{target_user_id}")
    warner_id = message['from']['id']
    
    # Извлекаем причину
    text = message.get('text', '')
    parts = text.split(' ', 1)
    reason = parts[1] if len(parts) > 1 else "Нарушение правил чата"
    
    # Добавляем предупреждение
    if add_warn(target_user_id, chat_id, reason, warner_id):
        warns_count = get_warns_count(target_user_id, chat_id)
        
        response_text = f"⚠️ <b>Предупреждение выдано!</b>\n\n"
        response_text += f"👤 Пользователь: @{target_username}\n"
        response_text += f"📝 Причина: {reason}\n"
        response_text += f"🔢 Количество предупреждений: {warns_count}/3\n"
        
        # Автоматический мут при 3 предупреждениях
        if warns_count >= 3:
            # Мут на 1 час
            until_date = int((datetime.now() + timedelta(hours=1)).timestamp())
            if restrict_user(chat_id, target_user_id, until_date):
                response_text += f"\n🚫 <b>Автоматический мут на 1 час!</b>"
                # Сбрасываем предупреждения
                remove_warns(target_user_id, chat_id)
        
        send_message(chat_id, response_text, parse_mode='HTML')
    else:
        send_message(chat_id, "❌ Ошибка при выдаче предупреждения!")

@admin_required
def handle_mut_command(message):
    """Команда /mut - замутить пользователя"""
    chat_id = message['chat']['id']
    chat_type = message['chat'].get('type', 'private')
    
    # Команда работает только в группах
    if chat_type not in ['group', 'supergroup']:
        send_message(chat_id, "❌ Эта команда работает только в группах!")
        return
    
    # Проверяем, есть ли ответ на сообщение
    if 'reply_to_message' not in message:
        send_message(chat_id, "❌ Ответьте на сообщение пользователя, которого хотите замутить!")
        return
    
    target_user = message['reply_to_message']['from']
    target_user_id = target_user['id']
    target_username = target_user.get('username', f"user_{target_user_id}")
    muter_id = message['from']['id']
    
    # Извлекаем время мута
    text = message.get('text', '')
    parts = text.split(' ')
    
    mute_time = 60  # По умолчанию 60 минут
    
    if len(parts) > 1:
        try:
            mute_time = int(parts[1])
        except ValueError:
            mute_time = 60
    
    # Ограничиваем максимальное время
    if mute_time > 10080:  # 1 неделя
        mute_time = 10080
    elif mute_time < 1:
        mute_time = 1
    
    until_date = int((datetime.now() + timedelta(minutes=mute_time)).timestamp())
    
    if restrict_user(chat_id, target_user_id, until_date):
        # Удаляем предупреждения пользователя
        warns_removed = remove_warns(target_user_id, chat_id)
        
        response_text = f"🔇 <b>Пользователь замучен!</b>\n\n"
        response_text += f"👤 Пользователь: @{target_username}\n"
        response_text += f"⏱ Время: {mute_time} минут\n"
        
        if warns_removed > 0:
            response_text += f"🗑 Удалено предупреждений: {warns_removed}"
        
        send_message(chat_id, response_text, parse_mode='HTML')
    else:
        send_message(chat_id, "❌ Ошибка при муте пользователя!")

@admin_required
def handle_unmut_command(message):
    """Команда /unmut - размутить пользователя"""
    chat_id = message['chat']['id']
    chat_type = message['chat'].get('type', 'private')
    
    # Команда работает только в группах
    if chat_type not in ['group', 'supergroup']:
        send_message(chat_id, "❌ Эта команда работает только в группах!")
        return
    
    # Проверяем, есть ли ответ на сообщение
    if 'reply_to_message' not in message:
        send_message(chat_id, "❌ Ответьте на сообщение пользователя, которого хотите размутить!")
        return
    
    target_user = message['reply_to_message']['from']
    target_user_id = target_user['id']
    target_username = target_user.get('username', f"user_{target_user_id}")
    
    if unrestrict_user(chat_id, target_user_id):
        send_message(chat_id, f"🔊 <b>Пользователь размучен!</b>\n\n👤 Пользователь: @{target_username}", parse_mode='HTML')
    else:
        send_message(chat_id, "❌ Ошибка при размуте пользователя!")

# =============== КОМАНДЫ ДЛЯ РАБОТЫ СО СКАМЕРАМИ ===============
@admin_required
def handle_add_scammer_command(message):
    """Команда /add_scammer - добавить скамера"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    text = message.get('text', '')
    
    # Проверяем формат команды
    if not text.strip():
        send_message(chat_id, 
                    "❌ Неверный формат!\n\n"
                    "📝 <b>Использование:</b>\n"
                    "<code>/add_scammer @username (причина) [пруфы]</code>\n\n"
                    "📌 <b>Примеры:</b>\n"
                    "<code>/add_scammer @scammer1 (скам на 1000 руб) https://t.me/proof</code>\n"
                    "<code>/add_scammer @scammer2 (не отправил товар)</code>\n\n"
                    "🔄 <b>Лучший способ:</b>\n"
                    "Ответьте на сообщение скамера командой\n"
                    "<code>/add_scammer_reply (причина) [пруфы]</code>",
                    parse_mode='HTML')
        return
    
    # Извлекаем username, причину и пруфы
    parts = text.split(' ', 1)
    if len(parts) < 2:
        send_message(chat_id, "❌ Укажите username и причину!")
        return
    
    rest = parts[1].strip()
    
    # Извлекаем username
    if rest.startswith('@'):
        username_end = rest.find(' ')
        if username_end == -1:
            send_message(chat_id, "❌ Укажите причину в скобках!")
            return
        
        username_to_add = rest[1:username_end]
        rest = rest[username_end:].strip()
    else:
        send_message(chat_id, "❌ Укажите username через @!")
        return
    
    # Извлекаем причину (в скобках)
    if not rest.startswith('('):
        send_message(chat_id, "❌ Причина должна быть в скобках!")
        return
    
    reason_end = rest.find(')', 1)
    if reason_end == -1:
        send_message(chat_id, "❌ Не закрыта скобка с причиной!")
        return
    
    reason = rest[1:reason_end].strip()
    proof_link = rest[reason_end+1:].strip()
    
    if not reason:
        send_message(chat_id, "❌ Причина не может быть пустой!")
        return
    
    # Если пруфы не указаны, используем дефолтные
    if not proof_link:
        proof_link = "(пруфы на скам)"
    
    # Получаем ID пользователя
    target_user_id = get_user_id_by_username(username_to_add)
    
    if not target_user_id:
        # Пробуем создать временного пользователя
        target_user_id = hash(username_to_add) % 1000000000
        logger.info(f"Пользователь @{username_to_add} не найден, создан временный ID: {target_user_id}")
    
    # Проверяем, не является ли пользователь уже скамером
    if is_scammer(target_user_id):
        send_message(chat_id, f"⚠️ Пользователь @{username_to_add} уже в списке скамеров!")
        return
    
    # Добавляем скамера
    success, result_message = add_scammer(target_user_id, username_to_add, reason, proof_link, user_id)
    
    send_message(chat_id, result_message)

@admin_required
def handle_add_scammer_reply_command(message):
    """Команда /add_scammer_reply - добавить скамера в ответ на сообщение"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    
    if 'reply_to_message' not in message:
        send_message(chat_id, "❌ Ответьте на сообщение скамера, которого хотите добавить")
        return
    
    target_user = message['reply_to_message']['from']
    target_user_id = target_user['id']
    target_username = target_user.get('username', f"user_{target_user_id}")
    target_first_name = target_user.get('first_name', 'User')
    
    text = message.get('text', '')
    parts = text.split(' ', 1)
    
    reason = "Скам"
    proof_link = "(пруфы на скам)"
    
    if len(parts) > 1:
        rest = parts[1].strip()
        
        # Извлекаем причину (в скобках)
        if rest.startswith('('):
            reason_end = rest.find(')', 1)
            if reason_end != -1:
                reason = rest[1:reason_end].strip()
                proof_link = rest[reason_end+1:].strip()
        else:
            reason = rest
    
    # Проверяем, не является ли пользователь уже скамером
    if is_scammer(target_user_id):
        send_message(chat_id, f"⚠️ Пользователь @{target_username} уже в списке скамеров!")
        return
    
    # Регистрируем пользователя если его нет
    if not get_user_info(target_user_id):
        register_user(target_user_id, target_username, target_first_name)
    
    # Добавляем скамера
    success, result_message = add_scammer(target_user_id, target_username, reason, proof_link, user_id)
    
    if success:
        send_message(chat_id, 
                    f"✅ <b>Скамер добавлен!</b>\n\n"
                    f"👤 Пользователь: @{target_username}\n"
                    f"🆔 ID: <code>{target_user_id}</code>\n"
                    f"📝 Причина: {reason}\n"
                    f"🔗 Пруфы: {proof_link}")
    else:
        send_message(chat_id, f"❌ {result_message}")

@admin_required
def handle_del_scammer_command(message):
    """Команда /del_scammer - удалить скамера"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, 
                    "❌ Неверный формат!\n\n"
                    "📝 <b>Использование:</b>\n"
                    "<code>/del_scammer @username</code>\n"
                    "<code>/del_scammer user_id</code>\n\n"
                    "📌 <b>Примеры:</b>\n"
                    "<code>/del_scammer @scammer1</code>\n"
                    "<code>/del_scammer 123456789</code>\n\n"
                    "🔄 <b>Лучший способ:</b>\n"
                    "Ответьте на сообщение скамера командой\n"
                    "<code>/del_scammer_reply</code>",
                    parse_mode='HTML')
        return
    
    target = parts[1].strip()
    
    # Определяем, это username или ID
    if target.startswith('@'):
        username_to_remove = target[1:]
        target_user_id = get_user_id_by_username(username_to_remove)
        
        if not target_user_id:
            send_message(chat_id, f"❌ Пользователь @{username_to_remove} не найден!")
            return
    else:
        try:
            target_user_id = int(target)
            username_to_remove = get_username_by_user_id(target_user_id) or f"user_{target_user_id}"
        except ValueError:
            send_message(chat_id, "❌ Неверный ID! ID должен быть числом.")
            return
    
    # Проверяем, является ли пользователь скамером
    if not is_scammer(target_user_id):
        send_message(chat_id, f"❌ Пользователь @{username_to_remove} не является скамером!")
        return
    
    # Удаляем скамера
    success, result_message = remove_scammer(target_user_id)
    send_message(chat_id, result_message)

@admin_required
def handle_del_scammer_reply_command(message):
    """Команда /del_scammer_reply - удалить скамера в ответ на сообщение"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    
    if 'reply_to_message' not in message:
        send_message(chat_id, "❌ Ответьте на сообщение скамера, которого хотите удалить")
        return
    
    target_user = message['reply_to_message']['from']
    target_user_id = target_user['id']
    target_username = target_user.get('username', f"user_{target_user_id}")
    
    # Проверяем, является ли пользователь скамером
    if not is_scammer(target_user_id):
        send_message(chat_id, f"❌ Пользователь @{target_username} не является скамером!")
        return
    
    # Удаляем скамера
    success, result_message = remove_scammer(target_user_id)
    
    if success:
        send_message(chat_id, 
                    f"✅ <b>Скамер удален!</b>\n\n"
                    f"👤 Пользователь: @{target_username}\n"
                    f"🆔 ID: <code>{target_user_id}</code>\n"
                    f"📛 Теперь обычный пользователь")
    else:
        send_message(chat_id, f"❌ {result_message}")

# =============== АДМИНСКИЕ КОМАНДЫ ===============
@admin_required
def handle_add_admin_by_id_command(message):
    """Добавить администратора по ID"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, 
                    "❌ Неверный формат!\n\n"
                    "📝 <b>Использование:</b>\n"
                    "<code>/add_admin_id user_id</code>\n\n"
                    "📌 <b>Пример:</b>\n"
                    "<code>/add_admin_id 123456789</code>\n\n"
                    "🔄 <b>Лучший способ:</b>\n"
                    "Ответьте на сообщение пользователя командой\n"
                    "<code>/add_admin_reply</code> - тогда бот узнает реальный username",
                    parse_mode='HTML')
        return
    
    try:
        new_admin_id = int(parts[1])
        
        # Нельзя добавить самого себя (если уже админ)
        if new_admin_id == user_id:
            send_message(chat_id, "⚠️ Вы уже администратор!")
            return
        
        # Нельзя добавить главного админа (он уже есть)
        if new_admin_id == ADMIN_ID:
            send_message(chat_id, "⚠️ Этот пользователь уже главный администратор!")
            return
        
        # Добавляем администратора
        success, result_message = add_admin_by_id(new_admin_id, user_id)
        
        send_message(chat_id, result_message)
            
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
    target_username = target_user.get('username', f"user_{target_user_id}")
    target_first_name = target_user.get('first_name', 'User')
    
    # Нельзя добавить самого себя (если уже админ)
    if target_user_id == user_id:
        send_message(chat_id, "⚠️ Вы уже администратор!")
        return
    
    # Нельзя добавить главного админа
    if target_user_id == ADMIN_ID:
        send_message(chat_id, "⚠️ Этот пользователь уже главный администратор!")
        return
    
    # Добавляем администратора с реальным username
    success, result_message = add_admin_by_id(
        target_user_id, 
        user_id, 
        username=target_username,
        first_name=target_first_name
    )
    
    if success:
        send_message(chat_id, 
                    f"✅ <b>Администратор добавлен!</b>\n\n"
                    f"👤 Пользователь: @{target_username}\n"
                    f"🆔 ID: <code>{target_user_id}</code>\n"
                    f"📛 Имя: {target_first_name}")
    else:
        send_message(chat_id, f"❌ {result_message}")

@admin_required
def handle_remove_admin_command(message):
    """Удалить администратора"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, 
                    "❌ Неверный формат!\n\n"
                    "📝 <b>Использование:</b>\n"
                    "<code>/remove_admin user_id</code>\n\n"
                    "📌 <b>Пример:</b>\n"
                    "<code>/remove_admin 123456789</code>\n\n"
                    "⚠️ <i>Нельзя удалить главного администратора</i>",
                    parse_mode='HTML')
        return
    
    try:
        admin_id_to_remove = int(parts[1])
        
        # Нельзя удалить главного администратора
        if admin_id_to_remove == ADMIN_ID:
            send_message(chat_id, "⛔ Нельзя удалить главного администратора!")
            return
        
        # Нельзя удалить себя
        if admin_id_to_remove == user_id:
            send_message(chat_id, "⚠️ Вы не можете удалить себя! Обратитесь к другому администратору.")
            return
        
        success, result_message = remove_admin_by_id(admin_id_to_remove)
        send_message(chat_id, result_message)
            
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
        admin_id, user_id, username, added_at, added_by_username = admin
        added_date = datetime.strptime(added_at, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
        
        text += f"👤 @{username}\n"
        text += f"🆔 ID: <code>{user_id}</code>\n"
        text += f"📅 Добавлен: {added_date}\n"
        text += f"👑 Добавил: @{added_by_username if added_by_username else 'unknown'}\n"
        
        # Помечаем главного админа
        if user_id == ADMIN_ID:
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
    text += f"👤 <b>Username:</b> @{username}\n"
    text += f"👑 <b>Статус:</b> {get_user_status(user_id)}\n\n"
    
    # Если это ответ на сообщение, показываем ID того пользователя
    if 'reply_to_message' in message:
        target_user = message['reply_to_message']['from']
        target_id = target_user['id']
        target_username = target_user.get('username', f"user_{target_id}")
        target_status = get_user_status(target_id)
        
        text += f"🎯 <b>Пользователь @{target_username}:</b>\n"
        text += f"   🆔 ID: <code>{target_id}</code>\n"
        text += f"   👑 Статус: {target_status}"
    
    send_message(chat_id, text, parse_mode='HTML')

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

🚨 <b>Работа со скамерами:</b>
<code>/add_scammer @username (причина) [пруфы]</code> - ➕ Добавить скамера
<code>/add_scammer_reply (причина) [пруфы]</code> - ➕ Добавить скамера (в ответ)
<code>/del_scammer @username</code> - ➖ Удалить скамера
<code>/del_scammer_reply</code> - ➖ Удалить скамера (в ответ)

👑 <b>Администраторы:</b>
<code>/add_admin_id 123456789</code> - ➕ Добавить админа по ID
<code>/add_admin_reply</code> - ➕ Добавить админа (в ответ на сообщение)
<code>/remove_admin 123456789</code> - ➖ Удалить админа
<code>/list_admins</code> - 📋 Список админов

🛡 <b>Модерация чата:</b>
<code>/open</code> - 🔓 Открыть чат
<code>/close</code> - 🔒 Закрыть чат
<code>/warn причина</code> - ⚠️ Выдать предупреждение (в ответ)
<code>/mut время_в_минутах</code> - 🔇 Замутить (в ответ)
<code>/unmut</code> - 🔊 Размутить (в ответ)

🆔 <b>Утилиты:</b>
<code>/id</code> - Показать свой ID и статус
<code>/id</code> (в ответ) - Показать ID и статус пользователя

⚠️ <i>Все команды работают только в личных сообщениях с ботом.</i>
    """
    
    send_message(chat_id, admin_text, parse_mode='HTML')

def handle_commands(message):
    """Обработчик команды /commands"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    chat_type = message['chat'].get('type', 'private')
    
    # В группах показываем только основные команды
    if chat_type != 'private':
        commands_text = """
🤖 <b>Команды бота в группах:</b>

🔍 <b>Проверка пользователей:</b>
/check @username - Проверить пользователя
/check (в ответ на сообщение) - Проверить автора сообщения

ℹ️ <i>Для полного функционала напишите боту в личные сообщения</i>
        """
    else:
        # В личных сообщениях показываем все команды
        commands_text = """
🤖 <b>Команды бота:</b>

👤 <b>Для всех пользователей:</b>
/start - 🚀 Запустить бота
/check @username - 🔍 Проверить пользователя
/check me - 👤 Проверить себя
/id - 🆔 Показать свой ID и статус
/id (в ответ) - 🆔 Показать ID и статус пользователя

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
            chat_type = message['chat'].get('type', 'private')
            
            # В группах удаляем все сообщения кроме команд проверки и модерации
            if chat_type in ['group', 'supergroup']:
                # Разрешаем только команды проверки и модерации
                allowed_commands = ['/check', '/check@', '/open', '/close', '/warn', '/mut', '/unmut']
                is_allowed = any(text.startswith(cmd) for cmd in allowed_commands)
                
                if text and not is_allowed:
                    # Удаляем сообщение в группе
                    delete_message(message['chat']['id'], message['message_id'])
                    return jsonify({'ok': True})
            
            # Фото теперь просто игнорируются, не показываем ID
            if 'photo' in message:
                return jsonify({'ok': True})  # Просто игнорируем фото
            
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
            
            # =========== КОМАНДЫ ДЛЯ РАБОТЫ СО СКАМЕРАМИ ===========
            # Добавить скамера
            elif text.startswith('/add_scammer'):
                handle_add_scammer_command(message)
                return jsonify({'ok': True})
            
            # Добавить скамера в ответ на сообщение
            elif text.startswith('/add_scammer_reply'):
                handle_add_scammer_reply_command(message)
                return jsonify({'ok': True})
            
            # Удалить скамера
            elif text.startswith('/del_scammer'):
                handle_del_scammer_command(message)
                return jsonify({'ok': True})
            
            # Удалить скамера в ответ на сообщение
            elif text.startswith('/del_scammer_reply'):
                handle_del_scammer_reply_command(message)
                return jsonify({'ok': True})
            
            # =========== МОДЕРАТОРСКИЕ КОМАНДЫ ===========
            # Открыть чат
            elif text.startswith('/open'):
                handle_open_command(message)
                return jsonify({'ok': True})
            
            # Закрыть чат
            elif text.startswith('/close'):
                handle_close_command(message)
                return jsonify({'ok': True})
            
            # Предупреждение
            elif text.startswith('/warn'):
                handle_warn_command(message)
                return jsonify({'ok': True})
            
            # Мут
            elif text.startswith('/mut'):
                handle_mut_command(message)
                return jsonify({'ok': True})
            
            # Размут
            elif text.startswith('/unmut'):
                handle_unmut_command(message)
                return jsonify({'ok': True})
            
            # =========== АДМИНСКИЕ КОМАНДЫ ===========
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
            
            # Обработка команды /commands
            elif text.startswith('/commands'):
                handle_commands(message)
                return jsonify({'ok': True})
            
            elif text == '📋 Список гарантов':
                send_message(message['chat']['id'], "📋 Список гарантов будет доступен позже")
                return jsonify({'ok': True})
            
            elif text == '⚙️ Команды бота':
                handle_commands(message)
                return jsonify({'ok': True})
            
            # Если текст не команда
            elif text and not text.startswith('/'):
                # В группах игнорируем
                if chat_type in ['group', 'supergroup']:
                    return jsonify({'ok': True})
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
