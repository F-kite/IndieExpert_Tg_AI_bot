from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
from config import *
from utils.logger import get_logger

load_dotenv()


client = MongoClient(MONGODB_BOT_URI)
db = client[MONGODB_DB_NAME]
users_collection = db["users"]
history_collection = db["history"]
logger = get_logger(__name__)

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
    # игнорирование бота как пользователя
    user_id = user.id
    if user_id == BOT_ID:
        return

    now = datetime.now()
    user_doc = users_collection.find_one({"user_id": user_id})

    # Если пользователя нет — создаём нового
    if not user_doc:
        request_limits = {}
        for key in AI_PRESETS.keys():
            request_limits[key] = {"count": 0, "last_reset": now}

        user_data = {
            "user_id": user_id,
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

        if not is_subscribed and user_id in ADMINS:
            users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"is_subscribed": True, "subscription_end": None}}  # Без ограничения по времени
            )

        if not is_subscribed:
           users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"ai_model": "gpt-4o", "role":"default"}}
        )
           
        # Сбрасываем лимиты в начале нового месяца
        if user_doc.get("last_month", None) != now.month:
            users_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "last_month": now.month,
                        "monthly_usage": {model_key: 0 for model_key in AI_PRESETS.keys()}
                    }
                }
            )
           
        # Если есть — обновляем только last_seen
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_seen": now}}
        )
    

def get_user_history(user_id):
    return list(history_collection.find({"user_id": user_id}, {"_id": 0}).sort("timestamp", -1))


def save_query_to_history(user_id, query, response):
    history_collection.insert_one({
        "user_id": user_id,
        "query": query,
        "response": response,
        "timestamp": datetime.now()
    })


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


def get_current_prompt(user_id):
    user_data = get_user_info(user_id)
    role_key = user_data.get("role", "default")
    custom_prompt = user_data.get("custom_prompt", "")

    if role_key == "custom" and custom_prompt:
        return custom_prompt
    else:
        preset = ROLE_PRESETS.get(role_key, ROLE_PRESETS["default"])
        return preset["prompt"]