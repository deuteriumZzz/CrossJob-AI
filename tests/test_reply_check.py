import tempfile
from pathlib import Path

from src.job import Job
from src.job_sources.applied_log import AppliedLog
from src.job_sources.reply_check import print_negotiation_replies


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
            score=8,
            gaps=[],
        )
        negotiations = [
            {"vacancy": {"id": 1}, "state": {"name": "приглашение"}}
        ]

        print_negotiation_replies("headhunter", negotiations, applied_log)
        out = capsys.readouterr().out
        assert "приглашение" in out
        assert "Acme" in out


def test_print_negotiation_replies_fires_on_new_reply_only_once(capsys):
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
            score=8,
            gaps=[],
        )
        negotiations = [
            {"vacancy": {"id": 1}, "state": {"name": "приглашение"}}
        ]
        calls = []

        print_negotiation_replies(
            "headhunter",
            negotiations,
            applied_log,
            on_new_reply=lambda entry, state: calls.append(state),
        )
        print_negotiation_replies(
            "headhunter",
            negotiations,
            applied_log,
            on_new_reply=lambda entry, state: calls.append(state),
        )

        assert calls == ["приглашение"]
