from telebot import types
from database.client import get_user_history

async def show_history_page(bot, chat_id, user_id, page_index):
    PAGE_SIZE = 2
    history = await get_user_history(user_id)
    total_items = len(history)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE  # округление вверх

    if page_index < 0 or page_index >= total_pages:
        await bot.send_message(chat_id, "⛔ Это конец истории.")
        return

    start_idx = page_index * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_items)
    current_page = history[start_idx:end_idx]

    response = f"📖 История запросов:\n\n"
    for item in current_page:
        date_str = item["timestamp"].strftime("%d.%m.%Y")
        response += f"🕒 {date_str}\n\n👤 {item['query']}\n🤖 {item['response']}\n\n"

    # Клавиатура
    markup = types.InlineKeyboardMarkup()
    buttons = []

    if page_index > 0:
        buttons.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"history_prev_{page_index}"))
    if end_idx < total_items:
        buttons.append(types.InlineKeyboardButton("➡️ Вперёд", callback_data=f"history_next_{page_index}"))

    if buttons:
        markup.row(*buttons)

    back_button = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
    clear_button = types.InlineKeyboardButton("🗑 Очистить историю", callback_data="clear_history")
    markup.add(back_button, clear_button)

    # Отправляем новое сообщение (или редактируем старое)
    await bot.send_message(chat_id, response, reply_markup=markup)