from __future__ import annotations

import json
from math import ceil
from pathlib import Path

from src.job import Job
from src.job_sources.applied_log import seen_ids_for
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import PlatformBlockedError
from src.job_sources.filters import (
    hh_employment,
    hh_experience,
    posted_within_days,
)
from src.job_sources.headhunter.browser_client import HeadHunterBrowserClient
from src.job_sources.headhunter.browser_mapping import (
    hh_html_vacancy_to_job,
    parse_search_results,
)
from src.job_sources.headhunter.source import _hh_work_formats
from src.job_sources.preferences import effective_list
from src.logging import logger
from src.utils.chrome_utils import is_driver_dead
from src.utils.file_lock import atomic_write_text, state_file_lock

# Выдача содержит много уже просмотренных вакансий. За один ход
# обходим небольшой участок, а номер следующей страницы сохраняем:
# поиск не занимает десятки минут до первого отклика и не теряет глубину.
PAGES_PER_POSITION = 100  # потолок hh.ru: 2000 вакансий на запрос
PAGES_PER_RUN_PER_POSITION = 6
DEFAULT_NEW_PER_RUN = 20
_SCAN_CURSOR_FILE = ".hh_scan_cursor.json"


def _load_scan_cursors(
    output_folder: Path | None,
) -> dict[str, tuple[int, int]]:
    if output_folder is None:
        return {}
    try:
        data = json.loads(
            (output_folder / _SCAN_CURSOR_FILE).read_text(encoding="utf-8")
        )
        cursors = {}
        for key, value in data.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, int) and value >= 0:
                cursors[key] = (value, 0)
            elif (
                isinstance(value, list)
                and len(value) == 2
                and all(isinstance(part, int) and part >= 0 for part in value)
            ):
                cursors[key] = (value[0], value[1])
        return cursors
    except (OSError, ValueError, AttributeError):
        return {}


def _save_scan_cursors(
    output_folder: Path | None, cursors: dict[str, tuple[int, int]]
) -> None:
    if output_folder is None:
        return
    path = output_folder / _SCAN_CURSOR_FILE
    with state_file_lock(path):
        current = _load_scan_cursors(output_folder)
        atomic_write_text(
            path, json.dumps({**current, **cursors}, ensure_ascii=False)
        )


class HeadHunterBrowserSource:
    def __init__(self, client: HeadHunterBrowserClient):
        self.client = client
        self._pending_scan_cursor: (
            tuple[Path | None, dict[str, tuple[int, int]]] | None
        ) = None

    def commit_scan_cursor(self) -> None:
        """Move to the next batch after the caller processes this one."""
        if self._pending_scan_cursor is None:
            return
        output_folder, cursors = self._pending_scan_cursor
        _save_scan_cursors(output_folder, cursors)
        self._pending_scan_cursor = None

    def search(self, preferences: dict) -> list[Job]:
        self._pending_scan_cursor = None
        work_formats = tuple(_hh_work_formats(preferences))

        seen_ids: set = set()
        already_seen = seen_ids_for(preferences, "headhunter")
        hh_settings = preferences.get("headhunter") or {}
        max_new = max(
            1, int(hh_settings.get("max_new_per_run", DEFAULT_NEW_PER_RUN))
        )
        positions = list(
            effective_list(preferences, "headhunter", "positions")
        )
        per_position_limit = ceil(max_new / max(len(positions), 1))
        output_folder = preferences.get("outputFileDirectory")
        cursors = _load_scan_cursors(output_folder)
        next_cursors = dict(cursors)
        failed_positions: set[str] = set()
        opened = 0
        jobs: list[Job] = []
        logger.info(
            f"hh.ru: ищу до {PAGES_PER_RUN_PER_POSITION} страниц на запрос, "
            f"до {max_new} новых вакансий за ход."
        )

        for position in positions:
            opened_for_position = 0
            start_page, start_item = cursors.get(position, (0, 0))
            start_page %= PAGES_PER_POSITION
            deep_start = max(start_page, 1)
            pages = [0] + [
                ((deep_start + offset - 1) % (PAGES_PER_POSITION - 1)) + 1
                for offset in range(PAGES_PER_RUN_PER_POSITION - 1)
            ]
            for page in pages:
                html = self.client.search_vacancies_html(
                    position,
                    remote_only=False,
                    page=page,
                    work_formats=work_formats,
                    only_with_salary=bool(preferences.get("only_with_salary")),
                    experience=tuple(hh_experience(preferences)),
                    employment=tuple(hh_employment(preferences)[0]),
                    internship=hh_employment(preferences)[1],
                    period_days=posted_within_days(preferences),
                )
                items = parse_search_results(html)
                logger.info(
                    f"hh.ru: «{position}», страница {page + 1}: "
                    f"{len(items)} карточек, открыто новых {opened}."
                )
                if not items:
                    next_cursors[position] = (0, 0)
                    break

                page_complete = True
                first_item = (
                    start_item if page != 0 and page == start_page else 0
                )
                for item_index in range(first_item, len(items)):
                    item = items[item_index]
                    if item.external_id in seen_ids:
                        continue
                    if item.external_id in already_seen:
                        continue  # уже в журнале — страницу не открываем
                    if (
                        opened >= max_new
                        or opened_for_position >= per_position_limit
                    ):
                        page_complete = False
                        if page != 0:
                            next_cursors[position] = (page, item_index)
                        break
                    seen_ids.add(item.external_id)
                    opened += 1
                    opened_for_position += 1

                    try:
                        detail_html = self.client.get_vacancy_html(
                            item.external_id
                        )
                    except PlatformBlockedError:
                        raise
                    except Exception as e:
                        driver = getattr(self.client, "_driver", None)
                        if driver is not None and is_driver_dead(driver):
                            self.client._driver = None
                            raise
                        failed_positions.add(position)
                        # Ошибка отдельной карточки не срывает поиск,
                        # но курсор этой должности не сдвигаем: сбой
                        # может быть временным и вакансию надо повторить.
                        logger.exception(
                            f"hh.ru вакансия {item.external_id} упала — "
                            f"повторю в следующем проходе: {e}"
                        )
                        continue
                    job = hh_html_vacancy_to_job(detail_html, item.external_id)
                    if not job.role:
                        job = item
                    else:
                        # hh_html_vacancy_to_job не размечает location
                        # (нет проверенного селектора на странице
                        # вакансии) — берём адрес, который уже пришёл
                        # с карточки поиска (vacancy-serp__vacancy-
                        # address, подтверждено живьём), иначе
                        # passes_blacklists всегда режет по пустой
                        # строке против locations-allowlist.
                        job.location = item.location
                    if passes_blacklists(job, preferences):
                        jobs.append(job)

                if page_complete and page != 0:
                    next_page = (page + 1) % PAGES_PER_POSITION or 1
                    next_cursors[position] = (next_page, 0)
                if not page_complete:
                    break

            if opened >= max_new:
                break

        for failed_position in failed_positions:
            if failed_position in cursors:
                next_cursors[failed_position] = cursors[failed_position]
            else:
                next_cursors.pop(failed_position, None)
        self._pending_scan_cursor = (output_folder, next_cursors)

        return jobs
