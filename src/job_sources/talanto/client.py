from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked_after_wait
from src.job_sources.talanto.selectors import SELECTORS
from src.utils.chrome_utils import init_browser, is_driver_dead

PAGE_LOAD_WAIT_SECONDS = 5
_JOB_PATH_RE = re.compile(SELECTORS.job_path_regex)

_VACANCY_JS = """
const q = (s) => document.querySelector(s);
const h1 = q('h1');
const heading = [...document.querySelectorAll('h2,h3')].find(
  (h) => h.innerText.trim() === arguments[0]);
const company = q(arguments[1]);
return {
  title: h1 ? h1.innerText.trim() : '',
  company: company ? company.innerText.trim() : '',
  meta: h1 && h1.parentElement ? h1.parentElement.innerText : '',
  description: heading && heading.parentElement
    ? heading.parentElement.innerText : '',
};"""

_CONTACTS_JS = """
const marker = arguments[0];
const heading = [...document.querySelectorAll('h1,h2,h3,p,div,span')].find(
  (e) => e.children.length === 0 && e.innerText.trim() === 'Контакты'
    && e.offsetParent !== null);
if (!heading) return null;
let box = heading;
for (let i = 0; i < 5 && box.parentElement; i++) {
  if (box.innerText.includes(marker)) break;
  box = box.parentElement;
}
return {
  text: box.innerText,
  links: [...box.querySelectorAll('a[href]')].map((a) => [
    a.innerText.trim(), a.getAttribute('href')]),
};"""


class TalantoClient:
    """talanto.work — агрегатор вакансий: отклика внутри сайта нет, есть
    ссылка на сайт работодателя и (иногда) контакты за кнопкой «Показать
    контакты». Клиент только читает: ссылку Apply не нажимает — клик по ней
    записал бы в «Откликах» Talanto отклик, которого не было. Вход — ваш,
    ручной, сохраняется в профиле Chrome (см. src/utils/shared_browser)."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self._driver: Optional[webdriver.Chrome] = None

    def __enter__(self) -> "TalantoClient":
        self._driver = init_browser(self.profile_dir)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._driver is not None:
            self._driver.quit()
            self._driver = None

    def _acquire_driver(self):
        if self._driver is None or is_driver_dead(self._driver):
            self._driver = init_browser(self.profile_dir)
        return self._driver

    def search_job_ids(self, query: str, page: int = 1) -> list[str]:
        """id вакансий страницы выдачи, самые новые первыми (sort=new)."""
        driver = self._acquire_driver()
        url = f"{SELECTORS.base_url}/?q={quote_plus(query)}&sort=new"
        if page > 1:
            url += f"&page={page}"
        driver.get(url)
        time.sleep(PAGE_LOAD_WAIT_SECONDS)
        raise_if_blocked_after_wait(driver)
        hrefs = driver.execute_script(
            "return [...document.querySelectorAll(arguments[0])]"
            ".map((a) => a.getAttribute('href'))",
            SELECTORS.job_link,
        )
        ids: list[str] = []
        for href in hrefs:
            match = _JOB_PATH_RE.match(href or "")
            if match and match.group(1) not in ids:
                ids.append(match.group(1))
        return ids

    def get_vacancy(self, job_id: str) -> dict:
        """{title, company, meta, description} страницы вакансии."""
        driver = self._acquire_driver()
        driver.get(f"{SELECTORS.base_url}/jobs/{job_id}")
        time.sleep(PAGE_LOAD_WAIT_SECONDS)
        raise_if_blocked_after_wait(driver)
        return driver.execute_script(
            _VACANCY_JS,
            SELECTORS.description_heading,
            SELECTORS.company_link,
        )

    def show_contacts(self, job_id: str) -> dict:
        """Нажимает «Показать контакты» на странице вакансии (откроет её, если
        ещё не открыта) и читает окно: {text, apply_url, links}.
        Может тратить лимит тарифа Talanto — вызывающий код ограничивает
        число вызовов в день."""
        driver = self._acquire_driver()
        if job_id not in driver.current_url:
            driver.get(f"{SELECTORS.base_url}/jobs/{job_id}")
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
        buttons = [
            b
            for b in driver.find_elements(By.TAG_NAME, "button")
            if (b.text or "").strip() == SELECTORS.contacts_button_text
            and b.is_displayed()
        ]
        if not buttons:
            return {"text": "", "apply_url": "", "company": "", "links": []}
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});"
            "arguments[0].click();",
            buttons[0],
        )
        time.sleep(3)
        box = driver.execute_script(
            _CONTACTS_JS, SELECTORS.contacts_dialog_marker
        )
        driver.execute_script(
            "document.dispatchEvent(new KeyboardEvent('keydown',"
            "{key:'Escape',keyCode:27,bubbles:true}));"
        )
        if not box:
            return {"text": "", "apply_url": "", "company": "", "links": []}
        apply_url = company = ""
        extra_text = []
        for text, href in box["links"]:
            if href.startswith(SELECTORS.apply_path):
                # Ссылка-переход Talanto: клик записывает отклик в «Откликах»
                # пользователя — поэтому только читаем её адрес, не нажимаем.
                apply_url = SELECTORS.base_url + href
                company = re.sub(r"^\s*Apply\s*", "", text).strip()
            elif href.startswith(("mailto:", "tel:")):
                extra_text.append(href.split(":", 1)[1])
        return {
            "text": "\n".join([box["text"], *extra_text]),
            "apply_url": apply_url,
            "company": company,
            "links": box["links"],
        }


def company_from_apply_url(apply_url: str) -> str:
    """Название компании по домену ссылки Apply — когда Talanto скрыл его
    за платным тарифом (в выдаче «•••••»)."""
    host = urlparse(apply_url).netloc.lower().removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    skip = {
        "jobs",
        "careers",
        "career",
        "apply",
        "hire",
        "work",
        "com",
        "org",
        "io",
        "net",
        "co",
        "ru",
        "de",
        "uk",
    }
    for part in parts:
        if part not in skip:
            return part.capitalize()
    return ""
