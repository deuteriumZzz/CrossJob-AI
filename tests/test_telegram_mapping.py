from dataclasses import dataclass

from src.job_sources.telegram.mapping import telegram_message_to_job
from src.job_sources.telegram.source import (
    _matches_any,
    _passes_telegram_filters,
)


@dataclass
class FakeMessage:
    id: int
    text: str


def test_telegram_message_to_job_maps_fields():
    message = FakeMessage(
        id=42, text="Ищем Python разработчика\nУдалённо, от 200К"
    )
    job = telegram_message_to_job("pythonjobs", message)
    assert job.role == "Ищем Python разработчика"
    assert job.link == "https://t.me/pythonjobs/42"
    assert job.source == "telegram"
    assert job.external_id == "pythonjobs_42"
    assert job.apply_method == "telegram_manual"
    assert "Удалённо" in job.description


def test_matches_any_case_insensitive():
    assert _matches_any("ищем python разработчика", ["Python"]) is True
    assert _matches_any("ищем java разработчика", ["Python"]) is False


def test_passes_telegram_filters_rejects_blacklisted_company_in_text():
    preferences = {"company_blacklist": ["wayfair"]}
    assert (
        _passes_telegram_filters("Vacancy at Wayfair, remote", preferences)
        is False
    )


def test_passes_telegram_filters_locations_allowlist_checks_full_text():
    preferences = {"locations": ["Berlin"]}
    assert (
        _passes_telegram_filters(
            "Ищем разработчика, Berlin office", preferences
        )
        is True
    )
    assert (
        _passes_telegram_filters(
            "Ищем разработчика, Moscow office", preferences
        )
        is False
    )


if __name__ == "__main__":
    test_telegram_message_to_job_maps_fields()
    test_matches_any_case_insensitive()
    test_passes_telegram_filters_rejects_blacklisted_company_in_text()
    test_passes_telegram_filters_locations_allowlist_checks_full_text()
    print("All tests passed.")
