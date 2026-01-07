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
    if not username:
        username = ""
    keyboard = {
        'inline_keyboard': [
            [
                {'text': 'Слить скамера', 'url': 'https://t.me/antiscambaseAS'},
                {'text': 'Вечная ссылка', 'url': f'https://t.me/{username}' if username else 'https://t.me'}
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
            elif text.startswith(('/add_', '/del_', '/open', '/close', '/warn', '/mut')):
                # Проверка прав администратора
                user_id = message['from']['id']
                if user_id != ADMIN_ID:
                    send_message(message['chat']['id'], "⛔ У вас нет прав администратора!")
                else:
                    send_message(message['chat']['id'], "ℹ️ Команда доступна только администраторам (функция в разработке)")
            else:
                send_message(message['chat']['id'], 
                            "ℹ️ Используйте кнопки или команды из меню 'Команды бота'")
        
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
    <h3>Инструкция по настройке:</h3>
    <ol>
        <li>В Render Dashboard перейдите в Environment Variables</li>
        <li>Добавьте переменную: <code>BOT_TOKEN = ваш_токен</code></li>
        <li>Перезапустите приложение</li>
        <li>Настройте webhook по ссылке:</li>
    </ol>
    <p><a href="https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url=https://anti-scam-bot1-1-omoy.onrender.com/webhook" target="_blank">
        Настроить Webhook
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
            <p><a href="/">Вернуться на главную</a></p>
            """
        else:
            return f"""
            <h1>❌ Ошибка установки webhook</h1>
            <p><strong>Ошибка:</strong> {result.get('description', 'Неизвестная ошибка')}</p>
            <p><a href="/">Вернуться на главную</a></p>
            """
    except Exception as e:
        return f"""
        <h1>❌ Ошибка</h1>
        <p><strong>Ошибка:</strong> {e}</p>
        <p><a href="/">Вернуться на главную</a></p>
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
        
        logger.info(f"Настраиваю webhook на URL: {webhook_url}")
        
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
    logger.info("=" * 50)
    
    # Автоматическая настройка webhook
    setup_webhook()
    
    # Запуск Flask сервера
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
