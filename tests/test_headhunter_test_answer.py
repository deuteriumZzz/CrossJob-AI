"""Эвристика ответа на тест/анкету вакансии HH (browser_test_answer.py) —
перенесена из hh-applicant-tool как fallback, см. docstring
answer_vacancy_test_if_present про статус."""

from unittest.mock import MagicMock

from src.job_sources.headhunter.browser_test_answer import (
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
