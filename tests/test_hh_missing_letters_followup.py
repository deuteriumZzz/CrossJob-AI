import main
from src.job import Job


def _log(tmp_path, *jobs):
    log = main.AppliedLog(tmp_path / "applied_log.json")
    for job_id, letter in jobs:
        job = Job(
            role=f"Dev {job_id}",
            company=f"Co {job_id}",
            link=f"https://hh.ru/vacancy/{job_id}",
            source="headhunter",
            external_id=job_id,
        )
        log.record(job, letter, "", "applied", 7, [])
    return log


def test_followup_regenerates_missing_letter_and_skips_rejected(
    tmp_path, monkeypatch
):
    log = _log(tmp_path, ("1", ""), ("2", "Письмо 2"), ("3", "Письмо 3"))
    log.update_fields("headhunter", "3", last_known_state="Отказ")
    sent = []

    def fake_send(driver, applied_log, entry, text):
        sent.append((entry["external_id"], text))
        return True

    monkeypatch.setattr(main, "_hh_chat_send", fake_send)
    monkeypatch.setattr(main, "wait_before_apply", lambda: None)

    main._send_missing_cover_letters(
        object(), log, lambda entry: f"Новое {entry['external_id']}"
    )

    # 1 — письма не было (генерация падала): написано заново и отправлено;
    # 2 — обычная досылка; 3 — работодатель отказал, письмо не доставляем.
    assert sent == [("1", "Новое 1"), ("2", "Письмо 2")]
    assert (
        log.find_by_source_and_external_id("headhunter", "1")["cover_letter"]
        == "Новое 1"
    )
    assert log.find_by_source_and_external_id("headhunter", "3")[
        "cover_letter_undeliverable"
    ]
