from typing import Callable, Optional

from src.job_sources.applied_log import AppliedLog

OnNewReply = Callable[[dict, str], None]

_NOT_FOUND_STATE = "не найден в текущих откликах"


def _print_replies(
    source: str,
    state_by_vacancy_id: dict,
    applied_log: AppliedLog,
    on_new_reply: Optional[OnNewReply] = None,
) -> None:
    entries = applied_log.entries_by_source_and_status(source, "applied")
    if not entries:
        print(f"Пока нет ни одного реального отклика на {source}.")
        return
    for entry in entries:
        state = state_by_vacancy_id.get(entry["external_id"], _NOT_FOUND_STATE)
        print(f"{entry['company']} — {entry['title']}: {state}")
        print(f"  {entry['link']}")

        if state == _NOT_FOUND_STATE:
            continue
        changed = applied_log.update_reply_state(
            source, entry["external_id"], state
        )
        if changed and on_new_reply is not None:
            on_new_reply(entry, state)


def print_negotiation_replies(
    source: str,
    negotiations: list,
    applied_log: AppliedLog,
    on_new_reply: Optional[OnNewReply] = None,
) -> None:
    """Для клиентов HH-семейства (HeadHunter, Zarplata.ru), у которых
    формат list_negotiations() подтверждён:
    [{"vacancy": {"id": ...}, "state": {"name": ...}}, ...].
    """
    state_by_vacancy_id = {
        str(n["vacancy"]["id"]): (n.get("state") or {}).get(
            "name", "неизвестно"
        )
        for n in negotiations
        if n.get("vacancy")
    }
    _print_replies(source, state_by_vacancy_id, applied_log, on_new_reply)


def print_superjob_replies(
    messages: list,
    applied_log: AppliedLog,
    on_new_reply: Optional[OnNewReply] = None,
) -> None:
    """Названия полей /messages/ у SuperJob для "какая вакансия"/"какой
    статус" не проверены боевым вызовом (см. докстринг
    SuperJobClient.list_messages) — пробуем наиболее вероятные названия
    полей, пропускаем сообщения без распознаваемого id вакансии, а не
    угадываем."""
    state_by_vacancy_id = {}
    for message in messages:
        vacancy_id = message.get("id_vacancy") or message.get("vacancy_id")
        if vacancy_id is None:
            continue
        state_by_vacancy_id[str(vacancy_id)] = (
            message.get("status_text") or message.get("status") or "неизвестно"
        )
    _print_replies("superjob", state_by_vacancy_id, applied_log, on_new_reply)
