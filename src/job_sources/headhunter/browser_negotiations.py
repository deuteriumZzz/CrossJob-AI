from __future__ import annotations

import re
import time
from datetime import datetime

from selenium.webdriver.common.by import By

from src.logging import logger

HH_BASE = "https://hh.ru"
NEGOTIATIONS_URL = f"{HH_BASE}/applicant/negotiations"
PAGE_LOAD_WAIT_SECONDS = 4

# ponytail: та же конвенция непроверенных селекторов, что в
# browser_replies.py/browser_test_answer.py — список переговоров
# переиспользует confirmed-селектор карточки ([data-qa*="negotiations-item"]),
# но статус/дата/кнопка отмены внутри карточки НЕ подтверждены прямым
# просмотром живой страницы.
_STATUS_KEYWORDS_DISCARD = ("отказ",)
_CANCEL_BUTTON_SELECTOR = (
    '[data-qa*="negotiations-item-collapse"], '
    'button[data-qa*="response-cancel"], button[data-qa*="cancel"]'
)
_CONFIRM_BUTTON_SELECTOR = 'button[data-qa*="confirm"]'


def list_withdrawable_negotiations(
    driver, older_than_days: int | None = None
) -> list[dict]:
    """Аналог отбора из hh-applicant-tool/operations/clear_negotiations.py:
    если older_than_days задан — отбирает отклики без изменений дольше
    этого числа дней (независимо от статуса); если не задан — только
    отклики в статусе "отказ". Каждый элемент результата хранит ссылку
    на сам Selenium-элемент карточки (ключ "element") — withdraw_negotiation
    кликает по нему напрямую, без повторного поиска на странице."""
    driver.get(NEGOTIATIONS_URL)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)

    results = []
    items = driver.find_elements(
        By.CSS_SELECTOR, '[data-qa*="negotiations-item"]'
    )
    for item in items:
        links = item.find_elements(By.CSS_SELECTOR, 'a[href*="/vacancy/"]')
        if not links:
            continue
        href = links[0].get_attribute("href") or ""
        vacancy_id_match = re.search(r"/vacancy/(\d+)", href)
        if not vacancy_id_match:
            continue

        item_text = (item.text or "").lower()
        is_discard = any(kw in item_text for kw in _STATUS_KEYWORDS_DISCARD)

        days_old = None
        time_elements = item.find_elements(By.CSS_SELECTOR, "time[datetime]")
        if time_elements:
            raw_datetime = time_elements[0].get_attribute("datetime")
            try:
                updated_at = datetime.fromisoformat(raw_datetime)
                days_old = (datetime.now(updated_at.tzinfo) - updated_at).days
            except (TypeError, ValueError):
                days_old = None

        if older_than_days is not None:
            selected = days_old is not None and days_old > older_than_days
        else:
            selected = is_discard

        if not selected:
            continue

        results.append(
            {
                "vacancy_id": vacancy_id_match.group(1),
                "vacancy_url": href,
                "is_discard": is_discard,
                "days_old": days_old,
                "element": item,
            }
        )

    return results


def withdraw_negotiation(driver, entry: dict) -> bool:
    """Кликает "Отменить отклик" на карточке из
    list_withdrawable_negotiations. ponytail: селектор кнопки НЕ
    подтверждён живым просмотром — деструктивное действие, вызывающий
    код обязан логировать каждую попытку (см. cleanup_headhunter_negotiations
    в main.py)."""
    item = entry.get("element")
    if item is None:
        return False
    buttons = item.find_elements(By.CSS_SELECTOR, _CANCEL_BUTTON_SELECTOR)
    if not buttons or not buttons[0].is_displayed():
        return False
    try:
        buttons[0].click()
        time.sleep(1)
        confirm = driver.find_elements(
            By.CSS_SELECTOR, _CONFIRM_BUTTON_SELECTOR
        )
        if confirm and confirm[0].is_displayed():
            confirm[0].click()
            time.sleep(1)
        return True
    except Exception as e:
        logger.warning(
            f"Не удалось отменить отклик {entry.get('vacancy_url')}: {e}"
        )
        return False
