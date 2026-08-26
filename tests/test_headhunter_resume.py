"""Резюме-клики на hh.ru (browser_resume.py) — браузерный аналог
hh-applicant-tool clone_resume.py/create_resume.py, без OAuth API (см.
clone_resume/start_resume_draft docstrings про обоснование)."""

from unittest.mock import MagicMock, patch

from src.job_sources.headhunter.browser_resume import (
    clone_resume,
    start_resume_draft,
)


def test_clone_resume_returns_none_when_button_missing():
    driver = MagicMock()
    driver.find_elements.return_value = []
    with patch("src.job_sources.headhunter.browser_resume.time.sleep"):
        assert clone_resume(driver, "abc123") is None


def test_clone_resume_returns_new_url_when_id_changes():
    button = MagicMock()
    button.is_displayed.return_value = True
    driver = MagicMock()
    driver.find_elements.return_value = [button]
    driver.current_url = "https://hh.ru/resume/def456"

    with patch("src.job_sources.headhunter.browser_resume.time.sleep"):
        result = clone_resume(driver, "abc123")

    assert result == "https://hh.ru/resume/def456"
    button.click.assert_called_once()


def test_clone_resume_returns_none_when_url_unchanged():
    button = MagicMock()
    button.is_displayed.return_value = True
    driver = MagicMock()
    driver.find_elements.return_value = [button]
    driver.current_url = "https://hh.ru/resume/abc123"

    with patch("src.job_sources.headhunter.browser_resume.time.sleep"):
        assert clone_resume(driver, "abc123") is None


def test_start_resume_draft_returns_none_when_create_button_missing():
    driver = MagicMock()
    driver.find_elements.return_value = []
    with patch("src.job_sources.headhunter.browser_resume.time.sleep"):
        assert start_resume_draft(driver, "Python разработчик") is None


def test_start_resume_draft_fills_title_and_returns_url():
    create_button = MagicMock()
    create_button.is_displayed.return_value = True
    title_input = MagicMock()
    title_input.is_displayed.return_value = True

    driver = MagicMock()

    def find_elements(by, selector):
        if "add-button" in selector:
            return [create_button]
        if "title" in selector or "vacancy-of-interest" in selector:
            return [title_input]
        return []

    driver.find_elements.side_effect = find_elements
    driver.current_url = "https://hh.ru/applicant/resumes/constructor/draft1"

    with patch("src.job_sources.headhunter.browser_resume.time.sleep"):
        result = start_resume_draft(driver, "Python разработчик")

    assert result == "https://hh.ru/applicant/resumes/constructor/draft1"
    create_button.click.assert_called_once()
    title_input.send_keys.assert_called_once_with("Python разработчик")
