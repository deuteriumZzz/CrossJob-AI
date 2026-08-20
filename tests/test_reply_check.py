import tempfile
from pathlib import Path

from src.job import Job
from src.job_sources.applied_log import AppliedLog
from src.job_sources.reply_check import (
    print_negotiation_replies,
    print_superjob_replies,
)


def test_print_negotiation_replies_matches_by_vacancy_id(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        applied_log = AppliedLog(Path(tmp) / "applied_log.json")
        applied_log.record(
            Job(
                role="Backend Dev",
                company="Acme",
                link="https://hh.ru/vacancy/1",
                source="headhunter",
                external_id="1",
            ),
            cover_letter="x",
            resume_id="r1",
            status="applied",
        )
        negotiations = [
            {"vacancy": {"id": 1}, "state": {"name": "приглашение"}}
        ]

        print_negotiation_replies("headhunter", negotiations, applied_log)
        out = capsys.readouterr().out
        assert "приглашение" in out
        assert "Acme" in out


def test_print_superjob_replies_falls_back_to_unknown_without_matching_vacancy(
    capsys,
):
    with tempfile.TemporaryDirectory() as tmp:
        applied_log = AppliedLog(Path(tmp) / "applied_log.json")
        applied_log.record(
            Job(
                role="QA",
                company="Beta",
                link="https://superjob.ru/vacancy/2",
                source="superjob",
                external_id="2",
            ),
            cover_letter="x",
            resume_id="r1",
            status="applied",
        )

        print_superjob_replies(messages=[], applied_log=applied_log)
        out = capsys.readouterr().out
        assert "не найден в текущих откликах" in out
