"""Кнопка 👋 под вакансией из Telegram-парсера: при smart_greeting=true
письмо должно быть от LLM, а не молча падать в статичный шаблон на
первой же временной ошибке (rate limit бесплатных лимитов вроде
Gemini "раз в минуту") — тот же retry, что уже есть у LLM-классификатора
вакансий (_llm_says_vacancy)."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from src.job_sources.telegram.watcher import save_watch_post


def _ctx(tmp_path: Path) -> dict:
    return {
        "outputFileDirectory": tmp_path,
        "dataFolder": tmp_path,
        "telegram": {"smart_greeting": True},
    }


def _callback(post_id: str) -> dict:
    return {
        "id": "1",
        "data": f"q:{post_id}:0:-1",
        "message": {"chat": {"id": 1}, "message_id": 5},
    }


def test_greeting_retries_on_rate_limit_then_uses_llm_text():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        post_id = save_watch_post(
            tmp_path,
            {
                "channel": "jobs",
                "link": "https://t.me/jobs/1",
                "text": "Python Dev, @hr_anna",
                "title": "Python Dev",
                "contacts": [{"kind": "telegram", "value": "hr_anna"}],
            },
        )
        parameters = _ctx(tmp_path)

        fake_client = MagicMock()
        fake_client.__enter__ = MagicMock(return_value=fake_client)
        fake_client.__exit__ = MagicMock(return_value=False)

        calls = {"n": 0}

        def flaky_generate(*a, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("429 Too Many Requests")
            return {"text": "Персональное письмо от LLM", "subject": ""}

        with patch("main._telegram_client", return_value=fake_client), patch(
            "main.generate_first_message", side_effect=flaky_generate
        ), patch("main.time.sleep") as mock_sleep, patch(
            "main.bot_request", return_value={}
        ):
            main._handle_vacancy_button(
                parameters, "fake-key", "tok", _callback(post_id)
            )

        assert calls["n"] == 3
        assert mock_sleep.call_count == 2
        sent_text = fake_client.send_message.call_args[0][1]
        assert sent_text == "Персональное письмо от LLM"


def test_greeting_falls_back_to_template_after_exhausting_retries():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        post_id = save_watch_post(
            tmp_path,
            {
                "channel": "jobs",
                "link": "https://t.me/jobs/2",
                "text": "Python Dev, @hr_anna",
                "title": "Python Dev",
                "contacts": [{"kind": "telegram", "value": "hr_anna"}],
            },
        )
        parameters = _ctx(tmp_path)

        fake_client = MagicMock()
        fake_client.__enter__ = MagicMock(return_value=fake_client)
        fake_client.__exit__ = MagicMock(return_value=False)

        with patch("main._telegram_client", return_value=fake_client), patch(
            "main.generate_first_message",
            side_effect=RuntimeError("429 rate limit"),
        ), patch("main.time.sleep") as mock_sleep, patch(
            "main.bot_request", return_value={}
        ):
            main._handle_vacancy_button(
                parameters, "fake-key", "tok", _callback(post_id)
            )

        assert mock_sleep.call_count == len(
            main.RATE_LIMIT_RETRY_DELAYS_SECONDS
        )
        sent_text = fake_client.send_message.call_args[0][1]
        assert "Python Dev" in sent_text  # шаблон с подставленной ролью
