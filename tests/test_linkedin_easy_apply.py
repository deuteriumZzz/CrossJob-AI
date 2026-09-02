from unittest.mock import MagicMock

from src.job_sources.linkedin.easy_apply import (
    _closest_option,
    _field_max_length,
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


if __name__ == "__main__":
    test_closest_option_exact_match_case_insensitive()
    test_closest_option_partial_match()
    test_closest_option_falls_back_to_first_option()
    test_field_max_length_reads_maxlength_attribute()
    test_field_max_length_none_when_attribute_missing()
    test_field_max_length_none_when_attribute_not_numeric()
    print("All tests passed.")
