from src.job import Job
from src.job_sources.blacklist_filter import passes_blacklists
from src.job_sources.block_detection import PlatformBlockedError
from src.job_sources.getmatch.client import GetMatchClient
from src.job_sources.getmatch.mapping import parse_search_results
from src.job_sources.preferences import effective_list
from src.logging import logger

# Сам поиск живёт здесь; реальный клик "Откликнуться" — в
# GetMatchClient.apply() (main.py вызывает его при auto_apply: true),
# подтверждён на живом аккаунте. Сопроводительное письмо генерируется
# для истории отклика, но никуда на самом GetMatch не вставляется —
# сайт нигде его не показывает.


# ponytail: полнофразовое совпадение ("python разработчик" целиком)
# вживую нашло 0 вакансий — реальные заголовки пишут "Python-
# разработчик" (дефис, не пробел) или вовсе по-английски "Python
# Developer". Родовые слова роли ни о чём не говорят и есть почти
# везде — отбрасываем их и матчим по оставшимся словам через "или".
_GENERIC_ROLE_WORDS = frozenset(
    {
        "разработчик",
        "программист",
        "специалист",
        "инженер",
        "developer",
        "engineer",
    }
)


def _significant_words(position: str) -> list:
    words = [w.lower() for w in position.split() if len(w) >= 3]
    significant = [w for w in words if w not in _GENERIC_ROLE_WORDS]
    return significant or words


def _matches_any_position(job: Job, positions: list) -> bool:
    text = f"{job.role} {job.description}".lower()
    return any(
        word in text
        for position in positions
        for word in _significant_words(position)
    )


# ponytail: без ?q= листаем по пустой странице как стоп-сигналу (как
# GeekjobSource — see PAGES_PER_POSITION), подтверждено вживую: p=10
# за концом списка отдаёт 0 карточек, не ошибку. Потолок — на случай,
# если сайт когда-нибудь перестанет отдавать пустую страницу и
# зациклит листание.
MAX_PAGES = 10


class GetMatchSource:
    def __init__(self, client: GetMatchClient):
        self.client = client

    def search(self, preferences: dict) -> list[Job]:
        gm_preferences = preferences.get("getmatch") or {}
        specializations = gm_preferences.get("specializations") or []
        # ponytail: с specializations сайт уже фильтрует сам через
        # sp= (чекбоксы "Сфера" на живой странице) — точнее и дешевле,
        # чем тащить весь общий список и грепать по словам (см.
        # _matches_any_position ниже). Без specializations — старое
        # поведение: общий список постранично + фильтр по positions
        # на нашей стороне, как у TelegramSource._matches_any для той
        # же ситуации (источник без серверного keyword-поиска).
        positions = effective_list(preferences, "getmatch", "positions")

        seen_ids: set = set()
        jobs: list[Job] = []
        for page in range(1, MAX_PAGES + 1):
            # ponytail: тот же краш посреди прогона, что чинили у
            # GeekjobSource — Chrome может умереть между driver.get()
            # (и _acquire_driver его не ловит, т.к. проверяет
            # живость драйвера ДО этого вызова, а не во время него).
            # Раньше исключение улетало наружу и хоронило весь
            # getmatch.search() целиком.
            try:
                html = self.client.search_vacancies_html(
                    page=page, specializations=specializations
                )
            except PlatformBlockedError:
                raise
            except Exception as e:
                logger.exception(
                    f"getmatch.ru поиск упал на стр.{page} — "
                    f"останавливаю пагинацию, отдаю что уже нашли: {e}"
                )
                break
            items = parse_search_results(html)
            if not items:
                break

            for job in items:
                if job.external_id in seen_ids:
                    continue
                if (
                    not specializations
                    and positions
                    and not _matches_any_position(job, positions)
                ):
                    continue
                seen_ids.add(job.external_id)
                if passes_blacklists(job, preferences):
                    jobs.append(job)

        return jobs
