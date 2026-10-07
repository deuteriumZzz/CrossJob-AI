from datetime import datetime, timedelta

from src.job import Job
from src.job_sources.applied_log import EASY_APPLY_MAX_ATTEMPTS, AppliedLog


def _job():
    return Job(
        role="Python Dev",
        company="Acme",
        link="https://www.linkedin.com/jobs/view/1",
        source="linkedin",
        external_id="1",
    )


def _expire(log: AppliedLog):
    data = log._data
    for e in data["applications"]:
        e["retry_after"] = (
            datetime.now().astimezone() - timedelta(minutes=1)
        ).isoformat()
    import json

    log.path.write_text(json.dumps(data))


def test_failed_form_is_retried_then_closed(tmp_path):
    log = AppliedLog(tmp_path / "applied_log.json")
    job = _job()

    assert log.record_easy_apply_failure(job, 7, [], "stuck") == 1
    assert log.already_applied(job)  # пауза до повтора — пока «уже было»
    assert "1" in log.seen_ids("linkedin")

    _expire(log)
    assert not log.already_applied(job)  # пора пробовать снова
    assert "1" not in log.seen_ids("linkedin")

    for attempt in range(2, EASY_APPLY_MAX_ATTEMPTS + 1):
        assert log.record_easy_apply_failure(job, 7, [], "stuck") == attempt
        _expire(log)
    assert log.already_applied(job)  # попытки кончились — закрыта насовсем
    assert len(log._data["applications"]) == 1


def test_successful_retry_replaces_failure_record(tmp_path):
    log = AppliedLog(tmp_path / "applied_log.json")
    job = _job()
    log.record_easy_apply_failure(job, 7, [], "stuck")
    _expire(log)

    log.record(job, "", "", "applied", 7, [])

    statuses = [e["status"] for e in log._data["applications"]]
    assert statuses == ["applied"]
