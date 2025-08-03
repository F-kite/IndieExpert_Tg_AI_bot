from telebot import types
from telebot.types import CallbackQuery
from config import *
from database.client import *
from utils.helpers import safe_edit_message, auto_delete_message, extract_russian_text
from utils.history_pages import show_history_page
from utils.logger import get_logger
from handlers.admin_handlers import *
from utils.keyboards import *


logger = get_logger(__name__)


def register_handlers(bot, ai_handlers):
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    async def handle_back_to_main(call: CallbackQuery):
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        markup = create_inline_menu(INLINE_BUTTONS)
        await ensure_user_exists(call.from_user)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=WELCOME_MESSAGE,
            reply_markup=markup
        )
        await bot.answer_callback_query(call.id, "Главное меню")


    @bot.callback_query_handler(func=lambda call:call.data == "show_profile" )
    async def handle_show_profile(call: CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        message_id = call.message.message_id
        await ensure_user_exists(call.from_user)
        try:
            user_profile = await get_user_info(user_id)
            markup = types.InlineKeyboardMarkup()
            is_admin =  ""

            if user_id in ADMINS : is_admin = "🔆 Администратор"

            if not user_profile:
                msg = await bot.send_message(chat_id, "❌ Профиль не найден.")
                await auto_delete_message(bot, chat_id, msg.message_id)
                return
            
            model_name = AI_PRESETS.get(user_profile.get("ai_model", "gpt-4o"), {}).get("name","Неизвестная модель")
            role_name = ROLE_PRESETS.get(user_profile.get("role", "tarot_reader"), {}).get("name", "Неизвестная роль")

            response = f"""
👤 Пользователь: <code>{user_profile.get('username')} </code>
{is_admin}

📅 Дата регистрации: <i>{user_profile.get("registered_at").strftime("%Y-%m-%d")}</i>
💸 Подписка: {"✅" if user_profile.get("is_subscribed", False) else "❌"}

🧠 Текущая модель ИИ: <i>{model_name}</i>
🎭 Текущая роль бота: <i>{extract_russian_text(role_name)}</i>
        """
            if is_admin:
                response += f"\n*️⃣ Есть доступ к команде /admin"

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
    async def handle_user_statistics(call: CallbackQuery):
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        user_id = call.from_user.id
        await ensure_user_exists(call.from_user)

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


    @bot.callback_query_handler(func=lambda call: call.data == "speech_settings")
    async def handle_speech_settings(call: CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        message_id = call.message.message_id
        await ensure_user_exists(call.from_user)
        user_doc = await get_user_info(user_id)
        is_subscribed = user_doc.get("is_subscribed", False)
        try:
            if not is_subscribed:
                msg = await bot.send_message(chat_id, "❗️Подпишись, чтобы разблокировать эту функцию")
                await auto_delete_message(bot, chat_id, msg.message_id)
                return    
            
            markup = await create_voice_settings_keyboard(user_id)

            response = TTS_SETTING_MESSAGE

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=response,
                reply_markup=markup,
                parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            await bot.answer_callback_query(call.id, "Ошибка при отображении настроек")


    @bot.callback_query_handler(func=lambda call: call.data == "toggle_process_voice")
    async def handle_speech_settings(call: CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        message_id = call.message.message_id

        user_data = await get_user_info(user_id)
        tts_settings = user_data.get("tts_settings", {})
        process_voice_messages = tts_settings.get("process_voice_messages", False)
        reply_voice_messages = tts_settings.get("reply_voice_messages", False)
        new_process_voice_messages = not process_voice_messages
            
        await users_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "tts_settings.process_voice_messages": new_process_voice_messages,
                    "tts_settings.reply_voice_messages": reply_voice_messages
                }
            }
        )


        response = TTS_SETTING_MESSAGE

        markup =  await create_voice_settings_keyboard(user_id)
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=response,
            reply_markup=markup,
            parse_mode="HTML"
        )
        

    @bot.callback_query_handler(func=lambda call: call.data == "toggle_reply_voice")
    async def handle_speech_settings(call: CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        message_id = call.message.message_id

        user_data = await get_user_info(user_id)
        tts_settings = user_data.get("tts_settings", {})
        process_voice_messages = tts_settings.get("process_voice_messages", False)
        reply_voice_messages = tts_settings.get("reply_voice_messages", False)
        new_reply_voice_messages = not reply_voice_messages
            
        await users_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "tts_settings.process_voice_messages": process_voice_messages,
                    "tts_settings.reply_voice_messages": new_reply_voice_messages
                }
            }
        )
        
        response = TTS_SETTING_MESSAGE

        markup =  await create_voice_settings_keyboard(user_id)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=response,
            reply_markup=markup,
            parse_mode="HTML"
        )


    @bot.callback_query_handler(func=lambda call: call.data == "choose_ai")
    async def handle_choose_ai(call: CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        await ensure_user_exists(call.from_user)
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
                msg = await bot.send_message(chat_id, "❌ Данная модель временно недоступна.")
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
    async def handle_choose_role(call: CallbackQuery): 
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        markup = await create_role_keyboard(user_id)
        await ensure_user_exists(call.from_user)
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
            if not is_subscribed and role_key not in  ["tarot_reader", "compatibility", "numerologist"]:
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
    async def handle_history_navigation(call: CallbackQuery):
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
    async def handle__clear_history(call: CallbackQuery):
        chat_id = call.message.chat.id
        markup = types.InlineKeyboardMarkup()
        confirm_btn = types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_clear")
        back_btn = types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_clear")
        markup.row(confirm_btn, back_btn)

        await bot.send_message(chat_id, CLEAR_DIALOG_MESSAGE, reply_markup=markup)


    @bot.callback_query_handler(func=lambda call: call.data == "confirm_clear")
    async def handle_confirm_clear(call: CallbackQuery):
        user = call.from_user
        deleted_count = await clear_user_history(user.id)

        await bot.answer_callback_query(call.id, "История очищена")
        await bot.send_message(call.message.chat.id, f"🗑️ История успешно очищена. Удалено записей: {deleted_count}")


    @bot.callback_query_handler(func=lambda call: call.data == "cancel_clear")
    async def handle_cancel_clear(call: CallbackQuery):
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения: {e}")
        
        await bot.answer_callback_query(call.id, "Действие отменено")


    @bot.callback_query_handler(func=lambda call:call.data == "subscribe" )
    async def handle_subscribe(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        await ensure_user_exists(call.from_user)

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
    async def handle_show_care_service(call: CallbackQuery):
        await bot.answer_callback_query(call.id, "Служба поддержки")

    # Обработчики админ-функционала
    @bot.callback_query_handler(func=lambda call:call.data == "admin_list_users")
    async def handle_list_users(call:CallbackQuery):
        await handle_admin_list_users(bot, call)

    # Колбэк для перехода к выдаче подписки
    @bot.callback_query_handler(func=lambda call:call.data == "admin_grant_subs")
    async def handle_grant_subs(call:CallbackQuery):
        await handle_admin_grant_subs(bot, call)

    # Колбэк для перехода к отзыву подписки
    @bot.callback_query_handler(func=lambda call: call.data == "admin_revoke_subscription")
    async def callback_admin_revoke_subs(call):
        await handle_admin_revoke_subs(bot, call)

    # Рассылка о тех. осблуживании
    @bot.callback_query_handler(func=lambda call: call.data == "admin_send_maintenance")
    async def handle_send_maintenance(call: CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id

        if user_id not in ADMINS:
            await bot.answer_callback_query(call.id, "⛔ Доступ запрещён")
            return

        # Подтверждение действия
        confirmation_text = (
            "⚠️ Вы уверены, что хотите отправить уведомление о техническом обслуживании всем пользователям?\n\n"
            "Это действие нельзя отменить."
        )
        markup = types.InlineKeyboardMarkup()
        confirm_button = types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_maintenance_send")
        cancel_button = types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_maintenance_send")
        markup.add(confirm_button, cancel_button)

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=confirmation_text,
            reply_markup=markup
        )
        await bot.answer_callback_query(call.id)


    @bot.callback_query_handler(func=lambda call: call.data == "confirm_maintenance_send")
    async def handle_confirm_maintenance_send(call: CallbackQuery):
        chat_id = call.message.chat.id

        msg =await bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="⏳ Рассылка уведомлений...",
            reply_markup=None
        )

        response = await send_maintenance_notification(bot)

        await auto_delete_message(bot, chat_id, msg.message_id, delay=3)
        await bot.send_message(chat_id, f"🔔 Все пользователи ({response[0]}) уведомлены о техническом обслуживании.\n⚠️ {response[1]} не были уведомлены.")


    @bot.callback_query_handler(func=lambda call: call.data == "cancel_maintenance_send")
    async def handle_cancel_maintenance_send(call: CallbackQuery):
        chat_id = call.message.chat.id
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="❌ Рассылка отменена",
            reply_markup=None
        )
        await bot.answer_callback_query(call.id, "Рассылка отменена")

    #Экспорт записей 
    @bot.callback_query_handler(func=lambda call: call.data == "process_export")
    async def handle_export_queries(call:CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        # Запрашиваем дату у пользователя
        await bot.send_message(chat_id, "📅 Введите дату в формате ГГГГ-ММ-ДД, от которой экспортировать запросы:")
        user_states[user_id] = "awaiting_export_date"