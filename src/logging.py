import logging
import logging.handlers
import os
import sys

from loguru import logger
from selenium.webdriver.remote.remote_connection import (
    LOGGER as selenium_logger,
)

from config import LOG_LEVEL, LOG_SELENIUM_LEVEL, LOG_TO_CONSOLE, LOG_TO_FILE


def remove_default_loggers():
    """Чистим обработчики и старый лог-файл, чтобы при повторном
    запуске/импорте логи прошлого запуска не мешались с текущим."""
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    if os.path.exists("log/app.log"):
        os.remove("log/app.log")


def init_loguru_logger():
    """Файловый и консольный вывод включаются независимо друг от
    друга флагами LOG_TO_FILE/LOG_TO_CONSOLE — например, чтобы
    отключить вывод в консоль в CI, оставив файл."""

    def get_log_filename():
        return "log/app.log"

    log_file = get_log_filename()

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger.remove()

    # Файловый логгер добавляем, только если включён LOG_TO_FILE
    if LOG_TO_FILE:
        logger.add(
            log_file,
            level=LOG_LEVEL,
            rotation="10 MB",
            retention="1 week",
            compression="zip",
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:"
                "<cyan>{line}</cyan> - <level>{message}</level>"
            ),
            backtrace=True,
            diagnose=True,
        )

    # Консольный логгер добавляем, только если включён LOG_TO_CONSOLE
    if LOG_TO_CONSOLE:
        logger.add(
            sys.stderr,
            level=LOG_LEVEL,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:"
                "<cyan>{line}</cyan> - <level>{message}</level>"
            ),
            backtrace=True,
            diagnose=True,
        )


def init_selenium_logger():
    """Selenium крайне многословен, поэтому его лог пишем в
    отдельный файл, не смешивая с логами приложения."""
    log_file = "log/selenium.log"
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    selenium_logger.handlers.clear()

    selenium_logger.setLevel(LOG_SELENIUM_LEVEL)

    # Создаём файловый обработчик для логгера selenium
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when="D", interval=1, backupCount=5
    )
    file_handler.setLevel(LOG_SELENIUM_LEVEL)

    # Задаём упрощённый формат записей для логгера selenium
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    # Подключаем файловый обработчик к логгеру selenium
    selenium_logger.addHandler(file_handler)


remove_default_loggers()
init_loguru_logger()
init_selenium_logger()
