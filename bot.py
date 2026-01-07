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
ADMIN_ID = 8281804228

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
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
                  (user_id, username or f"user_{user_id}", first_name or "User"))
    conn.commit()
    conn.close()

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

def add_scammer(scammer_id, username, reason, proof_link, added_by):
    """Добавить скамера в базу данных"""
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Добавляем в таблицу скамеров
        cursor.execute('''
            INSERT OR REPLACE INTO scammers (scammer_id, username, reason, proof_link, added_by) 
            VALUES (?, ?, ?, ?, ?)
        ''', (scammer_id, username, reason, proof_link, added_by))
        
        # Обновляем статус в таблице пользователей
        cursor.execute('INSERT OR REPLACE INTO users (user_id, username, status) VALUES (?, ?, ?)',
                      (scammer_id, username, 'scammer'))
        
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

def get_scammer_info(scammer_id):
    """Получить информацию о скамере"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, reason, proof_link, added_by, added_at FROM scammers WHERE scammer_id = ?', (scammer_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'username': result[0],
            'reason': result[1],
            'proof_link': result[2],
            'added_by': result[3],
            'added_at': result[4]
        }
    return None

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

def add_admin(admin_id, username, added_by):
    """Добавить администратора в базу данных"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Добавляем в таблицу админов
    cursor.execute('INSERT OR REPLACE INTO admins (admin_id, username, added_by) VALUES (?, ?, ?)',
                  (admin_id, username, added_by))
    
    # Обновляем статус в таблице пользователей
    cursor.execute('INSERT OR REPLACE INTO users (user_id, username, status) VALUES (?, ?, ?)',
                  (admin_id, username, 'admin'))
    
    conn.commit()
    conn.close()
    return True

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

# =============== ФУНКЦИИ TELEGRAM API ===============
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

# =============== НОВЫЕ АДМИНСКИЕ ФУНКЦИИ ===============
@admin_required
def handle_add_scammer_command(message):
    """Обработчик команды /add_scammer"""
    chat_id = message['chat']['id']
    admin_id = message['from']['id']
    text = message.get('text', '')
    
    # Формат команды: /add_scammer @username причина (proof_link)
    # Пример: /add_scammer @scammer1 Обманул на 1000$ (https://t.me/proofs/123)
    
    parts = text.split(' ', 2)
    if len(parts) < 3:
        send_message(chat_id, 
                    "❌ Неверный формат!\n"
                    "Использование:\n"
                    "<code>/add_scammer @username Причина (ссылка_на_пруфы)</code>\n\n"
                    "Пример:\n"
                    "<code>/add_scammer @scammer123 Обманул на 500$ при продаже аккаунта (https://t.me/proofs/123)</code>",
                    parse_mode='HTML')
        return
    
    username = parts[1].replace('@', '').strip()
    reason_and_proof = parts[2]
    
    # Извлекаем proof_link из скобок
    proof_link = None
    match = re.search(r'\((https?://[^)]+)\)', reason_and_proof)
    if match:
        proof_link = match.group(1)
        reason = reason_and_proof.replace(f'({proof_link})', '').strip()
    else:
        reason = reason_and_proof
        proof_link = "Пруфы не предоставлены"
    
    # Генерируем ID из username (в реальном боте здесь нужно получать реальный ID)
    scammer_id = hash(username) % 1000000000
    
    if add_scammer(scammer_id, username, reason, proof_link, admin_id):
        logger.info(f"Скамер добавлен: {scammer_id} (@{username})")
        send_message(chat_id, 
                    f"✅ Скамер добавлен!\n\n"
                    f"👤 @{username}\n"
                    f"📝 Причина: {reason}\n"
                    f"🔗 Пруфы: {proof_link}\n\n"
                    f"ID в базе: {scammer_id}")
    else:
        send_message(chat_id, f"❌ Ошибка при добавлении скамера @{username}")

@admin_required
def handle_remove_scammer_command(message):
    """Обработчик команды /remove_scammer"""
    chat_id = message['chat']['id']
    text = message.get('text', '')
    
    parts = text.split(' ', 1)
    if len(parts) < 2:
        send_message(chat_id, 
                    "❌ Неверный формат!\n"
                    "Использование:\n"
                    "<code>/remove_scammer @username</code>\n\n"
                    "Пример:\n"
                    "<code>/remove_scammer @scammer123</code>\n\n"
                    "Или по ID:\n"
                    "<code>/remove_scammer 123456789</code>",
                    parse_mode='HTML')
        return
    
    target = parts[1].strip()
    
    # Пытаемся определить, это username или ID
    if target.startswith('@'):
        username = target.replace('@', '')
        scammer_id = hash(username) % 1000000000
    else:
        try:
            scammer_id = int(target)
        except ValueError:
            send_message(chat_id, "❌ Неверный ID. Используйте @username или числовой ID")
            return
    
    if remove_scammer(scammer_id):
        send_message(chat_id, f"✅ Скамер удален из базы!\nID: {scammer_id}")
    else:
        send_message(chat_id, f"❌ Скамер с ID {scammer_id} не найден в базе")

@admin_required
def handle_list_scammers_command(message):
    """Обработчик команды /list_scammers"""
    chat_id = message['chat']['id']
    
    scammers = list_scammers(limit=20)
    
    if not scammers:
        send_message(chat_id, "📭 База скамеров пуста")
        return
    
    text = "📋 <b>Список скамеров в базе:</b>\n\n"
    
    for scammer in scammers:
        scammer_id, username, reason, added_at, added_by = scammer
        added_date = datetime.strptime(added_at, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
        
        text += f"👤 @{username}\n"
        text += f"🆔 ID: <code>{scammer_id}</code>\n"
        text += f"📝 Причина: {reason[:50]}...\n" if len(reason) > 50 else f"📝 Причина: {reason}\n"
        text += f"📅 Добавлен: {added_date}\n"
        text += f"👮 Добавил: @{added_by if added_by else 'unknown'}\n"
        text += "━━━━━━━━━━━━━━━━\n\n"
    
    text += f"\n📊 Всего в базе: {len(scammers)} скамеров"
    
    send_message(chat_id, text, parse_mode='HTML')

@admin_required  
def handle_scammer_info_command(message):
    """Обработчик команды /scammer_info"""
    chat_id = message['chat']['id']
    text = message.get('text', '')
    
    parts = text.split(' ', 1)
    if len(parts) < 2:
        send_message(chat_id, 
                    "❌ Неверный формат!\n"
                    "Использование:\n"
                    "<code>/scammer_info @username</code>\n\n"
                    "Пример:\n"
                    "<code>/scammer_info @scammer123</code>",
                    parse_mode='HTML')
        return
    
    target = parts[1].strip().replace('@', '')
    scammer_id = hash(target) % 1000000000
    
    info = get_scammer_info(scammer_id)
    
    if info:
        added_date = datetime.strptime(info['added_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
        
        text = f"📋 <b>Информация о скамере:</b>\n\n"
        text += f"👤 Username: @{info['username']}\n"
        text += f"🆔 ID: <code>{scammer_id}</code>\n"
        text += f"📝 Причина: {info['reason']}\n"
        text += f"🔗 Пруфы: {info['proof_link']}\n"
        text += f"📅 Дата добавления: {added_date}\n"
        text += f"👮 Добавил администратор ID: {info['added_by']}"
        
        send_message(chat_id, text, parse_mode='HTML')
    else:
        send_message(chat_id, f"❌ Скамер @{target} не найден в базе")

# =============== СУЩЕСТВУЮЩИЕ ФУНКЦИИ (без изменений) ===============
def check_user_profile(user_id, username, check_self=False):
    """Проверить профиль пользователя - ОДНА функция для всех случаев"""
    
    # Регистрируем пользователя если его нет
    if not get_user_info(user_id):
        register_user(user_id, username, "")
    
    status = get_user_status(user_id)
    
    # Увеличиваем счетчик проверок если проверяем не себя
    if not check_self:
        increment_search_count(user_id)
    
    user_info = get_user_info(user_id)
    search_count = user_info['search_count'] if user_info else 1
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    display_username = user_info['username'] if user_info else username
    
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
    checker_id = message['from']['id']
    
    target_user_id = hash(username_to_check) % 1000000000
    
    register_user(target_user_id, username_to_check, "User")
    
    text, photo_id, display_username = check_user_profile(target_user_id, username_to_check, check_self=False)
    
    result = send_message(chat_id, text, 
                         photo=photo_id,
                         reply_markup=get_inline_keyboard_for_profile(display_username))
    
    if result.get('ok'):
        checker_username = message['from'].get('username', 'пользователь')
        send_message(checker_id, f"✅ Вы проверили пользователя @{username_to_check}")

def handle_check_reply(message):
    """Обработчик /check в ответ на сообщение"""
    chat_id = message['chat']['id']
    
    if 'reply_to_message' in message and 'from' in message['reply_to_message']:
        target_user = message['reply_to_message']['from']
        target_user_id = target_user['id']
        target_username = target_user.get('username', f"user_{target_user_id}")
        
        text, photo_id, display_username = check_user_profile(target_user_id, target_username, check_self=False)
        
        send_message(chat_id, text, 
                     photo=photo_id,
                     reply_markup=get_inline_keyboard_for_profile(display_username))
    else:
        send_message(chat_id, "❌ Ответьте на сообщение пользователя, чтобы проверить его")

@admin_required
def handle_add_admin_command(message):
    """Добавить администратора"""
    chat_id = message['chat']['id']
    text = message.get('text', '')
    parts = text.split()
    
    if len(parts) < 2:
        send_message(chat_id, "❌ Использование: /add_admin @username")
        return
    
    username = parts[1].replace('@', '')
    
    admin_id = hash(username) % 1000000000
    
    if add_admin(admin_id, username, message['from']['id']):
        logger.info(f"Администратор добавлен: {admin_id} (@{username})")
        send_message(chat_id, f"✅ Администратор @{username} добавлен!")
        
        status = get_user_status(admin_id)
        send_message(chat_id, f"ℹ️ Статус пользователя @{username}: {status}")
    else:
        send_message(chat_id, f"❌ Ошибка при добавлении администратора")

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
    
    # Показываем админские кнопки только админам
    keyboard = [
        [{'text': '👤 Мой профиль'}],
        [{'text': '📋 Список гарантов'}, {'text': '⚙️ Команды бота'}]
    ]
    
    if get_user_status(user_id) == 'admin' or user_id == ADMIN_ID:
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
    
    if get_user_status(user_id) != 'admin' and user_id != ADMIN_ID:
        send_message(chat_id, "⛔ У вас нет прав администратора!")
        return
    
    admin_text = """
👑 <b>Админ панель</b>

📋 <b>Доступные команды:</b>

➕ <b>Добавить скамера:</b>
<code>/add_scammer @username Причина (ссылка_на_пруфы)</code>

➖ <b>Удалить скамера:</b>
<code>/remove_scammer @username</code>
<code>/remove_scammer ID_пользователя</code>

📋 <b>Список скамеров:</b>
<code>/list_scammers</code>

ℹ️ <b>Инфо о скамере:</b>
<code>/scammer_info @username</code>

👑 <b>Добавить админа:</b>
<code>/add_admin @username</code>

🔍 <b>Проверить пользователя:</b>
<code>/check @username</code>
<code>/check me</code>

📊 <b>Статистика:</b>
<code>/stats</code>

⚠️ <i>Все команды работают только с правами администратора.</i>
    """
    
    send_message(chat_id, admin_text, parse_mode='HTML')

# =============== ОСНОВНОЙ ОБРАБОТЧИК ===============
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        logger.info(f"Получен update: {json.dumps(update, ensure_ascii=False)[:200]}...")
        
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
            
            # =========== АДМИНСКИЕ КОМАНДЫ ===========
            # Добавить скамера
            elif text.startswith('/add_scammer'):
                handle_add_scammer_command(message)
                return jsonify({'ok': True})
            
            # Удалить скамера
            elif text.startswith('/remove_scammer'):
                handle_remove_scammer_command(message)
                return jsonify({'ok': True})
            
            # Список скамеров
            elif text.startswith('/list_scammers'):
                handle_list_scammers_command(message)
                return jsonify({'ok': True})
            
            # Инфо о скамере
            elif text.startswith('/scammer_info'):
                handle_scammer_info_command(message)
                return jsonify({'ok': True})
            
            # Добавить админа
            elif text.startswith('/add_admin'):
                handle_add_admin_command(message)
                return jsonify({'ok': True})
            
            # Обработка команды /start
            elif text == '/start' or text == '/start@AntilScam_Bot':
                handle_start(message)
                return jsonify({'ok': True})
            
            # Обработка других кнопок
            elif text == '⚙️ Команды бота':
                commands_text = """
🤖 Команды бота:

👤 Для всех:
/start - 🚀 Запустить бота
/check @username - 🔍 Проверить пользователя
/check me - 👤 Проверить себя
/check (в ответ на сообщение) - 🔍 Проверить автора сообщения

🛡 Для администраторов (ID: 8281804228):
/add_scammer @username причина (ссылка_на_пруфы) - ➕ Добавить скамера
/remove_scammer @username - ➖ Удалить скамера
/list_scammers - 📋 Список скамеров
/scammer_info @username - ℹ️ Информация о скамере
/add_admin @username - 👑 Добавить администратора

📸 Для получения ID фото:
Просто отправьте фото боту, и он покажет все ID
                """
                send_message(message['chat']['id'], commands_text)
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
