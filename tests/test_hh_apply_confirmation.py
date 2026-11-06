"""HH-отклик засчитывается, только если страница вакансии после него
показывает «Чат» вместо «Откликнуться» (2026-11-06: Битрикс24 после
анкеты записан как applied, а на HH отклика не было)."""

import itertools
from unittest.mock import MagicMock, patch

import pytest

from main import _is_hh_manual_captcha
from src.job_sources.block_detection import PlatformBlockedError, raise_if_blocked

from src.job_sources.headhunter.browser_client import (
    HeadHunterBrowserClient,
    _RESPONDED_SELECTOR,
)

URL = "https://hh.ru/vacancy/139161999"
RESPOND_BUTTON = '[data-qa="vacancy-response-link-top"]'


def _apply(responded, expected_gets) -> bool:
    """responded: "in_place" — «Чат» появился сам после клика, "reload" —
    только после перезагрузки вакансии, None — HH отклик не принял."""
    gets, clicked = [], []
    driver = MagicMock()
    driver.current_url = URL
    driver.get.side_effect = gets.append
    button = MagicMock()
    button.click.side_effect = lambda: clicked.append(True)

    def find_elements(_by, selector):
        shows_chat = (responded == "in_place" and clicked) or (
            responded == "reload" and len(gets) > 1
        )
        if selector == _RESPONDED_SELECTOR:
            return [MagicMock()] if shows_chat else []
        if selector == RESPOND_BUTTON and not shows_chat:
            return [button]
        return []

    driver.find_elements.side_effect = find_elements
    fake_time = MagicMock()
    fake_time.monotonic.side_effect = itertools.count(0, 100)
    with patch(
        "src.job_sources.headhunter.browser_client.init_browser",
        return_value=driver,
    ), patch(
        "src.job_sources.headhunter.browser_client.raise_if_page_blocked"
    ), patch("src.job_sources.headhunter.browser_client.time", fake_time):
        with HeadHunterBrowserClient("profile") as client:
            applied, _ = client.apply(URL, lambda: "letter")
    assert clicked
    assert gets == [URL] * expected_gets
    return applied


def test_click_without_hh_confirmation_is_not_applied():
    # Ждём на месте, перезагружаем вакансию — «Чат» так и не появился.
    assert _apply(None, expected_gets=2) is False


def test_response_confirmed_in_place_needs_no_reload():
    # Модалка/быстрый отклик: HH обновил страницу сам, отправку не рвём.
    assert _apply("in_place", expected_gets=1) is True


def test_response_confirmed_after_reload():
    assert _apply("reload", expected_gets=2) is True


def test_captcha_modal_after_click_is_raised_before_reload():
    """Вживую 2026-11-06 (Finstar): после «Respond» HH показал капчу
    модалкой на самой вакансии, без редиректа — бот считал это быстрым
    откликом. Ошибка должна уйти в ожидание капчи, а не в dry-run."""
    gets = []
    driver = MagicMock()
    driver.current_url = URL
    driver.get.side_effect = gets.append
    driver.find_elements.side_effect = (
        lambda _by, selector: [MagicMock()] if selector == RESPOND_BUTTON else []
    )
    fake_time = MagicMock()
    fake_time.monotonic.side_effect = itertools.count(0, 100)
    modal = PlatformBlockedError(
        "Blocked (detected 'enter the text from the picture' in response body)"
    )
    with patch(
        "src.job_sources.headhunter.browser_client.init_browser",
        return_value=driver,
    ), patch(
        "src.job_sources.headhunter.browser_client.raise_if_page_blocked",
        side_effect=[None, modal],  # до клика чисто, после — модалка
    ), patch("src.job_sources.headhunter.browser_client.time", fake_time):
        with HeadHunterBrowserClient("profile") as client:
            with pytest.raises(PlatformBlockedError):
                client.apply(URL, lambda: "letter")
    assert gets == [URL]  # модалку не потеряли перезагрузкой
    assert _is_hh_manual_captcha(modal)


def test_captcha_modal_text_blocks_even_on_long_vacancy_page():
    page = "Описание вакансии. " * 400 + (
        "Complete the CAPTCHA To confirm you are not a robot, "
        "enter the text from the picture"
    )
    with pytest.raises(PlatformBlockedError):
        raise_if_blocked(page, ignore_weak_keywords=True)



def test_is_shown_sees_modal_stuck_in_fade_in():
    """Свёрнутое окно: модалка отклика застряла с opacity 0 у предка —
    is_displayed() False, но элемент на экране (6.11, АСКОН)."""
    from src.utils.chrome_utils import is_shown

    stuck = MagicMock()
    stuck.is_displayed.return_value = False
    stuck.rect = {"height": 80}
    stuck.value_of_css_property.return_value = "visible"
    hidden = MagicMock()
    hidden.is_displayed.return_value = False
    hidden.rect = {"height": 0}
    assert is_shown(stuck) is True
    assert is_shown(hidden) is False
