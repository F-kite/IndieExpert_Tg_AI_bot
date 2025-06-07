from telebot import types
from telebot.types import CallbackQuery
from config import *
from database.client import users_collection, get_user_info, ensure_user_exists, clear_user_history, is_user_subscribed
from utils.keyboards import create_ai_keyboard, create_role_keyboard, create_inline_menu
from utils.helpers import safe_edit_message, auto_delete_message, extract_russian_text, auto_delete_message
from utils.logger import get_logger

logger = get_logger(__name__)


def register_handlers(bot):
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    def handle_back_to_main(call):
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        markup = create_inline_menu(INLINE_BUTTONS)

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=WELCOME_MESSAGE,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id, "Главное меню")


    @bot.callback_query_handler(func=lambda call:call.data == "show_profile" )
    def handle_show_profile(call):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        message_id = call.message.message_id
        user_profile = get_user_info(user_id)
        markup = types.InlineKeyboardMarkup()
        is_admin =  ""

        if user_id in ADMINS : is_admin = "🔆 Царь и бог (администратор)"

        if not user_profile:
            # bot.answer_callback_query(call.id, "❌ Профиль не найден.")
            msg = bot.send_message(chat_id, "❌ Профиль не найден.")
            auto_delete_message(chat_id, msg.message_id)
            return
        
        model_name = AI_PRESETS.get(user_profile.get("ai_model", "default"), {}).get("name","Неизвестная модель")
        role_name = ROLE_PRESETS.get(user_profile.get("role", "default"), {}).get("name", "Неизвестная роль")
        response = f"""
👤 Ваш профиль:

🪪 Пользователь: <code>{user_profile.get('username')}</code>
💸 Подписка: {"✅" if user_profile.get("is_subscribed", False) else "❌"}
📅 Дата регистрации: <i>{user_profile.get("registered_at").strftime("%Y-%m-%d")}</i>
🧠 Текущая модель ИИ: <i>{model_name}</i>
🎭 Текущая роль бота: <i>{extract_russian_text(role_name)}</i>
    """
        if is_admin:
            response += f"\n{is_admin}"

        stat_btn= types.InlineKeyboardButton("📊 Статистика", callback_data="user_statistics")
        back_btn = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
        markup.add(stat_btn)
        markup.add(back_btn)

        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response, reply_markup=markup, parse_mode="HTML")
        bot.answer_callback_query(call.id, "Профиль")


    @bot.callback_query_handler(func=lambda call: call.data == "user_statistics")
    def handle_user_statistics(call):
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        user_id = call.from_user.id
        user_profile = get_user_info(user_id)
        markup = types.InlineKeyboardMarkup()

        stat_btn= types.InlineKeyboardButton("👤 Профиль", callback_data="show_profile")
        back_btn = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
        markup.add(stat_btn)
        markup.add(back_btn)

        response = f"📊 Ваша статистика за текущий месяц:\n\n"
        for model, count in user_profile.get("monthly_usage", {}).items():
            ai_model = AI_PRESETS.get(model).get("name","Неизвестная модель")
            response += f"▫️ {ai_model}: <b>{count}</b>\n" 

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=response,
            reply_markup=markup,
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id, "Статистика запросов")

    @bot.callback_query_handler(func=lambda call: call.data == "choose_ai")
    def handle_choose_ai(call):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        user_data = get_user_info(user_id)

        if not user_data:
            ensure_user_exists(call.from_user)
            user_data = users_collection.find_one({"user_id": user_id})

        markup = create_ai_keyboard(user_id)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=AI_MENU_MESSAGE,
            reply_markup=markup
        )


    @bot.callback_query_handler(func=lambda call: call.data.startswith("ai_"))
    def handle_ai_callback(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        model_key = call.data[3:]
        model_data = AI_PRESETS.get(model_key)
        user_doc = get_user_info(user_id)
        is_subscribed = user_doc.get("is_subscribed", False)

        if not is_subscribed and model_key != "gpt-4o":
            msg = bot.send_message(chat_id, "❗️Подпишись, чтобы разблокировать эту модель")
            auto_delete_message(chat_id, msg.message_id)
            return
        
        if model_key == get_user_info(user_id).get("ai_model"):
            bot.answer_callback_query(call.id, "✅ Модель уже выбрана")
            return

        users_collection.update_one({"user_id": user_id}, {"$set": {"ai_model": model_key}})
        description = model_data["description"]
        name = model_data["name"]

        text = f"""
🧠 *{name}*

ℹ️ _{description}_
    """
        bot.answer_callback_query(call.id, f"Выбрана модель {AI_PRESETS[model_key]['name']}")
        safe_edit_message(bot, chat_id, call.message.message_id, text, create_ai_keyboard(user_id), "Markdown")


    @bot.callback_query_handler(func=lambda call: call.data == "choose_role")
    def handle_choose_role(call): 
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        markup = create_role_keyboard(user_id)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=ROLE_MENU_MESSAGE,
            reply_markup=markup,
            parse_mode="Markdown"
        )


    @bot.callback_query_handler(func=lambda call: call.data.startswith("role_"))
    def handle_role_callback(call: CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        role_key = call.data[5:]
        role_data = ROLE_PRESETS.get(role_key)
        user_doc = get_user_info(user_id)
        is_subscribed = user_doc.get("is_subscribed", False)

        if not is_subscribed and role_key != "default":
            msg = bot.send_message(chat_id, "❗️Подпишись, чтобы разблокировать эту роль")
            auto_delete_message(chat_id, msg.message_id)
            return

        if role_key == get_user_info(user_id).get("role"):
            bot.answer_callback_query(call.id, "✅ Роль уже выбрана")
            return
        
        if role_key == "custom":
            msg =  bot.send_message(chat_id, "⚠️ Функция находится в разработке")
            auto_delete_message(chat_id, msg.message_id)
            return
        else:
            users_collection.update_one({"user_id": user_id}, {"$set": {"role": role_key}})
            description = role_data["description"]
            name = role_data["name"]
            text = f"""
*{name}*

ℹ️ _{description}_
                    """

            bot.answer_callback_query(call.id, f"Роль изменена: {name}")
        safe_edit_message(bot, chat_id, call.message.message_id, text, create_role_keyboard(user_id), "Markdown")

    # Подтверждение очистки истории
    @bot.callback_query_handler(func=lambda call: call.data == "confirm_clear")
    def handle_confirm_clear(call):
        user = call.from_user
        deleted_count = clear_user_history(user.id)

        bot.answer_callback_query(call.id, "История очищена")
        bot.send_message(call.message.chat.id, f"🗑️ История успешно очищена. Удалено записей: {deleted_count}")


    @bot.callback_query_handler(func=lambda call:call.data == "subscribe" )
    def handle_subscribe(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        if is_user_subscribed(user_id):
            msg = bot.send_message(
                chat_id,
                "🔆 Вы уже оформили подписку, вторая не принесет новых возможностей"
            )
            auto_delete_message(chat_id, msg.message_id)
            return
        
        text = f"""
🌟 Подписка стоит всего {SUBSCRIPTION_PRICE} ⭐ в месяц.
Оформи подписку, чтобы получить полный доступ ко всем ИИ и ролям.
Срок подписки 30 дней. 
/subscribe
                """
        msg = bot.send_message(chat_id, text)
        auto_delete_message(chat_id, msg.message_id, 10)
        return


    @bot.callback_query_handler(func=lambda call:call.data == "show_care_service" )
    def handle_show_care_service(call):
        bot.answer_callback_query(call.id, "Служба поддержки")