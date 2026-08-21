import tempfile
from pathlib import Path

import pytest

from main import ConfigError, ConfigValidator


def _secrets_file(tmp, text):
    path = Path(tmp) / "secrets.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_legacy_key_used_when_no_provider_given():
    with tempfile.TemporaryDirectory() as tmp:
        secrets_file = _secrets_file(tmp, "llm_api_key: 'sk-legacy'\n")
        assert ConfigValidator.validate_secrets(secrets_file) == "sk-legacy"


def test_legacy_key_falls_back_for_config_default_provider():
    with tempfile.TemporaryDirectory() as tmp:
        secrets_file = _secrets_file(tmp, "llm_api_key: 'sk-legacy'\n")
        assert (
            ConfigValidator.validate_secrets(secrets_file, "openai")
            == "sk-legacy"
        )


def test_legacy_key_does_not_leak_into_other_provider():
    with tempfile.TemporaryDirectory() as tmp:
        secrets_file = _secrets_file(tmp, "llm_api_key: 'sk-legacy'\n")
        with pytest.raises(ConfigError):
            ConfigValidator.validate_secrets(secrets_file, "groq")


def test_per_provider_key_wins_over_legacy():
    with tempfile.TemporaryDirectory() as tmp:
        secrets_file = _secrets_file(
            tmp,
            "llm_api_key: 'sk-legacy'\n"
            "llm_api_keys:\n"
            "  groq: 'gsk-real'\n",
        )
        assert (
            ConfigValidator.validate_secrets(secrets_file, "groq")
            == "gsk-real"
        )


if __name__ == "__main__":
    test_legacy_key_used_when_no_provider_given()
    test_legacy_key_falls_back_for_config_default_provider()
    test_legacy_key_does_not_leak_into_other_provider()
    test_per_provider_key_wins_over_legacy()
    print("All tests passed.")
