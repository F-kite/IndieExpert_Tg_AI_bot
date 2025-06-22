from telebot.types import InlineKeyboardButton

BACK_BUTTON = InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")

SIDE_BUTTONS={
    "/start": "🏠 Главное меню",
    "/profile": "👤 Профиль",
    "/choose_ai": "🧠 Выбрать нейросеть",
    "/choose_role": "🎭 Выбрать роль бота",
    "/history": "📖 История запросов",
    "/privacy": "🔒 Политика конфиденциальности",
}

INLINE_BUTTONS = {
    "show_profile": "👤 Профиль",
    "choose_ai": "🧠 Выбрать модель ИИ",
    "subscribe": "💳 Оформить подписку",
    "choose_role": "🎭 Выбор роли",
    "https://t.me/w_ViIl": "💬 Служба поддержки",
}

SUPPORT_BUTTON = { "https://t.me/w_ViIl": "💬 Служба поддержки"}

AI_MODELS_BUTTONS = {
    "gpt4o": "🧠 GPT-4o",
    "yandex_gpt": "🧠 Yandex GPT",
    "gigachat": "🧠 GigaChat",
    "sonar": "🧠 Perplexity",
    "deepseek": "🧠 DeepSeek",
    "claude": "🧠 Claude 3.7",
    "dalle3": "🖼️ DALL·E 3",
    "midjourney": "🖼️ Midjourney"
}


