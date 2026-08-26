from __future__ import annotations

import re
import time

from selenium.webdriver.common.by import By

from src.logging import logger

HH_BASE = "https://hh.ru"
RESUMES_URL = f"{HH_BASE}/applicant/resumes"
PAGE_LOAD_WAIT_SECONDS = 4
_RESUME_ID_RE = re.compile(r"/resume/([a-f0-9]+)")

# ponytail: клонирование — единственный ЖИВОЙ (не закомментированный)
# путь в hh-applicant-tool (см. operations/clone_resume.py) и там же он
# идёт через OAuth API (POST /resume_profile), которого у нас нет —
# здесь это браузерный аналог того же результата: клик по кнопке
# копирования резюме на hh.ru вместо вызова недокументированного
# эндпоинта. Селекторы НЕ подтверждены живым просмотром (нет доступа к
# аккаунту с резюме).
_CLONE_BUTTON_SELECTOR = (
    '[data-qa*="resume-duplicate"], [data-qa*="resume-copy"], '
    '[data-qa*="resume-clone"]'
)
_CREATE_BUTTON_SELECTOR = '[data-qa*="resume-add-button"]'
_TITLE_INPUT_SELECTOR = (
    'input[data-qa*="resume-title"], input[data-qa*="vacancy-of-interest"]'
)
_NEXT_BUTTON_SELECTOR = 'button[data-qa*="next"], button[data-qa*="continue"]'


def clone_resume(driver, resume_id: str) -> str | None:
    """Клонирует существующее резюме кликом (аналог hh-applicant-tool
    clone_resume.py, но без OAuth API — см. ponytail выше). Возвращает
    URL нового резюме, если клон удался и редирект успели поймать по
    URL, иначе None (кнопка не найдена/клон не подтверждён — не
    ошибка, просто "не сработало", как и остальные best-effort
    HH-клики в этом каталоге)."""
    driver.get(f"{HH_BASE}/resume/{resume_id}")
    time.sleep(PAGE_LOAD_WAIT_SECONDS)

    buttons = driver.find_elements(By.CSS_SELECTOR, _CLONE_BUTTON_SELECTOR)
    if not buttons or not buttons[0].is_displayed():
        logger.warning(
            f"Кнопка клонирования резюме не найдена на /resume/{resume_id} "
            "— либо разметка изменилась, либо у HH нет прямой кнопки "
            "копирования на этой странице (проверьте вручную)."
        )
        return None
    try:
        buttons[0].click()
        time.sleep(2)
    except Exception as e:
        logger.warning(f"Не удалось кликнуть клонирование резюме: {e}")
        return None

    match = _RESUME_ID_RE.search(driver.current_url)
    if not match or match.group(1) == resume_id:
        logger.warning(
            "После клика клонирования URL не похож на новое резюме "
            f"({driver.current_url}) — проверьте вручную, клонировалось "
            "ли резюме."
        )
        return None
    return driver.current_url


def start_resume_draft(driver, desired_title: str) -> str | None:
    """Запускает мастер создания резюме на hh.ru и заполняет только то,
    что реально известно проекту (желаемая должность) — многошаговую
    анкету (опыт/образование/навыки) НЕ проходит, оставляет черновик
    пользователю на доделку вручную. См. обоснование в плане: полная
    автоматизация мастера — большой объём хрупких непроверенных
    селекторов ради разового действия, лучше кикстартнуть и передать
    человеку. Возвращает URL черновика (для ссылки пользователю) или
    None, если даже стартовую кнопку не нашли."""
    driver.get(RESUMES_URL)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)

    buttons = driver.find_elements(By.CSS_SELECTOR, _CREATE_BUTTON_SELECTOR)
    if not buttons or not buttons[0].is_displayed():
        logger.warning(
            "Кнопка 'Создать резюме' не найдена на "
            f"{RESUMES_URL} — проверьте вручную."
        )
        return None
    try:
        buttons[0].click()
        time.sleep(2)
    except Exception as e:
        logger.warning(f"Не удалось начать создание резюме: {e}")
        return None

    title_inputs = driver.find_elements(
        By.CSS_SELECTOR, _TITLE_INPUT_SELECTOR
    )
    if title_inputs and title_inputs[0].is_displayed():
        try:
            title_inputs[0].send_keys(desired_title)
        except Exception as e:
            logger.warning(f"Не удалось ввести желаемую должность: {e}")
    else:
        logger.warning(
            "Поле желаемой должности не найдено в мастере резюме — "
            "черновик создан без предзаполнения, доделайте вручную."
        )

    next_buttons = driver.find_elements(
        By.CSS_SELECTOR, _NEXT_BUTTON_SELECTOR
    )
    if next_buttons and next_buttons[0].is_displayed():
        try:
            next_buttons[0].click()
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Не удалось перейти к следующему шагу: {e}")

    logger.info(
        f"Черновик резюме открыт на {driver.current_url} — остальные поля "
        "(опыт, образование, навыки) нужно заполнить вручную на hh.ru."
    )
    return driver.current_url
