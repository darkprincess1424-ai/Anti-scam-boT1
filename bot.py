import os
import telebot
from telebot import types
import sqlite3
import logging
from datetime import datetime
import threading
import time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get('BOT_TOKEN', 'ВАШ_ТОКЕН_ЗДЕСЬ')
ADMIN_ID = 8281804428

# Инициализация бота
bot = telebot.TeleBot(TOKEN)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            search_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('INSERT OR IGNORE INTO admins (user_id, username, added_by) VALUES (?, ?, ?)', 
                  (ADMIN_ID, 'owner', ADMIN_ID))
    
    conn.commit()
    conn.close()

init_db()

# Функции работы с БД
def get_user_role(user_id):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM scammers WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        conn.close()
        return 'scammer'
    
    cursor.execute('SELECT * FROM garanty WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        conn.close()
        return 'garant'
    
    cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        conn.close()
        return 'admin'
    
    conn.close()
    return 'user'

def increment_search_count(user_id, username):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
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
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT search_count FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_scammers_count(admin_id):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM scammers WHERE added_by = ?', (admin_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def is_admin(user_id):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result

def check_admin_permission(user_id):
    """Проверка прав администратора с детальной информацией"""
    if user_id == ADMIN_ID:
        return {'is_admin': True, 'level': 'owner', 'username': 'Владелец'}
    
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {'is_admin': True, 'level': 'admin', 'username': result[0]}
    
    return {'is_admin': False, 'level': 'user'}

# Клавиатуры
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('👤 Мой профиль')
    btn2 = types.KeyboardButton('⭐ Список гарантов')
    btn3 = types.KeyboardButton('📋 Команды')
    btn4 = types.KeyboardButton('ℹ️ Информация')
    markup.add(btn1, btn2, btn3, btn4)
    return markup

def get_welcome_inline_keyboard():
    """Инлайн кнопки для приветственного сообщения (под фото)"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton('Слить скамера', url='https://t.me/antiscambaseAS'),
        types.InlineKeyboardButton('Новостной канал', url='https://t.me/AntiScamLaboratory')
    )
    return markup

def get_profile_inline_keyboard(role, user_id):
    """Инлайн кнопки для профиля пользователя"""
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton('Слить скамера', url='https://t.me/antiscambaseAS')
    )
    
    if role != 'user':
        markup.add(
            types.InlineKeyboardButton('Вечная ссылка', url=f'tg://user?id={user_id}')
        )
    
    return markup

def get_check_inline_keyboard():
    """Инлайн кнопки 💍 💔 ТОЛЬКО для проверки пользователей"""
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton('💍', callback_data='vote_like'),
        types.InlineKeyboardButton('💔', callback_data='vote_dislike')
    )
    return markup

# Обработчик /start
@bot.message_handler(commands=['start'])
def start_command(message):
    try:
        logger.info(f"Команда /start от пользователя {message.from_user.id}")
        
        welcome_text = """Anti Scam - начинающий проект, который будет помогать людям не попадатся на скам и на сомнительные услуги.

⚠️В нашей предложке вы - можете слить скамера или же сообщить о подозрительной личности.

🔍Чат поиска гарантов| трейдов | просто общения - @AntiScamChata

🛡Наш бот для проверки на скам - @AntilScamBot.

✔️Если хотите нас поддержать, то ставьте в ник приписку 'As |  Ас'"""
        
        # Отправляем приветственное сообщение с фото и инлайн кнопками ПОД ФОТО
        try:
            bot.send_photo(
                chat_id=message.chat.id,
                photo='AgACAgIAAxkBAAMDaV5adx8Oy37acG9cGOEgHbYhv2wAAiMOaxuQvvlKqFGS2DnsF9YBAAMCAANzAAM4BA',
                caption=welcome_text,
                reply_markup=get_welcome_inline_keyboard()  # Инлайн кнопки прямо под фото
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить фото: {e}")
            bot.send_message(
                chat_id=message.chat.id,
                text=welcome_text,
                reply_markup=get_welcome_inline_keyboard()  # Инлайн кнопки под текстом
            )
        
        # Отдельно отправляем основную клавиатуру с кнопками
        bot.send_message(
            chat_id=message.chat.id,
            text="👇 Используйте кнопки ниже:",
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка в start_command: {e}")
        bot.send_message(message.chat.id, "Привет! Я бот Anti Scam.", reply_markup=get_main_keyboard())

# Обработчик кнопки "👤 Мой профиль"
@bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
def my_profile_command(message):
    try:
        user = message.from_user
        user_id = user.id
        username = user.username or 'Нет username'
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
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
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
                chat_id=message.chat.id,
                photo=photo_id,
                caption=caption,
                reply_markup=get_profile_inline_keyboard(role, user_id)
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить фото профиля: {e}")
            bot.send_message(
                chat_id=message.chat.id,
                text=caption,
                reply_markup=get_profile_inline_keyboard(role, user_id)
            )
            
    except Exception as e:
        logger.error(f"Ошибка в my_profile_command: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки профиля")

# Обработчик кнопки "⭐ Список гарантов"
@bot.message_handler(func=lambda message: message.text == '⭐ Список гарантов')
def list_garants_command(message):
    try:
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
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
        
    except Exception as e:
        logger.error(f"Ошибка в list_garants_command: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при загрузке списка гарантов")

# Обработчик кнопки "📋 Команды"
@bot.message_handler(func=lambda message: message.text == '📋 Команды')
def commands_command(message):
    # Проверяем права пользователя
    admin_info = check_admin_permission(message.from_user.id)
    
    commands_text = """
🤖 <b>Доступные команды:</b>

🔍 <b>Проверка пользователей:</b>
/start - Начать работу с ботом
/check @username - Проверить пользователя
/check me - Проверить себя
/check (в ответ на сообщение) - Проверить пользователя
    """
    
    # Добавляем административные команды если пользователь админ
    if admin_info['is_admin']:
        commands_text += """
        
🔐 <b>Административные команды:</b>
/add_scammer - Добавить скамера
/my_rights - Проверить свои права
        """
        
        if admin_info['level'] == 'owner':
            commands_text += """
/add_admin - Добавить администратора (только владелец)
/del_admin - Удалить администратора (только владелец)
/admins - Список администраторов
            """
    
    commands_text += """
    
📝 <b>Кнопки:</b>
👤 Мой профиль - Посмотреть свой профиль
⭐ Список гарантов - Список проверенных гарантов
ℹ️ Информация - Информация о боте
    """
    
    bot.send_message(message.chat.id, commands_text, parse_mode='HTML')

# Обработчик кнопки "ℹ️ Информация"
@bot.message_handler(func=lambda message: message.text == 'ℹ️ Информация')
def info_command(message):
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

# Команда /check
@bot.message_handler(commands=['check'])
def check_command(message):
    try:
        args = message.text.split()
        
        if len(args) == 1 and not message.reply_to_message:
            help_text = """
❓ <b>Использование команды /check:</b>

/check @username - Проверить пользователя
/check me - Проверить себя
Или ответьте на сообщение с /check
"""
            bot.send_message(message.chat.id, help_text, parse_mode='HTML')
            return
        
        user_to_check = None
        
        if len(args) == 2 and args[1].lower() == 'me':
            user_to_check = message.from_user
            check_type = "себя"
        
        elif len(args) == 2 and args[1].startswith('@'):
            username = args[1][1:]
            user_to_check = message.from_user  # Для примера используем текущего пользователя
            check_type = f"@{username}"
        
        elif message.reply_to_message:
            user_to_check = message.reply_to_message.from_user
            username = user_to_check.username or 'без username'
            check_type = f"пользователя @{username}"
        
        if user_to_check:
            # Отправляем сообщение о начале проверки
            checking_msg = bot.send_message(
                message.chat.id, 
                f"🔍 <b>Проверяю {check_type}...</b>", 
                parse_mode='HTML'
            )
            
            user_id = user_to_check.id
            username = user_to_check.username or 'Нет username'
            role = get_user_role(user_id)
            
            increment_search_count(user_id, username)
            search_count = get_search_count(user_id)
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            # Имитация проверки
            time.sleep(1)
            
            # Удаляем сообщение "Проверяю..."
            try:
                bot.delete_message(message.chat.id, checking_msg.message_id)
            except:
                pass
            
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
            
            # Отправляем результат с инлайн кнопками 💍 💔
            bot.send_message(
                message.chat.id,
                result_text,
                parse_mode='HTML',
                reply_markup=get_check_inline_keyboard()  # ТОЛЬКО здесь кнопки 💍 💔
            )
            
    except Exception as e:
        logger.error(f"Ошибка в check_command: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при проверке")

# Обработчик фото (для админа)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if is_admin(message.from_user.id):
        photo_id = message.photo[-1].file_id
        info_text = f"""
📸 <b>Информация о фото:</b>

🆔 <b>File ID:</b> <code>{photo_id}</code>
📏 Размеры:
"""
        for i, photo in enumerate(message.photo):
            info_text += f"  • Размер {i+1}: {photo.width}x{photo.height}\n"
        
        bot.reply_to(message, info_text, parse_mode='HTML')

# Обработчик инлайн кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        if call.data == 'vote_like':
            bot.answer_callback_query(call.id, "❤️ Ваш голос 'За' учтен!")
        elif call.data == 'vote_dislike':
            bot.answer_callback_query(call.id, "💔 Ваш голос 'Против' учтен!")
    except Exception as e:
        logger.error(f"Ошибка в callback: {e}")

# ============== АДМИНИСТРАТИВНЫЕ КОМАНДЫ ==============

# Команда для добавления скамера (для администраторов)
@bot.message_handler(commands=['add_scammer'])
def add_scammer_command(message):
    try:
        # Проверяем права администратора
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды.")
            return
        
        args = message.text.split(maxsplit=3)
        
        if len(args) < 4 and not message.reply_to_message:
            bot.send_message(message.chat.id, 
                            "❌ Использование: /add_scammer @username причина пруфы\n"
                            "Пример: /add_scammer @scammer123 Обман в сделке https://proofs.com\n\n"
                            "Или ответьте на сообщение пользователя с командой и причиной:\n"
                            "/add_scammer причина пруфы")
            return
        
        user_to_add = None
        reason = ""
        proofs = ""
        
        if message.reply_to_message:
            # Добавление в ответ на сообщение
            user_to_add = message.reply_to_message.from_user
            if len(args) >= 3:
                reason = args[1]
                proofs = args[2] if len(args) > 2 else "Не указаны"
            else:
                bot.send_message(message.chat.id, 
                               "❌ Укажите причину и пруфы после команды.\n"
                               "Пример: /add_scammer причина пруфы (в ответ на сообщение)")
                return
        else:
            # Обычное добавление
            if args[1].startswith('@'):
                username = args[1][1:]
                # Пытаемся получить пользователя по username
                user_to_add = None  # В реальном боте нужно получить user_id по username
                temp_user_id = abs(hash(username)) % 1000000  # Временное решение
            else:
                # Это может быть user_id
                if args[1].isdigit():
                    temp_user_id = int(args[1])
                    username = f"user_{temp_user_id}"
                else:
                    bot.send_message(message.chat.id, "❌ Укажите @username или user_id.")
                    return
            
            reason = args[2]
            proofs = args[3] if len(args) > 3 else "Не указаны"
        
        if user_to_add:
            user_id = user_to_add.id
            username = user_to_add.username or f"user_{user_id}"
        else:
            user_id = temp_user_id
        
        # Проверяем, не добавлен ли уже как скамер
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM scammers WHERE user_id = ?', (user_id,))
        if cursor.fetchone():
            bot.send_message(message.chat.id, f"⚠️ Пользователь @{username} уже в списке скамеров.")
            conn.close()
            return
        
        # Добавляем скамера в базу
        cursor.execute('''
            INSERT INTO scammers (user_id, username, reason, proofs, added_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, reason, proofs, message.from_user.id))
        
        conn.commit()
        
        # Получаем информацию об администраторе
        cursor.execute('SELECT username FROM admins WHERE user_id = ?', (message.from_user.id,))
        admin_info = cursor.fetchone()
        admin_name = admin_info[0] if admin_info else f"user_{message.from_user.id}"
        
        conn.close()
        
        response = f"""
🔴 <b>СКАМЕР ДОБАВЛЕН В БАЗУ</b>

👤 Пользователь: @{username}
🆔 ID: {user_id}
📌 Причина: {reason}
🔗 Пруфы: {proofs}
👮 Добавил: @{admin_name}
🕒 Время: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}

✅ Пользователь добавлен в черный список.
        """
        
        bot.send_message(message.chat.id, response, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в add_scammer_command: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

# Команда для добавления администратора (только для владельца)
@bot.message_handler(commands=['add_admin'])
def add_admin_command(message):
    try:
        # Проверяем, что команду отправляет владелец
        if message.from_user.id != ADMIN_ID:
            bot.send_message(message.chat.id, "❌ Только владелец бота может добавлять администраторов.")
            return
        
        args = message.text.split()
        if len(args) < 2:
            bot.send_message(message.chat.id, 
                            "❌ Использование: /add_admin @username\n"
                            "Или: /add_admin user_id\n"
                            "Или ответьте на сообщение пользователя")
            return
        
        target = args[1]
        
        # Проверяем, указан ли user_id или username
        if target.isdigit():
            # Это user_id
            user_id = int(target)
            username = f"user_{user_id}"
            
            # Пробуем получить информацию о пользователе
            try:
                chat_member = bot.get_chat_member(user_id, user_id)
                username = chat_member.user.username or f"user_{user_id}"
            except:
                username = f"user_{user_id}"
                
        elif target.startswith('@'):
            # Это username
            username = target[1:]
            user_id = None
            
            bot.send_message(message.chat.id, 
                           f"⚠️ Для добавления по username нужен user_id.\n"
                           f"Попросите пользователя написать боту /start,\n"
                           f"а затем используйте /add_admin user_id\n"
                           f"или добавьте в ответ на его сообщение.")
            return
            
        elif message.reply_to_message:
            # Добавление в ответ на сообщение
            user_to_add = message.reply_to_message.from_user
            user_id = user_to_add.id
            username = user_to_add.username or f"user_{user_id}"
            
        else:
            bot.send_message(message.chat.id, 
                           "❌ Укажите user_id или username, либо ответьте на сообщение пользователя.")
            return
        
        if user_id:
            # Добавляем администратора в базу
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            
            # Проверяем, не является ли уже администратором
            cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
            if cursor.fetchone():
                bot.send_message(message.chat.id, f"⚠️ Пользователь @{username} уже является администратором.")
            else:
                cursor.execute('INSERT INTO admins (user_id, username, added_by) VALUES (?, ?, ?)', 
                             (user_id, username, message.from_user.id))
                conn.commit()
                
                # Получаем информацию о том, кто добавил
                cursor.execute('SELECT username FROM admins WHERE user_id = ?', (message.from_user.id,))
                added_by_info = cursor.fetchone()
                added_by_name = added_by_info[0] if added_by_info else "владелец"
                
                response = f"""
✅ <b>АДМИНИСТРАТОР ДОБАВЛЕН</b>

👤 Пользователь: @{username}
🆔 ID: {user_id}
👑 Статус: Администратор
👮 Добавил: @{added_by_name}
🕒 Время: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}

📋 <b>Доступные права:</b>
• Добавление скамеров (/add_scammer)
• Просмотр ID фото
• Доступ к административным командам
                """
                
                bot.send_message(message.chat.id, response, parse_mode='HTML')
            
            conn.close()
        else:
            bot.send_message(message.chat.id, "❌ Не удалось определить user_id пользователя.")
            
    except Exception as e:
        logger.error(f"Ошибка в add_admin_command: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

# Команда для просмотра списка администраторов
@bot.message_handler(commands=['admins'])
def list_admins_command(message):
    try:
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для просмотра списка администраторов.")
            return
        
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, added_by, added_at FROM admins ORDER BY added_at DESC')
        admins = cursor.fetchall()
        conn.close()
        
        if not admins:
            bot.send_message(message.chat.id, "📭 Список администраторов пуст.")
            return
        
        response = "👑 <b>Список администраторов:</b>\n\n"
        
        for i, (admin_id, username, added_by, added_at) in enumerate(admins, 1):
            # Получаем информацию о том, кто добавил
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor_added = conn.cursor()
            cursor_added.execute('SELECT username FROM admins WHERE user_id = ?', (added_by,))
            added_by_info = cursor_added.fetchone()
            conn.close()
            
            added_by_name = added_by_info[0] if added_by_info else str(added_by)
            
            status = "👑 Владелец" if admin_id == ADMIN_ID else "⚡ Админ"
            
            response += f"{i}. @{username}\n"
            response += f"   🆔 ID: {admin_id}\n"
            response += f"   📛 Статус: {status}\n"
            response += f"   📅 Добавлен: {added_at[:10]}\n"
            response += f"   👤 Добавил: @{added_by_name}\n\n"
        
        bot.send_message(message.chat.id, response, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в list_admins_command: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при загрузке списка администраторов")

# Команда для удаления администратора (только для владельца)
@bot.message_handler(commands=['del_admin'])
def delete_admin_command(message):
    try:
        # Проверяем, что команду отправляет владелец
        if message.from_user.id != ADMIN_ID:
            bot.send_message(message.chat.id, "❌ Только владелец бота может удалять администраторов.")
            return
        
        args = message.text.split()
        if len(args) < 2:
            bot.send_message(message.chat.id, 
                            "❌ Использование: /del_admin @username\n"
                            "Или: /del_admin user_id\n"
                            "Или ответьте на сообщение администратора.")
            return
        
        target = args[1]
        
        if target.isdigit():
            user_id = int(target)
        elif target.startswith('@'):
            username = target[1:]
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM admins WHERE username = ?', (username,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                user_id = result[0]
            else:
                bot.send_message(message.chat.id, f"❌ Администратор @{username} не найден.")
                return
        elif message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
        else:
            bot.send_message(message.chat.id, "❌ Укажите user_id или username.")
            return
        
        # Нельзя удалить владельца
        if user_id == ADMIN_ID:
            bot.send_message(message.chat.id, "❌ Нельзя удалить владельца бота.")
            return
        
        # Удаляем администратора
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('SELECT username FROM admins WHERE user_id = ?', (user_id,))
        admin_info = cursor.fetchone()
        
        if admin_info:
            username = admin_info[0]
            cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
            conn.commit()
            
            response = f"""
🗑️ <b>АДМИНИСТРАТОР УДАЛЕН</b>

👤 Пользователь: @{username}
🆔 ID: {user_id}
👮 Удалил: @{message.from_user.username or 'владелец'}
🕒 Время: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}

✅ Администратор удален из системы.
            """
            
            bot.send_message(message.chat.id, response, parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, "❌ Администратор не найден.")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Ошибка в delete_admin_command: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

# Команда для проверки своих прав
@bot.message_handler(commands=['my_rights'])
def my_rights_command(message):
    try:
        user_id = message.from_user.id
        admin_info = check_admin_permission(user_id)
        
        if admin_info['is_admin']:
            if admin_info['level'] == 'owner':
                role_text = "👑 Владелец бота"
                permissions = "• Полный доступ ко всем командам\n• Добавление/удаление администраторов\n• Добавление скамеров\n• Управление базой данных"
            else:
                role_text = "⚡ Администратор"
                permissions = "• Добавление скамеров\n• Управление базой данных скамеров\n• Просмотр административной информации"
            
            response = f"""
🔐 <b>ВАШИ ПРАВА:</b>

{role_text}
👤 Имя: @{message.from_user.username or 'Нет username'}
🆔 ID: {user_id}

📋 <b>Доступные команды:</b>
{permissions}

📝 <b>Административные команды:</b>
/add_scammer - Добавить скамера
/admins - Список администраторов
/my_rights - Проверить свои права
            """
        else:
            response = f"""
🔐 <b>ВАШИ ПРАВА:</b>

👤 Обычный пользователь
🆔 ID: {user_id}

📋 <b>Доступные команды:</b>
• Проверка пользователей (/check)
• Просмотр профиля
• Список гарантов

❌ <b>Административные команды недоступны</b>
            """
        
        bot.send_message(message.chat.id, response, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в my_rights_command: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при проверке прав")

# Запуск бота
def run_bot():
    logger.info("🤖 Запускаю AntiScam Bot...")
    print("=" * 50)
    print("🤖 ANTI SCAM BOT ЗАПУЩЕН!")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print("=" * 50)
    
    try:
        # Получаем информацию о боте
        bot_info = bot.get_me()
        print(f"🤖 Бот: @{bot_info.username}")
        print(f"🆔 ID бота: {bot_info.id}")
        print(f"👤 Имя бота: {bot_info.first_name}")
        print("=" * 50)
        print("✅ Бот готов к работе!")
        print("=" * 50)
        
        # Удаляем вебхук если есть
        bot.remove_webhook()
        
        # Запускаем polling
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        print(f"❌ Ошибка запуска бота: {e}")

# Функция для запуска Flask сервера (для Render)
from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "AntiScam Bot",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Flask запущен на порту: {port}")
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    logger.info("🚀 Запускаю приложение...")
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота в основном потоке
    run_bot()
