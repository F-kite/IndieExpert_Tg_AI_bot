from telebot import handler_backends

class BotStates(handler_backends.StatesGroup):
    custom_user_prompt = "waiting_for_custom_prompt"