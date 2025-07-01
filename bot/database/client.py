from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from dotenv import load_dotenv
from config import *
from utils.logger import get_logger

load_dotenv()


client = AsyncIOMotorClient(MONGODB_BOT_URI)
db = client[MONGODB_DB_NAME]
users_collection = db["users"]
history_collection = db["history"]
logger = get_logger(__name__)

DEFAULT_USER_DATA = {
    "is_subscribed": False,
    "subscription_start": "",
    "subscription_end": None,
    "ai_model": "gpt-4o",
    "role": "tarot_reader",
    "custom_prompt": "",
    "request_limits": {},
    "monthly_usage": {},
    "last_seen": None,
    "registered_at": None,
    "tts_settings": {
        "process_voice_messages":False, #После транскрибации текст отправляется к ИИ
        "reply_voice_messages":False #Транскрибация текста в речь и отправка голосового
    }
}


async def test_mongo_connection():
    """Проверяет подключение к MongoDB."""
    try:
        # Попытка получить список БД
        await client.admin.command('ping')
        logger.info("✅ Настроено соединение с базой данных")
        return True
    except Exception as e:
        logger.error(f"❌ Не удалось подключиться: {e}")
        return False
    

# Проверка, есть ли пользователь в базе
async def ensure_user_exists(user):
    # игнорирование бота как пользователя
    user_id = user.id
    if user_id == BOT_ID:
        return

    now = datetime.now()
    user_data = await users_collection.find_one({"user_id": user_id})

    # Если пользователя нет — создаём его в бд
    if not user_data:
        request_limits = {key: {"count": 0} for key in AI_PRESETS.keys()}
        monthly_usage = {key: 0 for key in AI_PRESETS.keys()}

        new_user_data = DEFAULT_USER_DATA.copy()
        new_user_data.update({
            "user_id": user_id,
            "first_name": user.first_name,
            "username": user.username,
            "registered_at": now,
            "last_seen": now,
            "request_limits": request_limits,
            "monthly_usage": monthly_usage
        })
        
        await users_collection.insert_one(new_user_data)
        return

    is_subscribed = user_data.get("is_subscribed", False)
    
    # Обновление полей у пользователей в бд
    update_data = {}
    
    for field, default_value in DEFAULT_USER_DATA.items():
        if field not in user_data:
            update_data[field] = default_value

    if update_data:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )

    # Выдача подписки админам
    if user_id in ADMINS:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"is_subscribed": True, "subscription_end": None}}  # Без ограничения по времени
        )

    subscription_end = user_data.get("subscription_end", None)

    if subscription_end == "":
        subscription_end = None
    elif isinstance(subscription_end, str):
        try:
            # Преобразуем строку в объект datetime
            subscription_end = datetime.fromisoformat(subscription_end)
        except ValueError:
            logger.warning(f"[DEBUG] Некорректный формат даты у пользователя {user_id}")
            logger.warning(f"[DEBUG] subscription_end: {subscription_end} | Тип: {type(subscription_end)}")
            subscription_end = None

    # Отключение подписки если истек ее срок
    if (subscription_end is not None) and (now.date() == subscription_end.date()):
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"is_subscribed": False}}
        )
        is_subscribed = False

    # Если нет подписки - все сбрасывается по умолчанию
    if not is_subscribed:
        await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"ai_model": "gpt-4o", "role":"tarot_reader", "subscription_start":"", "subscription_end":""}}
    )
        
    # Сбрасываем лимиты в начале нового месяца
    if user_data.get("last_month", None) != now.month:
        model_limit = {"count":0}

        await users_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "last_month": now.month,
                    "monthly_usage": {model_key: 0 for model_key in AI_PRESETS.keys()},
                    "request_limits": {model_key: model_limit for model_key in AI_PRESETS.keys()}
                    
                }
            }
        )
            
    # Обновляем дату последнего взаимодействия
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"last_seen": now}}
    )
    

async def get_all_users():
    cursor = users_collection.find()
    return await cursor.to_list(length=None)


async def get_user_history(user_id):
    cursor = history_collection.find({"user_id": user_id}, {"_id": 0})
    return await cursor.to_list(length=100)


async def save_query_to_history(user_id, query, response):
    await history_collection.insert_one({
        "user_id": user_id,
        "query": query,
        "response": response,
        "timestamp": datetime.now()
    })


async def is_user_subscribed(user_id):
    user_data = await users_collection.find_one({"user_id": user_id})
    if not user_data:
        return False
    
    # Админы всегда подписаны
    if user_id in ADMINS:
        return True

    return user_data.get("is_subscribed", False)


async def get_all_users_with_subscription():
    try:
        cursor = users_collection.find({
            "is_subscribed": True,
            "subscription_end": {"$ne": None},  # только с датой окончания
            "user_id": {"$ne": BOT_ID}  # исключаем самого бота
        })
        users = await cursor.to_list(length=None)
        return users
    except Exception as e:
        logger.error(f"❌ Ошибка при получении пользователей с подпиской: {e}")
        return []


async def clear_user_history(user_id):
    result = await history_collection.delete_many({"user_id": user_id})
    logger.info(f"🧹 Пользователь {user_id} очистил свою историю запросов.")
    return result.deleted_count


async def get_user_info(user_id):
    info = await users_collection.find_one({"user_id": user_id})
    return info


async def get_current_prompt(user_id):
    user_data = await get_user_info(user_id)
    role_key = user_data.get("role", "tarot_reader")
    custom_prompt = user_data.get("custom_prompt", "")

    if role_key == "custom" and custom_prompt:
        return custom_prompt
    else:
        preset = ROLE_PRESETS.get(role_key)
        return preset["prompt"]
    
# Выдача подписки админом
async def grant_subscription_to_users(user_ids):
    now = datetime.now()
    result = await users_collection.update_many(
        {"user_id": {"$in": user_ids}},
        {
            "$set": {
                "is_subscribed": True,
                "subscription_start": now,
                "subscription_end": now + timedelta(days=30)
            }
        }
    )
    return result.modified_count