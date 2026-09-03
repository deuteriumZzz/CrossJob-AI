from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import PlatformBlockedError
from src.job_sources.geekjob.client import GeekjobClient
from src.job_sources.geekjob.mapping import (
    geekjob_vacancy_to_job,
    parse_search_results,
)
from src.job_sources.preferences import effective_list
from src.logging import logger

# ponytail: фиксированная неглубокая пагинация (2 страницы на должность)
# вместо обхода всех страниц, увеличить, если это перестанет давать
# достаточно вакансий.
PAGES_PER_POSITION = 2

# Автоотклик есть (geekjob.auto_apply в work_preferences.yaml, см.
# main.py::search_geekjob → GeekjobClient.apply()) — best-effort клик
# по кнопке "Откликнуться" через Selenium, НЕ проверено на живом
# залогиненном аккаунте (вход у geekjob.ru только через OAuth
# соцсетей, см. GeekjobSession — пароль пользователя туда никогда не
# вводится).


class GeekjobSource:
    def __init__(self, client: GeekjobClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        seen_ids: set = set()
        jobs: list[Job] = []

        for position in effective_list(preferences, "geekjob", "positions"):
            for page in range(1, PAGES_PER_POSITION + 1):
                # ponytail: Chrome может умереть посреди прогона ("no
                # such window: target window already closed") —
                # _acquire_driver лечит это между вызовами, но не
                # спасает от исключения, вылетевшего из самого этого
                # driver.get(). Раньше оно улетало наружу и хоронило
                # весь geekjob.search() (весь плановый запуск площадки
                # шёл в лог как "geekjob упал"), хотя следующий вызов
                # клиента и так пересоздал бы драйвер. Ловим здесь и
                # просто переходим к следующей позиции — тем же
                # паттерном, что уже чинил Wellfound apply.
                try:
                    html = self.client.search_vacancies_html(position, page=page)
                except PlatformBlockedError:
                    raise
                except Exception as e:
                    logger.exception(
                        f"geekjob.ru поиск упал на '{position}' стр.{page} — "
                        f"пропускаю, продолжаю со следующей позицией: {e}"
                    )
                    break
                items = parse_search_results(html)
                if not items:
                    break

                for item in items:
                    vacancy_id = item["id"]
                    if vacancy_id in seen_ids:
                        continue
                    seen_ids.add(vacancy_id)

                    try:
                        detail_html = self.client.get_vacancy_html(vacancy_id)
                    except PlatformBlockedError:
                        raise
                    except Exception as e:
                        logger.exception(
                            f"geekjob.ru вакансия {vacancy_id} упала — "
                            f"пропускаю, продолжаю: {e}"
                        )
                        continue
                    job = geekjob_vacancy_to_job(detail_html, vacancy_id)
                    if passes_blacklists(job, preferences):
                        jobs.append(job)

        return jobs
