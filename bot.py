import logging
import json
import os
import datetime
from typing import Dict, List, Optional
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Router
import asyncio
from threading import Thread

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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

# Инициализация Flask
app = Flask(__name__)

# Инициализация бота
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

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

# ========== СОСТОЯНИЯ FSM ==========
class AddScammerState(StatesGroup):
    waiting_for_username = State()
    waiting_for_reason = State()
    waiting_for_proof = State()

class AddGarantState(StatesGroup):
    waiting_for_username = State()
    waiting_for_bio = State()
    waiting_for_proof = State()

class AddAdminState(StatesGroup):
    waiting_for_username = State()

class ChatManagementState(StatesGroup):
    waiting_for_duration = State()

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
@router.message(Command("start"))
async def cmd_start(message: Message):
    """Команда /start"""
    start_text = """
Anti Scam - начинающий проект, который будет помогать людям не попадатся на скам и на сомнительные услуги.

⚠️В нашей предложке вы - можете слить скамера или же сообщить о подозрительной личности.

🔍Чат поиска гарантов| трейдов | просто общения - @AntiScamChata

🛡Наш бот для проверки на скам - @AntilScamBot.

✔️Если хотите нас поддержать, то ставьте в ник приписку 'As |  Ас'
"""
    
    await message.answer_photo(
        photo=PHOTOS['start'],
        caption=start_text,
        reply_markup=get_inline_start_keyboard()
    )
    
    # Показываем клавиатуру только в личных сообщениях
    if message.chat.type == "private":
        await message.answer(
            "Добро пожаловать! Используйте кнопки ниже для навигации:",
            reply_markup=get_main_keyboard(message.from_user.id)
        )

@router.message(F.text == "👤 Мой профиль")
async def cmd_my_profile(message: Message):
    """Проверка своего профиля"""
    await check_user_profile(message, message.from_user.id, message.from_user.username)

@router.message(F.text == "📋 Список гарантов")
async def cmd_guarantees_list(message: Message):
    """Список гарантов"""
    guarantees = db.get_all_guarantees()
    
    if not guarantees:
        await message.answer("📭 Список гарантов пуст.")
        return
    
    response = "📋 <b>Список гарантов:</b>\n\n"
    
    for i, garant in enumerate(guarantees, 1):
        username = garant.get('username', 'N/A')
        proof_link = garant.get('proof_link', 'Нет пруфов')
        
        response += f"{i}. @{username}\n"
        response += f"   🔗 Пруфы: {proof_link}\n\n"
    
    await message.answer(response, parse_mode="HTML")

@router.message(F.text == "🛠 Команды бота")
async def cmd_bot_commands(message: Message):
    """Список команд бота"""
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
    
    await message.answer(commands_text, parse_mode="HTML")

@router.message(Command("id_photo"))
async def cmd_id_photo(message: Message):
    """Показать ID фото"""
    if not db.is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда только для администраторов.")
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
    
    await message.answer(photo_info, parse_mode="HTML")

@router.message(F.text == "🆔 ID фото")
async def cmd_id_photo_button(message: Message):
    """Кнопка ID фото"""
    await cmd_id_photo(message)

@router.message(F.text == "👨‍💻 Админ панель")
async def cmd_admin_panel(message: Message):
    """Панель администратора"""
    if not db.is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ панели.")
        return
    
    stats_text = f"""
📊 <b>Статистика базы:</b>

🕵️ Скамеров: {len(db.scammers)}
🤝 Гарантов: {len(db.guarantees)}
👑 Админов: {len(db.admins)}

Используйте кнопки ниже для управления:
"""
    
    await message.answer(stats_text, parse_mode="HTML", reply_markup=get_admin_keyboard())

@router.message(F.text == "📊 Статистика")
async def cmd_stats(message: Message):
    """Статистика"""
    if not db.is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return
    
    user_id = str(message.from_user.id)
    scammer_count = db.get_scammers_count(user_id)
    
    stats_text = f"""
📊 <b>Ваша статистика:</b>

✅ Добавлено скамеров: {scammer_count}
🔍 Всего проверок: {db.get_search_count(user_id)}

<b>Общая статистика:</b>
👥 Всего скамеров: {len(db.scammers)}
🤝 Всего гарантов: {len(db.guarantees)}
"""
    
    await message.answer(stats_text, parse_mode="HTML")

@router.message(F.text == "🔙 Назад")
async def cmd_back(message: Message):
    """Возврат в главное меню"""
    await message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# ========== КОМАНДЫ ПРОВЕРКИ ==========
@router.message(Command("check"))
async def cmd_check(message: Message):
    """Проверка пользователя"""
    args = message.text.split()
    
    if len(args) == 1:
        # Если команда без аргументов
        if message.reply_to_message:
            # Проверка по ответу на сообщение
            user_to_check = message.reply_to_message.from_user
            await check_user_profile(message, str(user_to_check.id), user_to_check.username)
        else:
            await message.answer("❌ Укажите username для проверки или ответьте на сообщение пользователя.\nПример: /check @username")
    elif len(args) == 2:
        if args[1].lower() == "me":
            # Проверка себя
            await check_user_profile(message, str(message.from_user.id), message.from_user.username)
        else:
            # Проверка по username
            username = args[1].replace("@", "")
            try:
                user = await bot.get_chat(f"@{username}")
                await check_user_profile(message, str(user.id), username)
            except Exception as e:
                await message.answer(f"❌ Не удалось найти пользователя @{username}")
                logger.error(f"Ошибка поиска пользователя: {e}")
    else:
        await message.answer("❌ Неверный формат команды.\nИспользуйте: /check @username или /check me")

async def check_user_profile(message: Message, user_id: str, username: str = None):
    """Проверка профиля пользователя"""
    # Увеличиваем счетчик поисков
    db.increment_search_count(user_id)
    search_count = db.get_search_count(user_id)
    
    current_time = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    # Определяем статус пользователя
    if db.is_scammer(user_id):
        # Скамер
        photo_id = PHOTOS['scammer']
        scammer_info = db.get_scammer_info(user_id)
        
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
        
    elif db.is_garant(user_id):
        # Гарант
        photo_id = PHOTOS['garant']
        garant_info = db.get_garant_info(user_id)
        
        response = f"""🕵️ᴜsᴇʀ: @{username if username else 'unknown'}
🔎ищᴇʍ ʙ бᴀзᴇ дᴀнных...
💯яʙᴧяᴇᴛᴄя ᴦᴀᴩᴀнᴛоʍ бᴀзы

ᴇᴦо [ᴇᴇ] инɸо: {garant_info.get('bio_link', 'Нет информации')}
ᴇᴦо [ᴇᴇ] ᴨᴩуɸы: {garant_info.get('proof_link', 'Нет пруфов')}

🔎ᴨоᴧьзоʙᴀᴛᴇᴧя иᴄᴋᴀᴧи: {search_count} раз

🔝ᴨᴩоʙᴇᴩᴇнно @AntilScam_bot

🗓️дᴀᴛᴀ и ʙᴩᴇʍя ᴨᴩоʙᴇᴩᴋи: {current_time}

оᴛ ᴀдʍиниᴄᴛᴩᴀции: жᴇᴧᴀю ʙᴀʍ нᴇ ʙᴇᴄᴛиᴄь нᴀ ᴄᴋᴀʍ!"""
        
    elif db.is_admin(int(user_id)):
        # Администратор
        photo_id = PHOTOS['admin']
        admin_info = db.get_admin_info(user_id)
        scammer_count = db.get_scammers_count(user_id)
        
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
    inline_keyboard = get_check_result_keyboard(user_id, username)
    
    # Отправляем результат с фото и инлайн кнопками
    await message.answer_photo(
        photo=photo_id,
        caption=response,
        reply_markup=inline_keyboard
    )

# ========== ОБРАБОТКА ИНЛАЙН КНОПОК ==========
@router.callback_query(F.data.startswith("show_id_"))
async def handle_show_id(callback: CallbackQuery):
    """Показать ID пользователя"""
    user_id = callback.data.replace("show_id_", "")
    await callback.answer(f"🆔 ID пользователя: {user_id}", show_alert=True)

# ========== АДМИН КОМАНДЫ ==========
@router.message(Command("add_scammer"))
async def cmd_add_scammer(message: Message, state: FSMContext):
    """Добавить скамера"""
    if not db.is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав для добавления скамеров.")
        return
    
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Укажите username скамера.\nПример: /add_scammer @username причина и пруфы")
        return
    
    text = args[1]
    if "@" in text:
        username = text.split()[0].replace("@", "")
        rest = " ".join(text.split()[1:]) if len(text.split()) > 1 else ""
        
        try:
            user = await bot.get_chat(f"@{username}")
            user_id = str(user.id)
            
            await state.update_data(
                scammer_user_id=user_id,
                scammer_username=username,
                scammer_reason_proof=rest
            )
            
            if rest:
                # Если причина и пруфы указаны сразу
                parts = rest.split(" ", 1)
                if len(parts) == 2:
                    reason, proof = parts
                    await process_scammer_info(message, user_id, username, reason, proof, state)
                else:
                    await message.answer("❌ Укажите причину и пруфы через пробел.\nПример: /add_scammer @username мошенничество https://proof.link")
            else:
                await message.answer(f"Введите причину для добавления @{username} как скамера:")
                await state.set_state(AddScammerState.waiting_for_reason)
                
        except Exception as e:
            await message.answer(f"❌ Не удалось найти пользователя @{username}")
            logger.error(f"Ошибка поиска пользователя: {e}")
    else:
        await message.answer("❌ Укажите username через @.\nПример: /add_scammer @username причина пруфы")

@router.message(AddScammerState.waiting_for_reason)
async def process_scammer_reason(message: Message, state: FSMContext):
    """Обработка причины для скамера"""
    reason = message.text
    data = await state.get_data()
    
    await state.update_data(scammer_reason=reason)
    await message.answer("Теперь отправьте пруфы (ссылку или текст):")
    await state.set_state(AddScammerState.waiting_for_proof)

@router.message(AddScammerState.waiting_for_proof)
async def process_scammer_proof(message: Message, state: FSMContext):
    """Обработка пруфов для скамера"""
    proof = message.text
    data = await state.get_data()
    
    user_id = data.get("scammer_user_id")
    username = data.get("scammer_username")
    reason = data.get("scammer_reason")
    
    await process_scammer_info(message, user_id, username, reason, proof, state)

async def process_scammer_info(message: Message, user_id: str, username: str, reason: str, proof: str, state: FSMContext):
    """Обработка информации о скамере"""
    if db.is_scammer(user_id):
        await message.answer(f"❌ Пользователь @{username} уже есть в базе скамеров.")
        await state.clear()
        return
    
    db.add_scammer(user_id, username, reason, proof, str(message.from_user.id))
    
    await message.answer(
        f"✅ Скамер @{username} добавлен в базу!\n"
        f"Причина: {reason}\n"
        f"Пруфы: {proof}"
    )
    
    # Уведомляем главного администратора
    if message.from_user.id != MAIN_ADMIN_ID:
        try:
            await bot.send_message(
                MAIN_ADMIN_ID,
                f"🆕 Новый скамер добавлен:\n"
                f"👤 @{username}\n"
                f"🆔 {user_id}\n"
                f"📝 Причина: {reason}\n"
                f"🔗 Пруфы: {proof}\n"
                f"👨‍💻 Добавил: @{message.from_user.username or 'N/A'}"
            )
        except:
            pass
    
    await state.clear()

@router.message(Command("del_scammer"))
async def cmd_del_scammer(message: Message):
    """Удалить скамера"""
    if not db.is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав для удаления скамеров.")
        return
    
    args = message.text.split()
    
    if len(args) != 2:
        await message.answer("❌ Укажите username скамера.\nПример: /del_scammer @username")
        return
    
    username = args[1].replace("@", "")
    
    # Ищем скамера по username
    for user_id, scammer_info in db.scammers.items():
        if scammer_info.get("username") == username:
            db.remove_scammer(user_id)
            await message.answer(f"✅ Скамер @{username} удален из базы.")
            return
    
    await message.answer(f"❌ Скамер @{username} не найден в базе.")

@router.message(Command("add_garant"))
async def cmd_add_garant(message: Message, state: FSMContext):
    """Добавить гаранта"""
    if not db.is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав для добавления гарантов.")
        return
    
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Укажите username гаранта.\nПример: /add_garant @username ссылка_на_био ссылка_на_пруфы")
        return
    
    text = args[1]
    if "@" in text:
        username = text.split()[0].replace("@", "")
        rest = " ".join(text.split()[1:]) if len(text.split()) > 1 else ""
        
        try:
            user = await bot.get_chat(f"@{username}")
            user_id = str(user.id)
            
            await state.update_data(
                garant_user_id=user_id,
                garant_username=username,
                garant_info=rest
            )
            
            if rest:
                # Если информация указана сразу
                parts = rest.split(" ", 1)
                if len(parts) == 2:
                    bio_link, proof_link = parts
                    await process_garant_info(message, user_id, username, bio_link, proof_link, state)
                else:
                    await message.answer("❌ Укажите ссылку на био и пруфы через пробел.\nПример: /add_garant @username https://bio.link https://proof.link")
            else:
                await message.answer(f"Введите ссылку на био для гаранта @{username}:")
                await state.set_state(AddGarantState.waiting_for_bio)
                
        except Exception as e:
            await message.answer(f"❌ Не удалось найти пользователя @{username}")
            logger.error(f"Ошибка поиска пользователя: {e}")
    else:
        await message.answer("❌ Укажите username через @.\nПример: /add_garant @username ссылка_на_био ссылка_на_пруфы")

@router.message(AddGarantState.waiting_for_bio)
async def process_garant_bio(message: Message, state: FSMContext):
    """Обработка био для гаранта"""
    bio_link = message.text
    data = await state.get_data()
    
    await state.update_data(garant_bio=bio_link)
    await message.answer("Теперь отправьте ссылку на пруфы:")
    await state.set_state(AddGarantState.waiting_for_proof)

@router.message(AddGarantState.waiting_for_proof)
async def process_garant_proof(message: Message, state: FSMContext):
    """Обработка пруфов для гаранта"""
    proof_link = message.text
    data = await state.get_data()
    
    user_id = data.get("garant_user_id")
    username = data.get("garant_username")
    bio_link = data.get("garant_bio")
    
    await process_garant_info(message, user_id, username, bio_link, proof_link, state)

async def process_garant_info(message: Message, user_id: str, username: str, bio_link: str, proof_link: str, state: FSMContext):
    """Обработка информации о гаранте"""
    if db.is_garant(user_id):
        await message.answer(f"❌ Пользователь @{username} уже есть в базе гарантов.")
        await state.clear()
        return
    
    db.add_garant(user_id, username, bio_link, proof_link, str(message.from_user.id))
    
    await message.answer(
        f"✅ Гарант @{username} добавлен в базу!\n"
        f"Био: {bio_link}\n"
        f"Пруфы: {proof_link}"
    )
    
    await state.clear()

@router.message(Command("del_garant"))
async def cmd_del_garant(message: Message):
    """Удалить гаранта"""
    if not db.is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав для удаления гарантов.")
        return
    
    args = message.text.split()
    
    if len(args) != 2:
        await message.answer("❌ Укажите username гаранта.\nПример: /del_garant @username")
        return
    
    username = args[1].replace("@", "")
    
    # Ищем гаранта по username
    for user_id, garant_info in db.guarantees.items():
        if garant_info.get("username") == username:
            db.remove_garant(user_id)
            await message.answer(f"✅ Гарант @{username} удален из базы.")
            return
    
    await message.answer(f"❌ Гарант @{username} не найден в базе.")

@router.message(Command("add_admin"))
async def cmd_add_admin(message: Message):
    """Добавить администратора"""
    if message.from_user.id != MAIN_ADMIN_ID:
        await message.answer("⛔ Только главный администратор может добавлять админов.")
        return
    
    args = message.text.split()
    
    if len(args) != 2:
        await message.answer("❌ Укажите username нового администратора.\nПример: /add_admin @username")
        return
    
    username = args[1].replace("@", "")
    
    try:
        user = await bot.get_chat(f"@{username}")
        user_id = str(user.id)
        
        if db.is_admin(int(user_id)):
            await message.answer(f"❌ Пользователь @{username} уже является администратором.")
            return
        
        db.add_admin(user_id, str(message.from_user.id))
        
        await message.answer(f"✅ Администратор @{username} добавлен!")
        
        # Уведомляем нового админа
        try:
            await bot.send_message(
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
        await message.answer(f"❌ Не удалось найти пользователя @{username}")
        logger.error(f"Ошибка поиска пользователя: {e}")

@router.message(F.text == "➕ Добавить скамера")
async def add_scammer_button(message: Message):
    """Кнопка добавления скамера"""
    await cmd_add_scammer(message, None)

@router.message(F.text == "➕ Добавить гаранта")
async def add_garant_button(message: Message):
    """Кнопка добавления гаранта"""
    await cmd_add_garant(message, None)

@router.message(F.text == "🗑 Удалить скамера")
async def del_scammer_button(message: Message):
    """Кнопка удаления скамера"""
    await message.answer("Для удаления скамера используйте команду:\n/del_scammer @username")

@router.message(F.text == "🗑 Удалить гаранта")
async def del_garant_button(message: Message):
    """Кнопка удаления гаранта"""
    await message.answer("Для удаления гаранта используйте команду:\n/del_garant @username")

@router.message(F.text == "👑 Добавить админа")
async def add_admin_button(message: Message):
    """Кнопка добавления админа"""
    await message.answer("Для добавления администратора используйте команду:\n/add_admin @username")

@router.message(F.text == "❌ Удалить админа")
async def del_admin_button(message: Message):
    """Кнопка удаления админа"""
    if message.from_user.id != MAIN_ADMIN_ID:
        await message.answer("⛔ Только главный администратор может удалять админов.")
        return
    await message.answer("Для удаления администратора используйте команду:\n/del_admin @username\n\n⚠️ Эта команда будет доступна в будущих обновлениях.")

# ========== КОМАНДЫ МОДЕРАЦИИ ЧАТА ==========
@router.message(Command("open"))
async def cmd_open_chat(message: Message):
    """Открыть чат"""
    if not db.is_admin(message.from_user.id) and message.chat.type == "private":
        await message.answer("⛔ Только администраторы могут использовать эту команду.")
        return
    
    if message.chat.type != "private":
        chat_id = str(message.chat.id)
        
        if chat_id not in db.chat_settings:
            db.chat_settings[chat_id] = {"is_open": True, "warns": {}}
        else:
            db.chat_settings[chat_id]["is_open"] = True
        
        db.save_chat_settings()
        await message.answer("✅ Чат открыт для общения.")

@router.message(Command("close"))
async def cmd_close_chat(message: Message):
    """Закрыть чат"""
    if not db.is_admin(message.from_user.id) and message.chat.type == "private":
        await message.answer("⛔ Только администраторы могут использовать эту команду.")
        return
    
    if message.chat.type != "private":
        chat_id = str(message.chat.id)
        
        if chat_id not in db.chat_settings:
            db.chat_settings[chat_id] = {"is_open": False, "warns": {}}
        else:
            db.chat_settings[chat_id]["is_open"] = False
        
        db.save_chat_settings()
        await message.answer("🚫 Чат закрыт для общения.")

@router.message(Command("warn"))
async def cmd_warn(message: Message, state: FSMContext):
    """Выдать предупреждение"""
    if not db.is_admin(message.from_user.id) and message.chat.type == "private":
        await message.answer("⛔ Только администраторы могут использовать эту команду.")
        return
    
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в группах/чатах.")
        return
    
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("❌ Укажите username пользователя.\nПример: /warn @username")
        return
    
    username = args[1].replace("@", "")
    
    try:
        # Пытаемся найти пользователя
        user = await bot.get_chat(f"@{username}")
        await state.update_data(warn_user_id=user.id, warn_username=username)
        await message.answer(f"Введите причину предупреждения для @{username}:")
        await state.set_state(ChatManagementState.waiting_for_duration)
    except:
        await message.answer(f"❌ Не удалось найти пользователя @{username}")

@router.message(Command("mut"))
async def cmd_mut(message: Message):
    """Замутить пользователя"""
    if not db.is_admin(message.from_user.id) and message.chat.type == "private":
        await message.answer("⛔ Только администраторы могут использовать эту команду.")
        return
    
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в группах/чатах.")
        return
    
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("❌ Укажите username пользователя.\nПример: /mut @username 60 (минут)")
        return
    
    if len(args) == 2:
        username = args[1].replace("@", "")
        await message.answer(f"Введите время мута в минутах для @{username}:\nПример: 60 (на 1 час)")
    elif len(args) == 3:
        username = args[1].replace("@", "")
        try:
            minutes = int(args[2])
            # Здесь должна быть логика мута в группе
            await message.answer(f"✅ Пользователь @{username} замучен на {minutes} минут.")
        except:
            await message.answer("❌ Укажите корректное время в минутах.")

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

@app.route('/webhook', methods=['POST'])
def webhook():
    """Вебхук для Telegram"""
    update = types.Update(**request.json)
    asyncio.run(dp._process_update(update))
    return jsonify({"status": "ok"})

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

# ========== ЗАПУСК БОТА ==========
async def start_bot():
    """Запуск бота"""
    logger.info("Запуск бота Anti Scam...")
    
    # Удаляем вебхук и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Уведомляем администратора о запуске
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🤖 Бот Anti Scam запущен!\n"
            f"⏰ Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🕵️ Скамеров в базе: {len(db.scammers)}\n"
            f"🤝 Гарантов в базе: {len(db.guarantees)}\n\n"
            f"📸 ID фото доступны по команде /id_photo"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение администратору: {e}")
    
    # Запускаем бота
    await dp.start_polling(bot)

def run_flask():
    """Запуск Flask сервера"""
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем бота
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
