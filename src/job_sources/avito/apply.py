import time

from selenium.webdriver.common.by import By

from src.job_sources.avito.browser import dismiss_vpn_notice
from src.job_sources.block_detection import raise_if_page_blocked

PAGE_LOAD_WAIT_SECONDS = 4
# ponytail: точная разметка кнопки отклика на детальной странице НЕ
# подтверждена вживую — avito.ru отдаёт "Доступ ограничен: проверка
# безопасности" на неё без реального залогиненного браузерного
# отпечатка (см. docstring init_avito_browser), увидеть саму кнопку
# было нечем. "Откликнуться"/"Отправить резюме" — обе формулировки
# встречаются в паблик-хелпе Авито про отклики на вакансии. Если
# первый реальный прогон с auto_apply вернёт dry-run на всех
# вакансиях с меткой "Отклик с резюме" — смотрите живую разметку и
# правьте эти строки.
_APPLY_TEXT_MARKERS = ("откликнуться", "отправить резюме", "откликнулись")


def apply_to_job(driver, job_link: str) -> bool:
    driver.get(job_link)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    dismiss_vpn_notice(driver)
    raise_if_page_blocked(driver)

    for el in driver.find_elements(
        By.CSS_SELECTOR, 'button, a[role="button"]'
    ):
        if not el.is_displayed():
            continue
        text = (el.text or "").strip().lower()
        if any(marker in text for marker in _APPLY_TEXT_MARKERS):
            driver.execute_script("arguments[0].click();", el)
            return _wait_responded(driver)
    return False


# Вживую 6.11: отклик на Авито — сам клик «Откликнуться» (кнопка потом не
# меняется), а в открывшемся чате с работодателем появляется системное
# «Вы откликнулись на вакансию». Нет его — отклик не засчитываем.
_RESPONDED_TEXT = "вы откликнулись"
RESPONDED_WAIT_SECONDS = 10


def _wait_responded(driver) -> bool:
    deadline = time.monotonic() + RESPONDED_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(1)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if _RESPONDED_TEXT in body:
            return True
    return False
