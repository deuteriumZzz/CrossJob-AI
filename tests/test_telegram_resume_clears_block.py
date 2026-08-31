import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import main
from src.job_sources.block_detection import is_still_blocked, mark_blocked
from src.scheduler_state import get_next_run


def test_resume_command_clears_captcha_block_and_forces_immediate_retry(
    monkeypatch,
):
    """Регрессия: /resume раньше только включал schedule_enabled обратно
    — источник всё равно молча ждал бы 24ч-кулдаун block_detection и
    оставшийся до interval_hours срок. Теперь /resume после того, как
    пользователь вручную решил капчу, должен снять блокировку и
    поставить площадку в очередь на следующий же тик планировщика."""
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data"
        output_folder = Path(tmp) / "output"
        data_folder.mkdir()
        output_folder.mkdir()

        secrets_file = data_folder / "secrets.yaml"
        secrets_file.write_text(
            "notifications:\n"
            "  telegram_bot_token: 'fake-token'\n"
            "  telegram_chat_id: '123'\n",
            encoding="utf-8",
        )
        work_prefs_file = data_folder / main.WORK_PREFERENCES_YAML
        work_prefs_file.write_text("headhunter:\n  auto_apply: false\n")

        mark_blocked(output_folder, "headhunter")
        assert is_still_blocked(output_folder, "headhunter") is True

        monkeypatch.setattr(
            main,
            "poll_control_commands",
            lambda *a, **k: [{"action": "resume", "source": "headhunter"}],
        )
        monkeypatch.setattr(main, "send_notification", lambda *a, **k: None)

        parameters = {
            "dataFolder": data_folder,
            "outputFileDirectory": output_folder,
            "secretsFile": secrets_file,
        }

        before = datetime.now()
        main.check_telegram_commands(parameters, "fake-llm-key")

        assert is_still_blocked(output_folder, "headhunter") is False
        next_run = get_next_run(output_folder, "headhunter")
        assert next_run is not None
        assert next_run <= before + timedelta(seconds=5)
