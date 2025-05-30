from telebot import types
from telebot.types import Message, LabeledPrice
from datetime import datetime, timedelta
from config import *
from database.client import ensure_user_exists, get_user_info, is_user_subscribed, get_user_history, users_collection
from utils.keyboards import create_inline_menu, create_ai_keyboard, create_role_keyboard, create_payment_keyboard
from utils.helpers import auto_delete_message
from utils.logger import get_logger

logger = get_logger(__name__)

def register_handlers(bot):
    @bot.message_handler(commands=["start"])
    def cmd_send_welcome(message: Message):
        ensure_user_exists(message.from_user)
        markup = create_inline_menu(INLINE_BUTTONS)
        bot.send_message(message.chat.id, WELCOME_MESSAGE, reply_markup=markup)


    @bot.message_handler(commands=["profile"])
    def cmd_send_profile(message: Message):
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
    def cmd_choose_ai(message: Message):
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
    def cmd_choose_role(message: Message):
        user = message.from_user
        user_id = user.id
        ensure_user_exists(user)

        user_data = get_user_info(user_id)
        if not user_data.get("is_subscribed", False):
            msg = bot.send_message(
                message.chat.id,
                "🔒 Нужна подписка, чтобы выбрать другую роль"
            )
            auto_delete_message(message.chat.id, msg.message_id)
            return

        markup = create_role_keyboard(user_id)
        bot.send_message(message.chat.id, ROLE_MENU_MESSAGE, reply_markup=markup, parse_mode="Markdown")


    @bot.message_handler(commands=["custom_role"])
    def cmd_custom_role(message: Message):
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


    @bot.message_handler(commands=["subscribe"])
    def cmd_subscribe(message: Message):
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
        

    @bot.message_handler(content_types=["successful_payment"])
    def handle_successful_payment(message: Message):
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

        
    @bot.message_handler(commands=["unsubscribe"])
    def cmd_unsubscribe(message: Message):
        user = message.from_user
        user_id = user.id
        ensure_user_exists(user)
        
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"is_subscribed": False}}
        )
        bot.send_message(message.chat.id, "❌ Вы отписались от бота.")


    @bot.message_handler(commands=["history"])
    def cmd_send_history(message: Message):
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
    def cmd_confirm_clear_history(message: Message):
        markup = types.InlineKeyboardMarkup()
        confirm_btn = types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_clear")
        back_btn = types.InlineKeyboardButton("❌ Отмена", callback_data="back_to_main")
        markup.row(confirm_btn, back_btn)
        text = "⚠️ После очистки истории вы безвозвратно потеряете возможность просмотретиь ваши старые запросы.\nВы уверены, что хотите очистить историю запросов?"

        bot.send_message(message.chat.id, CLEAR_DIALOG_MESSAGE, reply_markup=markup)


    @bot.message_handler(commands=["policy"])
    def cmd_send_policy(message: Message):
        bot.send_message(message.chat.id, POLICY_MESSAGE, parse_mode="Markdown")

