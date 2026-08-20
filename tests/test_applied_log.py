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
            job, cover_letter="Здравствуйте!", resume_id="r1", status="dry_run"
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
            dry_run_job, cover_letter="x", resume_id="r1", status="dry_run"
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
            real_job, cover_letter="x", resume_id="r1", status="applied"
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
        )

        assert applied_log.applied_today_count("headhunter") == 1
        assert applied_log.applied_today_count("superjob") == 1
        assert applied_log.applied_today_count("zarplata") == 0


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
        )

        hh_applied = applied_log.entries_by_source_and_status(
            "headhunter", "applied"
        )
        assert len(hh_applied) == 1
        assert hh_applied[0]["external_id"] == "1"


if __name__ == "__main__":
    test_record_dedup_and_html_report_written()
    test_already_applied_to_company_ignores_dry_runs()
    test_applied_today_count_only_counts_applied_status_for_source()
    test_entries_by_source_and_status_filters_correctly()
    print("All tests passed.")
