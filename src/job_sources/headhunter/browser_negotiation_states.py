from __future__ import annotations

import re
import time

from selenium.webdriver.common.by import By

from src.job_sources.block_detection import raise_if_blocked, visible_text

HH_BASE = "https://hh.ru"
PAGE_LOAD_WAIT_SECONDS = 4
MAX_PAGES = 15

# Разметка подтверждена на живом аккаунте 2026-09-24: карточка отклика —
# [data-qa="negotiations-item"], статус — тег с data-qa вида
# "negotiations-tag negotiations-item-<состояние>". Суффикс не зависит от
# языка интерфейса hh (у пользователя он английский: "Rejection").
_ITEM_SELECTOR = '[data-qa="negotiations-item"]'
_TAG_SELECTOR = '[data-qa^="negotiations-tag"]'
_TAG_STATE_RE = re.compile(r"negotiations-item-([a-z-]+)")
_VACANCY_ID_RE = re.compile(r"/vacancy/(\d+)")

# Русские подписи — их разбирает applied_log.effective_stage.
# ponytail: неизвестный суффикс сохраняется как есть и считается просто
# "ответили"; добавить сюда, если hh заведёт новое состояние.
STATE_LABELS = {
    "not-viewed": "Не просмотрен",
    "viewed": "Просмотрен",
    "discard": "Отказ",
    "invitation": "Приглашение",
    "interview": "Приглашение на интервью",
    "hired": "Выход на работу",
}


def list_negotiation_states(driver) -> dict[str, str]:
    """{id вакансии: статус переговоров} по всем страницам списка
    откликов /applicant/negotiations. Только чтение — ничего не
    нажимает."""
    states: dict[str, str] = {}
    for page in range(MAX_PAGES):
        driver.get(f"{HH_BASE}/applicant/negotiations?page={page}")
        time.sleep(PAGE_LOAD_WAIT_SECONDS)
        raise_if_blocked(visible_text(driver))
        new_on_page = 0
        for item in driver.find_elements(By.CSS_SELECTOR, _ITEM_SELECTOR):
            links = item.find_elements(By.CSS_SELECTOR, 'a[href*="/vacancy/"]')
            tags = item.find_elements(By.CSS_SELECTOR, _TAG_SELECTOR)
            if not links or not tags:
                continue
            vacancy = _VACANCY_ID_RE.search(links[0].get_attribute("href"))
            state = _TAG_STATE_RE.search(tags[0].get_attribute("data-qa"))
            if not vacancy or not state or vacancy.group(1) in states:
                continue
            states[vacancy.group(1)] = STATE_LABELS.get(
                state.group(1), state.group(1)
            )
            new_on_page += 1
        if not new_on_page:
            break
    return states
