import tempfile
from pathlib import Path

import pytest

import main


def test_auto_apply_requires_getmatch_email_in_secrets():
    with tempfile.TemporaryDirectory() as tmp:
        data_folder = Path(tmp)
        (data_folder / "resume.pdf").write_bytes(b"%PDF-fake")
        secrets_file = data_folder / "secrets.yaml"
        secrets_file.write_text("llm_api_key: 'sk-test'\n", encoding="utf-8")

        parameters = {
            "dataFolder": data_folder,
            "secretsFile": secrets_file,
            "getmatch": {"auto_apply": True},
        }

        with pytest.raises(main.ConfigError):
            main.search_getmatch(parameters, "sk-test")


if __name__ == "__main__":
    test_auto_apply_requires_getmatch_email_in_secrets()
    print("All tests passed.")
