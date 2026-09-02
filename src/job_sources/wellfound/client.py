from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import httpx
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.user_agents import random_user_agent
from src.utils.chrome_utils import init_browser

WF_BASE = "https://wellfound.com"
PAGE_LOAD_WAIT_SECONDS = 3
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SUBMIT_TEXT_MARKERS = ("submit", "send application", "apply")


def slugify(position: str) -> str:
    return _SLUG_RE.sub("-", position.strip().lower()).strip("-")


class WellfoundClient:
    """Официального API нет — страницы /role/... и /jobs/{id}-{slug}
    отдаются сервером (Next.js SSR), подтверждено прямым httpx-запросом
    без исполнения JS: карточки списка и schema.org JobPosting на
    странице вакансии присутствуют в исходном HTML. /role/r/{slug} —
    таксономия ролей, а не свободный текстовый поиск (подтверждено:
    случайный несуществующий slug молча редиректит на /remote вместо
    404) — search_role_html() поэтому сверяет итоговый URL после
    редиректов с запрошенным путём, а не просто статус-код."""

    def __init__(self, user_agent: Optional[str] = None):
        self._client = httpx.Client(
            base_url=WF_BASE,
            headers={"User-Agent": user_agent or random_user_agent()},
            timeout=30,
            follow_redirects=True,
        )

    def _get_if_matches(self, path: str) -> Optional[str]:
        response = self._client.get(path)
        raise_if_blocked(response)
        if response.status_code != 200:
            return None
        if urlparse(str(response.url)).path.rstrip("/") != path.rstrip("/"):
            return None
        return response.text

    def search_role_html(self, position: str) -> Optional[str]:
        slug = slugify(position)
        if not slug:
            return None
        html = self._get_if_matches(f"/role/r/{slug}")
        if html is not None:
            return html
        return self._get_if_matches(f"/role/{slug}")

    def get_vacancy_html(self, job_id: str, slug: str) -> str:
        response = self._client.get(f"/jobs/{job_id}-{slug}")
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def apply(
        self,
        vacancy_url: str,
        profile_dir: Path,
        answer_fn: Optional[Callable[[str], str]] = None,
    ) -> bool:
        """Best-effort, НЕ проверено на живом залогиненном аккаунте.
        Подтверждено вживую (2026-09-02, анонимно, без входа): кнопка
        "Apply Now" на странице вакансии ничего не кликает через
        data-атрибут — она навигирует на тот же URL с добавленным
        query-параметром ?autoOpenApplication=true (см. onclick="window.
        location.href='...'" в реальной разметке), который открывает
        модалку заявки сам по себе. Мы просто переходим по этому URL
        напрямую вместо поиска и клика кнопки — устойчивее к смене
        разметки. Если модалка после перехода всё ещё содержит поле
        пароля — сессия не аутентифицирована (WellfoundSession.
        ensure_logged_in() не был пройден вручную, либо профиль
        сброшен), и мы НИКОГДА не заполняем и не отправляем эту форму
        сами (это было бы созданием аккаунта за пользователя) —
        возвращаем False. Иначе пробуем обобщённо отвечать на видимые
        текстовые/select/radio/checkbox поля и жмём кнопку с текстом
        submit/apply/send application; если такой кнопки не нашлось —
        форма не подтверждена, тоже False."""
        driver = init_browser(profile_dir)
        try:
            separator = "&" if "?" in vacancy_url else "?"
            driver.get(f"{vacancy_url}{separator}autoOpenApplication=true")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))

            if driver.find_elements(
                By.CSS_SELECTOR, 'input[type="password"]'
            ):
                return False

            for field in driver.find_elements(
                By.CSS_SELECTOR,
                'textarea, input[type="text"], input[type="number"]',
            ):
                if field.is_displayed() and not field.get_attribute("value"):
                    question = _label_text_for(driver, field)
                    field.send_keys(_answer(question, answer_fn))

            for select_el in driver.find_elements(By.TAG_NAME, "select"):
                if not select_el.is_displayed():
                    continue
                _select_first_reasonable_option(select_el)

            for radio in driver.find_elements(
                By.CSS_SELECTOR, 'input[type="radio"]'
            ):
                if radio.is_displayed() and not radio.is_selected():
                    driver.execute_script("arguments[0].click();", radio)

            submit = _find_button_by_visible_text(
                driver, _SUBMIT_TEXT_MARKERS
            )
            if submit is None:
                return False
            driver.execute_script("arguments[0].click();", submit)
            time.sleep(1.5)
            return True
        finally:
            driver.quit()


def _answer(question: str, answer_fn: Optional[Callable[[str], str]]) -> str:
    if answer_fn is None or not question:
        return ""
    try:
        return answer_fn(question)
    except Exception:
        return ""


def _select_first_reasonable_option(select_el) -> None:
    from selenium.webdriver.support.ui import Select

    options = Select(select_el).options
    for option in options:
        if option.get_attribute("value"):
            Select(select_el).select_by_value(option.get_attribute("value"))
            return


def _label_text_for(driver, field) -> str:
    field_id = field.get_attribute("id")
    if field_id:
        labels = driver.find_elements(
            By.CSS_SELECTOR, f'label[for="{field_id}"]'
        )
        if labels:
            return labels[0].text.strip()
    try:
        return (
            driver.execute_script(
                "let n = arguments[0];"
                "while (n && !n.previousElementSibling && n.parentElement)"
                " { n = n.parentElement; }"
                "return n && n.previousElementSibling"
                " ? n.previousElementSibling.innerText : '';",
                field,
            )
            or ""
        ).strip()
    except Exception:
        return ""


def _find_button_by_visible_text(driver, needles: tuple[str, ...]):
    for el in driver.find_elements(By.CSS_SELECTOR, 'button, a[role="button"]'):
        if not el.is_displayed():
            continue
        text = (el.text or "").strip().lower()
        if any(needle in text for needle in needles):
            return el
    return None
