from unittest.mock import MagicMock

from src.job_sources.avito.search import _apply_click_filters


def test_apply_click_filters_opens_combobox_and_clicks_custom_option():
    driver = MagicMock()
    combo_el = MagicMock()
    option_el = MagicMock()
    option_el.is_displayed.return_value = True

    def find_elements(by, selector):
        if selector == '[data-marker="params[827]"]':
            return [combo_el]
        if selector == '[data-marker="params[827]/custom-option(11906)"]':
            return [option_el]
        return []

    driver.find_elements.side_effect = find_elements

    applied = _apply_click_filters(driver, "over_3_years", "")

    combo_el.click.assert_called_once()
    option_el.click.assert_called_once()
    assert applied is True


def test_apply_click_filters_skips_hidden_option():
    driver = MagicMock()
    combo_el = MagicMock()
    hidden_option = MagicMock()
    hidden_option.is_displayed.return_value = False

    def find_elements(by, selector):
        if selector == '[data-marker="params[827]"]':
            return [combo_el]
        if selector == '[data-marker="params[827]/custom-option(11906)"]':
            return [hidden_option]
        return []

    driver.find_elements.side_effect = find_elements

    applied = _apply_click_filters(driver, "over_3_years", "")

    hidden_option.click.assert_not_called()
    assert applied is False


def test_apply_click_filters_clicks_employment_checkbox():
    driver = MagicMock()
    checkbox_el = MagicMock()

    def find_elements(by, selector):
        if "22066866" in selector:
            return [checkbox_el]
        return []

    driver.find_elements.side_effect = find_elements

    applied = _apply_click_filters(driver, "", "part_time")

    checkbox_el.click.assert_called_once()
    assert applied is True


def test_apply_click_filters_noop_without_matches():
    driver = MagicMock()
    driver.find_elements.return_value = []
    assert _apply_click_filters(driver, "", "") is False


def test_apply_click_filters_ignores_unknown_values():
    driver = MagicMock()
    driver.find_elements.return_value = []
    assert _apply_click_filters(driver, "not_a_real_level", "made_up") is False
