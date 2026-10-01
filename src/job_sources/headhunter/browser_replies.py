from __future__ import annotations

import re
import time
from dataclasses import dataclass

from selenium.webdriver.common.by import By

from src.logging import logger

HH_BASE = "https://hh.ru"
NEGOTIATIONS_URL = f"{HH_BASE}/applicant/negotiations"
PAGE_LOAD_WAIT_SECONDS = 4
_URL_RE = re.compile(r"https?://\S+")
_BLOCK_EMPLOYER_BUTTON_SELECTOR = (
    '[data-qa*="employer-block"], button[data-qa*="block-employer"]'
)
_CONFIRM_BUTTON_SELECTOR = 'button[data-qa*="confirm"]'
_NEGOTIATION_CHAT_CONTROL_SELECTOR = (
    'button[data-qa="open_chat"], a[data-qa*="chat"], '
    'a[href*="/applicant/negotiations/"], a[href*="/chat/"]'
)
_CHATIK_FRAME_SELECTOR = 'iframe[src*="chatik.hh.ru/chat/"]'
_NEGOTIATION_ITEM_SELECTOR = '[data-qa*="negotiations-item"]'
_NEGOTIATION_PAGE_SELECTOR = 'button[data-qa^="number-pages-"]'
_ARCHIVED_VACANCY_TEXTS = (
    "вакансия в архиве",
    "вакансия уже в архиве",
    "вакансия закрыта",
    "вакансия не найдена",
    "вакансия была удалена",
    "vacancy is archived",
    "vacancy not found",
    "job is no longer available",
)
_AUTHORIZATION_UNAVAILABLE_TEXTS = (
    "the vacancy you are trying to open is not available under "
    "current authorization",
    "to view this document you should be authorized as applicant",
)


@dataclass(frozen=True)
class ChatSendResult:
    """Итог ручного перехода к чату вакансии HH."""

    sent: bool
    archived: bool = False
    unavailable: bool = False


def find_external_link(message_text: str) -> str | None:
    """Внешняя ссылка (например форма ATS) в сообщении работодателя —
    её не заполняем автоматически (см. docstring
    fetch_new_employer_messages), только сообщаем о ней пользователю."""
    match = _URL_RE.search(message_text or "")
    return match.group(0) if match else None


def _open_chat_from_controls(driver, controls) -> bool:
    """Открывает Chatik по уже найденной кнопке или ссылке HH."""
    if not controls:
        return False

    control = controls[0]
    href = control.get_attribute("href") or ""
    if href:
        driver.get(href)
        time.sleep(PAGE_LOAD_WAIT_SECONDS)
        return True

    control.click()
    for _ in range(PAGE_LOAD_WAIT_SECONDS * 2):
        frames = driver.find_elements(By.CSS_SELECTOR, _CHATIK_FRAME_SELECTOR)
        if frames:
            driver.switch_to.frame(frames[0])
            return True
        time.sleep(0.5)
    return False


def _open_negotiation_chat(driver, item) -> bool:
    """Открывает чат переговоров через ссылку или кнопку текущего HH."""
    driver.switch_to.default_content()
    controls = item.find_elements(
        By.CSS_SELECTOR, _NEGOTIATION_CHAT_CONTROL_SELECTOR
    )
    return _open_chat_from_controls(driver, controls)


def _open_chat_from_vacancy_page(driver) -> bool:
    """Открывает чат на странице конкретной вакансии из журнала."""
    driver.switch_to.default_content()
    controls = driver.find_elements(
        By.CSS_SELECTOR, _NEGOTIATION_CHAT_CONTROL_SELECTOR
    )
    return _open_chat_from_controls(driver, controls)


def _vacancy_page_is_archived(driver) -> bool:
    """Распознаёт только явный текст HH об архивной вакансии.

    Отсутствие кнопки чата не считается архивом: это может быть временная
    ошибка загрузки или изменение вёрстки, а не закрытая вакансия.
    """
    try:
        page_text = driver.execute_script("return document.body.innerText")
    except Exception:
        return False
    normalized = page_text.casefold() if isinstance(page_text, str) else ""
    return any(marker in normalized for marker in _ARCHIVED_VACANCY_TEXTS)


def _vacancy_page_is_unavailable_for_current_account(driver) -> bool:
    """Распознаёт страницу HH с запретом доступа к вакансии."""
    try:
        page_text = driver.execute_script("return document.body.innerText")
    except Exception:
        return False
    normalized = page_text.casefold() if isinstance(page_text, str) else ""
    return any(
        marker in normalized for marker in _AUTHORIZATION_UNAVAILABLE_TEXTS
    )


def _find_negotiation_item(driver, vacancy_id: str):
    """Находит карточку отклика на любой странице переговоров HH."""
    driver.get(NEGOTIATIONS_URL)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    page_count = max(
        1,
        len(driver.find_elements(By.CSS_SELECTOR, _NEGOTIATION_PAGE_SELECTOR)),
    )

    for page_number in range(1, page_count + 1):
        if page_number > 1:
            buttons = driver.find_elements(
                By.CSS_SELECTOR,
                f'button[data-qa^="number-pages-{page_number}"]',
            )
            if not buttons:
                break
            buttons[0].click()
            time.sleep(PAGE_LOAD_WAIT_SECONDS)

        for item in driver.find_elements(
            By.CSS_SELECTOR, _NEGOTIATION_ITEM_SELECTOR
        ):
            links = item.find_elements(By.CSS_SELECTOR, 'a[href*="/vacancy/"]')
            if not links:
                continue
            href = links[0].get_attribute("href") or ""
            match = re.search(r"/vacancy/(\d+)", href)
            if match and match.group(1) == str(vacancy_id):
                return item
    return None


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
    items = driver.find_elements(By.CSS_SELECTOR, _NEGOTIATION_ITEM_SELECTOR)
    for item in items:
        links = item.find_elements(By.CSS_SELECTOR, 'a[href*="/vacancy/"]')
        if not links:
            continue
        href = links[0].get_attribute("href") or ""
        vacancy_id_match = re.search(r"/vacancy/(\d+)", href)
        if not vacancy_id_match:
            continue

        if not _open_negotiation_chat(driver, item):
            continue
        try:
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
        finally:
            driver.switch_to.default_content()

    return results


def send_chat_cover_letter_result(
    driver, vacancy_id: str, text: str, vacancy_url: str | None = None
) -> ChatSendResult:
    """Отклик ушёл без сопроводительного письма (форма его не приняла,
    см. HeadHunterBrowserClient._fill_cover_letter_if_present) — письмо
    отправляется первым сообщением в чат этой вакансии, тем же способом,
    что fetch_new_employer_messages находит и открывает чат. ponytail:
    та же неподтверждённая разметка чата, что и в остальных
    best-effort местах этого источника."""
    if vacancy_url:
        driver.get(vacancy_url)
        time.sleep(PAGE_LOAD_WAIT_SECONDS)
        if _vacancy_page_is_archived(driver):
            return ChatSendResult(sent=False, archived=True)
        if _vacancy_page_is_unavailable_for_current_account(driver):
            return ChatSendResult(sent=False, unavailable=True)
        if _open_chat_from_vacancy_page(driver):
            try:
                return ChatSendResult(sent=send_reply(driver, text))
            finally:
                driver.switch_to.default_content()

    item = _find_negotiation_item(driver, vacancy_id)
    if item is None or not _open_negotiation_chat(driver, item):
        return ChatSendResult(sent=False)
    try:
        return ChatSendResult(sent=send_reply(driver, text))
    finally:
        driver.switch_to.default_content()


def send_chat_cover_letter(
    driver, vacancy_id: str, text: str, vacancy_url: str | None = None
) -> bool:
    """Совместимый bool-обёртка для прежних сценариев отправки."""
    return send_chat_cover_letter_result(
        driver, vacancy_id, text, vacancy_url
    ).sent


def send_reply(driver, text: str) -> bool:
    """Отправляет ответ в уже открытом чате (после
    fetch_new_employer_messages). ponytail: см. её докстринг про
    неподтверждённую разметку — то же самое касается поля ввода и
    кнопки отправки здесь."""
    inputs = driver.find_elements(
        By.CSS_SELECTOR,
        'textarea[data-qa="text-input"], '
        '[data-qa*="chat-message-input"], textarea',
    )
    if not inputs:
        return False
    inputs[0].send_keys(text)
    time.sleep(0.5)

    send_buttons = driver.find_elements(
        By.CSS_SELECTOR,
        'button[data-qa="chatik-do-send-message"], '
        '[data-qa*="chat-message-send"]',
    )
    if not send_buttons:
        return False
    send_buttons[0].click()
    time.sleep(1)
    return True


def block_employer(driver, employer_link: str) -> bool:
    """Кликает "Заблокировать работодателя" на странице чата/вакансии
    работодателя. ponytail: селектор НЕ подтверждён живым просмотром —
    это серверная блокировка на стороне HH, жёстче и труднее
    отменяется, чем локальный текстовый company_blacklist в
    blacklist_filter.py. Вызывается ТОЛЬКО вручную (webui-эндпоинт), не
    из автоматического цикла поиска/чата — см. main.py."""
    driver.get(employer_link)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    buttons = driver.find_elements(
        By.CSS_SELECTOR, _BLOCK_EMPLOYER_BUTTON_SELECTOR
    )
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
        logger.warning(f"Не удалось заблокировать работодателя: {e}")
        return False
