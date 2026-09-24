import tempfile
from pathlib import Path

import main
from src.job import Job
from src.job_sources.block_detection import (
    PlatformBlockedError,
    is_still_blocked,
)


class _FakeFit:
    score = 9
    gaps: list = []


class _FakeClient:
    """apply() бросает капчу на первой же вакансии — как на живом HH."""

    def __init__(self):
        self.apply_calls = 0

    def bump_resume(self, resume_id):
        return False

    def apply(self, link, cover_letter_fn, ai_answer_fn):
        self.apply_calls += 1
        raise PlatformBlockedError("captcha")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_captcha_during_apply_stops_run_instead_of_hammering_next_jobs(
    monkeypatch,
):
    """Регрессия: раньше PlatformBlockedError из client.apply() ловился
    общим except в цикле и просто continue'ил на следующую вакансию —
    бот продолжал долбить driver.get() по всем оставшимся вакансиям в
    уже заблокированной (капчей) сессии. Теперь должен остановиться
    после первой же и поставить площадку на cooldown."""
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data"
        output_folder = Path(tmp) / "output"
        data_folder.mkdir()
        output_folder.mkdir()
        (data_folder / main.RESUME_PDF).write_bytes(b"%PDF-1.4 fake")

        fake_client = _FakeClient()
        jobs = [
            Job(role="Dev A", company="Co A", link="https://hh.ru/vacancy/1"),
            Job(role="Dev B", company="Co B", link="https://hh.ru/vacancy/2"),
        ]

        monkeypatch.setattr(
            main,
            "HeadHunterSession",
            lambda profile_dir: type(
                "S", (), {"ensure_logged_in": lambda self, parameters: None}
            )(),
        )
        monkeypatch.setattr(
            main, "HeadHunterBrowserClient", lambda profile_dir: fake_client
        )
        monkeypatch.setattr(
            main.HeadHunterBrowserSource, "search", lambda self, prefs: jobs
        )
        monkeypatch.setattr(main, "score_job_fit", lambda *a, **k: _FakeFit())
        monkeypatch.setattr(main, "classify_fit", lambda *a, **k: "strong")
        monkeypatch.setattr(main, "notify", lambda *a, **k: None)

        parameters = {
            "dataFolder": data_folder,
            "outputFileDirectory": output_folder,
            "headhunter": {"auto_apply": True},
        }

        main.search_and_apply_headhunter(parameters, "fake-llm-key")

        assert fake_client.apply_calls == 1
        assert is_still_blocked(output_folder, "headhunter")


def test_auto_bump_without_resume_id_bumps_every_account_resume(monkeypatch):
    """Регрессия: пустой headhunter.resume_id (значение по умолчанию)
    раньше молча отключал auto_bump_resume — теперь бот сам берёт id
    всех резюме аккаунта и поднимает каждое."""
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data"
        output_folder = Path(tmp) / "output"
        data_folder.mkdir()
        output_folder.mkdir()
        (data_folder / main.RESUME_PDF).write_bytes(b"%PDF-1.4 fake")

        bumped: list[str] = []

        class _BumpClient(_FakeClient):
            def resume_ids(self):
                return ["aaa111", "bbb222"]

            def bump_resume(self, resume_id):
                bumped.append(resume_id)
                return True

        monkeypatch.setattr(
            main,
            "HeadHunterSession",
            lambda profile_dir: type(
                "S", (), {"ensure_logged_in": lambda self, parameters: None}
            )(),
        )
        monkeypatch.setattr(
            main, "HeadHunterBrowserClient", lambda profile_dir: _BumpClient()
        )
        monkeypatch.setattr(
            main.HeadHunterBrowserSource, "search", lambda self, prefs: []
        )
        monkeypatch.setattr(main, "notify", lambda *a, **k: None)

        main.search_and_apply_headhunter(
            {
                "dataFolder": data_folder,
                "outputFileDirectory": output_folder,
                "headhunter": {"auto_bump_resume": True, "resume_id": ""},
            },
            llm_api_key="",
        )

        assert bumped == ["aaa111", "bbb222"]
