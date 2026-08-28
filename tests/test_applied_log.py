import tempfile
from pathlib import Path

from src.job import Job
from src.job_sources.applied_log import AppliedLog


def test_record_dedup_and_html_report_written():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "applied_log.json"
        applied_log = AppliedLog(log_path)

        job = Job(
            role="Backend Developer",
            company="Acme <Ltd>",
            link="https://example.com/1",
            source="headhunter",
            external_id="1",
        )

        assert applied_log.already_applied(job) is False

        applied_log.record(
            job,
            cover_letter="Здравствуйте!",
            resume_id="r1",
            status="dry_run",
            score=8,
            gaps=[],
        )

        assert applied_log.already_applied(job) is True

        report_path = Path(tmp) / "applications.html"
        assert report_path.exists()
        report_html = report_path.read_text(encoding="utf-8")
        assert "Acme &lt;Ltd&gt;" in report_html
        assert "Здравствуйте!" in report_html

        # Новый экземпляр AppliedLog заново читает то же состояние
        # дедупликации с диска.
        reloaded = AppliedLog(log_path)
        assert reloaded.already_applied(job) is True
        assert len(reloaded.find_by_company("acme")) == 1


def test_already_applied_to_company_ignores_dry_runs():
    with tempfile.TemporaryDirectory() as tmp:
        applied_log = AppliedLog(Path(tmp) / "applied_log.json")
        dry_run_job = Job(
            role="A",
            company="Acme",
            link="https://example.com/1",
            source="headhunter",
            external_id="1",
        )
        applied_log.record(
            dry_run_job,
            cover_letter="x",
            resume_id="r1",
            status="dry_run",
            score=8,
            gaps=[],
        )
        assert applied_log.already_applied_to_company(dry_run_job) is False

        real_job = Job(
            role="B",
            company="Acme",
            link="https://example.com/2",
            source="headhunter",
            external_id="2",
        )
        applied_log.record(
            real_job,
            cover_letter="x",
            resume_id="r1",
            status="applied",
            score=8,
            gaps=[],
        )
        assert applied_log.already_applied_to_company(real_job) is True

        other_source_job = Job(
            role="C",
            company="Acme",
            link="https://example.com/3",
            source="superjob",
            external_id="3",
        )
        assert (
            applied_log.already_applied_to_company(other_source_job) is False
        )


def test_applied_today_count_only_counts_applied_status_for_source():
    with tempfile.TemporaryDirectory() as tmp:
        applied_log = AppliedLog(Path(tmp) / "applied_log.json")
        assert applied_log.applied_today_count("headhunter") == 0

        applied_log.record(
            Job(
                role="A",
                company="Acme",
                link="https://example.com/1",
                source="headhunter",
                external_id="1",
            ),
            cover_letter="x",
            resume_id="r1",
            status="applied",
            score=8,
            gaps=[],
        )
        applied_log.record(
            Job(
                role="B",
                company="Acme",
                link="https://example.com/2",
                source="headhunter",
                external_id="2",
            ),
            cover_letter="x",
            resume_id="r1",
            status="dry_run",
            score=8,
            gaps=[],
        )
        applied_log.record(
            Job(
                role="C",
                company="Acme",
                link="https://example.com/3",
                source="superjob",
                external_id="3",
            ),
            cover_letter="x",
            resume_id="r1",
            status="applied",
            score=8,
            gaps=[],
        )

        assert applied_log.applied_today_count("headhunter") == 1
        assert applied_log.applied_today_count("superjob") == 1
        assert applied_log.applied_today_count("geekjob") == 0
        assert applied_log.applied_today_count_all() == 2


def test_entries_by_source_and_status_filters_correctly():
    with tempfile.TemporaryDirectory() as tmp:
        applied_log = AppliedLog(Path(tmp) / "applied_log.json")
        applied_log.record(
            Job(
                role="A",
                company="Acme",
                link="https://example.com/1",
                source="headhunter",
                external_id="1",
            ),
            cover_letter="x",
            resume_id="r1",
            status="applied",
            score=8,
            gaps=[],
        )
        applied_log.record(
            Job(
                role="B",
                company="Acme",
                link="https://example.com/2",
                source="headhunter",
                external_id="2",
            ),
            cover_letter="x",
            resume_id="r1",
            status="dry_run",
            score=8,
            gaps=[],
        )
        applied_log.record(
            Job(
                role="C",
                company="Acme",
                link="https://example.com/3",
                source="superjob",
                external_id="3",
            ),
            cover_letter="x",
            resume_id="r1",
            status="applied",
            score=8,
            gaps=[],
        )

        hh_applied = applied_log.entries_by_source_and_status(
            "headhunter", "applied"
        )
        assert len(hh_applied) == 1
        assert hh_applied[0]["external_id"] == "1"


def test_update_reply_state_reports_change_only_once():
    with tempfile.TemporaryDirectory() as tmp:
        applied_log = AppliedLog(Path(tmp) / "applied_log.json")
        job = Job(
            role="A",
            company="Acme",
            link="https://example.com/1",
            source="headhunter",
            external_id="1",
        )
        applied_log.record(
            job,
            cover_letter="x",
            resume_id="r1",
            status="applied",
            score=8,
            gaps=[],
        )

        assert (
            applied_log.update_reply_state("headhunter", "1", "приглашение")
            is True
        )
        assert (
            applied_log.update_reply_state("headhunter", "1", "приглашение")
            is False
        )
        assert (
            applied_log.update_reply_state("headhunter", "1", "отказ") is True
        )
        assert applied_log.update_reply_state("headhunter", "999", "x") is (
            False
        )


def test_find_by_source_and_external_id_and_mark_replied():
    with tempfile.TemporaryDirectory() as tmp:
        applied_log = AppliedLog(Path(tmp) / "applied_log.json")
        job = Job(
            role="A",
            company="Acme",
            link="https://example.com/1",
            source="headhunter",
            external_id="1",
        )
        applied_log.record(
            job,
            cover_letter="x",
            resume_id="r1",
            status="applied",
            score=8,
            gaps=[],
        )

        assert (
            applied_log.find_by_source_and_external_id("headhunter", "999")
            is None
        )
        entry = applied_log.find_by_source_and_external_id("headhunter", "1")
        assert entry is not None
        assert entry["company"] == "Acme"
        assert "last_replied_message_id" not in entry

        applied_log.mark_replied("headhunter", "1", "msg-42")
        entry = applied_log.find_by_source_and_external_id("headhunter", "1")
        assert entry["last_replied_message_id"] == "msg-42"

        # Не найденная запись — no-op, не должно падать.
        applied_log.mark_replied("headhunter", "999", "msg-1")


def test_most_common_gaps_counts_across_entries():
    with tempfile.TemporaryDirectory() as tmp:
        applied_log = AppliedLog(Path(tmp) / "applied_log.json")
        for i, gaps in enumerate([["Docker"], ["Docker", "Go"], ["Go"]]):
            applied_log.record(
                Job(
                    role="A",
                    company="Acme",
                    link=f"https://example.com/{i}",
                    source="headhunter",
                    external_id=str(i),
                ),
                cover_letter="x",
                resume_id="r1",
                status="applied",
                score=6,
                gaps=gaps,
            )

        assert applied_log.most_common_gaps() == [("Docker", 2), ("Go", 2)]
        assert applied_log.most_common_gaps(limit=1) == [("Docker", 2)]


def test_suggest_blacklist_candidates_needs_min_attempts_and_no_reply():
    with tempfile.TemporaryDirectory() as tmp:
        applied_log = AppliedLog(Path(tmp) / "applied_log.json")

        def record(company, external_id, status="applied"):
            applied_log.record(
                Job(
                    role="A",
                    company=company,
                    link=f"https://example.com/{external_id}",
                    source="headhunter",
                    external_id=external_id,
                ),
                cover_letter="x",
                resume_id="r1",
                status=status,
                score=6,
                gaps=[],
            )

        # 3 попытки без ответа -> кандидат
        record("Ghosted Inc", "1")
        record("Ghosted Inc", "2")
        record("Ghosted Inc", "3")

        # 3 попытки, но с ответом на одну -> не кандидат
        record("Replied Co", "4")
        record("Replied Co", "5")
        record("Replied Co", "6")
        applied_log.update_reply_state("headhunter", "4", "приглашение")

        # только 2 попытки -> не набрал минимум
        record("Too Few LLC", "7")
        record("Too Few LLC", "8")

        assert applied_log.suggest_blacklist_candidates() == ["Ghosted Inc"]


if __name__ == "__main__":
    test_record_dedup_and_html_report_written()
    test_already_applied_to_company_ignores_dry_runs()
    test_applied_today_count_only_counts_applied_status_for_source()
    test_entries_by_source_and_status_filters_correctly()
    test_update_reply_state_reports_change_only_once()
    test_find_by_source_and_external_id_and_mark_replied()
    test_most_common_gaps_counts_across_entries()
    test_suggest_blacklist_candidates_needs_min_attempts_and_no_reply()
    print("All tests passed.")
