from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import httpx
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import (
    raise_if_blocked,
    raise_if_page_blocked,
)
from src.job_sources.user_agents import random_user_agent
from src.utils.chrome_utils import init_browser

WF_BASE = "https://wellfound.com"
PAGE_LOAD_WAIT_SECONDS = 3
_SLUG_RE = re.compile(r"[^a-z0-9]+")
# Порядок важен: ищем по приоритету. Голое "apply" убрано — на странице
# вакансии есть своя кнопка "Apply", она раньше "Submit application" в DOM,
# и бот кликал её, а потом писал "откликнулся" (2026-11-04).
_SUBMIT_TEXT_MARKERS = ("submit application", "send application", "submit")
CONFIRM_WAIT_SECONDS = 12
_CONFIRM_RE = re.compile(
    r"application (has been )?(sent|submitted)|you('ve| have)? applied|"
    r"thanks for applying|\bapplied\b",
    re.IGNORECASE,
)


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
        if urlparse(str(response.url)).path.rstrip("/") != (
            urlparse(path).path.rstrip("/")
        ):
            return None
        return response.text

    def search_role_html(self, position: str, page: int = 1) -> Optional[str]:
        slug = slugify(position)
        if not slug:
            return None
        query = f"?page={page}" if page > 1 else ""
        html = self._get_if_matches(f"/role/r/{slug}{query}")
        if html is not None:
            return html
        return self._get_if_matches(f"/role/{slug}{query}")

    def get_vacancy_html(self, job_id: str, slug: str) -> str:
        response = self._client.get(f"/jobs/{job_id}-{slug}")
        if response.status_code == 429:
            # 1.11: после пагинации бот открывал ~170 вакансий подряд и
            # ловил 429 — ждём, сколько просит сайт (не дольше минуты).
            retry_after = response.headers.get("retry-after", "")
            time.sleep(min(int(retry_after) if retry_after.isdigit() else 20, 60))
            response = self._client.get(f"/jobs/{job_id}-{slug}")
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def apply(
        self,
        vacancy_url: str,
        profile_dir: Path,
        answer_fn: Optional[Callable[[str], str]] = None,
        resume_path: Optional[Path] = None,
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
            raise_if_page_blocked(driver)

            if driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]'):
                return False
            # Модалка рисуется с задержкой (живьём 2026-11-04 бывало >5 с) —
            # ждём кнопку отправки, а не фиксированные 3 с.
            if not _wait_for_submit(driver):
                return False

            if resume_path is not None:
                for file_input in driver.find_elements(
                    By.CSS_SELECTOR, 'input[type="file"]'
                ):
                    if not file_input.get_attribute("value"):
                        file_input.send_keys(str(Path(resume_path).resolve()))

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

            _answer_radio_groups(driver, answer_fn)

            submit = _find_button_by_visible_text(driver, _SUBMIT_TEXT_MARKERS)
            if submit is None:
                return False
            driver.execute_script("arguments[0].click();", submit)
            return _wait_confirmed(driver)
        finally:
            driver.quit()


# Группа радио = одинаковый name. Вопрос — текст самого большого предка,
# который ещё содержит только эту группу, минус подписи вариантов (живьём
# 2026-11-04: у Wellfound подпись вопроса не связана с input через for).
_RADIO_GROUPS_JS = """
const groups = {};
for (const r of document.querySelectorAll('input[type="radio"]')) {
  if (!r.offsetParent) continue;
  (groups[r.name] = groups[r.name] || []).push(r);
}
const label = r => ((r.labels && r.labels[0]) || r.parentElement).innerText.trim();
return Object.values(groups).map(els => {
  const opts = els.map(label);
  let top = els[0].parentElement;
  for (let i = 0; i < 4; i++) {
    const up = top.parentElement;
    if (!up || up.querySelectorAll('input[type="radio"]').length !== els.length) break;
    top = up;
  }
  let q = top.innerText;
  for (const o of opts) q = q.replace(o, '');
  return {question: q.trim().slice(0, 400), options: opts, elements: els};
});
"""


def _answer_radio_groups(driver, answer_fn) -> None:
    """Раньше кликались все невыбранные радио подряд — в каждой паре
    Yes/No оставалось последнее ("No"), в том числе на "legally eligible
    to work?". Теперь ответ выбирает ИИ из вариантов; нет ответа или он
    не совпал ни с одним вариантом — группа остаётся пустой, форма не
    пройдёт и отклик честно не засчитается."""
    for group in driver.execute_script(_RADIO_GROUPS_JS):
        if any(el.is_selected() for el in group["elements"]):
            continue
        reply = _answer_with_options(
            group["question"], group["options"], answer_fn
        ).strip().lower()
        for el, option in zip(group["elements"], group["options"]):
            if reply and reply == option.strip().lower():
                driver.execute_script("arguments[0].click();", el)
                break


def _answer_with_options(question, options, answer_fn) -> str:
    if answer_fn is None or not question:
        return ""
    try:
        return answer_fn(question, options=options)
    except Exception:
        return ""


def _wait_for_submit(driver, timeout: float = 25) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _find_button_by_visible_text(driver, _SUBMIT_TEXT_MARKERS):
            return True
        time.sleep(1)
    return False


def _wait_confirmed(driver) -> bool:
    """Клик по кнопке — не отклик: без обязательного поля (резюме, ответ)
    модалка остаётся открытой, а бот раньше всё равно рапортовал успех.
    Успех = кнопки "Submit application" больше нет в DOM или на странице
    появилась фраза-подтверждение."""
    deadline = time.monotonic() + CONFIRM_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(1)
        if _find_button_by_visible_text(driver, ("submit application",)) is None:
            return True
        if _CONFIRM_RE.search(driver.find_element(By.TAG_NAME, "body").text):
            return True
    return False


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
        value = option.get_attribute("value")
        if value:
            Select(select_el).select_by_value(value)
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
