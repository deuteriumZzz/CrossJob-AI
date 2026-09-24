"""HabrCareerClient.apply() отправляет отклик одним кликом без формы
под письмо (см. client.py), но сразу после этого best-effort
дописывает сопроводительное письмо через "Посмотреть отклик" →
"Редактировать" (подтверждено вживую 2026-09-18, см.
_attach_cover_letter)."""

from unittest.mock import MagicMock, patch

from src.job_sources.habr_career.client import HabrCareerClient


def _el(text: str = "", tag: str = "button") -> MagicMock:
    el = MagicMock()
    el.is_displayed.return_value = True
    el.text = text
    el.tag_name = tag
    return el


def _make_driver(with_cover_letter_form: bool) -> MagicMock:
    apply_button = _el("Откликнуться")
    view_button = _el("Посмотреть отклик", tag="a")
    edit_button = _el("Редактировать")
    textarea = _el(tag="textarea")
    save_button = _el("Сохранить")

    def find_elements(by, selector):
        if selector == "button":
            return [apply_button]
        if selector == "button, a":
            return [view_button, edit_button]
        if selector == ".create-vacancy-response__button":
            return [edit_button] if with_cover_letter_form else []
        if selector == "textarea[name='body']":
            return [textarea] if with_cover_letter_form else []
        if selector == "button[type='submit']":
            return [save_button] if with_cover_letter_form else []
        return []

    driver = MagicMock()
    driver.find_elements.side_effect = find_elements
    return driver, textarea, save_button


def test_apply_attaches_cover_letter_after_successful_response():
    driver, textarea, save_button = _make_driver(with_cover_letter_form=True)
    with patch(
        "src.job_sources.habr_career.client.init_browser",
        return_value=driver,
    ), patch(
        "src.job_sources.habr_career.client.raise_if_blocked"
    ), patch(
        "src.job_sources.habr_career.client.visible_text", return_value=""
    ), patch(
        "src.job_sources.habr_career.client.time.sleep"
    ):
        client = HabrCareerClient("profile")
        applied = client.apply(
            "https://career.habr.com/vacancies/1", "<p>Здравствуйте</p>"
        )

    assert applied is True
    textarea.send_keys.assert_called_once_with("Здравствуйте")
    save_button.click.assert_called_once()


def test_apply_skips_cover_letter_step_when_no_letter_given():
    driver, textarea, save_button = _make_driver(with_cover_letter_form=True)
    with patch(
        "src.job_sources.habr_career.client.init_browser",
        return_value=driver,
    ), patch(
        "src.job_sources.habr_career.client.raise_if_blocked"
    ), patch(
        "src.job_sources.habr_career.client.visible_text", return_value=""
    ), patch(
        "src.job_sources.habr_career.client.time.sleep"
    ):
        client = HabrCareerClient("profile")
        applied = client.apply("https://career.habr.com/vacancies/1")

    assert applied is True
    textarea.send_keys.assert_not_called()


def test_apply_still_reports_success_when_cover_letter_form_missing():
    driver, textarea, save_button = _make_driver(with_cover_letter_form=False)
    with patch(
        "src.job_sources.habr_career.client.init_browser",
        return_value=driver,
    ), patch(
        "src.job_sources.habr_career.client.raise_if_blocked"
    ), patch(
        "src.job_sources.habr_career.client.visible_text", return_value=""
    ), patch(
        "src.job_sources.habr_career.client.time.sleep"
    ):
        client = HabrCareerClient("profile")
        applied = client.apply(
            "https://career.habr.com/vacancies/1", "Здравствуйте"
        )

    assert applied is True
    textarea.send_keys.assert_not_called()
