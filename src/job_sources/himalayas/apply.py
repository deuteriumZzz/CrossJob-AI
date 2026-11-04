import time
from typing import Callable, Optional
from urllib.parse import urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from src.job_sources.block_detection import raise_if_blocked_after_wait

PAGE_LOAD_WAIT_SECONDS = 3
# Порядок = приоритет (не порядок в DOM). Голое "apply" убрано из submit:
# оно находило ту же "Apply now" и вакансия шла как отправленная.
_SUBMIT_TEXT_MARKERS = ("submit application", "send application", "submit")
_APPLY_TEXT_MARKERS = ("apply now", "apply")
CONFIRM_WAIT_SECONDS = 10
_READY_TEXT_MARKERS = ("i'm ready to apply", "ready to apply")


def apply_to_job(
    driver,
    job_link: str,
    answer_fn: Optional[Callable[[str], str]] = None,
) -> bool:
    """Подтверждено вживую 2026-09-03 (реальный залогиненный аккаунт,
    micro1 "AI Engineer" — Applied в /plus/job-application-tracker):
    клик "Apply Now" почти всегда открывает промежуточную nudge-модалку
    ("Don't let your application get lost in the pile... Generate resume
    with AI / I'm ready to apply / Don't show this again") — без ВТОРОГО
    клика по "I'm ready to apply" заявка никуда не уходит, никакая форма
    с полями при этом не появляется вообще (проверено: после первого
    клика document.querySelectorAll('input,textarea,select') видимых
    полей не находит). Если модалка не появилась (другая структура
    вакансии), падаем на обобщённый сценарий как у WellfoundClient.apply/
    GeekjobClient.apply — отвечаем на видимые текстовые/select/radio
    поля и жмём кнопку submit/apply/send application. Если после клика
    "Apply Now" домен страницы сменился — сторонний ATS работодателя,
    его форму никогда не заполняем и не отправляем сами."""
    driver.get(job_link)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    raise_if_blocked_after_wait(driver)

    apply_button = _find_button_by_visible_text(driver, _APPLY_TEXT_MARKERS)
    if apply_button is None:
        return False
    original_host = urlparse(driver.current_url).netloc
    handles_before = set(driver.window_handles)
    driver.execute_script("arguments[0].click();", apply_button)
    time.sleep(2)

    # 2026-11-04 сверка с /plus/job-application-tracker: из 35 "applied"
    # бота в трекере Himalayas только 2 (micro1). У остальных "Apply now" —
    # переход на сайт работодателя, чаще в НОВОЙ вкладке: домен текущей
    # вкладки не менялся, и бот шёл дальше и рапортовал успех.
    new_tabs = set(driver.window_handles) - handles_before
    if new_tabs:
        main_handle = driver.current_window_handle
        for handle in new_tabs:
            driver.switch_to.window(handle)
            driver.close()
        driver.switch_to.window(main_handle)
        return False
    if urlparse(driver.current_url).netloc != original_host:
        return False

    if driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]'):
        return False

    ready_button = _find_button_by_visible_text(driver, _READY_TEXT_MARKERS)
    if ready_button is not None:
        driver.execute_script("arguments[0].click();", ready_button)
        time.sleep(2)
        if not driver.find_elements(
            By.CSS_SELECTOR,
            'textarea, input[type="text"], input[type="number"]',
        ):
            return _wait_confirmed(driver)
    elif not driver.find_elements(
        By.CSS_SELECTOR, 'textarea, input[type="text"], input[type="number"]'
    ):
        # Ни nudge-модалки, ни формы — это не собственный отклик Himalayas.
        return False

    for field in driver.find_elements(
        By.CSS_SELECTOR, 'textarea, input[type="text"], input[type="number"]'
    ):
        if field.is_displayed() and not field.get_attribute("value"):
            question = _label_text_for(driver, field)
            field.send_keys(_answer(question, answer_fn))

    for select_el in driver.find_elements(By.TAG_NAME, "select"):
        if not select_el.is_displayed():
            continue
        for option in Select(select_el).options:
            value = option.get_attribute("value")
            if value:
                Select(select_el).select_by_value(value)
                break

    submit = _find_button_by_visible_text(driver, _SUBMIT_TEXT_MARKERS)
    if submit is None:
        return False
    driver.execute_script("arguments[0].click();", submit)
    return _wait_confirmed(driver)


def _wait_confirmed(driver) -> bool:
    """Успех = модалка закрылась (кнопки "I'm ready"/"Submit" больше нет) и
    на странице нет текста ошибки. Клик сам по себе — не отклик."""
    deadline = time.monotonic() + CONFIRM_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(1)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "something went wrong" in body or "try again" in body:
            return False
        if _find_button_by_visible_text(
            driver, _READY_TEXT_MARKERS + _SUBMIT_TEXT_MARKERS
        ) is None:
            return True
    return False


def _answer(question: str, answer_fn: Optional[Callable[[str], str]]) -> str:
    if answer_fn is None or not question:
        return ""
    try:
        return answer_fn(question)
    except Exception:
        return ""


def _label_text_for(driver, field) -> str:
    field_id = field.get_attribute("id")
    if field_id:
        labels = driver.find_elements(
            By.CSS_SELECTOR, f'label[for="{field_id}"]'
        )
        if labels:
            return labels[0].text.strip()
    return ""


def _find_button_by_visible_text(driver, needles: tuple[str, ...]):
    visible = [
        (el, (el.text or "").strip().lower())
        for el in driver.find_elements(
            By.CSS_SELECTOR, 'button, a[role="button"]'
        )
        if el.is_displayed()
    ]
    for needle in needles:  # приоритет по порядку needles, не по DOM
        for el, text in visible:
            if needle in text:
                return el
    return None
