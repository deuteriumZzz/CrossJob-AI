from datetime import datetime, timedelta
from pathlib import Path

import pytest

import main
from src.job_sources.block_detection import PlatformBlockedError
from src.scheduler import Scheduler
from src.scheduler_state import load_state


class _CaptchaClient:
    def __init__(self, clearance):
        self.clearance = iter(clearance)

    def captcha_cleared(self):
        return next(self.clearance, False)


def test_hh_captcha_solved_within_window_retries_same_action(monkeypatch):
    clock = [0.0]
    notifications = []
    attempts = []
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        main.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    monkeypatch.setattr(
        main, "notify", lambda p, message, **kw: notifications.append(message)
    )

    def action():
        attempts.append(1)
        if len(attempts) == 1:
            raise PlatformBlockedError("hh.ru redirected to captcha page")
        return "vacancies"

    result, deadline = main._run_hh_action_with_captcha_wait(
        action, _CaptchaClient([False, True]), {}, None, None
    )

    assert result == "vacancies"
    assert attempts == [1, 1]
    assert deadline == 180.0
    assert len(notifications) == 1
    assert "3 минут" in notifications[0]


def test_hh_captcha_timeout_defers_without_hourly_cooldown(
    monkeypatch, tmp_path
):
    clock = [0.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        main.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    monkeypatch.setattr(main, "notify", lambda *a, **kw: None)

    with pytest.raises(main.HhCaptchaDeferred):
        main._run_hh_action_with_captcha_wait(
            lambda: (_ for _ in ()).throw(PlatformBlockedError("captcha")),
            _CaptchaClient([]),
            {"outputFileDirectory": tmp_path},
            None,
            None,
        )

    assert clock[0] == 180.0
    assert not (tmp_path / ".blocked_until.json").exists()


def test_hh_rate_limit_keeps_existing_block_handling(monkeypatch):
    monkeypatch.setattr(
        main, "notify", lambda *a, **kw: pytest.fail("notification")
    )
    with pytest.raises(PlatformBlockedError, match="429"):
        main._run_hh_action_with_captcha_wait(
            lambda: (_ for _ in ()).throw(PlatformBlockedError("HTTP 429")),
            _CaptchaClient([]),
            {},
            None,
            None,
        )


def test_hh_search_continues_in_same_turn_after_captcha(monkeypatch, tmp_path):
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    (data_folder / main.RESUME_PDF).write_bytes(b"%PDF-1.4 fake")
    searches = []
    notifications = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def captcha_cleared(self):
            return True

    def search(source, preferences):
        searches.append(1)
        if len(searches) == 1:
            raise PlatformBlockedError("hh.ru redirected to captcha page")
        return []

    monkeypatch.setattr(
        main,
        "HeadHunterSession",
        lambda profile: type(
            "Session", (), {"ensure_logged_in": lambda self, p: None}
        )(),
    )
    monkeypatch.setattr(
        main, "HeadHunterBrowserClient", lambda profile: Client()
    )
    monkeypatch.setattr(main.HeadHunterBrowserSource, "search", search)
    monkeypatch.setattr(
        main,
        "notify",
        lambda p, message, **kwargs: notifications.append(message),
    )

    result = main.search_and_apply_headhunter(
        {
            "dataFolder": data_folder,
            "outputFileDirectory": tmp_path,
            "headhunter": {"auto_apply": False},
        },
        "key",
    )

    assert result is None
    assert searches == [1, 1]
    assert len(notifications) == 1
    assert not (tmp_path / ".blocked_until.json").exists()


def test_captcha_timeout_places_hh_after_other_due_platforms(tmp_path):
    clock = [datetime(2026, 10, 10, 10, 0)]
    calls = []

    def hh(parameters, llm_api_key):
        calls.append("headhunter")
        clock[0] += timedelta(minutes=3)
        return main.DEFER_TO_NEXT_TURN

    def geekjob(parameters, llm_api_key):
        calls.append("geekjob")

    scheduler = Scheduler(
        source_map={"headhunter": hh, "geekjob": geekjob},
        parameters={
            "headhunter": {"schedule_enabled": True},
            "geekjob": {"schedule_enabled": True},
            "limits": {
                "continuous_cycle_enabled": True,
                "continuous_cycle_gap_minutes": 3,
            },
        },
        llm_api_key="key",
        output_folder=Path(tmp_path),
        now_fn=lambda: clock[0],
    )

    scheduler.run_once()
    assert load_state(tmp_path)["headhunter"]["status"] == "blocked"
    assert (
        load_state(tmp_path)["headhunter"]["next_run"]
        == (clock[0] + timedelta(minutes=3)).isoformat()
    )
    scheduler.run_once()
    assert calls == ["headhunter", "geekjob"]
