import telebot
from config import TELEGRAM_TOKEN, set_bot_id

bot = telebot.TeleBot(TELEGRAM_TOKEN)
set_bot_id(bot.get_me().id)