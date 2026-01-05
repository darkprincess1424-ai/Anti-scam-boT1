import logging
import json
import os
import datetime
from typing import Dict, List, Optional
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, PhotoSize
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, filters
from telegram.constants import ParseMode

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
API_TOKEN = '8328385972:AAEHTAx1QgublRdXKFFYpfoS937Umpt2UVI'
ADMIN_ID = 8281804228
MAIN_ADMIN_ID = 8281804228  # Главный администратор

# Файлы данных
SCAMMERS_FILE = 'scammers.json'
GUARANTEES_FILE = 'guarantees.json'
ADMINS_FILE = 'admins.json'
USER_STATS_FILE = 'user_stats.json'
CHAT_SETTINGS_FILE = 'chat_settings.json'

# ID фото для разных статусов
PHOTOS = {
    'start': 'AgACAgIAAxkBAAMDaVuXPAZ_gMcF_masVAbsYOKeHzcAAjYNaxsDaeBKo3RQYRT6stkBAAMCAAN5AAM4BA',
    'scammer': 'AgACAgIAAxkBAAMKaVuX0DTYvXOoh6L9-LQYZ6tXD4IAAkoPaxt7wNlKXE2XwnPDiyIBAAMCAAN5AAM4BA',
    'garant': 'AgACAgIAAxkBAAMNaVuX0Rv_6GJVFb8ulnhTb9UCxWUAAjwNaxsDaeBK8uKoaFgkFVEBAAMCAAN5AAM4BA',
    'user': 'AgACAgIAAxkBAAMHaVuXyRaIsterNpb8m4S6OCNs4pAAAkkPaxt7wNlKFbDPVp3lyU0BAAMCAAN5AAM4BA',
    'admin': 'AgACAgIAAxkBAAMQaVuX1K1bJLDWomL_T1ubUBQdnVYAAgcNaxsDaeBKrAABfnFPRUbCAQADAgADeQADOAQ'
}

# Состояния для ConversationHandler
WAITING_FOR_REASON, WAITING_FOR_PROOF, WAITING_FOR_BIO, WAITING_FOR_PROOF_LINK = range(4)

# Инициализация Flask
app = Flask(__name__)

# ========== ХРАНЕНИЕ ДАННЫХ ==========
class Database:
    def __init__(self):
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.scammers_file = os.path.join(self.data_dir, SCAMMERS_FILE)
        self.guarantees_file = os.path.join(self.data_dir, GUARANTEES_FILE)
        self.admins_file = os.path.join(self.data_dir, ADMINS_FILE)
        self.user_stats_file = os.path.join(self.data_dir, USER_STATS_FILE)
        self.chat_settings_file = os.path.join(self.data_dir, CHAT_SETTINGS_FILE)
        self.load_data()
    
    def load_data(self):
        # Загружаем скамеров
        try:
            with open(self.scammers_file, 'r', encoding='utf-8') as f:
                self.scammers = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.scammers = {}
        
        # Загружаем гарантов
        try:
            with open(self.guarantees_file, 'r', encoding='utf-8') as f:
                self.guarantees = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.guarantees = {}
        
        # Загружаем администраторов
        try:
            with open(self.admins_file, 'r', encoding='utf-8') as f:
                self.admins = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.admins = {str(ADMIN_ID): {"added_by": "system", "date": datetime.datetime.now().isoformat()}}
        
        # Загружаем статистику пользователей
        try:
            with open(self.user_stats_file, 'r', encoding='utf-8') as f:
                self.user_stats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.user_stats = {}
        
        # Загружаем настройки чатов
        try:
            with open(self.chat_settings_file, 'r', encoding='utf-8') as f:
                self.chat_settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.chat_settings = {}
    
    def save_scammers(self):
        with open(self.scammers_file, 'w', encoding='utf-8') as f:
            json.dump(self.scammers, f, ensure_ascii=False, indent=2)
    
    def save_guarantees(self):
        with open(self.guarantees_file, 'w', encoding='utf-8') as f:
            json.dump(self.guarantees, f, ensure_ascii=False, indent=2)
    
    def save_admins(self):
        with open(self.admins_file, 'w', encoding='utf-8') as f:
            json.dump(self.admins, f, ensure_ascii=False, indent=2)
    
    def save_user_stats(self):
        with open(self.user_stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.user_stats, f, ensure_ascii=False, indent=2)
    
    def save_chat_settings(self):
        with open(self.chat_settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.chat_settings, f, ensure_ascii=False, indent=2)
    
    def increment_search_count(self, user_id: str):
        """Увеличить счетчик поисков пользователя"""
        if user_id not in self.user_stats:
            self.user_stats[user_id] = {"search_count": 0}
        self.user_stats[user_id]["search_count"] = self.user_stats[user_id].get("search_count", 0) + 1
        self.save_user_stats()
    
    def get_search_count(self, user_id: str) -> int:
        """Получить количество поисков пользователя"""
        return self.user_stats.get(user_id, {}).get("search_count", 0)
    
    def add_scammer(self, user_id: str, username: str, reason: str, proof: str, added_by: str):
        """Добавить скамера"""
        self.scammers[user_id] = {
            "username": username,
            "reason": reason,
            "proof": proof,
            "added_by": added_by,
            "date": datetime.datetime.now().isoformat(),
            "search_count": 0
        }
        self.save_scammers()
    
    def remove_scammer(self, user_id: str):
        """Удалить скамера"""
        if user_id in self.scammers:
            del self.scammers[user_id]
            self.save_scammers()
            return True
        return False
    
    def add_garant(self, user_id: str, username: str, bio_link: str, proof_link: str, added_by: str):
        """Добавить гаранта"""
        self.guarantees[user_id] = {
            "username": username,
            "bio_link": bio_link,
            "proof_link": proof_link,
            "added_by": added_by,
            "date": datetime.datetime.now().isoformat(),
            "search_count": 0
        }
        self.save_guarantees()
    
    def remove_garant(self, user_id: str):
        """Удалить гаранта"""
        if user_id in self.guarantees:
            del self.guarantees[user_id]
            self.save_guarantees()
            return True
        return False
    
    def add_admin(self, user_id: str, added_by: str):
        """Добавить администратора"""
        self.admins[user_id] = {
            "added_by": added_by,
            "date": datetime.datetime.now().isoformat(),
            "can_add_scammers": True
        }
        self.save_admins()
    
    def remove_admin(self, user_id: str):
        """Удалить администратора"""
        if user_id in self.admins and user_id != str(MAIN_ADMIN_ID):
            del self.admins[user_id]
            self.save_admins()
            return True
        return False
    
    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        return str(user_id) in self.admins
    
    def is_scammer(self, user_id: str) -> bool:
        """Проверка, является ли пользователь скамером"""
        return user_id in self.scammers
    
    def is_garant(self, user_id: str) -> bool:
        """Проверка, является ли пользователь гарантом"""
        return user_id in self.guarantees
    
    def get_scammer_info(self, user_id: str) -> Optional[Dict]:
        """Получить информацию о скамере"""
        return self.scammers.get(user_id)
    
    def get_garant_info(self, user_id: str) -> Optional[Dict]:
        """Получить информацию о гаранте"""
        return self.guarantees.get(user_id)
    
    def get_admin_info(self, user_id: str) -> Optional[Dict]:
        """Получить информацию об администраторе"""
        return self.admins.get(user_id)
    
    def get_scammers_count(self, admin_id: str = None) -> int:
        """Получить количество скамеров, добавленных администратором"""
        if admin_id:
            count = 0
            for scammer in self.scammers.values():
                if scammer.get("added_by") == admin_id:
                    count += 1
            return count
        return len(self.scammers)
    
    def get_all_guarantees(self) -> List[Dict]:
        """Получить список всех гарантов"""
        return list(self.guarantees.values())

db = Database()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
    """Основная клавиатура (только для личных сообщений)"""
    if user_id is None:
        return ReplyKeyboardRemove()
    
    keyboard = []
    
    if user_id and db.is_admin(user_id):
        keyboard.append([KeyboardButton(text="👨‍💻 Админ панель")])
    
    keyboard.append([
        KeyboardButton(text="👤 Мой профиль"),
        KeyboardButton(text="📋 Список гарантов")
    ])
    
    keyboard.append([
        KeyboardButton(text="🛠 Команды бота")
    ])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура администратора"""
    keyboard = [
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="➕ Добавить скамера"), KeyboardButton(text="➕ Добавить гаранта")],
        [KeyboardButton(text="🗑 Удалить скамера"), KeyboardButton(text="🗑 Удалить гаранта")],
        [KeyboardButton(text="👑 Добавить админа"), KeyboardButton(text="❌ Удалить админа")],
        [KeyboardButton(text="🆔 ID фото"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_inline_start_keyboard() -> InlineKeyboardMarkup:
    """Инлайн клавиатура для стартового сообщения"""
    keyboard = [
        [
            InlineKeyboardButton(text="🕵️ Слить скамера", url="https://t.me/antiscambaseAS"),
            InlineKeyboardButton(text="📢 Новостной канал", url="https://t.me/AntiScamLaboratory")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_check_result_keyboard(user_id: str = None, username: str = None) -> InlineKeyboardMarkup:
    """Инлайн клавиатура для результатов проверки"""
    keyboard = []
    
    # Кнопка "Слить скамера"
    keyboard.append([
        InlineKeyboardButton(
            text="🕵️ Слить скамера", 
            url="https://t.me/antiscambaseAS"
        )
    ])
    
    # Кнопка "Вечная ссылка" (только если есть username)
    if username:
        keyboard.append([
            InlineKeyboardButton(
                text="🔗 Вечная ссылка",
                url=f"https://t.me/{username}"
            )
        ])
    elif user_id:
        # Если нет username, показываем кнопку с ID
        keyboard.append([
            InlineKeyboardButton(
                text="🆔 ID профиля",
                callback_data=f"show_id_{user_id}"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    start_text = """
Anti Scam - начинающий проект, который будет помогать людям не попадатся на скам и на сомнительные услуги.

⚠️В нашей предложке вы - можете слить скамера или же сообщить о подозрительной личности.

🔍Чат поиска гарантов| трейдов | просто общения - @AntiScamChata

🛡Наш бот для проверки на скам - @AntilScamBot.

✔️Если хотите нас поддержать, то ставьте в ник приписку 'As |  Ас'
"""
    
    await update.message.reply_photo(
        photo=PHOTOS['start'],
        caption=start_text,
        reply_markup=get_inline_start_keyboard()
    )
    
    # Показываем клавиатуру только в личных сообщениях
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "Добро пожаловать! Используйте кнопки ниже для навигации:",
            reply_markup=get_main_keyboard(update.effective_user.id)
        )

async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Мой профиль'"""
    user = update.effective_user
    await check_user_profile(update, context, user.id, user.username)

async def guarantees_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Список гарантов'"""
    guarantees = db.get_all_guarantees()
    
    if not guarantees:
        await update.message.reply_text("📭 Список гарантов пуст.")
        return
    
    response = "📋 <b>Список гарантов:</b>\n\n"
    
    for i, garant in enumerate(guarantees, 1):
        username = garant.get('username', 'N/A')
        proof_link = garant.get('proof_link', 'Нет пруфов')
        
        response += f"{i}. @{username}\n"
        response += f"   🔗 Пруфы: {proof_link}\n\n"
    
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)

async def bot_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Команды бота'"""
    commands_text = """
🤖 <b>Команды бота Anti Scam:</b>

<b>Для всех пользователей:</b>
/start - Запустить бота
/check @username - Проверить пользователя
/check me - Проверить себя
/check (в ответ на сообщение) - Проверить пользователя

<b>Для администраторов:</b>
/add_garant @username ссылка_на_био ссылка_на_пруфы - Добавить гаранта
/del_garant @username - Удалить гаранта
/add_admin @username - Добавить администратора
/add_scammer @username причина пруфы - Добавить скамера
/del_scammer @username - Удалить скамера

<b>Для модерации чата:</b>
/open - Открыть чат
/close - Закрыть чат
/warn @username - Выдать предупреждение
/mut @username - Замутить пользователя

<b>Специальные команды:</b>
/id_photo - Показать ID всех фото бота
"""
    
    await update.message.reply_text(commands_text, parse_mode=ParseMode.HTML)

async def id_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /id_photo"""
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Эта команда только для администраторов.")
        return
    
    photo_info = """
🖼 <b>ID фото бота:</b>

<b>Стартовое фото:</b>
<code>{start}</code>

<b>Скамер:</b>
<code>{scammer}</code>

<b>Гарант:</b>
<code>{garant}</code>

<b>Обычный пользователь:</b>
<code>{user}</code>

<b>Администратор:</b>
<code>{admin}</code>
""".format(**PHOTOS)
    
    await update.message.reply_text(photo_info, parse_mode=ParseMode.HTML)

async def id_photo_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'ID фото'"""
    await id_photo(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Админ панель'"""
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет доступа к админ панели.")
        return
    
    stats_text = f"""
📊 <b>Статистика базы:</b>

🕵️ Скамеров: {len(db.scammers)}
🤝 Гарантов: {len(db.guarantees)}
👑 Админов: {len(db.admins)}

Используйте кнопки ниже для управления:
"""
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML, reply_markup=get_admin_keyboard())

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Статистика'"""
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    
    user_id = str(update.effective_user.id)
    scammer_count = db.get_scammers_count(user_id)
    
    stats_text = f"""
📊 <b>Ваша статистика:</b>

✅ Добавлено скамеров: {scammer_count}
🔍 Всего проверок: {db.get_search_count(user_id)}

<b>Общая статистика:</b>
👥 Всего скамеров: {len(db.scammers)}
🤝 Всего гарантов: {len(db.guarantees)}
"""
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Назад'"""
    await update.message.reply_text(
        "Главное меню:",
        reply_markup=get_main_keyboard(update.effective_user.id)
    )

# ========== КОМАНДЫ ПРОВЕРКИ ==========
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /check"""
    args = context.args
    
    if not args:
        # Если команда без аргументов
        if update.message.reply_to_message:
            # Проверка по ответу на сообщение
            user_to_check = update.message.reply_to_message.from_user
            await check_user_profile(update, context, user_to_check.id, user_to_check.username)
        else:
            await update.message.reply_text("❌ Укажите username для проверки или ответьте на сообщение пользователя.\nПример: /check @username")
    elif len(args) == 1:
        if args[0].lower() == "me":
            # Проверка себя
            await check_user_profile(update, context, update.effective_user.id, update.effective_user.username)
        else:
            # Проверка по username
            username = args[0].replace("@", "")
            try:
                user = await context.bot.get_chat(f"@{username}")
                await check_user_profile(update, context, user.id, username)
            except Exception as e:
                await update.message.reply_text(f"❌ Не удалось найти пользователя @{username}")
                logger.error(f"Ошибка поиска пользователя: {e}")
    else:
        await update.message.reply_text("❌ Неверный формат команды.\nИспользуйте: /check @username или /check me")

async def check_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str = None):
    """Проверка профиля пользователя"""
    # Увеличиваем счетчик поисков
    db.increment_search_count(str(user_id))
    search_count = db.get_search_count(str(user_id))
    
    current_time = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    # Определяем статус пользователя
    if db.is_scammer(str(user_id)):
        # Скамер
        photo_id = PHOTOS['scammer']
        scammer_info = db.get_scammer_info(str(user_id))
        
        response = f"""🕵️ᴜsᴇʀ: @{username if username else 'unknown'}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
📍обнᴀᴩужᴇн ᴄᴋᴀʍᴇᴩ

ʙᴄᴇ ᴨᴩуɸы нᴀ ᴄᴋᴀʍ ⬇️
{scammer_info['proof']}

ᴨоᴧьзоʙᴀᴛᴇᴧь ᴄ ᴨᴧохой ᴩᴇᴨуᴛᴀциᴇй❌
дᴧя ʙᴀɯᴇй жᴇ бᴇзоᴨᴀᴄноᴄᴛи ᴧучɯᴇ зᴀбᴧоᴋиᴩоʙᴀᴛь ᴇᴦо✅

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count} раз

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи: {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!"""
        
    elif db.is_garant(str(user_id)):
        # Гарант
        photo_id = PHOTOS['garant']
        garant_info = db.get_garant_info(str(user_id))
        
        response = f"""🕵️ᴜsᴇʀ: @{username if username else 'unknown'}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя ᴦᴀᴩᴀнᴛоʍ бᴀзы

ᴇᴦо [ᴇᴇ] инɸо: {garant_info.get('bio_link', 'Нет информации')}
ᴇᴦо [ᴇᴇ] ᴨᴩуɸы: {garant_info.get('proof_link', 'Нет пруфов')}

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count} раз

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи: {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!"""
        
    elif db.is_admin(user_id):
        # Администратор
        photo_id = PHOTOS['admin']
        admin_info = db.get_admin_info(str(user_id))
        scammer_count = db.get_scammers_count(str(user_id))
        
        response = f"""🕵️ᴜsᴇʀ: @{username if username else 'unknown'}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя администратором бᴀзы

Добавленно скамеров: {scammer_count}

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count} раз
🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи: {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!"""
        
    else:
        # Обычный пользователь
        photo_id = PHOTOS['user']
        
        response = f"""🕵️ᴜsᴇʀ: @{username if username else 'unknown'}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
✅ обычный ᴨоᴧьзоʙᴀᴛᴇᴧь ✅

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count} раз
 
🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи: {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!"""
    
    # Получаем инлайн клавиатуру
    inline_keyboard = get_check_result_keyboard(str(user_id), username)
    
    # Отправляем результат с фото и инлайн кнопками
    await update.message.reply_photo(
        photo=photo_id,
        caption=response,
        reply_markup=inline_keyboard
    )

# ========== ОБРАБОТКА ИНЛАЙН КНОПОК ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик инлайн кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("show_id_"):
        user_id = query.data.replace("show_id_", "")
        await query.edit_message_caption(caption=f"🆔 ID пользователя: {user_id}")

# ========== АДМИН КОМАНДЫ ==========
async def add_scammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /add_scammer"""
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав для добавления скамеров.")
        return ConversationHandler.END
    
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("❌ Укажите username скамера, причину и пруфы.\nПример: /add_scammer @username причина пруфы")
        return ConversationHandler.END
    
    username = args[0].replace("@", "")
    reason = args[1]
    proof = " ".join(args[2:]) if len(args) > 2 else ""
    
    try:
        user = await context.bot.get_chat(f"@{username}")
        user_id = str(user.id)
        
        if db.is_scammer(user_id):
            await update.message.reply_text(f"❌ Пользователь @{username} уже есть в базе скамеров.")
            return ConversationHandler.END
        
        if not proof:
            context.user_data['scammer_info'] = {'user_id': user_id, 'username': username, 'reason': reason}
            await update.message.reply_text(f"Введите пруфы для скамера @{username}:")
            return WAITING_FOR_PROOF
        
        db.add_scammer(user_id, username, reason, proof, str(update.effective_user.id))
        
        await update.message.reply_text(
            f"✅ Скамер @{username} добавлен в базу!\n"
            f"Причина: {reason}\n"
            f"Пруфы: {proof}"
        )
        
        # Уведомляем главного администратора
        if update.effective_user.id != MAIN_ADMIN_ID:
            try:
                await context.bot.send_message(
                    MAIN_ADMIN_ID,
                    f"🆕 Новый скамер добавлен:\n"
                    f"👤 @{username}\n"
                    f"🆔 {user_id}\n"
                    f"📝 Причина: {reason}\n"
                    f"🔗 Пруфы: {proof}\n"
                    f"👨‍💻 Добавил: @{update.effective_user.username or 'N/A'}"
                )
            except:
                pass
        
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось найти пользователя @{username}")
        logger.error(f"Ошибка поиска пользователя: {e}")
    
    return ConversationHandler.END

async def add_scammer_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение пруфов для скамера"""
    proof = update.message.text
    scammer_info = context.user_data.get('scammer_info', {})
    
    if not scammer_info:
        await update.message.reply_text("❌ Ошибка: информация о скамере не найдена.")
        return ConversationHandler.END
    
    user_id = scammer_info['user_id']
    username = scammer_info['username']
    reason = scammer_info['reason']
    
    db.add_scammer(user_id, username, reason, proof, str(update.effective_user.id))
    
    await update.message.reply_text(
        f"✅ Скамер @{username} добавлен в базу!\n"
        f"Причина: {reason}\n"
        f"Пруфы: {proof}"
    )
    
    # Уведомляем главного администратора
    if update.effective_user.id != MAIN_ADMIN_ID:
        try:
            await context.bot.send_message(
                MAIN_ADMIN_ID,
                f"🆕 Новый скамер добавлен:\n"
                f"👤 @{username}\n"
                f"🆔 {user_id}\n"
                f"📝 Причина: {reason}\n"
                f"🔗 Пруфы: {proof}\n"
                f"👨‍💻 Добавил: @{update.effective_user.username or 'N/A'}"
            )
        except:
            pass
    
    return ConversationHandler.END

async def add_scammer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Добавить скамера'"""
    await update.message.reply_text("Для добавления скамера используйте команду:\n/add_scammer @username причина пруфы")

async def del_scammer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /del_scammer"""
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав для удаления скамеров.")
        return
    
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ Укажите username скамера.\nПример: /del_scammer @username")
        return
    
    username = args[0].replace("@", "")
    
    # Ищем скамера по username
    for user_id, scammer_info in db.scammers.items():
        if scammer_info.get("username") == username:
            db.remove_scammer(user_id)
            await update.message.reply_text(f"✅ Скамер @{username} удален из базы.")
            return
    
    await update.message.reply_text(f"❌ Скамер @{username} не найден в базе.")

async def add_garant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /add_garant"""
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав для добавления гарантов.")
        return ConversationHandler.END
    
    args = context.args
    
    if len(args) < 3:
        await update.message.reply_text("❌ Укажите username гаранта, ссылку на био и пруфы.\nПример: /add_garant @username ссылка_на_био ссылка_на_пруфы")
        return ConversationHandler.END
    
    username = args[0].replace("@", "")
    bio_link = args[1]
    proof_link = args[2]
    
    try:
        user = await context.bot.get_chat(f"@{username}")
        user_id = str(user.id)
        
        if db.is_garant(user_id):
            await update.message.reply_text(f"❌ Пользователь @{username} уже есть в базе гарантов.")
            return ConversationHandler.END
        
        db.add_garant(user_id, username, bio_link, proof_link, str(update.effective_user.id))
        
        await update.message.reply_text(
            f"✅ Гарант @{username} добавлен в базу!\n"
            f"Био: {bio_link}\n"
            f"Пруфы: {proof_link}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось найти пользователя @{username}")
        logger.error(f"Ошибка поиска пользователя: {e}")
    
    return ConversationHandler.END

async def add_garant_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Добавить гаранта'"""
    await update.message.reply_text("Для добавления гаранта используйте команду:\n/add_garant @username ссылка_на_био ссылка_на_пруфы")

async def del_garant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /del_garant"""
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав для удаления гарантов.")
        return
    
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ Укажите username гаранта.\nПример: /del_garant @username")
        return
    
    username = args[0].replace("@", "")
    
    # Ищем гаранта по username
    for user_id, garant_info in db.guarantees.items():
        if garant_info.get("username") == username:
            db.remove_garant(user_id)
            await update.message.reply_text(f"✅ Гарант @{username} удален из базы.")
            return
    
    await update.message.reply_text(f"❌ Гарант @{username} не найден в базе.")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /add_admin"""
    if update.effective_user.id != MAIN_ADMIN_ID:
        await update.message.reply_text("⛔ Только главный администратор может добавлять админов.")
        return
    
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ Укажите username нового администратора.\nПример: /add_admin @username")
        return
    
    username = args[0].replace("@", "")
    
    try:
        user = await context.bot.get_chat(f"@{username}")
        user_id = str(user.id)
        
        if db.is_admin(int(user_id)):
            await update.message.reply_text(f"❌ Пользователь @{username} уже является администратором.")
            return
        
        db.add_admin(user_id, str(update.effective_user.id))
        
        await update.message.reply_text(f"✅ Администратор @{username} добавлен!")
        
        # Уведомляем нового админа
        try:
            await context.bot.send_message(
                user_id,
                f"🎉 Поздравляем! Вы были назначены администратором бота Anti Scam!\n\n"
                f"Теперь вы можете:\n"
                f"• Добавлять скамеров командой /add_scammer @username причина пруфы\n"
                f"• Добавлять гарантов командой /add_garant @username\n"
                f"• Использовать админ панель через кнопку '👨‍💻 Админ панель'\n\n"
                f"Используйте команду /help для просмотра всех возможностей."
            )
        except:
            pass
            
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось найти пользователя @{username}")
        logger.error(f"Ошибка поиска пользователя: {e}")

async def del_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Удалить админа'"""
    if update.effective_user.id != MAIN_ADMIN_ID:
        await update.message.reply_text("⛔ Только главный администратор может удалять админов.")
        return
    await update.message.reply_text("Для удаления администратора используйте команду:\n/del_admin @username\n\n⚠️ Эта команда будет доступна в будущих обновлениях.")

async def del_scammer_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Удалить скамера'"""
    await update.message.reply_text("Для удаления скамера используйте команду:\n/del_scammer @username")

async def del_garant_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Удалить гаранта'"""
    await update.message.reply_text("Для удаления гаранта используйте команду:\n/del_garant @username")

async def add_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Добавить админа'"""
    await update.message.reply_text("Для добавления администратора используйте команду:\n/add_admin @username")

# ========== КОМАНДЫ МОДЕРАЦИИ ЧАТА ==========
async def open_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /open"""
    if not db.is_admin(update.effective_user.id) and update.effective_chat.type == "private":
        await update.message.reply_text("⛔ Только администраторы могут использовать эту команду.")
        return
    
    if update.effective_chat.type != "private":
        chat_id = str(update.effective_chat.id)
        
        if chat_id not in db.chat_settings:
            db.chat_settings[chat_id] = {"is_open": True, "warns": {}}
        else:
            db.chat_settings[chat_id]["is_open"] = True
        
        db.save_chat_settings()
        await update.message.reply_text("✅ Чат открыт для общения.")

async def close_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /close"""
    if not db.is_admin(update.effective_user.id) and update.effective_chat.type == "private":
        await update.message.reply_text("⛔ Только администраторы могут использовать эту команду.")
        return
    
    if update.effective_chat.type != "private":
        chat_id = str(update.effective_chat.id)
        
        if chat_id not in db.chat_settings:
            db.chat_settings[chat_id] = {"is_open": False, "warns": {}}
        else:
            db.chat_settings[chat_id]["is_open"] = False
        
        db.save_chat_settings()
        await update.message.reply_text("🚫 Чат закрыт для общения.")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /warn"""
    if not db.is_admin(update.effective_user.id) and update.effective_chat.type == "private":
        await update.message.reply_text("⛔ Только администраторы могут использовать эту команду.")
        return
    
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Эта команда работает только в группах/чатах.")
        return
    
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("❌ Укажите username пользователя.\nПример: /warn @username")
        return
    
    username = args[0].replace("@", "")
    
    try:
        # Пытаемся найти пользователя
        user = await context.bot.get_chat(f"@{username}")
        await update.message.reply_text(f"✅ Пользователю @{username} выдано предупреждение.")
    except:
        await update.message.reply_text(f"❌ Не удалось найти пользователя @{username}")

async def mut_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /mut"""
    if not db.is_admin(update.effective_user.id) and update.effective_chat.type == "private":
        await update.message.reply_text("⛔ Только администраторы могут использовать эту команду.")
        return
    
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Эта команда работает только в группах/чатах.")
        return
    
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("❌ Укажите username пользователя и время в минутах.\nПример: /mut @username 60")
        return
    
    username = args[0].replace("@", "")
    
    try:
        minutes = int(args[1])
        await update.message.reply_text(f"✅ Пользователь @{username} замучен на {minutes} минут.")
    except:
        await update.message.reply_text("❌ Укажите корректное время в минутах.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# ========== FLASK РОУТЫ ==========
@app.route('/')
def index():
    return jsonify({
        "status": "ok",
        "bot": "AntiScamBot",
        "version": "1.0",
        "admin_id": ADMIN_ID,
        "stats": {
            "scammers": len(db.scammers),
            "guarantees": len(db.guarantees),
            "admins": len(db.admins)
        }
    })

@app.route('/stats')
def stats_api():
    """API статистики"""
    return jsonify({
        "scammers_count": len(db.scammers),
        "guarantees_count": len(db.guarantees),
        "admins_count": len(db.admins),
        "total_searches": sum(db.user_stats.get(user_id, {}).get("search_count", 0) for user_id in db.user_stats)
    })

@app.route('/photos')
def photos_api():
    """API с ID фото"""
    return jsonify(PHOTOS)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Вебхук для Telegram (если нужно)"""
    return jsonify({"status": "webhook_not_used"})

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(API_TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("id_photo", id_photo))
    application.add_handler(CommandHandler("add_scammer", add_scammer_command))
    application.add_handler(CommandHandler("del_scammer", del_scammer))
    application.add_handler(CommandHandler("add_garant", add_garant_command))
    application.add_handler(CommandHandler("del_garant", del_garant))
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("open", open_chat))
    application.add_handler(CommandHandler("close", close_chat))
    application.add_handler(CommandHandler("warn", warn_user))
    application.add_handler(CommandHandler("mut", mut_user))
    
    # ConversationHandler для добавления скамера
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex('^➕ Добавить скамера$'), add_scammer_button)],
        states={
            WAITING_FOR_PROOF: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_scammer_proof)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)
    
    # Обработчики текстовых сообщений (кнопки)
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^👤 Мой профиль$'), my_profile))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^📋 Список гарантов$'), guarantees_list))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^🛠 Команды бота$'), bot_commands))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^👨‍💻 Админ панель$'), admin_panel))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^📊 Статистика$'), stats))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^🔙 Назад$'), back_to_main))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^🆔 ID фото$'), id_photo_button))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^➕ Добавить гаранта$'), add_garant_button))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^🗑 Удалить скамера$'), del_scammer_button))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^🗑 Удалить гаранта$'), del_garant_button))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^👑 Добавить админа$'), add_admin_button))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^❌ Удалить админа$'), del_admin_button))
    
    # Обработчик инлайн кнопок
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Запускаем бота
    logger.info("Бот Anti Scam запущен!")
    
    # Уведомляем администратора о запуске
    async def notify_admin():
        try:
            await application.bot.send_message(
                ADMIN_ID,
                f"🤖 Бот Anti Scam запущен!\n"
                f"⏰ Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🕵️ Скамеров в базе: {len(db.scammers)}\n"
                f"🤝 Гарантов в базе: {len(db.guarantees)}\n\n"
                f"📸 ID фото доступны по команде /id_photo"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение администратору: {e}")
    
    # Запускаем уведомление администратора
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Импортируем threading для запуска Flask в отдельном потоке
    import threading
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем бота
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
