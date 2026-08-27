import random
import time
from datetime import datetime

from src.logging import logger

# ponytail: фиксированное окно случайной задержки вместо адаптивного
# backoff-подхода, расширить, если платформа всё ещё считает аккаунт
# похожим на бота.
MIN_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 90

MIN_SOURCE_DELAY_SECONDS = 10
MAX_SOURCE_DELAY_SECONDS = 30

# Холодное сообщение незнакомцу в Telegram — на порядок чувствительнее
# отклика на вакансию: несколько личных сообщений подряд за секунды с
# личного аккаунта — самый быстрый способ словить ограничения от
# Telegram. Пауза в минутах, а не секундах, как у откликов на площадках.
MIN_TELEGRAM_MESSAGE_DELAY_SECONDS = 120
MAX_TELEGRAM_MESSAGE_DELAY_SECONDS = 600


def wait_before_telegram_message() -> None:
    """Случайная пауза (2-10 минут) перед каждым холодным сообщением
    контакту из поста в Telegram-канале."""
    delay = random.uniform(
        MIN_TELEGRAM_MESSAGE_DELAY_SECONDS, MAX_TELEGRAM_MESSAGE_DELAY_SECONDS
    )
    logger.debug(f"Waiting {delay:.0f}s before next Telegram message...")
    time.sleep(delay)


def within_active_hours(start_hour: int, end_hour: int) -> bool:
    """Живой человек не пишет рекрутёрам в 4 утра — если задан диапазон
    активных часов (локальное время машины), холодные сообщения вне
    него просто откладываются до следующего прогона, а не копятся в
    очередь на отправку разом, как только начнутся активные часы."""
    return start_hour <= datetime.now().hour < end_hour


def wait_before_apply() -> None:
    """Случайная пауза перед каждым реальным откликом, чтобы серия
    из нескольких откликов не выглядела для платформы как всплеск
    бот-трафика."""
    delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
    logger.debug(f"Waiting {delay:.0f}s before next application...")
    time.sleep(delay)


def wait_between_sources() -> None:
    """Более короткая пауза между площадками при запуске --auto all,
    чтобы переключение источников подряд тоже не выглядело
    скриптовым."""
    delay = random.uniform(MIN_SOURCE_DELAY_SECONDS, MAX_SOURCE_DELAY_SECONDS)
    logger.debug(f"Waiting {delay:.0f}s before next source...")
    time.sleep(delay)


def randomized_daily_limit(base: int) -> int:
    """base * случайный множитель 0.7-1.0, округлённый вниз (минимум
    1) — вызывается один раз за запуск источника, а не при каждой
    проверке лимита, иначе дневной лимит "плавал" бы посреди одного
    прогона. Идеально одинаковый DAILY_APPLICATION_LIMIT каждый день
    сам по себе выглядит как признак бота."""
    return max(1, int(base * random.uniform(0.7, 1.0)))
