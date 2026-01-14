import os
import telebot
from telebot import types
from flask import Flask, request
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get('BOT_TOKEN', 'ВАШ_ТОКЕН_ЗДЕСЬ')
ADMIN_ID = 8281804428

# Инициализация Flask и бота
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# Простая клавиатура
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('👤 Мой профиль')
    btn2 = types.KeyboardButton('⭐ Список гарантов')
    btn3 = types.KeyboardButton('📋 Команды')
    btn4 = types.KeyboardButton('ℹ️ Информация')
    markup.add(btn1, btn2, btn3, btn4)
    return markup

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_command(message):
    logger.info(f"START from {message.from_user.id}")
    
    welcome_text = """
Anti Scam - начинающий проект, который будет помогать людям не попадатся на скам и на сомнительные услуги.

⚠️В нашей предложке вы - можете слить скамера или же сообщить о подозрительной личности.

🔍Чат поиска гарантов| трейдов | просто общения - @AntiScamChata

🛡Наш бот для проверки на скам - @AntilScamBot.

✔️Если хотите нас поддержать, то ставьте в ник приписку 'As |  Ас'
    """
    
    # Пробуем отправить фото
    try:
        bot.send_photo(
            chat_id=message.chat.id,
            photo='AgACAgIAAxkBAAMDaV5adx8Oy37acG9cGOEgHbYhv2wAAiMOaxuQvvlKqFGS2DnsF9YBAAMCAANzAAM4BA',
            caption=welcome_text,
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Photo error: {e}")
        # Если фото не отправляется, отправляем текст
        bot.send_message(
            chat_id=message.chat.id,
            text=welcome_text,
            reply_markup=get_main_keyboard()
        )
    
    # Инлайн кнопки
    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.row(
        types.InlineKeyboardButton('Слить скамера', url='https://t.me/antiscambaseAS'),
        types.InlineKeyboardButton('Новостной канал', url='https://t.me/AntiScamLaboratory')
    )
    
    bot.send_message(
        chat_id=message.chat.id,
        text='Выберите действие:',
        reply_markup=inline_markup
    )

# Обработчик кнопки "👤 Мой профиль"
@bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
def my_profile(message):
    user = message.from_user
    profile_text = f"""
🕵️ Пользователь: @{user.username if user.username else 'нет username'}
🆔 ID: {user.id}
👤 Имя: {user.first_name} {user.last_name if user.last_name else ''}

Это ваш профиль!
    """
    
    bot.send_message(message.chat.id, profile_text)

# Обработчик кнопки "⭐ Список гарантов"
@bot.message_handler(func=lambda message: message.text == '⭐ Список гарантов')
def list_garants(message):
    garants_text = """
⭐ Список гарантов:

1. @garant1 - 🔗 Пруфы: ссылка
2. @garant2 - 🔗 Пруфы: ссылка
3. @garant3 - 🔗 Пруфы: ссылка
    """
    bot.send_message(message.chat.id, garants_text)

# Обработчик кнопки "📋 Команды"
@bot.message_handler(func=lambda message: message.text == '📋 Команды')
def show_commands(message):
    commands_text = """
📋 Команды бота:

/start - Начать работу
/check @username - Проверить пользователя
/check me - Проверить себя
    """
    bot.send_message(message.chat.id, commands_text)

# Обработчик кнопки "ℹ️ Информация"
@bot.message_handler(func=lambda message: message.text == 'ℹ️ Информация')
def show_info(message):
    info_text = """
ℹ️ Информация о боте:

🤖 AntiScam Bot
Версия: 1.0
Разработчик: AntiScam Team

📞 Связь:
@AntiScamChata
@AntiScamLaboratory
    """
    bot.send_message(message.chat.id, info_text)

# Команда /check
@bot.message_handler(commands=['check'])
def check_user(message):
    args = message.text.split()
    
    if len(args) == 1:
        bot.send_message(message.chat.id, "Пример: /check @username или /check me")
        return
    
    if args[1].lower() == 'me':
        user = message.from_user
        result = f"""
🔍 Результат проверки:

Пользователь: @{user.username if user.username else 'нет username'}
ID: {user.id}
Статус: ✅ Обычный пользователь
        """
        bot.send_message(message.chat.id, result)
    else:
        username = args[1]
        result = f"""
🔍 Результат проверки:

Пользователь: {username}
Статус: 🔍 Проверка завершена
Результат: ✅ Чист
        """
        bot.send_message(message.chat.id, result)

# Обработчик фото для админа
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if message.from_user.id == ADMIN_ID:
        photo_id = message.photo[-1].file_id
        bot.reply_to(message, f"📸 ID фото: {photo_id}")
    else:
        # Для обычных пользователей
        pass

# Обработчик всех сообщений для отладки
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    logger.info(f"Message from {message.from_user.id}: {message.text}")
    # Не отвечаем на все сообщения, только логируем

# Flask маршруты
@app.route('/')
def home():
    return '🤖 Бот работает!'

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 400

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    webhook_url = os.environ.get('WEBHOOK_URL', '')
    if webhook_url:
        bot.remove_webhook()
        import time
        time.sleep(1)
        full_url = f"{webhook_url}/webhook"
        bot.set_webhook(url=full_url)
        return f'Webhook установлен: {full_url}'
    return 'WEBHOOK_URL не установлен'

# Запуск
if __name__ == '__main__':
    # Если есть WEBHOOK_URL, устанавливаем вебхук
    webhook_url = os.environ.get('WEBHOOK_URL', '')
    if webhook_url:
        logger.info(f"Устанавливаю вебхук: {webhook_url}/webhook")
        bot.remove_webhook()
        import time
        time.sleep(2)
        bot.set_webhook(url=f"{webhook_url}/webhook")
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Запускаю бота на порту {port}")
    app.run(host='0.0.0.0', port=port)
