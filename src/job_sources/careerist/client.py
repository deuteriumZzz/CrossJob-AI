from __future__ import annotations

import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text
from src.job_sources.user_agents import random_user_agent
from src.utils.chrome_utils import init_browser

CR_BASE = "https://careerist.ru"
PAGE_LOAD_WAIT_SECONDS = 3
_SUBMIT_TEXT_MARKERS = ("отправить резюме", "откликнуться")


class CareeristClient:
    """Официального API нет — /jobs-{query}/ и /vakansii/{slug}-{id}.html
    отдаются сервером, подтверждено прямым httpx-запросом. Свободного
    текстового поиска через query-параметр нет: /vakansii/?text=...
    (301) редиректит на готовую SEO-страницу /jobs-{транслитерация}/ —
    сайт сам транслитерирует кириллицу (подтверждено: "менеджер по
    продажам" → /jobs-menedzher-po-prodazham/). Если совпадений нет,
    редиректа не происходит — отдаётся обычная (нефильтрованная)
    категория с кодом 200, поэтому здесь важен именно факт редиректа,
    а не статус-код (тот же паттерн, что у WellfoundClient)."""

    def __init__(self, user_agent: Optional[str] = None):
        self._client = httpx.Client(
            base_url=CR_BASE,
            headers={"User-Agent": user_agent or random_user_agent()},
            timeout=30,
        )

    def search_html(self, position: str) -> Optional[str]:
        response = self._client.get(
            "/vakansii/", params={"text": position}, follow_redirects=False
        )
        raise_if_blocked(response)
        if response.status_code not in (301, 302):
            return None
        target = response.headers.get("location", "")
        if not target or not urlparse(target).path.startswith("/jobs-"):
            return None
        result = self._client.get(target)
        raise_if_blocked(result)
        result.raise_for_status()
        return result.text

    def get_vacancy_html(self, path: str) -> str:
        # ponytail: careerist.ru отдаёт спорадические 502 на реально
        # существующие страницы (подтверждено: тот же URL — 502, затем
        # дважды подряд 200) — не блокировка (нет капчи/специфичного
        # текста), похоже на нестабильный бэкенд. Один повтор вместо
        # падения на первом же случайном сбое.
        for attempt in range(2):
            response = self._client.get(path)
            if response.status_code == 502 and attempt == 0:
                time.sleep(2)
                continue
            response.raise_for_status()
            raise_if_blocked(response)
            return response.text
        raise AssertionError("unreachable")

    def apply(self, vacancy_url: str, profile_dir: Path, resume_pdf_path: Path) -> bool:
        """Best-effort, НЕ проверено на живом залогиненном аккаунте —
        анонимно подтверждено только, что кнопка "ОТПРАВИТЬ РЕЗЮМЕ"
        (как и загрузка файла) ведёт на register.html, если пользователь
        не вошёл. Загружаем резюме в готовый <input type="file"
        id="quick-file-data"> (он есть в разметке сразу, в отличие от
        LinkedIn — там инпут появляется только после клика), затем ищем
        кнопку с текстом "отправить резюме"/"откликнуться", чей onclick
        НЕ ведёт на register.html — если такой нет, считаем сессию
        неаутентифицированной и возвращаем False, ничего не отправляя."""
        driver = init_browser(profile_dir)
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_blocked(visible_text(driver))

            file_inputs = driver.find_elements(
                By.CSS_SELECTOR, "#quick-file-data"
            )
            if file_inputs:
                file_inputs[0].send_keys(str(resume_pdf_path))
                time.sleep(2)

            submit = _find_authenticated_submit_button(driver)
            if submit is None:
                return False
            driver.execute_script("arguments[0].click();", submit)
            time.sleep(1.5)
            return True
        finally:
            driver.quit()


def _find_authenticated_submit_button(driver):
    for el in driver.find_elements(By.CSS_SELECTOR, "div, button, a"):
        if not el.is_displayed():
            continue
        text = (el.text or "").strip().lower()
        if not any(marker in text for marker in _SUBMIT_TEXT_MARKERS):
            continue
        onclick = el.get_attribute("onclick") or ""
        if "register.html" in onclick:
            continue
        return el
    return None
