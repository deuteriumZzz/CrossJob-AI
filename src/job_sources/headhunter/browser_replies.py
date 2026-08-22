from __future__ import annotations

import re
import time

from selenium.webdriver.common.by import By

HH_BASE = "https://hh.ru"
NEGOTIATIONS_URL = f"{HH_BASE}/applicant/negotiations"
PAGE_LOAD_WAIT_SECONDS = 4
_URL_RE = re.compile(r"https?://\S+")


def find_external_link(message_text: str) -> str | None:
    """Внешняя ссылка (например форма ATS) в сообщении работодателя —
    её не заполняем автоматически (см. docstring
    fetch_new_employer_messages), только сообщаем о ней пользователю."""
    match = _URL_RE.search(message_text or "")
    return match.group(0) if match else None


def fetch_new_employer_messages(driver) -> list[dict]:
    """ponytail: data-qa раздела переговоров/чатов hh.ru — из публично
    задокументированных паттернов разметки, НЕ проверено на живой
    сессии (живой залогиненный аккаунт для проверки был недоступен,
    как и в HeadHunterBrowserClient._fill_cover_letter_if_present).
    Если разметка не совпала — возвращает пустой список вместо
    падения, поэтому основной прогон поиска/отклика не ломается, даже
    если это конкретное место требует доработки под актуальную
    разметку hh.ru при первом живом запуске.

    Формы по внешним ссылкам (сторонние ATS/гугл-формы, которые иногда
    присылает работодатель в чате) сюда намеренно не заходят и не
    заполняются — см. find_external_link: только обнаруживаются и
    возвращаются вызывающему коду, чтобы уведомить пользователя, а не
    вводить его личные данные на незнакомом сайте без подтверждения."""
    driver.get(NEGOTIATIONS_URL)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)

    results = []
    items = driver.find_elements(
        By.CSS_SELECTOR, '[data-qa*="negotiations-item"]'
    )
    for item in items:
        links = item.find_elements(
            By.CSS_SELECTOR, 'a[href*="/vacancy/"]'
        )
        if not links:
            continue
        href = links[0].get_attribute("href") or ""
        vacancy_id_match = re.search(r"/vacancy/(\d+)", href)
        if not vacancy_id_match:
            continue

        chat_link = item.find_elements(By.CSS_SELECTOR, 'a[data-qa*="chat"]')
        if not chat_link:
            continue
        driver.get(chat_link[0].get_attribute("href"))
        time.sleep(PAGE_LOAD_WAIT_SECONDS)

        messages = driver.find_elements(
            By.CSS_SELECTOR, '[data-qa*="chat-message"]'
        )
        if not messages:
            continue
        last_message = messages[-1]
        is_from_employer = "applicant" not in (
            last_message.get_attribute("data-qa") or ""
        )
        text = last_message.text.strip()
        if not is_from_employer or not text:
            continue

        results.append(
            {
                "external_id": vacancy_id_match.group(1),
                "message_id": text[:200],
                "text": text,
            }
        )

    return results


def send_reply(driver, text: str) -> bool:
    """Отправляет ответ в уже открытом чате (после
    fetch_new_employer_messages). ponytail: см. её докстринг про
    неподтверждённую разметку — то же самое касается поля ввода и
    кнопки отправки здесь."""
    inputs = driver.find_elements(
        By.CSS_SELECTOR, '[data-qa*="chat-message-input"], textarea'
    )
    if not inputs:
        return False
    inputs[0].send_keys(text)
    time.sleep(0.5)

    send_buttons = driver.find_elements(
        By.CSS_SELECTOR, '[data-qa*="chat-message-send"]'
    )
    if not send_buttons:
        return False
    send_buttons[0].click()
    time.sleep(1)
    return True
