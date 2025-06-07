import threading
import re
import telebot
from datetime import datetime
from bot_init import bot
from database.client import get_user_history
from utils.logger import get_logger

logger = get_logger(__name__)

def build_history_messages(user_id, role_prompt, user_prompt, max_history=10):
    history = get_user_history(user_id)[-max_history:]
    messages = [{"role": "system", "content": role_prompt}]
    for entry in history:
        messages.append({"role": "user", "content": entry["query"]})
        messages.append({"role": "assistant", "content": entry["response"]})
    messages.append({"role": "user", "content": user_prompt})
    return messages

def auto_delete_message(chat_id, message_id, delay=5):
    def delete():
        try:
            bot.delete_message(chat_id, message_id)
        except Exception as e:
            logger.error(f"❌ Не удалось удалить сообщение в чате {message_id}: {e}")
    
    timer = threading.Timer(delay, delete)
    timer.start()

#В случаях, когда есть вероятность, что пользователь нажмет на одну кнопку несколько раз
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

def format_error_system_message(error_text, title="Ошибка",):
    """
    Форматирует сообщение об ошибке в HTML.
    Автоматически экранирует спецсимволы (<, >, &) в тексте ошибки.
    
    :param title: Заголовок ошибки (например, "Ошибка API")
    :param error_text: Текст ошибки (обычно str(e))
    :return: Готовое сообщение в HTML
    """
    escaped_error = error_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""
❌ <b>{title}</b>
Обратитесь в поддержку, предоставив следующий текст:
<code>{now}\n{escaped_error}</code>
    """.strip()

# Экранирование спецсимволов в MarkdownV2
def escape_markdown_v2(text):
    # Список символов, которые нужно экранировать в MarkdownV2
    escape_chars = r"'_\*\[\]\(\)~`>#+-=|{}.!"
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)
    