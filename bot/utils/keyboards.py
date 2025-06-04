from telebot import types
from dotenv import load_dotenv
from config import SUBSCRIPTION_PRICE, AI_PRESETS, ROLE_PRESETS
from database.client import get_user_info
from utils.helpers import extract_russian_text

load_dotenv()


def create_inline_menu(buttons):
    markup = types.InlineKeyboardMarkup()
    buttons_list = list(buttons.items())

    # Добавляем первые две кнопки в одной строке
    if len(buttons_list) >= 2:
        first_key, first_label = buttons_list[0]
        second_key, second_label = buttons_list[1]

        if first_key.startswith("http"):
            btn1 = types.InlineKeyboardButton(first_label, url=first_key)
        else:
            btn1 = types.InlineKeyboardButton(first_label, callback_data=first_key)

        if second_key.startswith("http"):
            btn2 = types.InlineKeyboardButton(second_label, url=second_key)
        else:
            btn2 = types.InlineKeyboardButton(second_label, callback_data=second_key)

        markup.row(btn1, btn2)

    # Остальные кнопки по одной
    for key, label in buttons_list[2:]:
        if key.startswith("http"):
            markup.add(types.InlineKeyboardButton(label, url=key))
        else:
            markup.add(types.InlineKeyboardButton(label, callback_data=key))

    return markup


def create_ai_keyboard(user_id):
    markup = types.InlineKeyboardMarkup()
    
    # Получаем текущую модель из БД
    user_data = get_user_info(user_id)
    current_model_key = user_data.get("ai_model", "gpt-4o")
    is_subscribed = user_data.get("is_subscribed", False)

    models = list(AI_PRESETS.items())
    for i in range(0, len(models), 2):
        row = []
        for key, data in models[i:i+2]:
            model_name = data["name"]
            
            if not is_subscribed and key != "gpt-4o":
                # Для неподписанных пользователей: заблокировать все, кроме gpt-4o
                btn = types.InlineKeyboardButton(f"🔒 {model_name}", callback_data="locked_ai")
            else:
                if key == current_model_key:
                    # Если это текущая модель — показываем галочку
                    btn = types.InlineKeyboardButton(f"✅ {model_name}", callback_data=f"ai_{key}")
                else:
                    # Другие модели для подписчиков
                    btn = types.InlineKeyboardButton(f"{model_name}", callback_data=f"ai_{key}")
                
            row.append(btn)
        
        markup.row(*row)

    # Кнопка "Назад"
    back_button = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
    markup.add(back_button)

    return markup


def create_role_keyboard(user_id):
    markup = types.InlineKeyboardMarkup()

    user_data = get_user_info(user_id)
    current_role_key = user_data.get("role", "default")
    is_subscribed = user_data.get("is_subscribed", False)

    roles = list(ROLE_PRESETS.items())

    for i in range(0, len(roles), 2):
        row = []
        for key, data in roles[i:i+2]:
            role_name = data["name"]
            
            if not is_subscribed and key != "default":
                # Для неподписанных пользователей: заблокировать все, кроме default
                btn = types.InlineKeyboardButton(f"🔒 {extract_russian_text(role_name)}", callback_data="locked_ai")
            else:
                if key == current_role_key:
                    # Если это текущая роль — показываем галочку
                    btn = types.InlineKeyboardButton(f"✅ {extract_russian_text(role_name)}", callback_data=f"role_{key}")
                else:
                    # Другие роли для подписчиков
                    btn = types.InlineKeyboardButton(f"{role_name}", callback_data=f"role_{key}")
                
            row.append(btn)
    
        markup.row(*row)

    # Кнопка "Назад"
    back_button = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
    markup.add(back_button)

    return markup


def create_payment_keyboard():
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton(f"💳 Подписаться за {SUBSCRIPTION_PRICE} ⭐", pay=True)
    markup.add(btn)
    return markup