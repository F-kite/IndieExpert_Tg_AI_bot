import telebot
from telebot import types
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
import openai
import atexit
import logging
import sys
import os

import messages
from presets.roles import ROLE_PRESETS
from presets.models import AI_PRESETS
from states import BotStates

# Загрузка переменных окружения
load_dotenv()

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME")

BACK_BUTTON = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)
openai.api_key = OPENAI_API_KEY

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
        types.BotCommand(cmd, desc) for cmd, desc in messages.SIDE_BUTTONS.items()
    ])
    logging.info("✅ Команды для бота корректно установлены")


# Вызов при старте бота
setup_bot_commands()

# --- Подключение к MongoDB ---
client = MongoClient(MONGODB_URI)
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

# Проверка, есть ли пользователь в базе
def ensure_user_exists(user):
    now = datetime.now()
    
    user_doc = users_collection.find_one({"user_id": user.id})

    if not user_doc:
        # Если пользователя нет — создаём нового
        user_data = {
            "user_id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "registered_at": now,
            "last_seen": now,
            "is_subscribed": False,
            "ai_model": "gpt4o",
            "role": "default",
        }
        users_collection.insert_one(user_data)
    else:
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

def get_user_info(user_id):
    return users_collection.find_one({"user_id": user_id})

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

def create_ai_model_keyboard():
    markup = types.InlineKeyboardMarkup()

    # Группируем по 2 кнопки в строке
    models = list(messages.AI_MODELS.items())
    for i in range(0, len(models), 2):
        row = []
        for key, label in models[i:i+2]:
            row.append(types.InlineKeyboardButton(label, callback_data=f"ai_{key}"))
        markup.row(*row)

    # Кнопка "Назад"
    back_button = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
    markup.add(back_button)

    return markup


def create_ai_keyboard():
    markup = types.InlineKeyboardMarkup()
    for key, data in AI_PRESETS.items():
        btn = types.InlineKeyboardButton(f"🧠 {data['name']}", callback_data=f"ai_{key}")
        markup.add(btn)
    markup.add(BACK_BUTTON)
    return markup

def create_role_keyboard():
    markup = types.InlineKeyboardMarkup()

    for key, data in ROLE_PRESETS.items():
        btn = types.InlineKeyboardButton(data["name"], callback_data=f"role_{key}")
        markup.add(btn)

    back_button = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
    markup.add(back_button)

    return markup


# Обработчик callback'ов
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    message_id = call.message.message_id

    if call.data == "show_profile":
        text = "👤 Ваш профиль:\n\nПодписка: ❌ Не активна"
        markup = create_inline_menu(messages.INLINE_BUTTONS)
        back_btn = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")
        markup.add(back_btn)

        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
        bot.answer_callback_query(call.id, "Профиль")

    elif call.data == "back_to_main":
        markup = create_inline_menu(messages.INLINE_BUTTONS)

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=messages.WELCOME_MESSAGE,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id, "Главное меню")

    elif call.data == "choose_ai":
        markup = create_ai_keyboard()
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="🧠 Выберите модель ИИ:",
            reply_markup=markup
        )

    elif call.data.startswith("ai_"):
        model_key = call.data[3:]
        users_collection.update_one({"user_id": user_id}, {"$set": {"ai_model": model_key}})
        bot.answer_callback_query(call.id, f"Модель изменена: {AI_PRESETS[model_key]['name']}")
        bot.send_message(chat_id, f"✅ Модель изменена: *{AI_PRESETS[model_key]['name']}*")


    elif call.data == "take_subscription":
        user = call.from_user
        user_doc = users_collection.find_one({"user_id": user.id})
        if not user_doc.get("is_subscribed", False):
            subscribe(call.message)
            return
        unsubscribe(call.message)
        #заглушка для подписки

    elif call.data == "choose_role":
        markup = create_role_keyboard()
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="🎭 Выберите роль:",
            reply_markup=markup
        )

    elif call.data.startswith("role_"):
        role_key = call.data[5:]
        users_collection.update_one({"user_id": user_id}, {"$set": {"role": role_key}})
        bot.answer_callback_query(call.id, f"Роль изменена: {ROLE_PRESETS[role_key]['name']}")
        bot.send_message(chat_id, f"✅ Роль изменена: *{ROLE_PRESETS[role_key]['name']}*")

    elif call.data == "show_care_service":
        bot.answer_callback_query(call.id, "Служба поддержки")
        # добавить сообщение с поддержкой


# --- Обработчики ---
@bot.message_handler(commands=["start"])
def send_welcome(message):    
    ensure_user_exists(message.from_user)
    markup = create_inline_menu(messages.INLINE_BUTTONS)
    bot.send_message(message.chat.id, messages.WELCOME_MESSAGE, reply_markup=markup)

#Подписка
@bot.message_handler(commands=["subscribe"])
def subscribe(message):
    user = message.from_user
    ensure_user_exists(user)

    users_collection.update_one(
        {"user_id": user.id},
        {"$set": {"is_subscribed": True}}
    )
    bot.send_message(message.chat.id, "✅ Вы подписались на бота!")

#Отписка
@bot.message_handler(commands=["unsubscribe"])
def unsubscribe(message):
    user = message.from_user
    ensure_user_exists(user)
    
    users_collection.update_one(
        {"user_id": user.id},
        {"$set": {"is_subscribed": False}}
    )
    bot.send_message(message.chat.id, "❌ Вы отписались от бота.")

@bot.message_handler(commands=["profile"])
def send_profile(message):
    user_id = message.from_user.id
    user_profile = get_user_info(user_id)

    response = "Ваша профиль:\n"
    for item in user_profile:
        response += f"\n🔹 Пользователь: {item['username']}\n🔹 Подписка: {item['is_subscribed']}\n🔹 Дата создания профиль: {item['registered_at'].strftime("%Y-%m-%d")}\n"

    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=["history"])
def send_history(message):
    user_id = message.from_user.id
    history = get_user_history(user_id)
    if not history:
        bot.send_message(message.chat.id, "История запросов пуста.")
        return

    response = "Ваша история:\n"
    for item in history:
        response += f"\n🔹 {item['query']}\n🤖 {item['response']}\n"

    bot.send_message(message.chat.id, response)

# Обработчик сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user = message.from_user
    chat_id = message.chat.id
    user_input = message.text
    ensure_user_exists(user)

    try:
        user_doc = users_collection.find_one({"user_id": user.id})
        if not user_doc.get("is_subscribed", False):
            bot.send_message(message.chat.id, "⚠️ Для использования этого бота требуется подписка. Используйте команду /subscribe")
            return
        
        user_data = get_user_info(user.id)
        ai_preset = AI_PRESETS.get(user_data["ai_model"], AI_PRESETS["gpt4o"])
        role_preset = ROLE_PRESETS.get(user_data["role"], ROLE_PRESETS["default"])

        prompt = message.text
        full_prompt = f"{prompt}\n\n{user_input}"
        # Вызов OpenAI когда будет ключ
        # response = openai.ChatCompletion.create(
        #     model="gpt-3.5-turbo",
        #     messages=[
        #         {"role": "system", "content": "Вы — помощник, который отвечает на вопросы пользователей."},
        #         {"role": "user", "content": user_input}
        #     ]
        # )
        # ai_response = response.choices[0].message.content.strip() 



        # Эмуляция ответа нейросети
        ai_response = f"""
🤖 Ответ от {ai_preset['name']} в роли "{role_preset['name']}"\n\n{
        f'Тема: {prompt}\n\n'
        'Это эмуляция нейросети.\n'
        'Представьте, что это реальный ответ.'
    }"""

        # Сохранение в историю
        save_query_to_history(user.id, user_input, ai_response)

        bot.send_message(message.chat.id, ai_response)
    except Exception as e:
        bot.send_message(message.chat.id, "Ошибка при обращении к нейросети.")
        logger.info(e)

# --- Запуск бота ---
if __name__ == "__main__":
    logger.info("🚀 Бот запущен...")
    bot.polling(none_stop=True)
