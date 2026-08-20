import tempfile
from pathlib import Path
from unittest.mock import patch

import main
from src.job import Job
from src.job_sources.applied_log import AppliedLog


def test_export_application_history_writes_txt_with_salary_and_site():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        applied_log = AppliedLog(output_folder / "applied_log.json")
        applied_log.record(
            Job(
                role="Backend Developer",
                company="Acme",
                link="https://example.com/1",
                source="headhunter",
                external_id="1",
                salary="100000-150000 RUR",
                company_url="https://acme.example",
            ),
            cover_letter="x",
            resume_id="r1",
            status="applied",
        )

        with patch.object(
            main.inquirer, "prompt", return_value={"format": "TXT"}
        ):
            main.export_application_history(
                {"outputFileDirectory": output_folder}
            )

        out_path = output_folder / "applications_export.txt"
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "Acme" in content
        assert "100000-150000 RUR" in content
        assert "https://acme.example" in content


def test_export_application_history_skips_when_log_empty():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        AppliedLog(output_folder / "applied_log.json")

        with patch.object(main.inquirer, "prompt") as mock_prompt:
            main.export_application_history(
                {"outputFileDirectory": output_folder}
            )
            mock_prompt.assert_not_called()

        assert not (output_folder / "applications_export.txt").exists()


if __name__ == "__main__":
    test_export_application_history_writes_txt_with_salary_and_site()
    test_export_application_history_skips_when_log_empty()
    print("All tests passed.")
