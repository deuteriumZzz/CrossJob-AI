"""Регрессия: create_cover_letter/create_resume_pdf_job_tailored/
create_resume_pdf передавали ResumeFacade(output_path=...) хардкод
Path("data_folder/output") вместо реального parameters
["outputFileDirectory"]. Для CLI это случайно работало (CWD всегда
корень проекта), но для дашборда/десктоп-приложения (CWD может быть
чем угодно) — ResumeFacade.__init__ пишет этот путь в
global_config.LOG_OUTPUT_FILE_PATH, а LLMLogger.log_request() потом
открывает "<path>/open_ai_calls.json" в режиме "a" без mkdir —
несуществующий путь роняет вызов LLM с FileNotFoundError."""

import base64
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import main


def _base_parameters(tmp: str) -> dict:
    output_folder = Path(tmp) / "data_folder" / "output"
    output_folder.mkdir(parents=True)
    plain_text_resume_file = (
        Path(tmp) / "data_folder" / "plain_text_resume.yaml"
    )
    plain_text_resume_file.write_text("resume: text\n", encoding="utf-8")
    return {
        "outputFileDirectory": output_folder,
        "plainTextResumeFile": plain_text_resume_file,
        "dataFolder": Path(tmp) / "data_folder",
    }


def _mock_facade(pdf_bytes: bytes = b"%PDF-fake"):
    facade = MagicMock()
    encoded = base64.b64encode(pdf_bytes).decode()
    facade.create_cover_letter.return_value = (encoded, "acme-corp")
    facade.create_resume_pdf_job_tailored.return_value = (
        encoded,
        "acme-corp",
    )
    facade.create_resume_pdf.return_value = encoded
    return facade


def test_create_cover_letter_uses_configured_output_folder():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _base_parameters(tmp)
        facade = _mock_facade()

        with patch(
            "main.ensure_plain_text_resume",
            return_value=parameters["plainTextResumeFile"],
        ), patch("main.init_browser"), patch("main.Resume"), patch(
            "main.ResumeFacade", return_value=facade
        ) as mock_class:
            main.create_cover_letter(
                parameters,
                "sk-test",
                style_name="Default",
                job_url="https://example.com/job",
            )

        _, kwargs = mock_class.call_args
        assert kwargs["output_path"] == parameters["outputFileDirectory"]


def test_create_resume_pdf_job_tailored_uses_configured_output_folder():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _base_parameters(tmp)
        facade = _mock_facade()

        with patch(
            "main.ensure_plain_text_resume",
            return_value=parameters["plainTextResumeFile"],
        ), patch("main.init_browser"), patch("main.Resume"), patch(
            "main.ResumeFacade", return_value=facade
        ) as mock_class:
            main.create_resume_pdf_job_tailored(
                parameters,
                "sk-test",
                style_name="Default",
                job_url="https://example.com/job",
            )

        _, kwargs = mock_class.call_args
        assert kwargs["output_path"] == parameters["outputFileDirectory"]


def test_create_resume_pdf_uses_configured_output_folder():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _base_parameters(tmp)
        facade = _mock_facade()

        with patch(
            "main.ensure_plain_text_resume",
            return_value=parameters["plainTextResumeFile"],
        ), patch("main.init_browser"), patch("main.Resume"), patch(
            "main.ResumeFacade", return_value=facade
        ) as mock_class:
            main.create_resume_pdf(parameters, "sk-test", style_name="Default")

        _, kwargs = mock_class.call_args
        assert kwargs["output_path"] == parameters["outputFileDirectory"]
