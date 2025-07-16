from telebot.types import LabeledPrice
from telebot.async_telebot import AsyncTeleBot
from telebot.apihelper import ApiTelegramException
from datetime import timedelta, datetime
from database.client import get_all_users_with_subscription, get_user_info
from utils.logger import get_logger
from utils.keyboards import create_payment_renew_keyboard
from config import SUBSCRIPTION_PRICE

logger = get_logger(__name__)

async def check_subscriptions_expiry(bot: AsyncTeleBot, user_id=0):
    """
    Фоновая задача: каждый день проверяет, у кого подписка заканчивается через 1 день
    """
    
    now = datetime.now().date()
    date_tomorrow = now + timedelta(days=1)
    
    if user_id == 0:
    # Получаем всех пользователей с подпиской
        logger.info("⏰ Начинаю ежедневную проверку подписок")
        users = await get_all_users_with_subscription()

        if len(users) == 0:
            logger.info("😨 Нет пользователей с подпиской")
            return
        
    else:
        user_data = await get_user_info(user_id)
        subscription_end = user_data.get("subscription_end")

        if not user_data:
            logger.warning(f"❌ Не найден пользователь {user_id}")
            return

        users = [user_data]  # оборачиваем в список для единообразия

    for user_data in users:
        user_id = user_data["user_id"]
        subscription_end = user_data.get("subscription_end")

        if not subscription_end or subscription_end is None:
            continue

        if subscription_end.date() < now:
            continue

        # Если до конца подписки 1 день
        if subscription_end.date() == date_tomorrow:
            try:
                logger.info(f"🔔 Подписка пользователя {user_id} закончится через 1 день")
                
                last_seen = user_data.get("last_seen", None)
                if not last_seen or (datetime.now() - last_seen).days > 1:
                    logger.info(f"💤 Пользователь {user_id} давно не писал боту")
                    continue
                
                markup = create_payment_renew_keyboard()

                # Генерируем ссылку на покупку через @invoice
                title = "Подписка на бота"
                description = """
ℹ️Завтра истекает срок вашей подписки. Самое время продлить ее
‼️ Оформление подписки не подразумевает возврата средств в будущем
                """
                payload = f"sub_{user_id}_{int(datetime.now().timestamp())}"
                currency = "XTR"
                provider_token=""
                prices = [LabeledPrice(label="Ежемесячная подписка", amount=SUBSCRIPTION_PRICE)]
                # photo_url = "https://example.com/subscription_image.jpg "  # Необязательно
                
                await bot.send_invoice(
                        chat_id=int(user_id),
                        title=title,
                        description=description,
                        invoice_payload=payload,
                        currency=currency,
                        prices=prices,
                        provider_token=provider_token,
                        # photo_url=photo_url,
                        is_flexible=False,
                        allow_paid_broadcast=True,  # Разрешаем оплату через Stars
                        reply_markup=markup
                    )
            except ApiTelegramException as e:
                if "bot was blocked by the user" in str(e).lower():
                    logger.warning(f"⛔ Пользователь {user_id} заблокировал бота")
                elif "chat not found" in str(e).lower():
                    logger.warning(f"❌ Чат {user_id} не найден (пользователь, возможно, не запускал бота)")
                else:
                    logger.error(f"❗Telegram API ошибка: {e}")
            except Exception as e:
                logger.error(f"❌ Не удалось отправить уведомление пользователю {user_id}: {e}")
        else:
            logger.info("🔔 Оканчивающихся подписок не найдено")