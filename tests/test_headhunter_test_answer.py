"""Эвристика ответа на тест/анкету вакансии HH (browser_test_answer.py) —
перенесена из hh-applicant-tool как fallback, см. docstring
answer_vacancy_test_if_present про статус."""

from unittest.mock import MagicMock, call

from selenium.webdriver.common.keys import Keys

from src.job_sources.headhunter.browser_test_answer import (
    _QUESTIONS_JS,
    _pick_option,
    answer_full_page_questionnaire,
    answer_vacancy_test_if_present,
)


def _make_option(text: str) -> MagicMock:
    option = MagicMock()
    option.text = text
    return option


def _make_block(
    options=None, free_text_field=None, text: str = ""
) -> MagicMock:
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
    options = [
        _make_option("Нет"),
        _make_option("Да"),
        _make_option("Не знаю"),
    ]
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


def _questionnaire_driver(radios=(), texts=(), buttons=()):
    """execute_script отдаёт то, что вернул бы _QUESTIONS_JS на живой
    странице (2026-11-06, Битрикс24): radio прозрачные, поэтому вопросы
    и варианты берутся одним JS, а не через is_displayed()."""
    driver = MagicMock()
    driver.current_url = "https://hh.ru/applicant/vacancy_response?vacancyId=1"
    questions = {"radios": list(radios), "texts": list(texts)}
    driver.execute_script.side_effect = (
        lambda script, *args: questions if script == _QUESTIONS_JS else None
    )
    driver.find_elements.side_effect = (
        lambda by, selector: list(buttons)
        if selector == 'button, a[role="button"]'
        else []
    )
    return driver


def _submit(text="Send application") -> MagicMock:
    submit = MagicMock()
    submit.is_displayed.return_value = True
    submit.text = text
    return submit


def _radio_group(question, options, checked=False):
    return {
        "q": question,
        "opts": options,
        "els": [MagicMock() for _ in options],
        "checked": checked,
    }


def test_full_page_questionnaire_ignored_on_other_urls():
    driver = MagicMock()
    driver.current_url = "https://hh.ru/vacancy/123"

    assert answer_full_page_questionnaire(driver) is False
    driver.find_elements.assert_not_called()


def test_full_page_questionnaire_picks_radio_chosen_by_ai_and_submits():
    group = _radio_group(
        "С какими бэкенд-технологиями у вас есть коммерческий опыт?",
        ["PHP", "Golang", "Python", "Не работал ранее с данными языками"],
    )
    submit = _submit()
    driver = _questionnaire_driver(radios=[group], buttons=[submit])
    ai_answer_fn = MagicMock(return_value="Python")

    assert answer_full_page_questionnaire(driver, ai_answer_fn) is True

    assert "Python" in ai_answer_fn.call_args[0][0]
    driver.execute_script.assert_any_call(
        "arguments[0].click();", group["els"][2]
    )
    driver.execute_script.assert_any_call("arguments[0].click();", submit)


def test_full_page_questionnaire_leaves_radio_empty_when_ai_misses():
    group = _radio_group("Опыт?", ["Менее 3 лет", "3–5 лет"])
    driver = _questionnaire_driver(radios=[group], buttons=[_submit()])

    answer_full_page_questionnaire(driver, MagicMock(return_value="Много"))

    for radio in group["els"]:
        assert call("arguments[0].click();", radio) not in (
            driver.execute_script.call_args_list
        )


def test_full_page_questionnaire_replaces_draft_answer_with_ai_answer():
    field = MagicMock()
    field.get_attribute.return_value = "старое сопроводительное"
    question = "В каком городе вы проживаете на постоянной основе?"
    driver = _questionnaire_driver(
        texts=[{"q": question, "el": field}], buttons=[_submit()]
    )
    ai_answer_fn = MagicMock(return_value="Мурманск")

    assert answer_full_page_questionnaire(driver, ai_answer_fn) is True

    ai_answer_fn.assert_called_once_with(question)
    assert field.send_keys.call_args_list[-1] == call("Мурманск")
    assert call(Keys.BACKSPACE) in field.send_keys.call_args_list


def test_full_page_questionnaire_returns_false_without_submit_button():
    field = MagicMock()
    field.get_attribute.return_value = ""
    driver = _questionnaire_driver(texts=[{"q": "Город?", "el": field}])

    assert answer_full_page_questionnaire(driver) is False
    field.send_keys.assert_called_once()  # вопрос всё равно заполнили


def test_pick_option_tolerates_dashes_and_explanations():
    options = ["Менее 3 лет", "3–5 лет", "5–8 лет"]
    assert _pick_option("3-5 лет", options) == 1
    assert _pick_option("5–8 лет, в основном Python", options) == 2
    assert _pick_option("не знаю", options) is None
    assert _pick_option("2", options) == 1
    assert _pick_option("3.", options) == 2
    assert _pick_option("У меня 2 года опыта", options) is None
    assert _pick_option("7", options) is None


def test_multiple_choice_yes_is_a_word_not_a_substring():
    options = [
        _make_option("Не работал ранее с данными языками"),
        _make_option("Python"),
        _make_option("Golang"),
    ]
    block = _make_block(options=options)
    driver = MagicMock()
    driver.find_elements.return_value = [block]

    answer_vacancy_test_if_present(driver)

    options[1].click.assert_called_once()  # середина, а не «да» в «данными»
    options[0].click.assert_not_called()
