from telebot import handler_backends

class BotStates(handler_backends.StatesGroup):
    choosing_ai_model = handler_backends.State()
    choosing_role = handler_backends.State()
    writing_prompt = handler_backends.State()