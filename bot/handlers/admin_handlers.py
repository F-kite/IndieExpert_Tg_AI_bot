from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message, CallbackQuery
import asyncio

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

    response = "👑 Администратор | 👤 Пользователь\n\n"

    for user in users:
        user_id = int(user["user_id"])
        username = user.get("username", "Не указан")
        sub_status = "✅" if user.get("is_subscribed", False) else "❌"
        role_label = "👑" if user_id in ADMINS else "👤"
        response += f"{role_label} @{username} ID: <code>{user_id}</code> Подписка: {sub_status}\n"

    await bot.send_message(chat_id, response, parse_mode="HTML")


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


async def handle_admin_revoke_subs(bot: AsyncTeleBot, call: CallbackQuery):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if user_id not in ADMINS:
        await bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return

    text = """
🚫 Что бы отозвать подписку у пользователя:
        Введите его ID или @username через запятую

ℹ️ Это действие нельзя отменить автоматически
    """
    await bot.send_message(chat_id, text)
    user_states[user_id] = "awaiting_user_ids_for_revoking"


async def process_revoke_subs_input(bot: AsyncTeleBot, message: Message, input_text: str):
    chat_id = message.chat.id
    admin_id = message.from_user.id

    if not input_text.strip():
        msg = await bot.send_message(chat_id, "⚠️ Введите хотя бы один `user_id` или `@username`")
        await auto_delete_message(bot, chat_id, msg.message_id, delay=5)
        return

    # Очищаем и разбираем ввод
    raw_inputs = [item.strip() for item in input_text.split(",") if item.strip()]
    failed_users = []
    revoked_count = 0

    for raw in raw_inputs:
        try:
            # Если это username
            if raw.startswith("@"):
                username = raw[1:]
                user_data = await users_collection.find_one({"username": username})
                if not user_data:
                    failed_users.append(raw)
                    continue
                user_id = user_data["user_id"]
            else:
                # Если это user_id
                user_id = int(raw)

            # Пропускаем админов
            if user_id in ADMINS:
                logger.info(f"🚫 Администратор {admin_id} попытался забрать подписку у другого админа {user_id}")
                continue

            # Обновляем подписку
            result = await users_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "is_subscribed": False,
                        "subscription_start": "",
                        "subscription_end": None
                    }
                }
            )

            if result.modified_count == 0:
                failed_users.append(str(user_id))
            else:
                revoked_count += 1

        except Exception as e:
            logger.error(f"❌ Ошибка при обработке {raw}: {e}")
            failed_users.append(raw)

    # Ответ админу
    success_msg = f"✅ Подписка отозвана у {revoked_count} пользователей."
    await bot.send_message(chat_id, success_msg)

    if failed_users:
        failed_msg = f"❌ Не удалось отозвать подписку у следующих пользователей: {', '.join(failed_users)}"
        await bot.send_message(chat_id, failed_msg)


#Рассылка о тех. обслуживании
async def send_maintenance_notification(bot: AsyncTeleBot):
    """
    Рассылает всем пользователям уведомление о техническом обслуживании.
    Игнорирует пользователей, которые не писали боту за последние 24 часа.
    """
    users = await get_all_users()

    if not users:
        logger.warning("Нет пользователей для отправки уведомления")
        return

    notification_text = (
        "⚠️ <b>Техническое обслуживание</b>\n\n"
        "Сейчас проводится плановое техническое обслуживание. "
        "Бот будет недоступен в течение некоторого времени.\n\n"
        "Приносим свои извинения за доставленные неудобства."
    )

    failed_sends = []

    for user in users:
        user_id = user.get("user_id")

        try:
            await bot.send_message(user_id, notification_text, parse_mode="HTML")
            await asyncio.sleep(0.05)  # Небольшая пауза, чтобы не спамить Telegram API
        except Exception as e:
            logger.error(f"❌ Не удалось отправить сообщение пользователю {user_id}: {e}")
            failed_sends.append(user_id)

    if failed_sends:
        logger.info(f"✅ Уведомление отправлено {len(users) - len(failed_sends)} пользователям")
        logger.warning(f"❌ Не удалось отправить уведомление {len(failed_sends)} пользователям")
    else:
        logger.info(f"✅ Уведомление успешно отправлено всем {len(users)} пользователям")

    return [len(users) - len(failed_sends), len(failed_sends)]