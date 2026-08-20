import tempfile
from pathlib import Path

import pytest

from scripts import explore_getmatch_bot as explore


def test_load_telegram_credentials_reads_secrets_yaml(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp)
        (data_folder / "secrets.yaml").write_text(
            "telegram:\n  api_id: '12345'\n  api_hash: 'abc'\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(explore, "DATA_FOLDER", data_folder)
        assert explore._load_telegram_credentials() == (12345, "abc")


def test_load_telegram_credentials_requires_api_id_and_hash(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp)
        (data_folder / "secrets.yaml").write_text(
            "telegram:\n  api_id: ''\n  api_hash: ''\n", encoding="utf-8"
        )
        monkeypatch.setattr(explore, "DATA_FOLDER", data_folder)
        with pytest.raises(SystemExit):
            explore._load_telegram_credentials()
