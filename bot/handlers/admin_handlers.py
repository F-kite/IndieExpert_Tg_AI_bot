from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message, CallbackQuery

from database.client import get_all_users, grant_subscription_to_users, users_collection
from config import ADMINS, user_states
from utils.logger import get_logger
from utils.helpers import auto_delete_message

logger = get_logger(__name__)


async def handle_admin_list_users(bot: AsyncTeleBot, call: CallbackQuery):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if user_id not in ADMINS:
        await bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return

    users = await get_all_users()

    if not users:
        await bot.send_message(chat_id, "🫥 База данных пуста.")
        return

    response = "👥 Список пользователей:\n\n"

    for user in users:
        user_id = int(user["user_id"])
        username = user.get("username", "Не указан")
        sub_status = "✅" if user.get("is_subscribed", False) else "❌"

        response += f"@{username} | ID: {user_id} | Подписка: {sub_status}\n"

    await bot.send_message(chat_id, response)


async def handle_admin_grant_subs(bot: AsyncTeleBot, call: CallbackQuery):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if user_id not in ADMINS:
        await bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    text = """
*️⃣ Что бы выдать подписку одному пользователю:
        Введите его ID или @username
*️⃣ Что бы выдать подписку нескольким пользователям:
        Введите их ID или @username через запятую

ℹ️ Подписка выдается на месяц
"""
    await bot.send_message(chat_id, text)
    user_states[user_id] = "awaiting_user_ids_for_subscription"


async def process_grant_subs_input(bot: AsyncTeleBot, message: Message, input_text: str):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not input_text.strip():
        msg = await bot.send_message(chat_id, "⚠️ Введите хотя бы один `user_id` или `@username`")
        await auto_delete_message(bot, chat_id, msg.message_id, 5)
        return

    try:
        ids_to_grant = []
        input_list = [item.strip() for item in input_text.split(",")]

        for identifier in input_list:
            if identifier.startswith("@"):
                # Поиск по username
                user_doc = await users_collection.find_one({"username": identifier[1:]})
                if user_doc:
                    ids_to_grant.append(user_doc["user_id"])
            elif identifier.isdigit():
                # Поиск по user_id
                user_doc = await users_collection.find_one({"user_id": int(identifier)})
                if user_doc:
                    ids_to_grant.append(int(identifier))
            else:
                logger.warning(f"❗ Неверный формат: {identifier}")

        if not ids_to_grant:
            msg = await bot.send_message(chat_id, "❌ Ни один пользователь не найден")
            await auto_delete_message(bot, chat_id, msg.message_id, 5)
            return

        count = await grant_subscription_to_users(ids_to_grant)

        success_msg = await bot.send_message(
            chat_id, f"✅ Подписка активирована для {count} пользователей."
        )
        await auto_delete_message(bot, chat_id, success_msg.message_id, delay=5)

    except Exception as e:
        logger.error(f"❌ Ошибка при выдаче подписки: {e}")
        msg = await bot.send_message(chat_id, "❌ Не удалось выдать подписку")
        await auto_delete_message(bot, chat_id, msg.message_id, 5)