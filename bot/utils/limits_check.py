from datetime import datetime
from config import AI_PRESETS, AI_REQUEST_LIMIT, ADMINS
from database.client import users_collection, get_user_info
from utils.logger import get_logger

logger = get_logger(__name__)

async def check_ai_usage(user_id, ai_model_key):
    now = datetime.now()
    user_data = await get_user_info(user_id)
    is_subscribed = user_data.get("is_subscribed", False)

    if not is_subscribed:
        return False, "Подписка не активирована"

    limits = user_data.get("request_limits", {})
    model_limit = limits.get(ai_model_key, {"count": 0})

    if model_limit["count"] >= AI_REQUEST_LIMIT and user_id not in ADMINS:
        return False, f"❌ Лимит использования {AI_PRESETS[ai_model_key]['name']} исчерпан"

    # Увеличиваем счетчик
    users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {f"request_limits.{ai_model_key}.count": 1}}
    )

    return True, ""