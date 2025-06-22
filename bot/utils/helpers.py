import asyncio
import re
import telebot
from datetime import datetime
from config import GENERAL_SYSTEM_PROMPT
from database.client import get_user_history
from utils.logger import get_logger

logger = get_logger(__name__)

async def build_history_messages(user_id, role_prompt, user_prompt, max_history=10):
    user_history = await get_user_history(user_id)
    history = user_history[-max_history:]

    role_prompt += f"\n{GENERAL_SYSTEM_PROMPT}"

    messages = [{"role": "system", "content": role_prompt}]
    for entry in history:
        messages.append({"role": "user", "content": entry["query"]})
        messages.append({"role": "assistant", "content": entry["response"]})
    messages.append({"role": "user", "content": user_prompt})
    return messages


async def auto_delete_message(bot, chat_id, message_id, delay=5):
    try:
        await asyncio.sleep(delay)  # Ждём указанное количество секунд
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить сообщение {message_id}: {e}")

#В случаях, когда есть вероятность, что пользователь нажмет на одну кнопку несколько раз
async def safe_edit_message(bot, chat_id, message_id, text, reply_markup=None, parse_mode=None):
    try:
        await bot.edit_message_text(
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


async def safe_delete_message(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {message_id}: {e}")


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
❌ *{title}*
Обратитесь в поддержку, предоставив следующий текст:
```
{now}\n{escaped_error}
```
    """.strip()

# Очистка от лишних символов 
def clean_ai_response(text):
    if not isinstance(text, str):
        return ""

    # Удаляем все основные элементы Markdown
    text = re.sub(r'[\*\_\`\~\#\>\+\!\$\^]', '', text)

    # Удаляем ссылки и изображения
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

    # Удаляем лишние переносы строк
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'\\', '', text)

    return text.strip()

