"""Отмена зависших откликов и блокировка работодателя на hh.ru
(browser_negotiations.py, browser_replies.block_employer) — оба
деструктивны на реальном аккаунте, поэтому только opt-in/ручные
действия, см. cleanup_headhunter_negotiations/block_headhunter_employer
в main.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.job_sources.headhunter.browser_negotiations import (
    list_withdrawable_negotiations,
    withdraw_negotiation,
)
from src.job_sources.headhunter.browser_replies import block_employer


def _make_item(
    vacancy_id: str,
    text: str = "",
    days_old: int | None = None,
    has_cancel_button: bool = True,
) -> MagicMock:
    item = MagicMock()
    item.text = text
    link = MagicMock()
    link.get_attribute.return_value = f"https://hh.ru/vacancy/{vacancy_id}"

    time_el = MagicMock()
    if days_old is not None:
        dt = datetime.now(timezone.utc) - timedelta(days=days_old)
        time_el.get_attribute.return_value = dt.isoformat()

    cancel_button = MagicMock()
    cancel_button.is_displayed.return_value = has_cancel_button

    def find_elements(by, selector):
        if "vacancy" in selector:
            return [link]
        if "time" in selector:
            return [time_el] if days_old is not None else []
        if "cancel" in selector or "collapse" in selector:
            return [cancel_button] if has_cancel_button else []
        return []

    item.find_elements.side_effect = find_elements
    item._cancel_button = cancel_button
    return item


def test_list_withdrawable_selects_discard_status_by_default():
    discard_item = _make_item("1", text="Отклик отправлен. Отказ.")
    active_item = _make_item("2", text="Отклик просмотрен")
    driver = MagicMock()
    driver.find_elements.return_value = [discard_item, active_item]

    with patch("src.job_sources.headhunter.browser_negotiations.time.sleep"):
        entries = list_withdrawable_negotiations(driver)

    assert len(entries) == 1
    assert entries[0]["vacancy_id"] == "1"
    assert entries[0]["is_discard"] is True


def test_list_withdrawable_selects_by_age_when_older_than_given():
    old_item = _make_item("1", days_old=45)
    recent_item = _make_item("2", days_old=5)
    driver = MagicMock()
    driver.find_elements.return_value = [old_item, recent_item]

    with patch("src.job_sources.headhunter.browser_negotiations.time.sleep"):
        entries = list_withdrawable_negotiations(driver, older_than_days=30)

    assert len(entries) == 1
    assert entries[0]["vacancy_id"] == "1"


def test_withdraw_negotiation_returns_false_when_button_missing():
    entry = {"element": _make_item("1", has_cancel_button=False)}
    driver = MagicMock()
    assert withdraw_negotiation(driver, entry) is False


def test_withdraw_negotiation_clicks_cancel_button():
    item = _make_item("1", has_cancel_button=True)
    entry = {"element": item, "vacancy_url": "https://hh.ru/vacancy/1"}
    driver = MagicMock()
    driver.find_elements.return_value = []  # no confirm popup

    with patch("src.job_sources.headhunter.browser_negotiations.time.sleep"):
        assert withdraw_negotiation(driver, entry) is True
    item._cancel_button.click.assert_called_once()


def test_block_employer_returns_false_when_button_missing():
    driver = MagicMock()
    driver.find_elements.return_value = []
    with patch("src.job_sources.headhunter.browser_replies.time.sleep"):
        assert block_employer(driver, "https://hh.ru/employer/1") is False


def test_block_employer_clicks_block_button():
    button = MagicMock()
    button.is_displayed.return_value = True
    driver = MagicMock()

    def find_elements(by, selector):
        return [button] if "block" in selector else []

    driver.find_elements.side_effect = find_elements

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"):
        assert block_employer(driver, "https://hh.ru/employer/1") is True
    button.click.assert_called_once()
