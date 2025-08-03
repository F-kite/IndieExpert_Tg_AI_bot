from telebot import types
from telebot.async_telebot import AsyncTeleBot
import asyncio
import atexit
from openai import AsyncOpenAI
from bot_init import init_bot
from config import *
from database.client import *
from handlers import callback_handlers, message_handlers
from handlers.ai_handlers import *
from utils.logger import get_logger
from utils.helpers import *
from utils.subscription_checker import check_subscriptions_expiry


logger = get_logger(__name__)

@atexit.register
def shutdown_logger():
    logger.info("⛔ Бот остановлен.")

# Инициализация ИИ
client_gpt = AsyncOpenAI(api_key=OPENAI_API_KEY)
client_perplexity = AsyncOpenAI(api_key=PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")
client_deepseek = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
client_gemini = ""
client_claude = ""
client_midjourney = ""

ai_handlers = {
    "gpt-4o": {"client": client_gpt, "method":send_to_gpt},
    "dalle3": {"client": client_gpt, "method":send_to_dalle},
    #perplexity
    "sonar": {"client": client_perplexity, "method":send_to_perplexity},
    "deepseek": {"client": client_deepseek, "method":send_to_deepseek},
    # "gemini": {"client": client_gemini, "method":send_to_gemini},
    # "claude": {"client": client_claude, "method":send_to_claude},
    # "midjourney": {"client": client_midjourney, "method":send_to_midjourney},
}


# Установка боковой панели кнопок при старте бота
async def setup_bot_commands(bot):
    await bot.set_my_commands([
        types.BotCommand(cmd, desc) for cmd, desc in SIDE_BUTTONS.items()
    ])

# Ежедневная проверка подписок пользователй
async def daily_subscription_check(bot: AsyncTeleBot):
    while True:
        await check_subscriptions_expiry(bot)
        # Ждём 24 часа перед следующей проверкой
        await asyncio.sleep(86400)  # 24 * 60 * 60 = 86400


# --- Запуск бота ---
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    try:
        bot = loop.run_until_complete(init_bot())

        # Регистрируем хэндлеры с ботом
        callback_handlers.register_handlers(bot, ai_handlers)
        message_handlers.register_handlers(bot, user_tasks, ai_handlers)

        # Настраиваем команды
        loop.run_until_complete(setup_bot_commands(bot))

        # Запускаем фоновую проверку подписок
        loop.create_task(daily_subscription_check(bot))

        # Запускаем polling
        loop.run_until_complete(bot.polling(none_stop=True))
    except Exception as e:
        logger.error(f"⛔ Критическая ошибка: {e}")
    finally:
        loop.close()
