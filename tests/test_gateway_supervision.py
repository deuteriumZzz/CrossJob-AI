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
