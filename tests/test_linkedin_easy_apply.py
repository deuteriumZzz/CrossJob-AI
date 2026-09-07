from unittest.mock import MagicMock

from src.job_sources.linkedin.easy_apply import (
    _answer_uncovered_required_fields,
    _closest_option,
    _field_max_length,
    _label_text_for,
)


def test_closest_option_exact_match_case_insensitive():
    assert _closest_option("Yes", ["Yes", "No"]) == "Yes"
    assert _closest_option("yes", ["Yes", "No"]) == "Yes"


def test_closest_option_partial_match():
    assert (
        _closest_option("3-5 years", ["0-2 years", "3-5 years", "6+ years"])
        == "3-5 years"
    )


def test_closest_option_falls_back_to_first_option():
    assert (
        _closest_option(
            "something completely unrelated", ["Option A", "Option B"]
        )
        == "Option A"
    )


def test_field_max_length_reads_maxlength_attribute():
    field = MagicMock()
    field.get_attribute.return_value = "20"
    assert _field_max_length(field) == 20


def test_field_max_length_none_when_attribute_missing():
    field = MagicMock()
    field.get_attribute.return_value = None
    assert _field_max_length(field) is None


def test_field_max_length_none_when_attribute_not_numeric():
    field = MagicMock()
    field.get_attribute.return_value = ""
    assert _field_max_length(field) is None


def test_label_text_for_uses_label_element():
    driver = MagicMock()
    field = MagicMock()
    field.get_attribute.side_effect = lambda name: {"id": "loc"}.get(name)
    label = MagicMock()
    label.text = "Location (city)*"
    driver.find_elements.return_value = [label]
    assert _label_text_for(driver, field) == "Location (city)"


def test_label_text_for_falls_back_to_placeholder():
    driver = MagicMock()
    field = MagicMock()
    field.get_attribute.side_effect = lambda name: {
        "placeholder": "Enter city or location"
    }.get(name)
    driver.find_elements.return_value = []
    assert _label_text_for(driver, field) == "Enter city or location"


def test_answer_uncovered_required_fields_fills_empty_required_field():
    driver = MagicMock()
    form = MagicMock()
    driver.find_element.return_value = form
    driver.find_elements.return_value = []  # no <label for=...> found

    field = MagicMock()
    field.is_displayed.return_value = True
    field.get_attribute.side_effect = lambda name: {
        "value": "",
        "required": "",
        "placeholder": "Enter city or location",
    }.get(name)
    form.find_elements.return_value = [field]

    answerer = MagicMock()
    answerer.answer.return_value = "Moscow"

    _answer_uncovered_required_fields(driver, answerer)

    answerer.answer.assert_called_once()
    field.send_keys.assert_called_once_with("Moscow")


def test_answer_uncovered_required_fields_skips_filled_and_optional():
    driver = MagicMock()
    form = MagicMock()
    driver.find_element.return_value = form

    filled_field = MagicMock()
    filled_field.is_displayed.return_value = True
    filled_field.get_attribute.side_effect = lambda name: {
        "value": "Moscow"
    }.get(name)

    optional_field = MagicMock()
    optional_field.is_displayed.return_value = True
    optional_field.get_attribute.side_effect = lambda name: {"value": ""}.get(
        name
    )

    form.find_elements.return_value = [filled_field, optional_field]

    answerer = MagicMock()
    _answer_uncovered_required_fields(driver, answerer)

    answerer.answer.assert_not_called()
    filled_field.send_keys.assert_not_called()
    optional_field.send_keys.assert_not_called()


if __name__ == "__main__":
    test_closest_option_exact_match_case_insensitive()
    test_closest_option_partial_match()
    test_closest_option_falls_back_to_first_option()
    test_field_max_length_reads_maxlength_attribute()
    test_field_max_length_none_when_attribute_missing()
    test_field_max_length_none_when_attribute_not_numeric()
    test_label_text_for_uses_label_element()
    test_label_text_for_falls_back_to_placeholder()
    test_answer_uncovered_required_fields_fills_empty_required_field()
    test_answer_uncovered_required_fields_skips_filled_and_optional()
    print("All tests passed.")
