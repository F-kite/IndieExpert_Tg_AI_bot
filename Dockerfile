FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot/ ./bot/
COPY RU.json /app/RU.json
COPY EN.json /app/EN.json

CMD ["python", "bot/bot.py"]