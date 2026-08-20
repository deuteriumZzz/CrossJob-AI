import tempfile
from pathlib import Path
from unittest.mock import patch

import main


def test_declining_wizard_does_not_create_data_folder():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"
        with patch("inquirer.confirm", return_value=False):
            result = main.run_setup_wizard(data_folder)

        assert result is False
        assert not data_folder.exists()


def test_accepting_wizard_copies_template_and_writes_api_key():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"
        with patch("inquirer.confirm", return_value=True), patch(
            "inquirer.text", return_value="sk-test-123"
        ):
            result = main.run_setup_wizard(data_folder)

        assert result is True
        assert (data_folder / "secrets.yaml").exists()
        assert (data_folder / "work_preferences.yaml").exists()
        secrets_text = (data_folder / "secrets.yaml").read_text(
            encoding="utf-8"
        )
        assert "llm_api_key: 'sk-test-123'" in secrets_text


def test_accepting_wizard_without_api_key_leaves_template_placeholder():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"
        with patch("inquirer.confirm", return_value=True), patch(
            "inquirer.text", return_value=""
        ):
            result = main.run_setup_wizard(data_folder)

        assert result is True
        secrets_text = (data_folder / "secrets.yaml").read_text(
            encoding="utf-8"
        )
        # llm_api_key строка из шаблона осталась как есть (не пустая
        # строка, не переписана set_top_level_field, т.к. пользователь
        # ничего не ввёл)
        assert "llm_api_key:" in secrets_text
        assert "sk-test-123" not in secrets_text


def test_accepting_wizard_fills_only_missing_required_files():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"
        data_folder.mkdir()
        (data_folder / "work_preferences.yaml").write_text(
            "positions:\n  - custom already here\n", encoding="utf-8"
        )
        with patch("inquirer.confirm", return_value=True), patch(
            "inquirer.text", return_value=""
        ):
            result = main.run_setup_wizard(data_folder)

        assert result is True
        assert (data_folder / "secrets.yaml").exists()
        # существующий файл не перезаписан копией из шаблона
        assert "custom already here" in (
            data_folder / "work_preferences.yaml"
        ).read_text(encoding="utf-8")
