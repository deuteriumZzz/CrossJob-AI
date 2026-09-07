import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import main


def _parameters(data_folder: Path) -> dict:
    (data_folder / "resume.pdf").write_bytes(b"%PDF-fake")
    secrets_file = data_folder / "secrets.yaml"
    secrets_file.write_text(
        "llm_api_key: 'sk-test'\ngetmatch:\n  email: 'test@example.com'\n",
        encoding="utf-8",
    )
    return {
        "dataFolder": data_folder,
        "secretsFile": secrets_file,
        "outputFileDirectory": data_folder,
        "getmatch": {"auto_apply": True},
    }


def test_search_getmatch_propagates_when_login_keeps_failing():
    """ensure_logged_in() already retries once internally
    (get_with_retry) — if it still fails, search_getmatch() must let
    that exception through rather than swallow it, so the scheduler's
    own try/except (src/scheduler.py) can record an "error" run status
    and send the Telegram alert instead of silently reporting "ok"."""
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp)
        parameters = _parameters(data_folder)
        with patch("main.is_still_blocked", return_value=False), patch(
            "main.GetMatchSession"
        ) as session_cls, patch("main.GetMatchClient") as client_cls:
            session_cls.return_value.ensure_logged_in.side_effect = Exception(
                "Timed out receiving message from renderer"
            )
            with pytest.raises(Exception, match="renderer"):
                main.search_getmatch(parameters, "sk-test")
            client_cls.assert_not_called()


if __name__ == "__main__":
    test_search_getmatch_propagates_when_login_keeps_failing()
    print("All tests passed.")
