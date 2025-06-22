from telebot import types
from telebot.types import CallbackQuery
from config import *
from database.client import users_collection, get_user_info, ensure_user_exists, clear_user_history, is_user_subscribed
from utils.keyboards import create_ai_keyboard, create_role_keyboard, create_inline_menu
from utils.helpers import safe_edit_message, auto_delete_message, extract_russian_text
from utils.history_pages import show_history_page
from utils.logger import get_logger
from handlers.admin_handlers import handle_admin_grant_subs, handle_admin_list_users

logger = get_logger(__name__)


def register_handlers(bot, ai_handlers):
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    async def handle_back_to_main(call):
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        markup = create_inline_menu(INLINE_BUTTONS)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=WELCOME_MESSAGE,
            reply_markup=markup
        )
        await bot.answer_callback_query(call.id, "Главное меню")


    @bot.callback_query_handler(func=lambda call:call.data == "show_profile" )
    async def handle_show_profile(call):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        message_id = call.message.message_id
        try:
            user_profile = await get_user_info(user_id)
            markup = types.InlineKeyboardMarkup()
            is_admin =  ""

            if user_id in ADMINS : is_admin = "🔆 Царь и бог (администратор)"

            if not user_profile:
                msg = await bot.send_message(chat_id, "❌ Профиль не найден.")
                await auto_delete_message(bot, chat_id, msg.message_id)
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

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=response,
                reply_markup=markup,
                parse_mode="HTML"
            )
            await bot.answer_callback_query(call.id, "Профиль")
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            await bot.answer_callback_query(call.id, "Ошибка при отображении профиля")


    @bot.callback_query_handler(func=lambda call: call.data == "user_statistics")
    async def handle_user_statistics(call):
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        user_id = call.from_user.id
        try:
            user_profile = await get_user_info(user_id)
            markup = types.InlineKeyboardMarkup()

            profile_btn= types.InlineKeyboardButton("👤 Профиль", callback_data="show_profile")
            back_btn = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
            markup.add(profile_btn)
            markup.add(back_btn)

            monthly_usage = user_profile.get("monthly_usage", {})
            response = ""
            if not monthly_usage:
                response = "ℹ️ Статистика пока пуста. Самое время начать пользоваться ботом 😉"
            else:
                response = f"📊 Ваша статистика за текущий месяц:\n\n"
                for model, count in monthly_usage.items():
                    ai_model = AI_PRESETS.get(model, {}).get("name", "ℹ️ Неизвестная модель")
                    response += f"▫️ {ai_model} : <b>{count}</b>\n"

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=response,
                reply_markup=markup,
                parse_mode="HTML"
            )
            await bot.answer_callback_query(call.id, "Статистика запросов")
        
        except Exception as e:
            logger.error(f"❌ Ошибка при выводе статистики: {e}")
            await bot.answer_callback_query(call.id, "Ошибка при загрузке статистики")
            msg = await bot.send_message(chat_id, "⚠️ Не удалось загрузить статистику")
            await auto_delete_message(bot, chat_id, msg.message_id, delay=5)


    @bot.callback_query_handler(func=lambda call: call.data == "choose_ai")
    async def handle_choose_ai(call):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        user_data = await get_user_info(user_id)

        if not user_data:
            await ensure_user_exists(call.from_user)
            user_data = await users_collection.find_one({"user_id": user_id})

        markup = await create_ai_keyboard(user_id, ai_handlers)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=AI_MENU_MESSAGE,
            reply_markup=markup
        )


    @bot.callback_query_handler(func=lambda call: call.data.startswith("ai_"))
    async def handle_ai_callback(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        model_key = call.data[3:]
        model_data = AI_PRESETS.get(model_key)
        user_doc = await get_user_info(user_id)
        is_subscribed = user_doc.get("is_subscribed", False)

        try:
            if not is_subscribed and model_key != "gpt-4o":
                msg = await bot.send_message(chat_id, "❗️Подпишись, чтобы разблокировать эту модель")
                await auto_delete_message(bot, chat_id, msg.message_id)
                return
            
            handler_info = ai_handlers.get(model_key)
            if not handler_info:
                msg =await bot.send_message(chat_id, "❌ Данная модель временно недоступна.")
                await auto_delete_message(bot, chat_id, msg.message_id, 2)
                return
            
            if model_key == user_doc.get("ai_model"):
                await bot.answer_callback_query(call.id, "✅ Модель уже выбрана")
                return

            await users_collection.update_one({"user_id": user_id}, {"$set": {"ai_model": model_key}})
            description = model_data["description"]
            name = model_data["name"]

            text = f"""
🧠 *{name}*

ℹ️ _{description}_
        """
            await bot.answer_callback_query(call.id, f"Выбрана модель {AI_PRESETS[model_key]['name']}")
            markup = await create_ai_keyboard(user_id, ai_handlers)
            await safe_edit_message(bot, chat_id, call.message.message_id, text, markup, "Markdown")

        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            await bot.answer_callback_query(call.id, "Ошибка при выборе модели")


    @bot.callback_query_handler(func=lambda call: call.data == "choose_role")
    async def handle_choose_role(call): 
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        markup = await create_role_keyboard(user_id)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=ROLE_MENU_MESSAGE,
            reply_markup=markup,
            parse_mode="Markdown"
        )


    @bot.callback_query_handler(func=lambda call: call.data.startswith("role_"))
    async def handle_role_callback(call: CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        role_key = call.data[5:]
        role_data = ROLE_PRESETS.get(role_key)
        user_doc = await get_user_info(user_id)
        is_subscribed = user_doc.get("is_subscribed", False)

        try:
            if not is_subscribed and role_key != "default":
                msg = await bot.send_message(chat_id, "❗️Подпишись, чтобы разблокировать эту роль")
                await auto_delete_message(bot, chat_id, msg.message_id)
                return

            if role_key == user_doc.get("role"):
                await bot.answer_callback_query(call.id, "✅ Роль уже выбрана")
                return
            
            if role_key == "custom":
                msg = await bot.send_message(chat_id, "⚠️ Функция находится в разработке")
                await auto_delete_message(bot, chat_id, msg.message_id)
                return
            else:
                await users_collection.update_one({"user_id": user_id}, {"$set": {"role": role_key}})
                description = role_data["description"]
                name = role_data["name"]
                text = f"""
*{name}*

ℹ️ _{description}_
                        """

            await bot.answer_callback_query(call.id, f"Роль изменена: {name}")
            markup = await create_role_keyboard(user_id)
            await safe_edit_message(bot, chat_id, call.message.message_id, text, markup, "Markdown")

        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            await bot.answer_callback_query(call.id, "Ошибка при выборе роли")


    @bot.callback_query_handler(func=lambda call: call.data.startswith("history_"))
    async def handle_history_navigation(call):
        try:
            data_parts = call.data.split("_")
            direction = data_parts[1]
            page_index = int(data_parts[2])
        except (ValueError, IndexError):
            await bot.answer_callback_query(call.id, "Неверные данные")
            return

        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if direction == "prev":
            new_index = page_index - 1
        elif direction == "next":
            new_index = page_index + 1
        else:
            await bot.answer_callback_query(call.id, "Неизвестная команда")
            return

        # Удаляем старое сообщение и показываем новую страницу
        await bot.delete_message(chat_id, message_id)
        await show_history_page(bot, chat_id, user_id, new_index)
        await bot.answer_callback_query(call.id)


    @bot.callback_query_handler(func=lambda call: call.data == "clear_history")
    async def handle__clear_history(call):
        chat_id = call.message.chat.id
        markup = types.InlineKeyboardMarkup()
        confirm_btn = types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_clear")
        back_btn = types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_clear")
        markup.row(confirm_btn, back_btn)

        await bot.send_message(chat_id, CLEAR_DIALOG_MESSAGE, reply_markup=markup)


    @bot.callback_query_handler(func=lambda call: call.data == "confirm_clear")
    async def handle_confirm_clear(call):
        user = call.from_user
        deleted_count = await clear_user_history(user.id)

        await bot.answer_callback_query(call.id, "История очищена")
        await bot.send_message(call.message.chat.id, f"🗑️ История успешно очищена. Удалено записей: {deleted_count}")


    @bot.callback_query_handler(func=lambda call: call.data == "cancel_clear")
    async def handle_cancel_clear(call):
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения: {e}")
        
        await bot.answer_callback_query(call.id, "Действие отменено")


    @bot.callback_query_handler(func=lambda call:call.data == "subscribe" )
    async def handle_subscribe(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        if await is_user_subscribed(user_id):
            msg = await bot.send_message(
                chat_id,
                "🔆 Вы уже оформили подписку, вторая не принесет новых возможностей"
            )
            await auto_delete_message(bot, chat_id, msg.message_id)
            return
        
        text = f"""
🌟 Подписка стоит всего {SUBSCRIPTION_PRICE} ⭐ в месяц.
Оформи подписку, чтобы получить полный доступ ко всем ИИ и ролям.
Срок подписки 30 дней. 
/subscribe
                """
        msg = await bot.send_message(chat_id, text)
        await auto_delete_message(bot, chat_id, msg.message_id, 10)
        return
    
    
    @bot.pre_checkout_query_handler(func=lambda q: True)
    async def checkout(pre_checkout_query):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


    @bot.callback_query_handler(func=lambda call:call.data == "show_care_service" )
    async def handle_show_care_service(call):
        await bot.answer_callback_query(call.id, "Служба поддержки")

    # Обработчики админ-функционала
    @bot.callback_query_handler(func=lambda call:call.data == "admin_list_users")
    async def handle_list_users(call:CallbackQuery):
        await handle_admin_list_users(bot, call)


    @bot.callback_query_handler(func=lambda call:call.data == "admin_grant_subs")
    async def handle_grant_subs(call:CallbackQuery):
        await handle_admin_grant_subs(bot, call)