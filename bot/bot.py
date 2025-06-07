from telebot import types
import atexit
import logging
import openai
from openai import OpenAI
from bot_init import bot
from config import *
from database.client import get_user_info, get_current_prompt, save_query_to_history, ensure_user_exists, users_collection
from handlers import callback_handlers, message_handlers
from utils.keyboards import create_inline_menu
from utils.logger import get_logger
from utils.helpers import auto_delete_message, format_error_system_message, build_history_messages, escape_markdown_v2
from utils.limits import check_ai_usage


callback_handlers.register_handlers(bot)
message_handlers.register_handlers(bot)
logger = get_logger(__name__)

@atexit.register
def shutdown_logger():
    logger.info("⛔ Бот остановлен.")

# Инициализация ИИ
client_gpt = OpenAI(api_key=OPENAI_API_KEY)

# Установка боковой панели кнопок при старте бота
def setup_bot_commands():
    bot.set_my_commands([
        types.BotCommand(cmd, desc) for cmd, desc in SIDE_BUTTONS.items()
    ])
setup_bot_commands()


# ---- Обработчкики ----
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id

    if user_id == BOT_ID:
        logging.warning(f"⚠️ Callback от бота — игнорируется.\n`{ call.message.text}`")
        return


# Обработка подтверждения подписки
@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


# Обработчик других сообщений
@bot.message_handler(func=lambda message: True)
def cmd_handle_message(message):
    user = message.from_user
    user_id = user.id
    chat_id = message.chat.id
    user_input = message.text
    ensure_user_exists(user)

    def get_key_by_name(name):
        for key, data in AI_PRESETS.items():
            if data.get("name") == name:
                return key
        return None  # Если не найдено

    try:
        user_data = get_user_info(user_id)
        ai_preset = AI_PRESETS.get(user_data["ai_model"], AI_PRESETS["gpt-4o"])
        ai_role = ROLE_PRESETS.get(user_data["role"], ROLE_PRESETS["default"])
        ai_model = get_key_by_name(ai_preset["name"])
        
        role_prompt = get_current_prompt(user_id)
        user_prompt = user_input

        # Проверяем подписку и лимиты
        allowed, reason = check_ai_usage(user_id, user_data["ai_model"])
        if not allowed:
            msg = bot.send_message(chat_id, reason + ".\n\nС подпиской ограничения на использование ИИ исчезнут")
            auto_delete_message(chat_id, msg.message_id, 3)
            return
        
        # Формирование messages с историей прошлых запросов
        messages = build_history_messages(user_id, role_prompt, user_prompt, max_history=10)
        
        # Вызов gpt
        response = client_gpt.chat.completions.create(
            model=ai_model,
            messages=messages,
            temperature=ai_role["temperature"],
            max_tokens=ai_role["max_tokens"],
            top_p=ai_role["top_p"],
            frequency_penalty=ai_role["frequency_penalty"],
            presence_penalty=ai_role["presence_penalty"]
        )

        ai_response = response.choices[0].message.content.strip()
        save_query_to_history(user_id, user_input, ai_response)
        
        safe_response = escape_markdown_v2(ai_response)

        bot.send_message(chat_id, safe_response, parse_mode="MarkdownV2")

        #Счетчик исп-я +1
        users_collection.update_one(
            {"user_id": user_id},
            {"$inc": {f"monthly_usage.{ai_model}": 1}}  # Увеличиваем счётчик
        )

    except openai.RateLimitError as e:
        msg = bot.send_message(chat_id, "❌ Превышен лимит обращений к OpenAI. Подождите немного.",)
        auto_delete_message(chat_id, msg.message_id, 5)
        logger.error(f"Rate limit error: {e}")

    except openai.APIError as e:
        error_message = format_error_system_message(
            title="Ошибка при обращении",
            error_text=str(e)
        )
        markup = create_inline_menu(SUPPORT_BUTTON)
        msg = bot.send_message(chat_id, error_message, reply_markup=markup, parse_mode="HTML")
        auto_delete_message(chat_id, msg.message_id, 60)
        logger.error(f"OpenAI API error: {e}")

    except Exception as e:
        error_message = format_error_system_message(
            title="Неизвестная ошибка.",
            error_text=str(e)
        )
        markup = create_inline_menu(SUPPORT_BUTTON)
        msg = bot.send_message(chat_id, error_message, reply_markup=markup, parse_mode="HTML")
        auto_delete_message(chat_id, msg.message_id, 60)
        logger.error(f"Ошибка: {e}")


# --- Запуск бота ---
if __name__ == "__main__":
    logger.info("🚀 Бот запущен...")
    bot.polling(none_stop=True)

