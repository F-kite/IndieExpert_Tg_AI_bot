import telebot
from config import TELEGRAM_TOKEN, set_bot_id

# bot = telebot.TeleBot(TELEGRAM_TOKEN)
# set_bot_id(bot.get_me().id)

try:
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    set_bot_id(bot.get_me().id)
    print(bot.get_me())  # Если токен неверный — здесь будет ошибка
except Exception as e:
    print(f"Ошибка при проверке токена: {e}")