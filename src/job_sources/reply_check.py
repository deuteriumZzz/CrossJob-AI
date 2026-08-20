from src.job_sources.applied_log import AppliedLog


def _print_replies(
    source: str, state_by_vacancy_id: dict, applied_log: AppliedLog
) -> None:
    entries = applied_log.entries_by_source_and_status(source, "applied")
    if not entries:
        print(f"Пока нет ни одного реального отклика на {source}.")
        return
    for entry in entries:
        state = state_by_vacancy_id.get(
            entry["external_id"], "не найден в текущих откликах"
        )
        print(f"{entry['company']} — {entry['title']}: {state}")
        print(f"  {entry['link']}")


def print_negotiation_replies(
    source: str, negotiations: list, applied_log: AppliedLog
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
    _print_replies(source, state_by_vacancy_id, applied_log)


def print_superjob_replies(messages: list, applied_log: AppliedLog) -> None:
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
    _print_replies("superjob", state_by_vacancy_id, applied_log)
