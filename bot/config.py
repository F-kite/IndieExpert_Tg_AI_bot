import os
from types import SimpleNamespace
from dotenv import load_dotenv
import presets.messages as messages
import presets.buttons as buttons
import presets.models as models
import presets.roles as roles

load_dotenv()

cfg = SimpleNamespace()

token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token or token.startswith("sk-") or len(token) < 35:
    raise ValueError("❌ Неверный токен Telegram")

BOT_ID = None

# Глобальная переменная для хранения активных задач
user_tasks = {}
# Глобальная переменная для хранения состояний пользователей
user_states = {}

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMINS = [int(x.strip()) for x in os.getenv("TELEGRAM_ADMINS_ID", "").split(",") if x.strip()]
AI_REQUEST_LIMIT = os.getenv("AI_REQUEST_LIMIT")
subscription_price_str = os.getenv("SUBSCRIPTION_PRICE", "150")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME")
MONGODB_BOT_URI = os.getenv("MONGODB_BOT_URI")

#Ключи
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Проверяем, что это действительно число
if subscription_price_str.strip() == "":
    SUBSCRIPTION_PRICE = 150
else:
    try:
        SUBSCRIPTION_PRICE = int(subscription_price_str)
    except ValueError:
        raise ValueError("SUBSCRIPTION_PRICE должен быть целым числом")


# Текста
WELCOME_MESSAGE = messages.WELCOME_MESSAGE
AI_MENU_MESSAGE = messages.AI_MENU_MESSAGE
ROLE_MENU_MESSAGE = messages.ROLE_MENU_MESSAGE
SUBSCRIPTION_MESSAGE = messages.SUBSCRIPTION_MESSAGE
HISTORY_MESSAGE = messages.HISTORY_MESSAGE
CLEAR_DIALOG_MESSAGE = messages.CLEAR_DIALOG_MESSAGE
PRIVACY_MESSAGE = messages.PRIVACY_MESSAGE
GENERAL_SYSTEM_PROMPT = messages.GENERAL_SYSTEM_PROMPT


# Панель кнопок
BACK_BUTTON = buttons.BACK_BUTTON
SIDE_BUTTONS = buttons.SIDE_BUTTONS
INLINE_BUTTONS = buttons.INLINE_BUTTONS
SUPPORT_BUTTON = buttons.SUPPORT_BUTTON
AI_MODELS_BUTTONS = buttons.AI_MODELS_BUTTONS


# Присеты
AI_PRESETS = models.AI_PRESETS
ROLE_PRESETS = roles.ROLE_PRESETS

def set_bot_id(bot_id):
    global BOT_ID
    BOT_ID = bot_id

def setup_globals():
    cfg.BOT_ID = None
setup_globals()
