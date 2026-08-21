import tempfile
from pathlib import Path
from unittest.mock import patch

from src.job_sources.llm_usage import check_and_mark_alert, record_usage


def test_no_alert_when_below_threshold():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        record_usage(out, "openai", "gpt-4o-mini", 1000, 500)
        assert check_and_mark_alert(out, 100.0) is False


def test_no_alert_when_cost_unknown_provider():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        record_usage(out, "groq", "llama-3.3", 1_000_000, 1_000_000)
        # cost неизвестна для groq — check_and_mark_alert не может
        # сравнить с порогом, значит не алертит.
        assert check_and_mark_alert(out, 0.0001) is False


def test_alert_fires_once_when_threshold_crossed():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        record_usage(out, "openai", "gpt-4o", 1_000_000, 1_000_000)
        # ~$12.5 потрачено (gpt-4o pricing) — порог $1.
        assert check_and_mark_alert(out, 1.0) is True
        # тот же день — второй вызов не должен алертить повторно.
        assert check_and_mark_alert(out, 1.0) is False


def test_alert_resets_on_a_new_day():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        record_usage(out, "openai", "gpt-4o", 1_000_000, 1_000_000)
        assert check_and_mark_alert(out, 1.0) is True

        # искусственно "переносим" отметку на вчера, чтобы проверить,
        # что новый день снова алертит.
        alert_path = out / ".llm_usage_alert.json"
        alert_path.write_text('{"last_alert_date": "2000-01-01"}')
        assert check_and_mark_alert(out, 1.0) is True


def test_scheduler_run_once_triggers_llm_cost_notification():
    from src.scheduler import Scheduler

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        record_usage(out, "openai", "gpt-4o", 1_000_000, 1_000_000)

        scheduler = Scheduler(
            source_map={},
            parameters={"limits": {"llm_daily_cost_alert_usd": 1.0}},
            llm_api_key="key",
            output_folder=out,
        )

        with patch("src.scheduler.notify_from_secrets") as mock_notify:
            scheduler.run_once()

        mock_notify.assert_called_once()
        args, _ = mock_notify.call_args
        assert "LLM" in args[1]


def test_scheduler_run_once_skips_check_without_threshold():
    from src.scheduler import Scheduler

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        record_usage(out, "openai", "gpt-4o", 1_000_000, 1_000_000)

        scheduler = Scheduler(
            source_map={},
            parameters={},
            llm_api_key="key",
            output_folder=out,
        )

        with patch("src.scheduler.notify_from_secrets") as mock_notify:
            scheduler.run_once()

        mock_notify.assert_not_called()
