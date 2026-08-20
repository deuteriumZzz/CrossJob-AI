import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from src.scheduler import Scheduler
from src.scheduler_state import load_state


def _make_scheduler(tmp, parameters, source_map, now=None):
    return Scheduler(
        source_map=source_map,
        parameters=parameters,
        llm_api_key="key",
        output_folder=Path(tmp),
        now_fn=lambda: now or datetime(2026, 8, 20, 10, 0, 0),
    )


def test_due_sources_skips_disabled_sources():
    with tempfile.TemporaryDirectory() as tmp:
        scheduler = _make_scheduler(
            tmp,
            parameters={
                "headhunter": {"schedule_enabled": True},
                "superjob": {"schedule_enabled": False},
            },
            source_map={
                "headhunter": lambda p, k: None,
                "superjob": lambda p, k: None,
            },
        )
        assert scheduler.due_sources() == ["headhunter"]


def test_due_sources_respects_next_run():
    with tempfile.TemporaryDirectory() as tmp:
        calls = []
        scheduler = _make_scheduler(
            tmp,
            parameters={"headhunter": {"schedule_enabled": True}},
            source_map={"headhunter": lambda p, k: calls.append(1)},
        )
        scheduler.run_once()
        assert calls == [1]

        # Тот же момент времени снова — уже не due, next_run в будущем.
        assert scheduler.due_sources() == []


def test_run_once_advances_next_run_by_interval_hours():
    with tempfile.TemporaryDirectory() as tmp:
        now = datetime(2026, 8, 20, 10, 0, 0)
        scheduler = _make_scheduler(
            tmp,
            parameters={
                "headhunter": {
                    "schedule_enabled": True,
                    "interval_hours": 5,
                }
            },
            source_map={"headhunter": lambda p, k: None},
            now=now,
        )
        scheduler.run_once()

        state = load_state(Path(tmp))
        assert state["headhunter"]["status"] == "ok"
        expected_next = now + timedelta(hours=5)
        assert state["headhunter"]["next_run"] == expected_next.isoformat()


def test_run_once_records_error_and_does_not_raise():
    with tempfile.TemporaryDirectory() as tmp:

        def boom(p, k):
            raise RuntimeError("network down")

        scheduler = _make_scheduler(
            tmp,
            parameters={"headhunter": {"schedule_enabled": True}},
            source_map={"headhunter": boom},
        )

        scheduler.run_once()

        state = load_state(Path(tmp))
        assert state["headhunter"]["status"] == "error"
        assert "network down" in state["headhunter"]["last_error"]


if __name__ == "__main__":
    test_due_sources_skips_disabled_sources()
    test_due_sources_respects_next_run()
    test_run_once_advances_next_run_by_interval_hours()
    test_run_once_records_error_and_does_not_raise()
    print("All tests passed.")
