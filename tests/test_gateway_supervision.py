import tempfile
from collections import namedtuple
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import logging as app_logging
from src.scheduler import MIN_FREE_DISK_BYTES, Scheduler


def _scheduler(tmp, telegram):
    return Scheduler(
        source_map={},
        parameters={"telegram": telegram},
        llm_api_key="k",
        output_folder=Path(tmp),
        now_fn=lambda: datetime(2026, 10, 7, 12, 0, 0),
    )


def test_dead_gateway_is_restarted_by_supervisor():
    with tempfile.TemporaryDirectory() as tmp:
        scheduler = _scheduler(tmp, {"watch_enabled": True})
        dead = MagicMock()
        dead.is_alive.return_value = False
        scheduler._telegram_watcher = dead
        fresh = MagicMock()
        with patch(
            "src.job_sources.telegram.watcher.active_watcher",
            return_value=None,
        ), patch(
            "src.job_sources.telegram.watcher.start_telegram_watcher",
            return_value=fresh,
        ) as start:
            scheduler._supervise_gateway()
        start.assert_called_once()
        assert scheduler._telegram_watcher is fresh


def test_supervisor_ignores_a_gateway_turned_off_in_the_dashboard():
    with tempfile.TemporaryDirectory() as tmp:
        scheduler = _scheduler(tmp, {"watch_enabled": False})
        scheduler._telegram_watcher = None
        with patch(
            "src.job_sources.telegram.watcher.start_telegram_watcher"
        ) as start:
            scheduler._supervise_gateway()
        start.assert_not_called()


def test_low_disk_space_sends_one_alert_per_day():
    usage = namedtuple("usage", "total used free")
    with tempfile.TemporaryDirectory() as tmp:
        scheduler = _scheduler(tmp, {})
        with patch(
            "src.scheduler.shutil.disk_usage",
            return_value=usage(10, 9, MIN_FREE_DISK_BYTES - 1),
        ), patch("src.scheduler.notify_from_secrets") as notify:
            scheduler._check_disk_space()
            scheduler._disk_checked = 0.0  # прошёл час
            scheduler._check_disk_space()
        assert notify.call_count == 1


def test_bot_token_is_masked_in_logs():
    record = {
        "message": "GET https://api.telegram.org/bot1234567890:"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/getUpdates"
    }
    app_logging._mask_tokens(record)
    assert "AAAAAAAA" not in record["message"]
    assert "bot<скрыт>/getUpdates" in record["message"]


def test_reminder_hours_moscow():
    from datetime import datetime, timezone

    from src.job_sources.hr_replies import is_reminder_hour

    mon_noon = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)  # 12:00 МСК
    sat_noon = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
    mon_night = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
    assert is_reminder_hour(mon_noon)
    assert not is_reminder_hour(sat_noon)
    assert not is_reminder_hour(mon_night)


def test_geekjob_params_follow_common_filters():
    from src.job_sources.filters import geekjob_search_params

    assert geekjob_search_params({"remote": True}) == {"rm": "1"}
    assert geekjob_search_params({"onsite": True})["ih"] == "1"
    mixed = geekjob_search_params({"remote": True, "onsite": True})
    assert "rm" not in mixed and "ih" not in mixed
    assert geekjob_search_params({"only_with_salary": True})["s"] == "1"


def test_djinni_and_talanto_salary_and_experience():
    import json

    from src.job_sources.djinni.search import parse_jobs, search_params
    from src.job_sources.filters import talanto_salary_params

    params = search_params("Python", 1, {"levels": ["middle"]})
    assert params["exp_level"] == ["3y", "4y", "5y"]
    assert "exp_level" not in search_params("Python", 1, {})
    assert talanto_salary_params({}) == ""
    assert "salary_min=1" in talanto_salary_params({"only_with_salary": True})

    def page(base):
        item = {
            "@type": "JobPosting",
            "url": "https://djinni.co/jobs/1-x/",
            "title": "Dev",
            "identifier": 1,
        }
        if base:
            item["baseSalary"] = base
        return (
            f'<script type="application/ld+json">{json.dumps(item)}</script>'
        )

    salary = {
        "currency": "USD",
        "value": {"minValue": 550, "maxValue": 700},
    }
    assert parse_jobs(page(salary))[0].salary == "550–700 USD"
    assert parse_jobs(page(None), only_with_salary=True) == []
    assert len(parse_jobs(page(salary), only_with_salary=True)) == 1


def test_same_error_on_three_platforms_alerts_once():
    import json

    with tempfile.TemporaryDirectory() as tmp:
        scheduler = _scheduler(tmp, {})
        run = datetime(2026, 10, 7, 11, 0, 0).isoformat()
        state = {
            name: {
                "status": "error",
                "last_run": run,
                "last_error": "LLM key rejected (401)",
            }
            for name in ("djinni", "habr_career", "getmatch")
        }
        state["linkedin"] = {
            "status": "error",
            "last_run": run,
            "last_error": "other",
        }
        (Path(tmp) / ".scheduler_state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
        with patch("src.scheduler.notify_from_secrets") as notify:
            scheduler._check_shared_errors()
            scheduler._check_shared_errors()
        notify.assert_called_once()
        assert "3 площадок" in notify.call_args[0][1]


def test_time_limit_guard_applies_to_collectors_outside_the_cycle():
    received = {}

    def collector(parameters, key, stop_event=None):
        received["stop"] = stop_event

    def plain(parameters, key):
        received["plain"] = True

    scheduler = Scheduler(
        source_map={"hirify": collector, "direct_like": plain},
        parameters={},
        llm_api_key="k",
        output_folder=Path("."),
    )
    scheduler._call_source("hirify", platform_turn=False)
    scheduler._call_source("direct_like", platform_turn=False)
    assert received["stop"] is not None and not received["stop"].is_set()
    assert received["plain"] is True
