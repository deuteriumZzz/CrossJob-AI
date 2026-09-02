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
    """Для клиентов в духе HeadHunter API, у которых
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
