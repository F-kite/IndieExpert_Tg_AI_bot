from datetime import datetime
from config import AI_PRESETS
from database.client import users_collection, get_user_info

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