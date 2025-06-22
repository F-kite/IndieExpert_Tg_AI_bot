from telebot.async_telebot import AsyncTeleBot
from database.client import test_mongo_connection
from config import TELEGRAM_TOKEN, set_bot_id
from utils.logger import get_logger

logger = get_logger(__name__)

async def init_bot():
    bot = AsyncTeleBot(TELEGRAM_TOKEN)
    try:
        me = await bot.get_me()
        set_bot_id(me.id)
        logger.info(f"🚀 Бот создан. {me.first_name} (@{me.username})")

        if not await test_mongo_connection():
            logger.error("❌ Ошибка при подключении к базе данных")
            exit(1)

        return bot
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации бота: {e}")
        raise
    