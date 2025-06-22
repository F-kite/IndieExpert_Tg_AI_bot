import openai
import re
from utils.logger import get_logger

logger = get_logger(__name__)

async def send_to_gpt(model, role, messages, client):
    try: 
        # Вызов gpt
        response = client.chat.completions.create(
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
        return None

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        return None
    

async def send_to_perplexity(model, role, messages, client):
    try:  
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=role["temperature"],
            max_tokens=role["max_tokens"],
            top_p=role["top_p"],
            frequency_penalty=role["frequency_penalty"],
            presence_penalty=role["presence_penalty"]
        )

        response = response.choices[0].message.content.strip()
        formatted_response = re.sub(r'\[\d\]+', '', response)

        return formatted_response

    except openai.RateLimitError as e:
        logger.error(f"Rate limit error: {str(e)}")
        return None

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        return None


async def send_to_deepseek(model, role, messages, client):
    try: 
        if model == "deepseek": model += "-chat"
        response = client.chat.completions.create(
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
        return None

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        return None


async def send_to_gemini():
    pass


async def send_to_claude():
    pass


async def send_to_dalle(model, role, messages, client):
    try: 
        user_prompt = messages[-1]["content"]
        
        response = client.images.generate(
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
        return None
    
    except openai.BadRequestError as e:
        if "content_policy_violation" in str(e).lower():
            error_text = "🥲 Ваш запрос не соответствует политике безопасности OpenAI"
        else:
            error_text = f"⚠️ Не удалось сгенерировать изображение: {str(e)}"
        return error_text
    
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        return None


async def send_to_midjourney():
    pass





