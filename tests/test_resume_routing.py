from pathlib import Path

from src.job_sources.resume_routing import (
    available_resumes,
    resolve_resume,
    resume_relative_name,
)


def _files(data: Path) -> None:
    (data / "telegram").mkdir()
    (data / "resume.pdf").write_bytes(b"%PDF")
    (data / "resume_linkedin.pdf").write_bytes(b"%PDF")
    (data / "telegram" / "Dmitry_CV.pdf").write_bytes(b"%PDF")
    (data / "telegram" / "Dmitry_CV_RU.pdf").write_bytes(b"%PDF")


def test_default_routing_separates_channel_and_language(tmp_path):
    _files(tmp_path)
    parameters = {"dataFolder": tmp_path}

    assert (
        resolve_resume(parameters, "email", russian=True).name == "resume.pdf"
    )
    assert (
        resolve_resume(parameters, "email", russian=False).name
        == "resume_linkedin.pdf"
    )
    assert (
        resolve_resume(parameters, "telegram", russian=True).name
        == "Dmitry_CV_RU.pdf"
    )
    assert (
        resolve_resume(parameters, "telegram", russian=False).name
        == "Dmitry_CV.pdf"
    )


def test_explicit_routing_wins_and_cannot_escape_data_folder(tmp_path):
    _files(tmp_path)
    parameters = {
        "dataFolder": tmp_path,
        "resume_routing": {
            "telegram_ru": "telegram/Dmitry_CV.pdf",
            "email_en": "../outside.pdf",
        },
    }

    assert (
        resume_relative_name(
            parameters,
            resolve_resume(parameters, "telegram", russian=True),
        )
        == "telegram/Dmitry_CV.pdf"
    )
    # Небезопасный/несуществующий путь игнорируется, работает EN fallback.
    assert (
        resolve_resume(parameters, "email", russian=False).name
        == "resume_linkedin.pdf"
    )
    assert {item["value"] for item in available_resumes(parameters)} == {
        "resume.pdf",
        "resume_linkedin.pdf",
        "telegram/Dmitry_CV.pdf",
        "telegram/Dmitry_CV_RU.pdf",
    }


def test_available_resumes_ignores_symlink_outside_data_folder(tmp_path):
    _files(tmp_path)
    outside = tmp_path.parent / "outside-resume.pdf"
    outside.write_bytes(b"%PDF")
    (tmp_path / "telegram" / "outside.pdf").symlink_to(outside)

    values = {
        item["value"] for item in available_resumes({"dataFolder": tmp_path})
    }

    assert "telegram/outside.pdf" not in values
