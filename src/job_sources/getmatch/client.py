import re
import time
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.html_text import html_letter_to_plain_text
from src.utils.chrome_utils import init_browser, is_driver_dead

# ponytail: GetMatch поменял "Откликнуться" с одиночной модалки
# (сопроводительное письмо + "Отправить отклик") на мастер анкеты в
# несколько шагов ("Шаг 1 из 5" — форматы работы, "Шаг 2 из 5" —
# специальности, ...) — подтверждено вживую 2026-09-02. Заполнять эти
# шаги вслепую рискованно (реальные профильные данные пользователя),
# поэтому просто детектим новый мастер и не притворяемся, что отклик
# отправлен.
_WIZARD_STEP_RE = re.compile(r"Шаг \d+ из \d+")

GM_BASE = "https://getmatch.ru"
# ponytail: раньше здесь был фиксированный sleep вместо явного ожидания
# элемента — не успевал за первой загрузкой
# /vacancies на свежезапущенном Chrome (холодный старт — JS-бандл ещё не
# скомпилирован/не закэширован) — вживую поймано дважды: search()
# получал 0 карточек на странице 1 и молча считал список пустым
# (see MAX_PAGES stop-on-empty в source.py), хотя вакансии были и
# та же страница рендерилась нормально на уже прогретом браузере.
# Bounded-poll вместо sleep — тот же приём, что у HeadHunterBrowserClient.
# _wait_for_any (см. его докстринг: та же гонка чинилась там для клика
# "Откликнуться").
VACANCIES_PAGE_TIMEOUT_SECONDS = 10.0
VACANCIES_PAGE_POLL_INTERVAL_SECONDS = 0.5


def _wait_for_vacancies_page(driver) -> None:
    deadline = time.monotonic() + VACANCIES_PAGE_TIMEOUT_SECONDS
    while True:
        if driver.find_elements(By.CSS_SELECTOR, "div.b-vacancy-card"):
            return
        # "Найдено N вакансий" остаётся в DOM даже на пустой странице
        # за концом списка (see MAX_PAGES) — по нему тоже можно
        # понять, что рендер уже закончился, а не просто карточек нет.
        if "Найден" in visible_text(driver):
            return
        if time.monotonic() >= deadline:
            return
        time.sleep(VACANCIES_PAGE_POLL_INTERVAL_SECONDS)


def _wait_until(predicate, timeout=10.0, interval=0.5) -> bool:
    """Общий bounded-poll — тот же приём, что у _wait_for_vacancies_page
    и HeadHunterBrowserClient._wait_for_any, но без завязки на конкретный
    селектор: predicate сам решает, что считать готовностью."""
    deadline = time.monotonic() + timeout
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


class GetMatchClient:
    """GetMatch — это SPA на Next.js с клиентским рендерингом: в
    исходном HTML вообще нет данных о вакансиях (подтверждено прямым
    запросом: 0 ссылок на вакансии до выполнения JS), поэтому здесь
    используется настоящий браузер Selenium вместо httpx, в отличие
    от остальных скрейперов. profile_dir (если передан) даёт Chrome
    постоянный профиль вместо чистого запуска каждый раз — см.
    src/utils/chrome_utils.py.

    ponytail: используйте как контекстный менеджер (`with
    GetMatchClient(profile_dir) as client:`), чтобы один Chrome-процесс
    переиспользовался на весь прогон (поиск + отклики) вместо
    открытия/закрытия браузера на каждый вызов — см. тот же приём и
    обоснование в HeadHunterBrowserClient. Без `with` — старое
    поведение (свой driver на вызов), для обратной совместимости."""

    def __init__(self, profile_dir: Optional[Path] = None):
        self.profile_dir = profile_dir
        self._driver: Optional[webdriver.Chrome] = None

    def __enter__(self) -> "GetMatchClient":
        self._driver = init_browser(self.profile_dir)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._driver is not None:
            self._driver.quit()
            self._driver = None

    def _acquire_driver(self):
        # ponytail: та же проверка живости driver'а, что у
        # HeadHunterBrowserClient — общая chrome_utils.is_driver_dead,
        # см. её докстринг.
        if self._driver is not None:
            if is_driver_dead(self._driver):
                self._driver = init_browser(self.profile_dir)
            return self._driver, False
        return init_browser(self.profile_dir), True

    def search_vacancies_html(
        self, page: int = 1, specializations: Optional[list] = None
    ) -> str:
        """Без текстового запроса — GetMatch убрал его со страницы
        /vacancies (подтверждено вживую 2026-09-02: `?q=...` в URL
        молча отбрасывается, отдаёт тот же общий список независимо от
        значения). Вместо этого — `sp=` (специализация, чекбоксы
        "Сфера" на живой странице, например `sp=python`) — этих
        параметров можно передать несколько, площадка складывает их
        через "или" (подтверждено вживую: `sp=python&sp=dev_ops`
        отдаёт объединение, не пересечение). Без specializations —
        общий список, фильтрация по GetMatchSource.positions на
        нашей стороне (см. GetMatchSource.search()). Пагинация — тем
        же `page`, что и раньше (подтверждено вживую: `p=10` за
        концом списка отдаёт 0 карточек, не ошибку — чистый
        стоп-сигнал, как у GeekjobClient)."""
        driver, owns_it = self._acquire_driver()
        try:
            # l=remote, se=junior/middle — подтверждено кликом по
            # реальным чекбоксам фильтра "Регион и формат работы" /
            # "Уровень вакансии" на живой странице и чтением итогового
            # URL, а не угадано; кандидат ищет только удалённую работу
            # уровня junior/middle.
            url = f"{GM_BASE}/vacancies?p={page}&l=remote&se=junior&se=middle"
            for slug in specializations or []:
                url += f"&sp={slug}"
            driver.get(url)
            _wait_for_vacancies_page(driver)
            raise_if_blocked(visible_text(driver))
            return driver.page_source
        finally:
            if owns_it:
                driver.quit()

    def apply(self, vacancy_url: str, cover_letter: str = "") -> bool:
        """Клик на "Откликнуться" открывает модалку. Раньше (до
        2026-09) это была форма из одного шага — зарплата/локация
        (уже подставлены из профиля) и поле "Сопроводительное
        письмо" — вписываем письмо и жмём "Отправить отклик". Теперь
        GetMatch иногда вместо этого открывает мастер анкеты в
        несколько шагов ("Шаг 1 из 5", ...) без textarea/кнопки
        отправки на первом шаге — заполнять его вслепую небезопасно
        (реальные профильные данные), поэтому в этом случае просто
        закрываем модалку и возвращаем False, а не притворяемся, что
        отклик ушёл (см. _WIZARD_STEP_RE). Требует, чтобы
        GetMatchSession.ensure_logged_in() уже был пройден для этого
        profile_dir — иначе кнопки "Откликнуться" не будет (форма
        входа), и apply() вернёт False.

        ponytail: те же два fixed sleep, что были у
        search_vacancies_html (и с той же гонкой на холодном
        браузере), — заменены на bounded-poll (_wait_until). Второй
        (после клика) даже опаснее первого: если модалка не успевала
        отрендериться за 1.5с, textarea/"Отправить отклик" не
        находились, и код молча падал в `return True`, ничего на
        самом деле не заполнив и не отправив — то самое "не жмёт
        дальше 'Откликнуться'"."""
        driver, owns_it = self._acquire_driver()
        try:
            driver.get(vacancy_url)
            # ponytail: predicate сохраняет найденное в buttons вместо
            # того, чтобы просто вернуть bool — иначе пришлось бы
            # запрашивать те же кнопки у driver'а второй раз сразу
            # после опроса (лишний Selenium round-trip и рассинхрон с
            # моками в тестах).
            buttons: list = []

            def _respond_button_ready() -> bool:
                nonlocal buttons
                buttons = driver.find_elements(
                    By.XPATH, '//button[normalize-space()="Откликнуться"]'
                )
                return bool(buttons)

            _wait_until(_respond_button_ready)
            raise_if_blocked(visible_text(driver))
            if not buttons:
                return False
            buttons[0].click()

            modal_text = ""

            def _modal_ready() -> bool:
                nonlocal modal_text
                modal_text = visible_text(driver)
                return (
                    bool(_WIZARD_STEP_RE.search(modal_text))
                    or bool(driver.find_elements(By.TAG_NAME, "textarea"))
                    or bool(
                        driver.find_elements(
                            By.XPATH,
                            '//button[normalize-space()="Отправить отклик"]',
                        )
                    )
                    or bool(
                        driver.find_elements(
                            By.XPATH, '//button[@aria-label="Закрыть"]'
                        )
                    )
                )

            _wait_until(_modal_ready)

            if _WIZARD_STEP_RE.search(modal_text):
                close_buttons = driver.find_elements(
                    By.XPATH, '//button[@aria-label="Закрыть"]'
                )
                if close_buttons:
                    close_buttons[0].click()
                return False

            if cover_letter:
                textareas = driver.find_elements(By.TAG_NAME, "textarea")
                if textareas:
                    textareas[0].send_keys(
                        html_letter_to_plain_text(cover_letter)
                    )

            submit_buttons = driver.find_elements(
                By.XPATH, '//button[normalize-space()="Отправить отклик"]'
            )
            if submit_buttons:
                submit_buttons[0].click()
                time.sleep(1.5)
            return True
        finally:
            if owns_it:
                driver.quit()
