import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

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
                "geekjob": {"schedule_enabled": False},
            },
            source_map={
                "headhunter": lambda p, k: None,
                "geekjob": lambda p, k: None,
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


def test_run_once_notifies_on_failure():
    with tempfile.TemporaryDirectory() as tmp:

        def boom(p, k):
            raise RuntimeError("network down")

        scheduler = _make_scheduler(
            tmp,
            parameters={"headhunter": {"schedule_enabled": True}},
            source_map={"headhunter": boom},
        )

        with patch("src.scheduler.notify_from_secrets") as mock_notify:
            scheduler.run_once()

        mock_notify.assert_called_once()
        args, _ = mock_notify.call_args
        assert args[0] is scheduler.parameters
        assert "headhunter" in args[1]
        assert "network down" in args[1]


if __name__ == "__main__":
    test_due_sources_skips_disabled_sources()
    test_due_sources_respects_next_run()
    test_run_once_advances_next_run_by_interval_hours()
    test_run_once_records_error_and_does_not_raise()
    test_run_once_notifies_on_failure()
    print("All tests passed.")


def test_reply_checks_on_by_default_but_hh_only_with_platform():
    noop = lambda p, k: None  # noqa: E731
    checks = {
        "check_email_replies": noop,
        "check_telegram_commands": noop,
        "check_hh_replies": noop,
    }
    with tempfile.TemporaryDirectory() as tmp:
        off = _make_scheduler(
            tmp,
            {"check_telegram_commands": {"schedule_enabled": False}},
            checks,
        )
        assert off.due_sources() == [
            "check_email_replies"
        ]  # hh не в расписании — браузер не открываем
        on = _make_scheduler(
            tmp, {"headhunter": {"schedule_enabled": True}}, checks
        )
        assert sorted(on.due_sources()) == sorted(checks)


def test_continuous_cycle_runs_one_source_per_tick_round_robin():
    """limits.continuous_cycle_enabled: все площадки из ротации сначала
    due одновременно, но за один run_once() уходит только первая по
    порядку — следующий тик подхватывает следующую (round-robin), а не
    все разом. check_* задачи в ротацию не входят и идут как обычно."""
    with tempfile.TemporaryDirectory() as tmp:
        calls = []
        now = datetime(2026, 8, 20, 10, 0, 0)
        parameters = {
            "headhunter": {"schedule_enabled": True},
            "geekjob": {"schedule_enabled": True},
            "getmatch": {"schedule_enabled": True},
            "limits": {
                "continuous_cycle_enabled": True,
                "continuous_cycle_gap_minutes": 3,
            },
        }
        source_map = {
            name: (lambda p, k, n=name: calls.append(n))
            for name in ("headhunter", "geekjob", "getmatch")
        }
        scheduler = _make_scheduler(tmp, parameters, source_map, now=now)
        scheduler.run_once()
        assert calls == ["headhunter"]
        scheduler.run_once()
        assert calls == ["headhunter", "geekjob"]
        scheduler.run_once()
        assert calls == ["headhunter", "geekjob", "getmatch"]

        # Ещё виток раньше 3 минут — headhunter пока не due снова.
        scheduler.run_once()
        assert calls == ["headhunter", "geekjob", "getmatch"]

        from src.scheduler_state import get_next_run

        assert get_next_run(Path(tmp), "headhunter") == now + timedelta(
            minutes=3
        )


def test_continuous_cycle_piggybacks_hh_replies_on_headhunter_turn():
    """Постоянный цикл: check_hh_replies не идёт по своему таймеру —
    срабатывает сразу после хода headhunter в том же тике, одним заходом."""
    with tempfile.TemporaryDirectory() as tmp:
        calls = []
        now = datetime(2026, 8, 20, 10, 0, 0)
        parameters = {
            "headhunter": {"schedule_enabled": True},
            "limits": {
                "continuous_cycle_enabled": True,
                "continuous_cycle_gap_minutes": 3,
            },
        }
        source_map = {
            "headhunter": lambda p, k: calls.append("headhunter"),
            "check_hh_replies": lambda p, k: calls.append("check_hh_replies"),
        }
        scheduler = _make_scheduler(tmp, parameters, source_map, now=now)
        scheduler.run_once()
        assert calls == ["headhunter", "check_hh_replies"]

        # На следующем тике до истечения gap — headhunter не due, и
        # check_hh_replies за ним следом тоже не запускается сам по себе.
        scheduler.run_once()
        assert calls == ["headhunter", "check_hh_replies"]
