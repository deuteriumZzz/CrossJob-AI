from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import httpx
from selenium import webdriver
from selenium.webdriver.common.by import By

from src.job_sources.block_detection import (
    raise_if_blocked,
    raise_if_page_blocked,
)
from src.job_sources.html_text import html_letter_to_plain_text
from src.job_sources.user_agents import random_user_agent
from src.logging import logger
from src.utils.chrome_utils import init_browser, is_driver_dead

HC_BASE = "https://career.habr.com"
PAGE_LOAD_WAIT_SECONDS = 3
_APPLY_BUTTON_TEXT = "откликнуться"
_ALREADY_APPLIED_MARKERS = ("посмотреть отклик", "редактировать")
# id значения <select> "Квалификация" на /vacancies (`qid=`) —
# подтверждено вживую 2026-09-29: открыт фильтр-сайдбар на живой
# странице, для каждого варианта выбран option и прочитан итоговый
# location.href (qid=5 для Senior и т.д.). Пропуск id=2 в исходной
# разметке сайта — не опечатка, площадка сама его не использует.
QUALIFICATION_IDS = {
    "intern": 1,
    "junior": 3,
    "middle": 4,
    "senior": 5,
    "lead": 6,
}
# Значения <select> "Тип занятости" (`employment_type=`) — тот же
# живой прогон, что и QUALIFICATION_IDS.
EMPLOYMENT_TYPES = frozenset({"full_time", "part_time"})


class HabrCareerClient:
    """Официального API нет для этого проекта (доступ — по ручному
    одобрению Хабра, не для личных ботов) — /vacancies?q=... и
    /vacancies/{id} отдаются сервером, подтверждено прямым httpx-
    запросом без исполнения JS — поиск здесь всегда идёт через httpx,
    браузер нужен только для apply().

    ponytail: используйте как контекстный менеджер (`with
    HabrCareerClient(profile_dir) as client:`), чтобы один Chrome
    переиспользовался на все отклики за прогон (тот же паттерн, что
    у HeadHunterBrowserClient — тоже раньше открывал/закрывал браузер
    на каждый вызов, есть жалоба пользователя на это же поведение).
    Без `with` — свой одноразовый driver на вызов apply()."""

    def __init__(
        self,
        profile_dir: Optional[Path] = None,
        user_agent: Optional[str] = None,
    ):
        self.profile_dir = profile_dir
        self._driver: Optional[webdriver.Chrome] = None
        self._client = httpx.Client(
            base_url=HC_BASE,
            headers={"User-Agent": user_agent or random_user_agent()},
            timeout=30,
        )

    def __enter__(self) -> "HabrCareerClient":
        if self.profile_dir is not None:
            self._driver = init_browser(self.profile_dir)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._driver is not None:
            self._driver.quit()
            self._driver = None

    def _acquire_driver(self):
        # ponytail: та же проверка живости driver'а, что у
        # HeadHunterBrowserClient — общая chrome_utils.is_driver_dead.
        if self._driver is not None:
            if is_driver_dead(self._driver):
                self._driver = init_browser(self.profile_dir)
            return self._driver, False
        if self.profile_dir is None:
            raise RuntimeError(
                "HabrCareerClient.apply() needs profile_dir (constructor "
                "arg or __enter__)."
            )
        return init_browser(self.profile_dir), True

    def search_html(
        self,
        position: str,
        page: int = 1,
        remote_only: bool = False,
        qualification: Optional[str] = None,
        employment_type: Optional[str] = None,
        only_with_salary: bool = False,
    ) -> str:
        """Фильтры сайдбара /vacancies — подтверждено вживую
        2026-09-29 (см. QUALIFICATION_IDS/EMPLOYMENT_TYPES выше):
        чекбокс "Можно удалённо" -> `remote=true`, выпадающий список
        "Квалификация" (одиночный выбор, не чекбоксы) -> `qid=<id>`,
        выпадающий список "Тип занятости" -> `employment_type=
        full_time|part_time`. Неизвестный qualification/employment_type
        молча игнорируется — HabrCareerSource уже фильтрует по
        известным значениям до вызова этого метода."""
        # Без sort=date: сортировка по дате подмешивает свежие, но
        # нерелевантные вакансии (вживую 2026-10-08: по «Python …» шли
        # аналитики и .NET), а лимит открытий уходит на них. Релевантность
        # ставит нужные вакансии первыми.
        params = {"q": position}
        if page > 1:
            params["page"] = str(page)
        if remote_only:
            params["remote"] = "true"
        if qualification in QUALIFICATION_IDS:
            params["qid"] = str(QUALIFICATION_IDS[qualification])
        if employment_type in EMPLOYMENT_TYPES:
            params["employment_type"] = employment_type
        if only_with_salary:
            # Проверено вживую 2026-10-07: 4 страницы выдачи против 5.
            params["with_salary"] = "true"
        response = self._client.get("/vacancies", params=params)
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def get_vacancy_html(self, vacancy_id: str) -> str:
        response = self._client.get(f"/vacancies/{vacancy_id}")
        response.raise_for_status()
        raise_if_blocked(response)
        return response.text

    def apply(self, vacancy_url: str, cover_letter: str = "") -> bool:
        """Подтверждено на живом залогиненном аккаунте (2026-08-28):
        для вошедшего пользователя "Откликнуться" — мгновенная
        отправка ОДНИМ кликом, без модалки, без поля под письмо, без
        кнопки подтверждения. Сопроводительное письмо прикладывается
        отдельным шагом ПОСЛЕ отправки через _attach_cover_letter —
        подтверждено вживую 2026-09-18: "Посмотреть отклик" →
        "Редактировать" на карточке своего резюме открывает секцию
        "Сопроводительное письмо" с textarea[name=body] и кнопкой
        "Сохранить".
        Анонимная форма ("Откликнуться без регистрации") — под
        reCAPTCHA, которую бот не проходит принципиально, поэтому сюда
        не заходим вообще: если после клика не появились маркеры уже
        отправленного отклика ("Посмотреть отклик"/"Редактировать") —
        считаем, что сессия не аутентифицирована (сработала анонимная
        ветка с капчей или что-то ещё), и возвращаем False, ничего
        больше не нажимая."""
        driver, owns_it = self._acquire_driver()
        try:
            driver.get(vacancy_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            raise_if_page_blocked(driver)

            apply_buttons = [
                el
                for el in driver.find_elements(By.CSS_SELECTOR, "button")
                if el.is_displayed()
                and (el.text or "").strip().lower() == _APPLY_BUTTON_TEXT
            ]
            if not apply_buttons:
                return False
            driver.execute_script("arguments[0].click();", apply_buttons[0])
            time.sleep(2)

            texts = [
                (el.text or "").strip().lower()
                for el in driver.find_elements(By.CSS_SELECTOR, "button, a")
                if el.is_displayed()
            ]
            applied = any(
                marker in text
                for text in texts
                for marker in _ALREADY_APPLIED_MARKERS
            )
            if applied and cover_letter:
                # Отклик уже ушёл: сбой при дописывании письма не должен
                # терять отметку «откликнулся» (иначе вакансию возьмут
                # повторно, а в журнале её нет).
                try:
                    self._attach_cover_letter(driver, cover_letter)
                except Exception as e:
                    logger.warning(
                        f"Отклик на {vacancy_url} отправлен, письмо не "
                        f"дописалось: {e}"
                    )
            return applied
        finally:
            if owns_it:
                driver.quit()

    def _attach_cover_letter(self, driver, cover_letter: str) -> None:
        """Best-effort: отклик уже отправлен (applied=True в apply()
        выше) независимо от того, получится ли дописать письмо здесь
        — поэтому любая непройденная стадия просто return, без
        исключения наружу."""
        view_buttons = [
            el
            for el in driver.find_elements(By.CSS_SELECTOR, "button, a")
            if el.is_displayed()
            and (el.text or "").strip().lower() == "посмотреть отклик"
        ]
        if not view_buttons:
            return
        driver.execute_script("arguments[0].click();", view_buttons[0])
        time.sleep(1.5)

        edit_buttons = [
            el
            for el in driver.find_elements(
                By.CSS_SELECTOR, ".create-vacancy-response__button"
            )
            if el.is_displayed()
            and "редактировать" in (el.text or "").strip().lower()
        ]
        if not edit_buttons:
            return
        driver.execute_script("arguments[0].click();", edit_buttons[0])
        time.sleep(1)

        textareas = [
            t
            for t in driver.find_elements(
                By.CSS_SELECTOR, "textarea[name='body']"
            )
            if t.is_displayed()
        ]
        if not textareas:
            return
        textareas[0].send_keys(html_letter_to_plain_text(cover_letter))

        save_buttons = [
            el
            for el in driver.find_elements(
                By.CSS_SELECTOR, "button[type='submit']"
            )
            if el.is_displayed()
            and "сохранить" in (el.text or "").strip().lower()
        ]
        if save_buttons:
            save_buttons[0].click()
            time.sleep(1.5)
