import os
import telebot
from telebot import types
import sqlite3
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
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

def is_admin(user_id):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result

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

# ============== ОБРАБОТЧИКИ КОМАНД ==============

# Обработчик /start
@bot.message_handler(commands=['start'])
def start_command(message):
    try:
        logger.info(f"START от {message.from_user.id}")
        
        welcome_text = """Anti Scam - начинающий проект, который будет помогать людям не попадатся на скам и на сомнительные услуги.

⚠️В нашей предложке вы - можете слить скамера или же сообщить о подозрительной личности.

🔍Чат поиска гарантов| трейдов | просто общения - @AntiScamChata

🛡Наш бот для проверки на скам - @AntilScamBot.

✔️Если хотите нас поддержать, то ставьте в ник приписку 'As |  Ас'"""
        
        # Пытаемся отправить фото с инлайн кнопками
        try:
            bot.send_photo(
                chat_id=message.chat.id,
                photo='AgACAgIAAxkBAAMDaV5adx8Oy37acG9cGOEgHbYhv2wAAiMOaxuQvvlKqFGS2DnsF9YBAAMCAANzAAM4BA',
                caption=welcome_text,
                reply_markup=get_welcome_inline_keyboard()
            )
        except Exception as e:
            logger.warning(f"Ошибка фото: {e}")
            bot.send_message(
                chat_id=message.chat.id,
                text=welcome_text,
                reply_markup=get_welcome_inline_keyboard()
            )
        
        # Отправляем основную клавиатуру
        bot.send_message(
            chat_id=message.chat.id,
            text="👇 Используйте кнопки ниже:",
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")
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
            caption = f"""🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
📍обнᴀᴩужᴇн ᴄᴋᴀʍᴇᴩ

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}"""
        
        elif role == 'garant':
            photo_id = 'AgACAgIAAxkBAAMZaV5d0ng4BuFtTjmwQbwAAYBsHktuAAJFDmsbkL75Ssa18PFEpyhEAQADAgADeQADOAQ'
            caption = f"""🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя ᴦᴀᴩᴀнᴛоʍ

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}"""
        
        elif role == 'admin':
            photo_id = 'AgACAgIAAxkBAAMVaV5dle8QkMo02yTdfGKefimIAAEDAAJEDmsbkL75StvZ04a4hKQJAQADAgADeQADOAQ'
            caption = f"""🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя администратором

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}"""
        
        else:
            photo_id = 'AgACAgIAAxkBAAMbaV5d5EjzLoxlESB0a3aRaO9ENrAAAkgOaxuQvvlKzGwdJxbnZlsBAAMCAAN5AAM4BA'
            caption = f"""🕵️ᴜsᴇʀ: @{username}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
✅ обычный ᴨоᴧьзоʙᴀᴛᴇᴧь ✅

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}"""
        
        try:
            bot.send_photo(
                chat_id=message.chat.id,
                photo=photo_id,
                caption=caption,
                reply_markup=get_profile_inline_keyboard(role, user_id)
            )
        except:
            bot.send_message(
                chat_id=message.chat.id,
                text=caption,
                reply_markup=get_profile_inline_keyboard(role, user_id)
            )
            
    except Exception as e:
        logger.error(f"Ошибка в профиле: {e}")
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
        
        response = "⭐ Список гарантов:\n\n"
        for i, (username, proofs_link) in enumerate(garants, 1):
            response += f"{i}. @{username}\n"
            response += f"   🔗 Пруфы: {proofs_link}\n\n"
        
        bot.send_message(message.chat.id, response)
        
    except Exception as e:
        logger.error(f"Ошибка в списке гарантов: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при загрузке")

# Обработчик кнопки "📋 Команды"
@bot.message_handler(func=lambda message: message.text == '📋 Команды')
def commands_command(message):
    commands_text = """🤖 Доступные команды:

🔍 Проверка пользователей:
/start - Начать работу
/check @username - Проверить пользователя
/check me - Проверить себя

📝 Кнопки:
👤 Мой профиль - Посмотреть свой профиль
⭐ Список гарантов - Список проверенных гарантов
ℹ️ Информация - Информация о боте"""
    
    bot.send_message(message.chat.id, commands_text)

# Обработчик кнопки "ℹ️ Информация"
@bot.message_handler(func=lambda message: message.text == 'ℹ️ Информация')
def info_command(message):
    info_text = """ℹ️ Информация о боте:

🤖 AntiScam Bot
Версия: 1.0
Разработчик: AntiScam Team

📞 Связь:
Чат: @AntiScamChata
Канал: @AntiScamLaboratory"""
    
    bot.send_message(message.chat.id, info_text)

# Команда /check
@bot.message_handler(commands=['check'])
def check_command(message):
    try:
        args = message.text.split()
        
        if len(args) == 1 and not message.reply_to_message:
            bot.send_message(message.chat.id, 
                "❓ Использование:\n/check @username\n/check me\nИли ответьте на сообщение")
            return
        
        user_to_check = None
        
        if len(args) == 2 and args[1].lower() == 'me':
            user_to_check = message.from_user
        
        elif len(args) == 2 and args[1].startswith('@'):
            user_to_check = message.from_user
        
        elif message.reply_to_message:
            user_to_check = message.reply_to_message.from_user
        
        if user_to_check:
            user_id = user_to_check.id
            username = user_to_check.username or 'Нет username'
            role = get_user_role(user_id)
            
            increment_search_count(user_id, username)
            search_count = get_search_count(user_id)
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            if role == 'scammer':
                result_text = f"""🔴 РЕЗУЛЬТАТ ПРОВЕРКИ

👤 Пользователь: @{username}
🆔 ID: {user_id}
⚠️ СТАТУС: СКАМЕР

📊 Проверок: {search_count}
🕒 Время: {current_time}"""
            
            elif role == 'garant':
                result_text = f"""🟢 РЕЗУЛЬТАТ ПРОВЕРКИ

👤 Пользователь: @{username}
🆔 ID: {user_id}
✅ СТАТУС: ГАРАНТ

📊 Проверок: {search_count}
🕒 Время: {current_time}"""
            
            elif role == 'admin':
                result_text = f"""🔵 РЕЗУЛЬТАТ ПРОВЕРКИ

👤 Пользователь: @{username}
🆔 ID: {user_id}
👑 СТАТУС: АДМИНИСТРАТОР

📊 Проверок: {search_count}
🕒 Время: {current_time}"""
            
            else:
                result_text = f"""🟡 РЕЗУЛЬТАТ ПРОВЕРКИ

👤 Пользователь: @{username}
🆔 ID: {user_id}
👤 СТАТУС: ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ

📊 Проверок: {search_count}
🕒 Время: {current_time}"""
            
            bot.send_message(
                message.chat.id,
                result_text,
                reply_markup=get_check_inline_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка в check: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при проверке")

# Обработчик фото (для админа)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if is_admin(message.from_user.id):
        photo_id = message.photo[-1].file_id
        bot.reply_to(message, f"📸 ID фото: {photo_id}")

# Обработчик инлайн кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        if call.data == 'vote_like':
            bot.answer_callback_query(call.id, "❤️ Голос учтен!")
        elif call.data == 'vote_dislike':
            bot.answer_callback_query(call.id, "💔 Голос учтен!")
    except:
        pass

# ============== ЗАПУСК БОТА ==============

if __name__ == '__main__':
    print("=" * 50)
    print("🤖 ЗАПУСКАЮ ANTI SCAM BOT...")
    print("=" * 50)
    
    try:
        # Удаляем вебхук если был
        bot.remove_webhook()
        
        # Запускаем polling
        print("✅ Бот запущен в режиме polling")
        print(f"👑 Админ ID: {ADMIN_ID}")
        print("=" * 50)
        print("Ожидаю сообщения...")
        
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print("🔄 Перезапуск через 10 секунд...")
        import time
        time.sleep(10)
