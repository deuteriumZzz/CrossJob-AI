import os
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


def test_bootstrap_data_folder_uses_meipass_when_frozen():
    """Регрессия: в PyInstaller-сборке (desktop_app.spec) datas
    (data_folder_example) распаковываются в sys._MEIPASS, а не рядом
    с main.py — _project_root() должен предпочесть sys._MEIPASS,
    когда он выставлен (имитирует замороженный exe), а не всегда
    смотреть рядом с исходником."""
    with tempfile.TemporaryDirectory() as tmp:
        fake_bundle = Path(tmp) / "bundle"
        bundled_example = fake_bundle / "data_folder_example"
        bundled_example.mkdir(parents=True)
        (bundled_example / "secrets.yaml").write_text(
            "llm_api_key: 'from-bundle'\n", encoding="utf-8"
        )
        (bundled_example / "work_preferences.yaml").write_text(
            "positions: []\n", encoding="utf-8"
        )

        data_folder = Path(tmp) / "data_folder"
        with patch.object(main.sys, "_MEIPASS", str(fake_bundle), create=True):
            main.bootstrap_data_folder(data_folder)

        assert "from-bundle" in (data_folder / "secrets.yaml").read_text(
            encoding="utf-8"
        )


def test_bootstrap_data_folder_works_regardless_of_process_cwd():
    """Регрессия: раньше data_folder_example искался как путь
    относительно CWD, что ломалось всегда, когда сервер (веб-
    дашборд/десктоп-приложение) запущен не из корня проекта —
    воспроизведено вживую при первой проверке веб-визарда в браузере
    (500: FileNotFoundError: data_folder_example)."""
    original_cwd = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            data_folder = Path(tmp) / "elsewhere" / "data_folder"

            result = main.bootstrap_data_folder(data_folder, "sk-cwd-test")

            assert result["created_folder"] is True
            assert (data_folder / "secrets.yaml").exists()
    finally:
        os.chdir(original_cwd)


def test_bootstrap_data_folder_reports_what_it_did():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"

        result = main.bootstrap_data_folder(data_folder, "sk-direct")

        assert result == {"created_folder": True, "api_key_written": True}
        secrets_text = (data_folder / "secrets.yaml").read_text(
            encoding="utf-8"
        )
        assert "llm_api_key: 'sk-direct'" in secrets_text


def test_bootstrap_data_folder_without_api_key():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"

        result = main.bootstrap_data_folder(data_folder)

        assert result == {"created_folder": True, "api_key_written": False}


def test_bootstrap_data_folder_on_existing_folder_does_not_recreate():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp) / "data_folder"
        data_folder.mkdir()
        (data_folder / "work_preferences.yaml").write_text(
            "positions:\n  - already here\n", encoding="utf-8"
        )

        result = main.bootstrap_data_folder(data_folder)

        assert result["created_folder"] is False
        assert "already here" in (
            data_folder / "work_preferences.yaml"
        ).read_text(encoding="utf-8")
