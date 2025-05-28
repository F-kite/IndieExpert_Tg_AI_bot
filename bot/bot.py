import telebot
from telebot import types
from telebot.types import LabeledPrice
from pymongo import MongoClient
from datetime import datetime, timedelta
from dotenv import load_dotenv
from states import BotStates
import openai
from openai import OpenAI
import atexit
import logging
import threading
import sys
import os

import bot.config.messages as messages
import bot.buttons as buttons
from presets.roles import ROLE_PRESETS
from presets.models import AI_PRESETS

# Загрузка переменных окружения
load_dotenv()

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGODB_BOT_URI = os.getenv("MONGODB_BOT_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME")
ADMINS = [int(x.strip()) for x in os.getenv("TELEGRAM_ADMINS_ID", "").split(",") if x.strip()]
SUBSCRIPTION_PRICE=os.getenv("SUBSCRIPTION_PRICE")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Текста
WELCOME_MESSAGE = messages.WELCOME_MESSAGE
AI_MENU_MESSAGE = messages.AI_MENU_MESSAGE
ROLE_MENU_MESSAGE = messages.ROLE_MENU_MESSAGE
SUBSCRIPTION_MESSAGE = messages.SUBSCRIPTION_MESSAGE
HISTORY_MESSAGE = messages.HISTORY_MESSAGE
CLEAR_DIALOG_MESSAGE = messages.CLEAR_DIALOG_MESSAGE
POLICY_MESSAGE = messages.POLICY_MESSAGE

# Панель кнопок
SIDE_BUTTONS = buttons.SIDE_BUTTONS
INLINE_BUTTONS = buttons.INLINE_BUTTONS
AI_MODELS_BUTTONS = buttons.AI_MODELS_BUTTONS

BACK_BUTTON = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)
BOT_ID = bot.get_me().id

user_states = {}

# Инициализация ИИ
client_gpt = OpenAI(api_key=OPENAI_API_KEY)

# --- Логирование событий ---
LOGS_DIR = "../logs"
os.makedirs(LOGS_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOGS_DIR, "app.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()  # Логи также будут выводиться в консоль
    ]
)

logger = logging.getLogger(__name__)

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Вызовы Ctrl+C не логируем
        return sys.__excepthook__(exc_type, exc_value, exc_traceback)
    
    logging.error("Необработанное исключение", exc_info=(exc_type, exc_value, exc_traceback))

# Перехватываем все необработанные исключения
sys.excepthook = handle_exception

@atexit.register
def shutdown_logger():
    logger.info("⛔ Бот остановлен.")

# -------------------------------

def setup_bot_commands():
    bot.set_my_commands([
        types.BotCommand(cmd, desc) for cmd, desc in SIDE_BUTTONS.items()
    ])

# Установка боковой панели кнопок при старте бота
setup_bot_commands()

# --- Подключение к MongoDB ---
 
client = MongoClient(MONGODB_BOT_URI)
db = client[MONGODB_DB_NAME]
users_collection = db["users"]
history_collection = db["history"]

def test_mongo_connection():
    """Проверяет подключение к MongoDB."""
    try:
        # Попытка получить список БД
        client.admin.command('ping')
        logger.info("✅ Настроено соединение с базой данных.")
        return True
    except Exception as e:
        logger.error(f"❌ Не удалось подключиться: {e}")
        return False
if not test_mongo_connection():
    logger.error("⛔ Остановка бота. Проблемы с подключением к базе данных.")
    exit(1)

# -----------------------------

# Проверка, есть ли пользователь в базе
def ensure_user_exists(user):
    # игнорирование бота как пользователя
    if user.id == BOT_ID:
        return

    now = datetime.now()
    user_doc = users_collection.find_one({"user_id": user.id})

    # Если пользователя нет — создаём нового
    if not user_doc:
        request_limits = {}
        for key in AI_PRESETS.keys():
            request_limits[key] = {"count": 0, "last_reset": now}

        user_data = {
            "user_id": user.id,
            "first_name": user.first_name,
            "username": user.username,
            "registered_at": now,
            "last_seen": now,
            "is_subscribed": False,
            "subscription_start":"",
            "subscription_end": "",
            "ai_model": "gpt-4o",
            "role": "default",
            "custom_prompt":"",
            "request_limits": request_limits
        }
        users_collection.insert_one(user_data)
    else:
        is_subscribed = user_doc.get("is_subscribed", False)

        if not is_subscribed:
           users_collection.update_one(
            {"user_id": user.id},
            {"$set": {"ai_model": "gpt-4o", "role":"default"}}
        )
           
        # Сбрасываем лимиты в начале нового месяца
        if user_doc.get("last_month", None) != now.month:
            users_collection.update_one(
                {"user_id": user.id},
                {
                    "$set": {
                        "last_month": now.month,
                        "monthly_usage": {model_key: 0 for model_key in AI_PRESETS.keys()}
                    }
                }
            )
           
        # Если есть — обновляем только last_seen
        users_collection.update_one(
            {"user_id": user.id},
            {"$set": {"last_seen": now}}
        )

def save_query_to_history(user_id, query, response):
    history_collection.insert_one({
        "user_id": user_id,
        "query": query,
        "response": response,
        "timestamp": datetime.now()
    })

def get_user_history(user_id):
    return list(history_collection.find({"user_id": user_id}, {"_id": 0}))

def is_user_subscribed(user_id):
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        return False
    
    # Админы всегда подписаны
    if user_id in ADMINS:
        return True

    return user_data.get("is_subscribed", False)

def clear_user_history(user_id):
    result = history_collection.delete_many({"user_id": user_id})
    logger.info(f"🧹 Пользователь {user_id} очистил свою историю запросов.")
    return result.deleted_count

def get_user_info(user_id):
    return users_collection.find_one({"user_id": user_id})

def auto_delete_message(chat_id, message_id, delay=5):
    def delete():
        try:
            bot.delete_message(chat_id, message_id)
        except Exception as e:
            logger.error(f"❌ Не удалось удалить сообщение в чате {message_id}: {e}")
    
    timer = threading.Timer(delay, delete)
    timer.start()

def safe_edit_message(bot, chat_id, message_id, text, reply_markup=None, parse_mode=None):
    try:
        bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" in str(e):
            # Сообщение не изменилось — ничего страшного
            return False
        else:
            raise  # Другая ошибка — пробрасываем дальше
    return True

def get_current_prompt(user_id):
    user_data = get_user_info(user_id)
    role_key = user_data.get("role", "default")
    custom_prompt = user_data.get("custom_prompt", "")

    if role_key == "custom" and custom_prompt:
        return custom_prompt
    else:
        preset = ROLE_PRESETS.get(role_key, ROLE_PRESETS["default"])
        return preset["prompt"]
    
def check_ai_usage(user_id, ai_model_key):
    now = datetime.now()
    user_data = get_user_info(user_id)
    is_subscribed = user_data.get("is_subscribed", False)

    if is_subscribed:
        return True, ""

    limits = user_data.get("request_limits", {})
    model_limit = limits.get(ai_model_key, {"count": 0, "last_reset": now})

    # Сброс лимита, если начался новый месяц
    last_reset = model_limit["last_reset"]
    if last_reset.month != now.month or last_reset.year != now.year:
        model_limit["count"] = 0
        model_limit["last_reset"] = now
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {f"request_limits.{ai_model_key}": model_limit}}
        )

    if model_limit["count"] >= 2:
        return False, f"❌ Лимит использования {AI_PRESETS[ai_model_key]['name']} исчерпан"

    # Увеличиваем счетчик
    users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {f"request_limits.{ai_model_key}.count": 1}}
    )

    return True, ""
    
def extract_russian_text(text):
    start_index = None
    for i, char in enumerate(text):
        if 'А' <= char.upper() <= 'Я' or char.lower() in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя':
            start_index = i
            break
    if start_index is not None:
        return text[start_index:]
    return ""

# --- Клавиатуры ---
def create_inline_menu(buttons):
    markup = types.InlineKeyboardMarkup()
    buttons_list = list(buttons.items())

    # Добавляем первые две кнопки в одной строке
    if len(buttons_list) >= 2:
        first_key, first_label = buttons_list[0]
        second_key, second_label = buttons_list[1]

        if first_key.startswith("http"):
            btn1 = types.InlineKeyboardButton(first_label, url=first_key)
        else:
            btn1 = types.InlineKeyboardButton(first_label, callback_data=first_key)

        if second_key.startswith("http"):
            btn2 = types.InlineKeyboardButton(second_label, url=second_key)
        else:
            btn2 = types.InlineKeyboardButton(second_label, callback_data=second_key)

        markup.row(btn1, btn2)

    # Остальные кнопки по одной
    for key, label in buttons_list[2:]:
        if key.startswith("http"):
            markup.add(types.InlineKeyboardButton(label, url=key))
        else:
            markup.add(types.InlineKeyboardButton(label, callback_data=key))

    return markup

def create_ai_keyboard(user_id):
    markup = types.InlineKeyboardMarkup()
    
    # Получаем текущую модель из БД
    user_data = get_user_info(user_id)
    current_model_key = user_data.get("ai_model", "gpt-4o")
    is_subscribed = user_data.get("is_subscribed", False)

    models = list(AI_PRESETS.items())
    for i in range(0, len(models), 2):
        row = []
        for key, data in models[i:i+2]:
            model_name = data["name"]
            
            if not is_subscribed and key != "gpt-4o":
                # Для неподписанных пользователей: заблокировать все, кроме gpt-4o
                btn = types.InlineKeyboardButton(f"🔒 {model_name}", callback_data="locked_ai")
            else:
                if key == current_model_key:
                    # Если это текущая модель — показываем галочку
                    btn = types.InlineKeyboardButton(f"✅ {model_name}", callback_data=f"ai_{key}")
                else:
                    # Другие модели для подписчиков
                    btn = types.InlineKeyboardButton(f"{model_name}", callback_data=f"ai_{key}")
                
            row.append(btn)
        
        markup.row(*row)

    # Кнопка "Назад"
    back_button = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
    markup.add(back_button)

    return markup

def create_role_keyboard(user_id):
    markup = types.InlineKeyboardMarkup()

    user_data = get_user_info(user_id)
    current_role_key = user_data.get("role", "default")
    is_subscribed = user_data.get("is_subscribed", False)

    roles = list(ROLE_PRESETS.items())

    for i in range(0, len(roles), 2):
        row = []
        for key, data in roles[i:i+2]:
            role_name = data["name"]
            
            if not is_subscribed and key != "default":
                # Для неподписанных пользователей: заблокировать все, кроме default
                btn = types.InlineKeyboardButton(f"🔒 {extract_russian_text(role_name)}", callback_data="locked_ai")
            else:
                if key == current_role_key:
                    # Если это текущая роль — показываем галочку
                    btn = types.InlineKeyboardButton(f"✅ {extract_russian_text(role_name)}", callback_data=f"role_{key}")
                else:
                    # Другие роли для подписчиков
                    btn = types.InlineKeyboardButton(f"{role_name}", callback_data=f"role_{key}")
                
            row.append(btn)
    
        markup.row(*row)

    # Кнопка "Назад"
    back_button = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
    markup.add(back_button)

    return markup

def create_payment_keyboard():
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton(f"💳 Подписаться за {SUBSCRIPTION_PRICE} ⭐", pay=True)
    markup.add(btn)
    return markup

# --- Обработчик callback'ов ---
@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_back_to_main(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    markup = create_inline_menu(INLINE_BUTTONS)

    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=WELCOME_MESSAGE,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id, "Главное меню")

@bot.callback_query_handler(func=lambda call: call.data == "choose_ai")
def handle_choose_ai(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_doc = users_collection.find_one({"user_id": user_id})

    if not user_doc:
        ensure_user_exists(call.from_user)
        user_doc = users_collection.find_one({"user_id": user_id})

    markup = create_ai_keyboard(user_id)
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text=AI_MENU_MESSAGE,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "choose_role")
def handle_choose_role(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    markup = create_role_keyboard(user_id)
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text=ROLE_MENU_MESSAGE,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "confirm_clear")
def handle_confirm_clear(call):
    user = call.from_user
    deleted_count = clear_user_history(user.id)

    bot.answer_callback_query(call.id, "История очищена")
    bot.send_message(call.message.chat.id, f"🗑️ История успешно очищена. Удалено записей: {deleted_count}")

#заглушка для подписки
@bot.callback_query_handler(func=lambda call:call.data == "subscribe" )
def handle_subscribe(call):
    text = f"""🌟 Подписка стоит всего {SUBSCRIPTION_PRICE} ⭐ в месяц.
Оформите подписку, чтобы получить полный доступ ко всем ИИ и ролям.
Срок подписки 30 дней. 
/subscribe"""
    msg = bot.send_message(call.message.chat.id, text)
    auto_delete_message(call.message.chat.id, msg.message_id)

# добавить сообщение с поддержкой
@bot.callback_query_handler(func=lambda call:call.data == "show_care_service" )
def handle_show_care_service(call):
    bot.answer_callback_query(call.id, "Служба поддержки")

@bot.callback_query_handler(func=lambda call:call.data == "show_profile" )
def handle_show_profile(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    message_id = call.message.message_id

    user_profile = get_user_info(user_id)
    markup = types.InlineKeyboardMarkup()

    if not user_profile:
        # bot.answer_callback_query(call.id, "❌ Профиль не найден.")
        msg = bot.send_message(chat_id, "❌ Профиль не найден.")
        auto_delete_message(chat_id, msg.message_id)
        return
    
    model_name = AI_PRESETS.get(user_profile.get("ai_model", "default"), {}).get("name","Неизвестная модель")
    role_name = ROLE_PRESETS.get(user_profile.get("role", "default"), {}).get("name", "Неизвестная роль")
    
    text = f"""
👤 Ваш профиль:

🔹 Пользователь: {user_profile.get('username')}
🔹 Подписка: {"✅" if user_profile.get("is_subscribed", False) else "❌"}
🔹 Дата регистрации: {user_profile.get("registered_at").strftime("%Y-%m-%d")}
🔹 Текущая модель ИИ: {model_name}
🔹 Текущая роль бота: {extract_russian_text(role_name)}
"""
    
    back_btn = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
    markup.add(back_btn)

    bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
    bot.answer_callback_query(call.id, "Профиль")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if user_id == BOT_ID:
        logging.warning(f"⚠️ Callback от бота — игнорируется.\n`{ call.message.text}`")
        return

    elif call.data.startswith("ai_"):
        model_key = call.data[3:]
        model_data = AI_PRESETS.get(model_key)
        user_doc = users_collection.find_one({"user_id": user_id})
        is_subscribed = user_doc.get("is_subscribed", False)

        if not is_subscribed and model_key != "gpt-4o":
            msg = bot.send_message(chat_id, "❗️Подпишись, чтобы разблокировать эту модель")
            auto_delete_message(chat_id, msg.message_id)
            return
        
        if model_key == get_user_info(user_id).get("ai_model"):
            bot.answer_callback_query(call.id, "✅ Модель уже выбрана")
            return

        users_collection.update_one({"user_id": user_id}, {"$set": {"ai_model": model_key}})
        description = model_data["description"]
        name = model_data["name"]

        text = f"""
🧠 *{name}*

ℹ️ _{description}_
"""
        
        users_collection.update_one({"user_id": user_id}, {"$set": {"ai_model": model_key}})
        bot.answer_callback_query(call.id, f"Выбрана модель {AI_PRESETS[model_key]['name']}")
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=create_ai_keyboard(user_id),
                parse_mode="Markdown"
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e):
                return
            else:
                logger.error(f"❌ Не удалось обновить сообщение: {e}")

    elif call.data.startswith("role_"):
        role_key = call.data[5:]
        role_data = ROLE_PRESETS.get(role_key)
        user_doc = users_collection.find_one({"user_id": user_id})
        is_subscribed = user_doc.get("is_subscribed", False)

        if not is_subscribed and role_key != "default":
            msg = bot.send_message(chat_id, "❗️Подпишись, чтобы разблокировать эту роль")
            auto_delete_message(chat_id, msg.message_id)
            return
        
        if role_key == get_user_info(user_id).get("role"):
            bot.answer_callback_query(call.id, "✅ Роль уже выбрана")
            return
        
        if role_key == "custom":
            cmd_custom_role(call.message)
            return
        else:
            users_collection.update_one({"user_id": user_id}, {"$set": {"role": role_key}})
            description = role_data["description"]
            name = role_data["name"]

            text = f"""
*{name}*

ℹ️ _{description}_
    """
              
            bot.answer_callback_query(call.id, f"Выбрана роль {name}")
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=create_role_keyboard(user_id),
                parse_mode="Markdown"
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e):
                return
            else:
                logger.error(f"❌ Не удалось обновить сообщение: {e}")



# --- Обработчики команд ---
@bot.message_handler(commands=["start"])
def cmd_send_welcome(message):    
    ensure_user_exists(message.from_user)
    markup = create_inline_menu(INLINE_BUTTONS)
    bot.send_message(message.chat.id, WELCOME_MESSAGE, reply_markup=markup)

@bot.message_handler(commands=["profile"])
def cmd_send_profile(message):
    user_id = message.from_user.id
    user_profile = get_user_info(user_id)
    is_admin =  ""
    if user_id in ADMINS : is_admin = "🔆 Царь и бог (администратор)"

    if not user_profile:
        msg = bot.send_message(message.chat.id, "❌ Профиль не найден.")
        auto_delete_message(message.chat.id, msg.message_id)
        return
    
    response = f"""
👤 Ваш профиль:

🔹 Пользователь: {user_profile.get('username')}
🔹 Подписка: {"✅" if user_profile.get("is_subscribed", False) else "❌"}
🔹 Дата регистрации: {user_profile.get("registered_at").strftime("%Y-%m-%d")}
🔹 Текущая модель ИИ: {user_profile.get("ai_model", "не выбрана")}
🔹 Текущая роль бота: {ROLE_PRESETS.get(user_profile.get("role", "default"), {}).get("name", "Неизвестная роль")}
"""
    if is_admin:
        response += f"\n{is_admin}"

    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=["choose_ai"])
def cmd_choose_ai(message):
    user = message.from_user
    user_id = user.id
    ensure_user_exists(user)
    
    user_data = get_user_info(user_id)
    if not user_data.get("is_subscribed", False) and AI_PRESETS[user_data.get("ai_model", "gpt-4o")] != "gpt-4o":
        msg = bot.send_message(message.chat.id, "🔒 Нужна подписка, чтобы выбрать другую модель")
        auto_delete_message(message.chat.id, msg.message_id)
        return
    
    markup = create_ai_keyboard(user_id)
    bot.send_message(message.chat.id, AI_MENU_MESSAGE, reply_markup=markup)

@bot.message_handler(commands=["choose_role"])
def cmd_choose_role(message):
    user = message.from_user
    user_id = user.id
    ensure_user_exists(user)

    user_data = get_user_info(user_id)
    if not user_data.get("is_subscribed", False):
        
        msg = bot.send_message(
            message.chat.id,
            "❌ К сожалению, эта функция доступна только подписчикам.\nДля активации подписки используйте команду /subscribe"
        )
        auto_delete_message(message.chat.id, msg.message_id)
        return

    markup = create_role_keyboard(user_id)
    bot.send_message(message.chat.id, ROLE_MENU_MESSAGE, reply_markup=markup, parse_mode="Markdown")

# --- Подписка \ отписка  ---
@bot.message_handler(commands=["subscribe"])
def cmd_subscribe(message):
    user = message.from_user
    user_id = user.id
    chat_id = message.chat.id
    ensure_user_exists(user)

    if is_user_subscribed(user_id):
        msg = bot.send_message(
            message.chat.id,
            "🔆 Вы уже оформили подписку, вторая не принесет новых возможностей"
        )
        auto_delete_message(message.chat.id, msg.message_id)
        return

    if user_id in ADMINS:
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"is_subscribed": True, "subscription_end": None}}  # Без ограничения по времени
        )
        msg = bot.send_message(message.chat.id, "👑 Вы — админ. Подписка активна навсегда.")
        auto_delete_message(message.chat.id, msg.message_id)
        return

    # Генерируем ссылку на покупку через @invoice
    title = "Подписка на бота"
    description = "‼️ Оформление подписки не подразумевает возврата средств в будущем"
    payload = f"sub_{user_id}_{int(datetime.now().timestamp())}"
    currency = "XTR"
    provider_token=""
    prices = [LabeledPrice(label="Ежемесячная подписка", amount=SUBSCRIPTION_PRICE)]
    # photo_url = "https://example.com/subscription_image.jpg "  # Необязательно

    bot.send_invoice(
            chat_id,
            title=title,
            description=description,
            invoice_payload=payload,
            currency=currency,
            prices=prices,
            provider_token=provider_token,
            # photo_url=photo_url,
            is_flexible=False,
            allow_paid_broadcast=True,  # Разрешаем оплату через Stars
            reply_markup=create_payment_keyboard()
        )

@bot.message_handler(commands=["unsubscribe"])
def cmd_unsubscribe(message):
    user = message.from_user
    user_id = user.id
    ensure_user_exists(user)
    
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"is_subscribed": False}}
    )
    bot.send_message(message.chat.id, "❌ Вы отписались от бота.")


# --- Обработка подписки ---
@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=["successful_payment"])
def handle_successful_payment(message):
    user_id = message.from_user.id
    payment_info = message.successful_payment
    logger.info(f"💰 Пользователь {user_id} оплатил подписку: {payment_info.total_amount} {payment_info.currency}")

    users_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "is_subscribed": True,
                "subscription_start": datetime.now(),
                "subscription_end": datetime.now() + timedelta(days=30)
            }
        }
    )
    bot.send_message(message.chat.id, "✅ Вы успешно оформили подписку на 30 дней!")

# --- ---------------------------- ---

@bot.message_handler(commands=["history"])
def cmd_send_history(message):
    user_id = message.from_user.id
    history = get_user_history(user_id)
    if not history:
        msg =bot.send_message(message.chat.id, "История запросов пуста.")
        auto_delete_message(message.chat.id, msg.message_id)
        return

    response = f"{HISTORY_MESSAGE}\n\n"
    for item in history:
        response += f"\n🔹 {item['query']}\n🤖 {item['response']}\n"

    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=["clear_history"])
def cmd_confirm_clear_history(message):
    markup = types.InlineKeyboardMarkup()
    confirm_btn = types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_clear")
    back_btn = types.InlineKeyboardButton("❌ Отмена", callback_data="back_to_main")
    markup.row(confirm_btn, back_btn)
    text = "⚠️ После очистки истории вы безвозвратно потеряете возможность просмотретиь ваши старые запросы.\nВы уверены, что хотите очистить историю запросов?"

    bot.send_message(message.chat.id, CLEAR_DIALOG_MESSAGE, reply_markup=markup)

@bot.message_handler(commands=["policy"])
def cmd_send_policy(message):
    bot.send_message(message.chat.id, POLICY_MESSAGE, parse_mode="Markdown")

@bot.message_handler(commands=["custom_role"])
def cmd_custom_role(message):
    msg =  bot.send_message(message.chat.id, "⚠️ Функция находится в разработке")
    auto_delete_message(message.chat.id, msg.message_id)
    return
    user = message.from_user
    ensure_user_exists(user)
    user_id = user.id

    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"role": "custom"}}
    )

    bot.send_message(message.chat.id, """
✏️ Введите свой системный промпт.
Пример:
"Вы — личный коуч, который помогает людям находить себя и менять жизнь."

Ваш промпт:
""")
    user_states[user_id] = "waiting_for_custom_prompt"

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "waiting_for_custom_prompt")
def handle_custom_prompt(message):
    user_id = message.from_user.id
    user_input = message.text.strip()

    if not user_input:
        msg = bot.send_message(message.chat.id, "⚠️ Промпт не может быть пустым.")
        auto_delete_message(message.chat.id, msg.message_id)
        return

    # Сохраняем в БД
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"custom_prompt": user_input}}
    )

    # Выходим из режима ожидания
    user_states.pop(user_id, None)

    msg = bot.send_message(message.chat.id, f"✅ Ваш новый промпт установлен:\n\n*{user_input}*", parse_mode="Markdown")
    auto_delete_message(message.chat.id, msg.message_id)


# Обработчик других сообщений
@bot.message_handler(func=lambda message: True)
def cmd_handle_message(message):
    user = message.from_user
    chat_id = message.chat.id
    user_input = message.text
    ensure_user_exists(user)

    def get_key_by_name(name):
        for key, data in AI_PRESETS.items():
            if data.get("name") == name:
                return key
        return None  # Если не найдено



    try:
        user_data = get_user_info(user.id)
        ai_preset = AI_PRESETS.get(user_data["ai_model"], AI_PRESETS["gpt-4o"])
        ai_model = get_key_by_name(ai_preset["name"])
        
        role_prompt = get_current_prompt(user.id)
        user_prompt = user_input

        # Проверяем подписку и лимиты
        allowed, reason = check_ai_usage(user.id, user_data["ai_model"])
        if not allowed:
            msg = bot.send_message(chat_id, reason + ".\n\nС подпиской ограничения на использование ИИ исчезнут")
            auto_delete_message(chat_id, msg.message_id, 3)
            return

        # Реальный вызов gpt-3.5-turbo или gpt-4o
        response = client_gpt.chat.completions.create(
            model=ai_model,
            messages=[
                {"role": "system", "content": role_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=ai_preset["temperature"],
            max_tokens=300,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0
        )

        ai_response = response.choices[0].message.content.strip()
        save_query_to_history(user.id, user_input, ai_response)
        bot.send_message(chat_id, ai_response)

    except openai.RateLimitError as e:
        msg = bot.send_message(chat_id, "❌ Превышен лимит обращений к OpenAI. Подождите немного.")
        auto_delete_message(chat_id, msg.message_id, 3)
        logger.error(f"Rate limit error: {e}")

    except openai.APIError as e:
        msg = bot.send_message(chat_id, "❌ Ошибка при обращении к нейросети.")
        auto_delete_message(chat_id, msg.message_id, 3)
        logger.error(f"OpenAI API error: {e}")

    except Exception as e:
        msg = bot.send_message(chat_id, "❌ Неизвестная ошибка при обращении к нейросети.")
        auto_delete_message(chat_id, msg.message_id, 3)
        logger.error(f"Ошибка: {e}")



# --- Запуск бота ---
if __name__ == "__main__":
    logger.info("🚀 Бот запущен...")
    bot.polling(none_stop=True)
