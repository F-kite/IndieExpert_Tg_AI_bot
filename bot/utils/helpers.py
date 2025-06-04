import threading
import telebot
from bot_init import bot
from utils.logger import get_logger

logger = get_logger(__name__)

def auto_delete_message(chat_id, message_id, delay=5):
    def delete():
        try:
            bot.delete_message(chat_id, message_id)
        except Exception as e:
            logger.error(f"❌ Не удалось удалить сообщение в чате {message_id}: {e}")
    
    timer = threading.Timer(delay, delete)
    timer.start()

def safe_edit_message(bot, chat_id, message_id, text, reply_markup=None, parse_mode=None):
    try:
        bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" in str(e):
            # Сообщение не изменилось — ничего страшного
            return False
        else:
           logger.error(f"❌ Не удалось обновить сообщение: {e}")
    return True

def extract_russian_text(text):
    start_index = None
    for i, char in enumerate(text):
        if 'А' <= char.upper() <= 'Я' or char.lower() in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя':
            start_index = i
            break
    if start_index is not None:
        return text[start_index:]
    return ""