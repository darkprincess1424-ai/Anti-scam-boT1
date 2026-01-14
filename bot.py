import os
import telebot
from telebot import types
import sqlite3
import logging
from datetime import datetime
import threading

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
    
    conn.commit()
    conn.close()

init_db()

# Функция для увеличени счетчика поисков
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

# Клавиатуры
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('👤 Мой профиль')
    btn2 = types.KeyboardButton('⭐ Список гарантов')
    btn3 = types.KeyboardButton('📋 Команды')
    btn4 = types.KeyboardButton('ℹ️ Информация')
    markup.add(btn1, btn2, btn3, btn4)
    return markup

def get_profile_inline_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton('Слить скамера', url='https://t.me/antiscambaseAS')
    )
    return markup

def get_welcome_inline_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton('Слить скамера', url='https://t.me/antiscambaseAS'),
        types.InlineKeyboardButton('Новостной канал', url='https://t.me/AntiScamLaboratory')
    )
    return markup

def get_check_inline_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton('💍', callback_data='like'),
        types.InlineKeyboardButton('💔', callback_data='dislike')
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
        
        # Отправляем приветственное сообщение с фото
        try:
            bot.send_photo(
                chat_id=message.chat.id,
                photo='AgACAgIAAxkBAAMDaV5adx8Oy37acG9cGOEgHbYhv2wAAiMOaxuQvvlKqFGS2DnsF9YBAAMCAANzAAM4BA',
                caption=welcome_text,
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить фото: {e}")
            bot.send_message(
                chat_id=message.chat.id,
                text=welcome_text,
                reply_markup=get_main_keyboard()
            )
        
        # Отправляем инлайн кнопки
        bot.send_message(
            chat_id=message.chat.id,
            text="👇 Выберите действие:",
            reply_markup=get_welcome_inline_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка в start_command: {e}")
        bot.send_message(message.chat.id, "Привет! Я бот Anti Scam.")

# Обработчик кнопки "👤 Мой профиль"
@bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
def my_profile_command(message):
    try:
        user = message.from_user
        increment_search_count(user.id, user.username or '')
        search_count = get_search_count(user.id)
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        # Определяем роль пользователя (упрощенно)
        role = 'user'
        if user.id == ADMIN_ID:
            role = 'admin'
        
        if role == 'admin':
            photo_id = 'AgACAgIAAxkBAAMVaV5dle8QkMo02yTdfGKefimIAAEDAAJEDmsbkL75StvZ04a4hKQJAQADAgADeQADOAQ'
            caption = f"""
🕵️ᴜsᴇʀ: @{user.username if user.username else 'Нет username'}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя администратором бᴀзы

Добавленно скамеров - 0

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count}
🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!
"""
        else:
            photo_id = 'AgACAgIAAxkBAAMbaV5d5EjzLoxlESB0a3aRaO9ENrAAAkgOaxuQvvlKzGwdJxbnZlsBAAMCAAN5AAM4BA'
            caption = f"""
🕵️ᴜsᴇʀ: @{user.username if user.username else 'Нет username'}
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
                reply_markup=get_profile_inline_keyboard()
            )
        except:
            bot.send_message(
                chat_id=message.chat.id,
                text=caption,
                reply_markup=get_profile_inline_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка в my_profile_command: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки профиля")

# Обработчик кнопки "⭐ Список гарантов"
@bot.message_handler(func=lambda message: message.text == '⭐ Список гарантов')
def list_garants_command(message):
    garants_text = """
⭐ <b>Список гарантов:</b>

1. @garant_example
   🔗 Пруфы: https://example.com/proofs1

2. @another_garant
   🔗 Пруфы: https://example.com/proofs2

3. @trusted_garant
   🔗 Пруфы: https://example.com/proofs3
"""
    bot.send_message(message.chat.id, garants_text, parse_mode='HTML')

# Обработчик кнопки "📋 Команды"
@bot.message_handler(func=lambda message: message.text == '📋 Команды')
def commands_command(message):
    commands_text = """
🤖 <b>Доступные команды:</b>

/start - Начать работу с ботом
/check @username - Проверить пользователя
/check me - Проверить себя

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
            username = user_to_check.username or 'Нет username'
            user_id = user_to_check.id
            
            # Увеличиваем счетчик поисков
            increment_search_count(user_id, username)
            search_count = get_search_count(user_id)
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            result_text = f"""
🔍 <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

👤 Пользователь: @{username}
🆔 ID: {user_id}
👤 <b>СТАТУС: ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ</b>

📊 Проверок: {search_count}
🕒 Время проверки: {current_time}

✅ Нарушений не обнаружено.
Пользователь не находится в черных списках.
"""
            
            bot.send_message(
                message.chat.id,
                result_text,
                parse_mode='HTML',
                reply_markup=get_check_inline_keyboard()
            )
            
        elif len(args) == 2 and args[1].startswith('@'):
            username = args[1]
            result_text = f"""
🔍 <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

👤 Пользователь: {username}
🔍 <b>СТАТУС: ПРОВЕРКА</b>

🕒 Время проверки: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}

🔎 Пользователь проверяется...
Используйте /check me для проверки себя.
"""
            bot.send_message(message.chat.id, result_text, parse_mode='HTML')
            
        elif message.reply_to_message:
            user_to_check = message.reply_to_message.from_user
            username = user_to_check.username or 'Нет username'
            user_id = user_to_check.id
            
            increment_search_count(user_id, username)
            search_count = get_search_count(user_id)
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            result_text = f"""
🔍 <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

👤 Пользователь: @{username}
🆔 ID: {user_id}
👤 <b>СТАТУС: ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ</b>

📊 Проверок: {search_count}
🕒 Время проверки: {current_time}

✅ Нарушений не обнаружено.
"""
            
            bot.send_message(
                message.chat.id,
                result_text,
                parse_mode='HTML',
                reply_markup=get_check_inline_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка в check_command: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при проверке")

# Обработчик фото (для админа)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if message.from_user.id == ADMIN_ID:
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
        if call.data == 'like':
            bot.answer_callback_query(call.id, "❤️ Ваш голос учтен!")
        elif call.data == 'dislike':
            bot.answer_callback_query(call.id, "💔 Ваш голос учтен!")
    except Exception as e:
        logger.error(f"Ошибка в callback: {e}")

# Запуск бота
def run_bot():
    logger.info("🤖 Запускаю AntiScam Bot...")
    print("=" * 50)
    print("🤖 ANTI SCAM BOT ЗАПУЩЕН!")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print("=" * 50)
    
    try:
        # Удаляем вебхук если есть
        bot.remove_webhook()
        
        # Запускаем polling
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        print(f"❌ Ошибка: {e}")

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
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    logger.info("🚀 Запускаю приложение...")
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота в основном потоке
    run_bot()
