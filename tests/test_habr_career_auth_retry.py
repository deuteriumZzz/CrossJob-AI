from unittest.mock import MagicMock, patch

from src.job_sources.habr_career.auth import HabrCareerSession


def _driver_logged_in():
    driver = MagicMock()
    driver.find_elements.return_value = [MagicMock()]
    return driver


def test_ensure_logged_in_retries_once_then_succeeds():
    driver = _driver_logged_in()
    driver.get.side_effect = [
        Exception("Timed out receiving message from renderer"),
        None,
    ]
    with patch(
        "src.job_sources.habr_career.auth.init_browser",
        return_value=driver,
    ), patch("src.job_sources.habr_career.auth.time.sleep"):
        HabrCareerSession(profile_dir=None).ensure_logged_in({})
    assert driver.get.call_count == 2
    driver.quit.assert_called_once()


def test_ensure_logged_in_raises_after_second_failure():
    driver = _driver_logged_in()
    driver.get.side_effect = [Exception("first"), Exception("second")]
    with patch(
        "src.job_sources.habr_career.auth.init_browser",
        return_value=driver,
    ), patch("src.job_sources.habr_career.auth.time.sleep"):
        try:
            HabrCareerSession(profile_dir=None).ensure_logged_in({})
            assert False, "expected the second failure to propagate"
        except Exception as e:
            assert "second" in str(e)
    driver.quit.assert_called_once()


if __name__ == "__main__":
    test_ensure_logged_in_retries_once_then_succeeds()
    test_ensure_logged_in_raises_after_second_failure()
    print("All tests passed.")
