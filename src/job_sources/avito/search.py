import time
from urllib.parse import quote

from selenium.webdriver.common.by import By

from src.job import Job
from src.job_sources.avito.browser import dismiss_vpn_notice
from src.job_sources.avito.mapping import parse_search_html
from src.job_sources.block_detection import raise_if_blocked, visible_text

SEARCH_URL = "https://www.avito.ru/all/vakansii"
# ponytail: фильтр "Удалённо" — отдельный URL-путь, не query-параметр
# формата "remote=1" — подтверждено вживую 2026-09-29 (клик по
# радиокнопке "Удалённо" в фильтрах привёл именно на этот адрес).
# `f=` — непрозрачный хэш состояния фильтров Авито, `context=` в
# исходном URL — токен сессии поиска, опущен: прямой заход без него
# применяет тот же фильтр (проверено вживую). Комбинировать несколько
# фильтров через этот хэш нельзя — он кодирует ВСЁ состояние панели
# фильтров целиком, не по одному параметру на фильтр (проверено
# вживую: клик по "Занятость" на этой же странице дал другой,
# несовместимый f=). Поэтому опыт работы/занятость ниже применяются
# кликами по живой странице (как dismiss_vpn_notice), а не URL.
REMOTE_SEARCH_URL = (
    "https://www.avito.ru/all/vakansii/format_raboty/"
    "udalenno-ASgBAgICAUSejBW~lZED"
)
REMOTE_FILTER_PARAM = "f=ASgBAgICAkSUzQ_S6vQCnowVvpWRAw"
PAGE_LOAD_WAIT_SECONDS = 4

# "Опыт работы" — визуально стилизованный combobox
# (data-marker="params[827]"), настоящий <select> под ним скрыт (0×0,
# ElementNotInteractable в Selenium — подтверждено вживую 2026-09-29:
# Select().select_by_value() падает). Открывается живым кликом по
# контейнеру; сами опции в открывшемся списке — отдельные <button>
# с собственным стабильным маркером
# data-marker="params[827]/custom-option(<id>)" (не путать со скрытыми
# <option data-marker="params[827]/option(<id>)"> внутри select — те
# невидимы точно так же, как сам select). id совпадают с value у
# скрытого select — те же, что уже были подтверждены вживую раньше.
EXPERIENCE_LEVEL_VALUES = {
    "no_experience": "11904",
    "under_1_year": "3370663",
    "over_1_year": "11905",
    "over_3_years": "11906",
    "over_5_years": "12055",
    "over_10_years": "11907",
}
EXPERIENCE_COMBOBOX_MARKER = '[data-marker="params[827]"]'

# "Занятость" — обычные чекбоксы с data-marker, живой клик по ним
# подтверждён вживую (URL получает новый f= сразу, без кнопки
# "Найти" — SPA перерисовывает результаты сама).
EMPLOYMENT_TYPE_CHECKBOX_MARKERS = {
    "full_time": "params[172242]/checkbox/22066761",
    "part_time": "params[172242]/checkbox/22066866",
    "temporary": "params[172242]/checkbox/22066872",
}
FILTER_CLICK_WAIT_SECONDS = 1.5

# «Формат работы» — радио params[172815]; в отличие от «Занятости» выдачу
# обновляет только кнопка «Найти» (проверено вживую 2026-10-08).
WORK_FORMAT_MARKERS = {
    "office": "params[172815]/3286366",
    "hybrid": "params[172815]/3286368",
}
SUBMIT_MARKER = '[data-marker="search-form/submit-button"]'


COUNT_SCRIPT = (
    "const c=document.querySelector('[data-marker=\"page-title/count\"]');"
    "return c?c.innerText:'';"
)


def _result_signature(driver) -> str:
    """Счётчик объявлений + адрес: меняется, когда фильтр применился."""
    count = driver.execute_script(COUNT_SCRIPT) or ""
    return f"{count}|{'f=' in driver.current_url}"


def _apply_work_format(driver, work_format: str) -> bool:
    """Радио + «Найти». Сайт принимает клик не каждый раз (вживую
    2026-10-08: то 84 из 89, то без изменений), поэтому сверяем выдачу
    до и после и повторяем один раз."""
    marker = WORK_FORMAT_MARKERS.get(work_format)
    if not marker:
        return False
    for _ in range(2):
        radios = driver.find_elements(
            By.CSS_SELECTOR, f'[data-marker="{marker}"]'
        )
        submit = driver.find_elements(By.CSS_SELECTOR, SUBMIT_MARKER)
        if not radios or not submit:
            return False
        before = _result_signature(driver)
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", radios[0]
        )
        # Обычный клик Selenium по радио не проходит (элемент перекрыт).
        driver.execute_script("arguments[0].click();", radios[0])
        time.sleep(FILTER_CLICK_WAIT_SECONDS)
        driver.execute_script("arguments[0].click();", submit[0])
        time.sleep(PAGE_LOAD_WAIT_SECONDS + 3)
        if _result_signature(driver) != before:
            return True
    return False


def _apply_click_filters(
    driver, experience_level: str, employment_type: str
) -> bool:
    """Опыт работы/занятость — не URL (см. модульный докстринг), а
    реальные клики по живой странице поиска. Возвращает True, если
    что-то реально применили (значит нужен повторный парсинг страницы
    после того, как SPA перерисует результаты)."""
    applied = False
    value_id = EXPERIENCE_LEVEL_VALUES.get(experience_level)
    if value_id:
        combos = driver.find_elements(
            By.CSS_SELECTOR, EXPERIENCE_COMBOBOX_MARKER
        )
        if combos:
            combos[0].click()
            time.sleep(FILTER_CLICK_WAIT_SECONDS)
            options = driver.find_elements(
                By.CSS_SELECTOR,
                f'[data-marker="params[827]/custom-option({value_id})"]',
            )
            visible = [o for o in options if o.is_displayed()]
            if visible:
                visible[0].click()
                applied = True
    marker = EMPLOYMENT_TYPE_CHECKBOX_MARKERS.get(employment_type)
    if marker:
        elements = driver.find_elements(
            By.CSS_SELECTOR, f'[data-marker="{marker}"]'
        )
        if elements:
            elements[0].click()
            applied = True
    return applied


def search_jobs(
    driver,
    position: str,
    remote_only: bool = False,
    experience_level: str = "",
    employment_type: str = "",
    work_format: str = "",
) -> list[Job]:
    """Одна страница выдачи на позицию — подтверждено вживую 2026-09-29:
    для узкого поискового запроса пагинация на avito.ru не появляется
    (её DOM-узел присутствует, но пуст — paginationHidden), а
    добавление ?p=2 к URL молча отбрасывается SPA-роутером. Если для
    более широких positions это окажется не так — здесь нужно будет
    добавить обход страниц по тому же паттерну, что у geekjob."""
    if remote_only:
        url = f"{REMOTE_SEARCH_URL}?{REMOTE_FILTER_PARAM}&q={quote(position)}"
    else:
        url = f"{SEARCH_URL}?q={quote(position)}"
    driver.get(url)
    time.sleep(PAGE_LOAD_WAIT_SECONDS)
    dismiss_vpn_notice(driver)
    raise_if_blocked(visible_text(driver))
    if work_format and not remote_only:
        try:
            if _apply_work_format(driver, work_format):
                time.sleep(PAGE_LOAD_WAIT_SECONDS)
                dismiss_vpn_notice(driver)
                raise_if_blocked(visible_text(driver))
        except Exception:
            pass  # необязательное уточнение, как и остальные клики
    if experience_level or employment_type:
        try:
            if _apply_click_filters(driver, experience_level, employment_type):
                time.sleep(PAGE_LOAD_WAIT_SECONDS)
                dismiss_vpn_notice(driver)
                raise_if_blocked(visible_text(driver))
        except Exception:
            # ponytail: разметка фильтров могла смениться — best-effort,
            # не роняем весь поиск позиции из-за необязательного уточнения.
            pass
    return parse_search_html(driver.page_source)
