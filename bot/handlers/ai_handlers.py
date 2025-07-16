import openai
import re
from utils.logger import get_logger
from io import BytesIO
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message
from utils.helpers import auto_delete_message, clean_ai_response
from utils.logger import get_logger


logger = get_logger(__name__)

async def send_to_gpt(model, role, messages, client):
    try: 
        # Вызов gpt
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=role["temperature"],
            max_tokens=role["max_tokens"],
            top_p=role["top_p"],
            frequency_penalty=role["frequency_penalty"],
            presence_penalty=role["presence_penalty"]
        )

        response = response.choices[0].message.content.strip()

        return response

    except openai.RateLimitError as e:
        logger.error(f"Rate limit error: {str(e)}")
        return "⚠️ Превышен лимит обращений к GPT. Попробуйте позже."

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        logger.warning(e)
        return "❌ Не удалось получить ответ от GPT"
    

async def send_to_perplexity(model, role, messages, client):
    try:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": role.get("temperature", 0.7),
            "max_tokens": role.get("max_tokens", 800),
            "top_p": role.get("top_p", 1.0),
        }

        if role.get("presence_penalty", 0.0) != 0.0:
            kwargs["presence_penalty"] = role["presence_penalty"]
        elif role.get("frequency_penalty", 0.0) != 0.0:
            kwargs["frequency_penalty"] = role["frequency_penalty"]

        response = await client.chat.completions.create(**kwargs)

        response = response.choices[0].message.content.strip()
        formatted_response = re.sub(r'\[\d\]+', '', response)

        return formatted_response

    except openai.RateLimitError as e:
        logger.error(f"Rate limit error: {str(e)}")
        return "⚠️ Превышен лимит обращений к Perplexity. Попробуйте позже."

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        logger.warning(e)
        return "❌ Не удалось получить ответ от Perplexity"
    

async def send_to_deepseek(model, role, messages, client):
    try: 
        if model == "deepseek": model += "-chat"
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=role["temperature"],
            max_tokens=role["max_tokens"],
            top_p=role["top_p"],
            frequency_penalty=role["frequency_penalty"],
            presence_penalty=role["presence_penalty"]
        )

        response = response.choices[0].message.content.strip()

        return response

    except openai.RateLimitError as e:
        logger.error(f"Rate limit error: {str(e)}")
        return "⚠️ Превышен лимит обращений к DeepSeek. Попробуйте позже."

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        return "❌ Не удалось получить ответ от DeepSeek"


async def send_to_gemini():
    pass


async def send_to_claude():
    pass


async def send_to_dalle(model, role, messages, client):
    try: 
        user_prompt = messages[-1]["content"]
        
        response = await client.images.generate(
            model="dall-e-3",
            prompt=user_prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )

        image_url = response.data[0].url

        return image_url

    except openai.RateLimitError as e:
        logger.error(f"Rate limit error: {str(e)}")
        return "⚠️ Превышен лимит обращений к DALLE. Попробуйте позже."
    
    except openai.BadRequestError as e:
        if "content_policy_violation" in str(e).lower():
            error_text = "🥲 Ваш запрос не соответствует политике безопасности OpenAI"
        else:
            error_text = f"⚠️ Не удалось сгенерировать изображение: {str(e)}"
        return error_text
    
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        return "❌ Не удалось получить ответ от DALLE"


async def send_to_midjourney():
    pass

# Обработка голосового сообщения
async def handle_voice_message(bot: AsyncTeleBot, message: Message, client):
    chat_id = message.chat.id
    
    try:
        # Получаем информацию о голосовом файле
        file_info = await bot.get_file(message.voice.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        
        if not file_info.file_path.endswith((".ogg", ".oga", ".mp3", ".mp4", ".wav", ".webm", ".mpeg", ".m4a", ".flac")):
            msg = await bot.reply_to(message, f"⚠️ Неподдерживаемый формат файла {file_info.file_path}")
            await auto_delete_message(bot, chat_id, msg.message_id, delay=5)
            return
        
        # Загружаем в память
        voice_data = BytesIO(downloaded_file)
        voice_data.name = "audio.ogg"

        # Отправляем в OpenAI Whisper
        transcription = await client.audio.transcriptions.create(
            model="whisper-1",
            file=voice_data,
            response_format="text"
        )

        if not transcription or not transcription.strip():
            logger.warning("⚠️ Не удалось распознать речь")
            msg = await bot.send_message(chat_id, "⚠️ Не удалось распознать речь в голосовом сообщении.")
            await auto_delete_message(bot, chat_id, msg.message_id, delay=5)
            return

        # Экранируем текст перед выводом в Telegram
        safe_text = clean_ai_response(transcription)

        # Отправляем результат
        return safe_text

    except Exception as e:
        logger.error(f"❌ Ошибка при обработке голосового сообщения: {e}")
        error_msg = await bot.send_message(chat_id, f"⚠️ Ошибка при обработке голоса: {str(e)}")
        await auto_delete_message(bot, chat_id, error_msg.message_id, delay=5)

# Генерация голосового
async def handle_text_to_speech(bot: AsyncTeleBot, message: Message, text, client):
    chat_id = message.chat.id
    try:
        response = await client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="nova",
            input=text,
            instructions = """
Emotionality/ Individuality: A Cheerful Guide 

Tone: Friendly, clear and encouraging, creating a calm atmosphere and making the listener feel confident and comfortable.

Pronunciation: Clear, articulate and steady, accelerated, making it easy to understand each instruction while maintaining the natural flow of conversation.

Pause: Brief, purposeful pauses after key instructions (such as "cross the street" and "turn right") to give the listener time to process and follow the information.

Emotions: Warm and supportive, conveying empathy and caring, ensuring that the listener feels guided and safe throughout the journey. quickly and clearly.
"""
        )

        if not response:
            logger.warning("⚠️ Не удалось сгенерировать речь")
            msg = await bot.send_message(chat_id, "⚠️ Не удалось сгенерировать голосовой ответ.")
            await auto_delete_message(bot, chat_id, msg.message_id, delay=5)
            return
        
        # Сохраняем аудио в память
        audio_data = BytesIO(response.content)
        audio_data.name = "output.ogg"
        return audio_data
    
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации голосового сообщения: {e}")
        error_msg = await bot.send_message(chat_id, f"⚠️ Ошибка при генерации голосового сообщения: {str(e)}")
        await auto_delete_message(bot, chat_id, error_msg.message_id, delay=5)