from src.job_sources.wellfound.auth import _login_finished


def test_login_page_and_checks_are_not_finished():
    assert not _login_finished("https://wellfound.com/login")
    assert not _login_finished("https://wellfound.com/login?redirect=/jobs")
    assert not _login_finished(
        "https://wellfound.com/cdn-cgi/challenge-platform/x"
    )
    assert not _login_finished("https://wellfound.com/signup")
    assert not _login_finished("https://accounts.google.com/o/oauth2/auth")


def test_logged_in_pages_are_finished():
    assert _login_finished("https://wellfound.com/jobs")
    assert _login_finished("https://wellfound.com/role/python-developer")
