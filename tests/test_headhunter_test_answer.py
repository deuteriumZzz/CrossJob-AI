"""Эвристика ответа на тест/анкету вакансии HH (browser_test_answer.py) —
перенесена из hh-applicant-tool как fallback, см. docstring
answer_vacancy_test_if_present про статус."""

from unittest.mock import MagicMock

from src.job_sources.headhunter.browser_test_answer import (
    answer_full_page_questionnaire,
    answer_vacancy_test_if_present,
)


def _make_option(text: str) -> MagicMock:
    option = MagicMock()
    option.text = text
    return option


def _make_block(options=None, free_text_field=None, text: str = "") -> MagicMock:
    block = MagicMock()
    block.is_displayed.return_value = True
    block.text = text

    def find_elements(by, selector):
        if options is not None and "radio" in selector:
            return options
        if free_text_field is not None and "textarea" in selector:
            return [free_text_field]
        return []

    block.find_elements.side_effect = find_elements
    return block


def test_no_test_present_returns_false():
    driver = MagicMock()
    driver.find_elements.return_value = []
    assert answer_vacancy_test_if_present(driver) is False


def test_multiple_choice_prefers_yes_option():
    options = [_make_option("Нет"), _make_option("Да"), _make_option("Не знаю")]
    block = _make_block(options=options)
    driver = MagicMock()
    driver.find_elements.return_value = [block]

    assert answer_vacancy_test_if_present(driver) is True
    options[1].click.assert_called_once()
    options[0].click.assert_not_called()
    options[2].click.assert_not_called()


def test_multiple_choice_falls_back_to_middle_option_3():
    options = [_make_option("A"), _make_option("B"), _make_option("C")]
    block = _make_block(options=options)
    driver = MagicMock()
    driver.find_elements.return_value = [block]

    answer_vacancy_test_if_present(driver)
    options[1].click.assert_called_once()  # индекс 3//2 == 1


def test_multiple_choice_falls_back_to_middle_option_5():
    options = [_make_option(str(i)) for i in range(5)]
    block = _make_block(options=options)
    driver = MagicMock()
    driver.find_elements.return_value = [block]

    answer_vacancy_test_if_present(driver)
    options[2].click.assert_called_once()  # индекс 5//2 == 2


def test_free_text_with_url_never_calls_ai():
    field = MagicMock()
    field.is_displayed.return_value = True
    block = _make_block(
        free_text_field=field,
        text="Расскажите о себе, ссылка: https://example.com/form",
    )
    driver = MagicMock()
    driver.find_elements.return_value = [block]
    ai_answer_fn = MagicMock(return_value="AI ответ")

    answer_vacancy_test_if_present(driver, ai_answer_fn)

    ai_answer_fn.assert_not_called()
    field.send_keys.assert_not_called()


def test_free_text_without_ai_defaults_to_da():
    field = MagicMock()
    field.is_displayed.return_value = True
    block = _make_block(free_text_field=field, text="Готовы к переезду?")
    driver = MagicMock()
    driver.find_elements.return_value = [block]

    answer_vacancy_test_if_present(driver, ai_answer_fn=None)

    field.send_keys.assert_called_once_with("Да")


def test_free_text_with_ai_uses_ai_answer():
    field = MagicMock()
    field.is_displayed.return_value = True
    block = _make_block(free_text_field=field, text="Готовы к переезду?")
    driver = MagicMock()
    driver.find_elements.return_value = [block]
    ai_answer_fn = MagicMock(return_value="Да, готов")

    answer_vacancy_test_if_present(driver, ai_answer_fn)

    ai_answer_fn.assert_called_once_with("Готовы к переезду?")
    field.send_keys.assert_called_once_with("Да, готов")


def _make_radio(radio_id: str, name: str) -> MagicMock:
    radio = MagicMock()
    radio.is_displayed.return_value = True
    radio.get_attribute.side_effect = lambda attr: {
        "id": radio_id,
        "name": name,
    }.get(attr)
    radio.find_elements.return_value = []  # нет label-предка
    return radio


def _make_label(text: str) -> MagicMock:
    label = MagicMock()
    label.text = text
    return label


def _make_questionnaire_driver(
    radios=None, free_text_fields=None, buttons=None, labels_by_for=None
):
    driver = MagicMock()
    driver.current_url = (
        "https://hh.ru/applicant/vacancy_response?vacancyId=1"
    )
    labels_by_for = labels_by_for or {}

    def find_elements(by, selector):
        if selector == 'input[type="radio"]':
            return radios or []
        if selector == "textarea, input[type=\"text\"]":
            return free_text_fields or []
        if selector.startswith("label[for="):
            field_id = selector.split('"')[1]
            return labels_by_for.get(field_id, [])
        if selector == 'button, a[role="button"]':
            return buttons or []
        return []

    driver.find_elements.side_effect = find_elements
    # По умолчанию — как если бы JS-фолбэк в _label_text_for ничего не
    # нашёл (пустая строка, а не MagicMock, который в `in`-проверке
    # внутри _answer_free_text вёл бы себя как истинный).
    driver.execute_script.return_value = ""
    return driver


def test_full_page_questionnaire_ignored_on_other_urls():
    driver = MagicMock()
    driver.current_url = "https://hh.ru/vacancy/123"

    assert answer_full_page_questionnaire(driver) is False
    driver.find_elements.assert_not_called()


def test_full_page_questionnaire_prefers_yes_radio_and_submits():
    yes_radio = _make_radio("q1-yes", "q1")
    no_radio = _make_radio("q1-no", "q1")
    submit = MagicMock()
    submit.is_displayed.return_value = True
    submit.text = "Respond"
    driver = _make_questionnaire_driver(
        radios=[no_radio, yes_radio],
        buttons=[submit],
        labels_by_for={
            "q1-yes": [_make_label("Да")],
            "q1-no": [_make_label("Нет")],
        },
    )

    assert answer_full_page_questionnaire(driver) is True

    yes_radio.click.assert_called_once()
    no_radio.click.assert_not_called()
    driver.execute_script.assert_any_call(
        "arguments[0].click();", submit
    )


def test_full_page_questionnaire_fills_free_text_via_ai():
    field = MagicMock()
    field.is_displayed.return_value = True
    field.get_attribute.side_effect = lambda attr: {"id": "q2"}.get(attr)
    field.find_elements.return_value = []
    submit = MagicMock()
    submit.is_displayed.return_value = True
    submit.text = "Откликнуться"
    driver = _make_questionnaire_driver(
        free_text_fields=[field],
        buttons=[submit],
        labels_by_for={"q2": [_make_label("Расскажите о себе")]},
    )
    ai_answer_fn = MagicMock(return_value="Пять лет опыта")

    assert answer_full_page_questionnaire(driver, ai_answer_fn) is True

    ai_answer_fn.assert_called_once_with("Расскажите о себе")
    field.send_keys.assert_called_once_with("Пять лет опыта")


def test_full_page_questionnaire_returns_false_without_submit_button():
    field = MagicMock()
    field.is_displayed.return_value = True
    field.get_attribute.return_value = None
    field.find_elements.return_value = []
    driver = _make_questionnaire_driver(free_text_fields=[field], buttons=[])

    assert answer_full_page_questionnaire(driver) is False
    field.send_keys.assert_called_once()  # вопрос всё равно заполнили
