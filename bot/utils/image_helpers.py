import aiohttp
from io import BytesIO

async def download_url_image(chat_id, image_url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Не удалось загрузить изображение. Код ответа: {resp.status}")

                # Загружаем данные изображения
                image_data = BytesIO(await resp.read())
                image_data.name = f"generated_image_{chat_id}.png"
                return image_data
    except Exception as e:
        return Exception(f"Ошибка загрузки изображения: {e}")