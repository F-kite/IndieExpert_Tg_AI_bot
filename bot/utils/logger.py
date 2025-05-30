import logging
import sys
import os

LOGS_DIR = "../logs"
LOG_FILE = os.path.join(LOGS_DIR, "app.log")
os.makedirs(LOGS_DIR, exist_ok=True)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()  # Логи также будут выводиться в консоль
    ]
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Вызовы Ctrl+C не логируем
        return sys.__excepthook__(exc_type, exc_value, exc_traceback)
    logging.error("Необработанное исключение", exc_info=(exc_type, exc_value, exc_traceback))
    
# Перехватываем все необработанные исключения
sys.excepthook = handle_exception