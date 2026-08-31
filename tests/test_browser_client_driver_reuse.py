"""Один Chrome-процесс должен переиспользоваться на весь прогон площадки
(поиск + карточки вакансий + отклики), если клиент используется как
контекстный менеджер — вместо открытия/закрытия браузера на каждый
вызов, как было раньше (см. HeadHunterBrowserClient/GetMatchClient)."""

from unittest.mock import MagicMock, patch

from src.job_sources.geekjob.client import GeekjobClient
from src.job_sources.getmatch.client import GetMatchClient
from src.job_sources.headhunter.browser_client import (
    HeadHunterBrowserClient,
    _wait_for_any,
)


def test_headhunter_client_reuses_one_driver_inside_with_block():
    with patch(
        "src.job_sources.headhunter.browser_client.init_browser"
    ) as mock_init, patch(
        "src.job_sources.headhunter.browser_client.raise_if_blocked"
    ), patch(
        "src.job_sources.headhunter.browser_client.visible_text",
        return_value="",
    ), patch(
        "src.job_sources.headhunter.browser_client.time.sleep"
    ):
        mock_init.return_value.find_elements.return_value = []

        with HeadHunterBrowserClient("profile") as client:
            client.search_vacancies_html("python", True, page=0)
            client.get_vacancy_html("123")
            client.apply("https://hh.ru/vacancy/123", lambda: "letter")

        # Один driver на весь блок, а не по одному на каждый из 3 вызовов.
        assert mock_init.call_count == 1
        driver = mock_init.return_value
        # Закрывается ровно один раз, на выходе из `with`, а не после
        # каждого вызова.
        assert driver.quit.call_count == 1


def test_headhunter_client_without_with_opens_and_closes_per_call():
    with patch(
        "src.job_sources.headhunter.browser_client.init_browser"
    ) as mock_init, patch(
        "src.job_sources.headhunter.browser_client.raise_if_blocked"
    ), patch(
        "src.job_sources.headhunter.browser_client.visible_text",
        return_value="",
    ), patch(
        "src.job_sources.headhunter.browser_client.time.sleep"
    ):
        mock_init.return_value.find_elements.return_value = []

        client = HeadHunterBrowserClient("profile")
        client.get_vacancy_html("1")
        client.get_vacancy_html("2")

        # Обратная совместимость: без `with` — старое поведение,
        # свой driver на каждый вызов.
        assert mock_init.call_count == 2


def test_headhunter_client_reconnects_after_dead_session_mid_run():
    """Chrome может упасть посреди прогона (invalid session id) — на
    следующем вызове клиент должен тихо пересоздать driver тем же
    профилем, а не продолжать отдавать мёртвую сессию всем остальным
    вакансиям до конца прогона."""
    with patch(
        "src.job_sources.headhunter.browser_client.init_browser"
    ) as mock_init, patch(
        "src.job_sources.headhunter.browser_client.raise_if_blocked"
    ), patch(
        "src.job_sources.headhunter.browser_client.visible_text",
        return_value="",
    ), patch(
        "src.job_sources.headhunter.browser_client.time.sleep"
    ):
        dead_driver = MagicMock()
        type(dead_driver).current_url = property(
            lambda self: (_ for _ in ()).throw(
                Exception("invalid session id: session deleted")
            )
        )
        fresh_driver = MagicMock()
        fresh_driver.find_elements.return_value = []
        mock_init.side_effect = [dead_driver, fresh_driver]

        with HeadHunterBrowserClient("profile") as client:
            assert client._driver is dead_driver
            client.get_vacancy_html("123")

        assert mock_init.call_count == 2
        dead_driver.quit.assert_called_once()
        fresh_driver.quit.assert_called_once()


def test_getmatch_client_reuses_one_driver_inside_with_block():
    with patch(
        "src.job_sources.getmatch.client.init_browser"
    ) as mock_init, patch(
        "src.job_sources.getmatch.client.raise_if_blocked"
    ), patch(
        "src.job_sources.getmatch.client.visible_text", return_value=""
    ), patch(
        "src.job_sources.getmatch.client.time.sleep"
    ):
        mock_init.return_value.find_elements.return_value = []

        with GetMatchClient("profile") as client:
            client.search_vacancies_html("python")
            client.apply("https://getmatch.ru/vacancies/1", "letter")

        assert mock_init.call_count == 1
        assert mock_init.return_value.quit.call_count == 1


def test_geekjob_client_reuses_one_driver_inside_with_block():
    with patch(
        "src.job_sources.geekjob.client.init_browser"
    ) as mock_init, patch(
        "src.job_sources.geekjob.client.raise_if_blocked"
    ), patch(
        "src.job_sources.geekjob.client.visible_text", return_value=""
    ), patch(
        "src.job_sources.geekjob.client.time.sleep"
    ):
        with GeekjobClient("profile") as client:
            client.search_vacancies_html("python", page=1)
            client.get_vacancy_html("123")

        assert mock_init.call_count == 1
        assert mock_init.return_value.quit.call_count == 1


def test_geekjob_client_without_with_opens_and_closes_per_call():
    with patch(
        "src.job_sources.geekjob.client.init_browser"
    ) as mock_init, patch(
        "src.job_sources.geekjob.client.raise_if_blocked"
    ), patch(
        "src.job_sources.geekjob.client.visible_text", return_value=""
    ), patch(
        "src.job_sources.geekjob.client.time.sleep"
    ):
        client = GeekjobClient("profile")
        client.get_vacancy_html("1")
        client.get_vacancy_html("2")

        assert mock_init.call_count == 2


def test_geekjob_search_uses_qs_query_param_not_q():
    # Настоящий параметр поиска geekjob.ru — qs (подтверждено формой
    # поиска на живой странице), не q — раньше здесь был q, из-за чего
    # площадка молча игнорировала запрос и всегда отдавала один и тот
    # же дефолтный список вакансий.
    with patch(
        "src.job_sources.geekjob.client.init_browser"
    ) as mock_init, patch(
        "src.job_sources.geekjob.client.raise_if_blocked"
    ), patch(
        "src.job_sources.geekjob.client.visible_text", return_value=""
    ), patch(
        "src.job_sources.geekjob.client.time.sleep"
    ):
        client = GeekjobClient("profile")
        client.search_vacancies_html("python разработчик", page=1)

        driver = mock_init.return_value
        called_url = driver.get.call_args[0][0]
        assert "qs=" in called_url
        assert "q=python" not in called_url


def test_wait_for_any_returns_true_when_selector_appears():
    driver = MagicMock()
    driver.find_elements.return_value = [MagicMock(is_displayed=lambda: True)]
    with patch("src.job_sources.headhunter.browser_client.time.sleep"):
        assert (
            _wait_for_any(driver, ['[data-qa="x"]'], timeout=1, interval=0.1)
            is True
        )


def test_wait_for_any_returns_false_on_timeout_without_hanging():
    driver = MagicMock()
    driver.find_elements.return_value = []
    with patch("src.job_sources.headhunter.browser_client.time.sleep"):
        assert (
            _wait_for_any(
                driver, ['[data-qa="x"]'], timeout=0.05, interval=0.01
            )
            is False
        )


if __name__ == "__main__":
    test_headhunter_client_reuses_one_driver_inside_with_block()
    test_headhunter_client_without_with_opens_and_closes_per_call()
    test_getmatch_client_reuses_one_driver_inside_with_block()
    test_wait_for_any_returns_true_when_selector_appears()
    test_wait_for_any_returns_false_on_timeout_without_hanging()
    print("All tests passed.")
