from telebot import types
from telebot.types import Message, LabeledPrice
from datetime import datetime, timedelta
from config import *
from database.client import *
from utils.keyboards import create_inline_menu, create_ai_keyboard, create_role_keyboard, create_payment_keyboard
from utils.helpers import *
from utils.history_pages import show_history_page
from utils.limits_check import check_ai_usage
from utils.logger import get_logger
from utils.subscription_checker import check_subscriptions_expiry
from utils.image_helpers import download_url_image

from handlers.admin_handlers import process_grant_subs_input
from utils.keyboards import create_admin_keyboard

logger = get_logger(__name__)

def register_handlers(bot, user_tasks, ai_handlers):
    @bot.message_handler(commands=["start"])
    async def cmd_send_welcome(message: Message):        
        await ensure_user_exists(message.from_user)
        markup = create_inline_menu(INLINE_BUTTONS)
        await bot.send_message(message.chat.id, WELCOME_MESSAGE, reply_markup=markup)


    @bot.message_handler(commands=["profile"])
    async def cmd_send_profile(message: Message):
        markup = types.InlineKeyboardMarkup()
        user_id = message.from_user.id
        await ensure_user_exists(message.from_user)
        user_profile = await get_user_info(user_id)
        is_admin =  ""

        if user_id in ADMINS : is_admin = "🔆 Царь и бог (администратор)"

        if not user_profile:
            msg = await bot.send_message(message.chat.id, "❌ Профиль не найден.")
            await auto_delete_message(bot, message.chat.id, msg.message_id)
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

        await bot.send_message(message.chat.id, response, reply_markup=markup, parse_mode="HTML")


    @bot.message_handler(commands=["choose_ai"])
    async def cmd_choose_ai(message: Message):
        user = message.from_user
        user_id = user.id
        await ensure_user_exists(user)
        
        user_data = await get_user_info(user_id)
        
        markup = await create_ai_keyboard(user_id, ai_handlers)
        await bot.send_message(message.chat.id, AI_MENU_MESSAGE, reply_markup=markup)


    @bot.message_handler(commands=["choose_role"])
    async def cmd_choose_role(message: Message):
        user = message.from_user
        user_id = user.id
        await ensure_user_exists(user)

        user_data = await get_user_info(user_id)

        markup = await create_role_keyboard(user_id)
        await bot.send_message(message.chat.id, ROLE_MENU_MESSAGE, reply_markup=markup, parse_mode="Markdown")


    @bot.message_handler(commands=["custom_role"])
    async def cmd_custom_role(message: Message):
        msg = await bot.send_message(message.chat.id, "⚠️ Функция находится в разработке")
        await auto_delete_message(bot, message.chat.id, msg.message_id)
        return
        user = message.from_user
        ensure_user_exists(user)
        user_id = user.id

        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"role": "custom"}}
        )

        await bot.send_message(message.chat.id, """
    ✏️ Введите свой системный промпт.
    Пример:
    "Вы — личный коуч, который помогает людям находить себя и менять жизнь."

    Ваш промпт:
    """)
        user_states[user_id] = "waiting_for_custom_prompt"


    @bot.message_handler(commands=["subscribe"])
    async def cmd_subscribe(message: Message):
        user = message.from_user
        user_id = user.id
        chat_id = message.chat.id
        await ensure_user_exists(user)

        if await is_user_subscribed(user_id):
            msg = await bot.send_message(
                message.chat.id,
                "🔆 Вы уже оформили подписку, вторая не принесет новых возможностей"
            )
            await auto_delete_message(bot, message.chat.id, msg.message_id)
            return

        if user_id in ADMINS:
            users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"is_subscribed": True, "subscription_end": None}}  # Без ограничения по времени
            )
            msg = await bot.send_message(message.chat.id, "👑 Вы — админ. Подписка активна навсегда.")
            await auto_delete_message(bot, message.chat.id, msg.message_id)
            return

        # Генерируем ссылку на покупку через @invoice
        title = "Подписка на бота"
        description = "‼️ Оформление подписки не подразумевает возврата средств в будущем"
        payload = f"sub_{user_id}_{int(datetime.now().timestamp())}"
        currency = "XTR"
        provider_token=""
        prices = [LabeledPrice(label="Ежемесячная подписка", amount=SUBSCRIPTION_PRICE)]
        # photo_url = "https://example.com/subscription_image.jpg "  # Необязательно

        await bot.send_invoice(
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
    async def handle_successful_payment(message: Message):
        user_id = message.from_user.id
        payment_info = message.successful_payment
        logger.info(f"💰 Пользователь {user_id} оплатил подписку: {payment_info.total_amount} {payment_info.currency}")

        await users_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "is_subscribed": True,
                    "subscription_start": datetime.now(),
                    "subscription_end": datetime.now() + timedelta(days=30)
                }
            }
        )
        await bot.send_message(message.chat.id, "✅ Вы успешно оформили подписку на 30 дней!")

        
    @bot.message_handler(commands=["unsubscribe"])
    async def cmd_unsubscribe(message: Message):
        user = message.from_user
        user_id = user.id
        await ensure_user_exists(user)
        
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"is_subscribed": False}}
        )
        await bot.send_message(message.chat.id, "❌ Вы отписались от бота.")


    @bot.message_handler(commands=["history"])
    async def cmd_send_history(message: Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        history = await get_user_history(user_id)
        await ensure_user_exists(message.from_user)

        if not history:
            msg = await bot.send_message(message.chat.id, "История запросов пуста.")
            await auto_delete_message(bot, message.chat.id, msg.message_id)
            return
        
        await show_history_page(bot, chat_id, user_id, page_index=0)


    @bot.message_handler(commands=["privacy"])
    async def cmd_send_privacy(message: Message):
        await ensure_user_exists(message.from_user)
        await bot.send_message(message.chat.id, PRIVACY_MESSAGE, parse_mode="HTML")
    
    # --- Панель администратора ---
    @bot.message_handler(commands=["admin"])
    async def cmd_admin_panel(message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id

        if user_id not in ADMINS:
            msg = await bot.reply_to(message, "⚠️ Эта команда не обрабатывается")
            await auto_delete_message(bot, chat_id, msg.message_id, 3)
            return

        await bot.send_message(
            chat_id=chat_id,
            text="🔐 Панель администратора",
            reply_markup=create_admin_keyboard()
        )

    # Принимаем ввод пользователей от админа
    @bot.message_handler(func=lambda m: m.from_user.id in ADMINS and user_states.get(m.from_user.id) == "awaiting_user_ids_for_subscription")
    async def handle_grant_subscription_input(message: Message):
        user_id = message.from_user.id
        input_text = message.text
        await process_grant_subs_input(bot, message, input_text)
        user_states.pop(user_id, None)

    @bot.message_handler(func=lambda message: True)
    async def cmd_handle_message(message: Message):
        user = message.from_user
        user_id = user.id
        chat_id = message.chat.id
        user_prompt = message.text
        error_markup = create_inline_menu(SUPPORT_BUTTON)
        processing_msg = None
        await ensure_user_exists(user)

        def get_key_by_name(name):
            for key, data in AI_PRESETS.items():
                if data.get("name") == name:
                    return key
            return None  # Если не найдено

        try:
            if user_prompt.strip().startswith("/"):
                # Игнор команд, которые не обрабатываются отдельно
                logger.warning(f"Пользователь {user_id} отправил команду, но она не поддерживается: {user_prompt}")
                msg = await bot.reply_to(message, "⚠️ Эта команда не обрабатывается")
                await auto_delete_message(bot, chat_id, msg.message_id, 3)
                return
            
            await check_subscriptions_expiry(bot, user_id=user_id)

            
            # Проверка, есть ли уже активный запрос у пользователя
            if user_id in user_tasks:
                msg = await bot.send_message(chat_id, "⏳ Пожалуйста, дождитесь ответа на предыдущее сообщение")
                await auto_delete_message(bot, chat_id, msg.message_id, 2)
                return
            
            user_data = await get_user_info(user_id)
            ai_preset = AI_PRESETS.get(user_data["ai_model"], AI_PRESETS["gpt-4o"])
            ai_role = ROLE_PRESETS.get(user_data["role"], ROLE_PRESETS["default"])
            ai_model = get_key_by_name(ai_preset["name"])
            role_prompt = await get_current_prompt(user_id)


            handler_info = ai_handlers.get(ai_model)
            if not handler_info:
                msg = await bot.send_message(chat_id, "❌ Данная модель временно недоступна.")
                await auto_delete_message(bot, chat_id, msg.message_id, 2)
                return
            
            ai_method = handler_info["method"]
            ai_client = handler_info["client"]

            # Проверяем подписку и лимиты
            allowed, reason = await check_ai_usage(user_id, user_data["ai_model"])
            if not allowed:
                msg = await bot.send_message(chat_id, reason + ".\n\nС подпиской ограничения на использование ИИ исчезнут")
                await auto_delete_message(bot, chat_id, msg.message_id, 3)
                return
            
            # Формирование messages с историей прошлых запросов
            messages = await build_history_messages(user_id, role_prompt, user_prompt, max_history=10)
            
            processing_msg_text = ""
            # Временное сообщение об обработке
            if ai_model in ["dalle3", "midjourney"]:
                processing_msg_text = f"🧠 {ai_preset['name']} генерирует изображение по вашему описанию\n\nℹ️ Созданные изображения не сохраняются в истории"
            else:
                processing_msg_text = f"🧠 {ai_preset['name']} формулирует ответ как {ai_role["name"]}"
            
            processing_msg = await bot.reply_to(message, processing_msg_text)

            # Добавление в очередь задач
            user_tasks[user_id] = True

            # Вызов ИИ
            ai_response = await ai_method(
                ai_model, ai_role,
                messages, ai_client
                
            )

            if ai_response != None and ai_model not in ["dalle3", "midjourney"]:
                formatted_response = clean_ai_response(ai_response)
                # formatted_response = ai_response
                await save_query_to_history(user_id, user_prompt, formatted_response)
                
                # Удаление временного сообщения
                await safe_delete_message(bot, chat_id, processing_msg.message_id )

                # Отправка реального сообщения
                await bot.send_message(chat_id, formatted_response, parse_mode="HTML")

                #Счетчик исп-я +1
                await users_collection.update_one(
                    {"user_id": user_id},
                    {"$inc": {f"monthly_usage.{ai_model}": 1}}  # Увеличиваем счётчик
                )

            elif ai_response != None and ai_model in ["dalle3", "midjourney"]:
                
                image = await download_url_image(chat_id, ai_response)
                caption=f"""
🖼️Изображение по вашему запросу:
```Запрос
{messages[-1]["content"]}
```
                        """
                
                # Удаление временного сообщения
                await safe_delete_message(bot, chat_id, processing_msg.message_id )

                # Отправляем фото
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=image,
                    caption=caption,
                    parse_mode="MarkdownV2"
                )

                #Счетчик исп-я +1
                await users_collection.update_one(
                    {"user_id": user_id},
                    {"$inc": {f"monthly_usage.{ai_model}": 1}}  # Увеличиваем счётчик
                )

            else:
                error_message = format_error_system_message(
                    title="Неизвестная ошибка.",
                    error_text=str(e)
                )
                msg = await bot.send_message(chat_id, error_message, reply_markup=error_markup, parse_mode="MarkdownV2")
                await auto_delete_message(bot, chat_id, msg.message_id, 30)

        except Exception as e:
            logger.error(f"Ошибка при обработке запроса: {e}")
            if processing_msg:
                await safe_delete_message(bot, chat_id, processing_msg.message_id)

            error_message = format_error_system_message(
                    title="Неизвестная ошибка.",
                    error_text=str(e)
                )
            msg = await bot.send_message(chat_id, error_message, reply_markup=error_markup, parse_mode="MarkdownV2")
            await auto_delete_message(bot, chat_id, msg.message_id, 30)
        finally:
            # Удаляем из списка активных задач
            if user_id in user_tasks:
                del user_tasks[user_id]

