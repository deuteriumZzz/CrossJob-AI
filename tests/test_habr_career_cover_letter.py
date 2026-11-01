"""HabrCareerClient.apply() откликается одним кликом, затем дописывает
письмо: сначала в блоке «Ваш отклик» («Дополнить отклик», 1.11), иначе
через «Посмотреть отклик» → «Редактировать» → «Сохранить». Письмо
считается приложенным, только если его текст потом виден на странице."""

from unittest.mock import MagicMock, patch

from src.job_sources.habr_career.client import HabrCareerClient

LETTER = "<p>Здравствуйте, меня заинтересовала ваша вакансия Python</p>"


def _el(text: str = "", tag: str = "button") -> MagicMock:
    el = MagicMock()
    el.is_displayed.return_value = True
    el.text = text
    el.tag_name = tag
    return el


def _make_driver(route: str, letter_shows: bool = True):
    """route: "post_apply" — блок «Дополнить отклик» сразу после отклика,
    "edit" — только «Посмотреть отклик» → «Редактировать», "none" —
    поля письма нет (компании, где письмо не предусмотрено)."""
    apply_button = _el("Откликнуться")
    view_button = _el("Посмотреть отклик", tag="a")
    edit_button = _el("Редактировать")
    textarea = _el(tag="textarea")
    submit = _el("Дополнить отклик" if route == "post_apply" else "Сохранить")

    def find_elements(by, selector):
        if selector == "button":
            return [apply_button] + ([submit] if route != "none" else [])
        if selector == "button, a":
            return [view_button, edit_button]
        if selector == ".create-vacancy-response__button":
            return [edit_button] if route == "edit" else []
        if selector == "textarea":
            return [textarea] if route != "none" else []
        return []

    def execute_script(script, *args):
        if "innerText" in script:
            return (
                "Отклик отправлен Здравствуйте, меня заинтересовала ваша "
                "вакансия Python"
                if letter_shows
                else "Отклик отправлен"
            )
        return None

    driver = MagicMock()
    driver.find_elements.side_effect = find_elements
    driver.execute_script.side_effect = execute_script
    return driver, textarea, submit


def _apply(driver, letter=LETTER):
    with patch(
        "src.job_sources.habr_career.client.init_browser",
        return_value=driver,
    ), patch(
        "src.job_sources.habr_career.client.raise_if_page_blocked"
    ), patch(
        "src.job_sources.habr_career.client.time.sleep"
    ):
        client = HabrCareerClient("profile")
        return client, client.apply("https://career.habr.com/vacancies/1", letter)


def test_letter_goes_into_post_apply_form():
    driver, textarea, submit = _make_driver("post_apply")
    client, applied = _apply(driver)
    assert applied is True and client.letter_attached is True
    textarea.send_keys.assert_called_once_with(
        "Здравствуйте, меня заинтересовала ваша вакансия Python"
    )
    driver.execute_script.assert_any_call("arguments[0].click();", submit)


def test_falls_back_to_edit_route():
    driver, textarea, submit = _make_driver("edit")
    client, applied = _apply(driver)
    assert applied is True and client.letter_attached is True
    driver.execute_script.assert_any_call("arguments[0].click();", submit)


def test_no_letter_field_still_counts_application_but_not_letter():
    driver, textarea, _ = _make_driver("none")
    client, applied = _apply(driver)
    assert applied is True and client.letter_attached is False
    textarea.send_keys.assert_not_called()


def test_letter_not_visible_after_submit_is_not_counted():
    driver, _, _ = _make_driver("post_apply", letter_shows=False)
    client, applied = _apply(driver)
    assert applied is True and client.letter_attached is False


def test_skips_letter_step_when_no_letter_given():
    driver, textarea, _ = _make_driver("post_apply")
    client, applied = _apply(driver, letter="")
    assert applied is True and client.letter_attached is False
    textarea.send_keys.assert_not_called()


def test_letter_step_crash_keeps_application():
    """Отклик уже ушёл — сбой на письме не превращается в исключение."""
    driver, _, _ = _make_driver("post_apply")
    with patch.object(
        HabrCareerClient,
        "_attach_cover_letter",
        side_effect=RuntimeError("element click intercepted"),
    ):
        client, applied = _apply(driver)
    assert applied is True and client.letter_attached is False
