import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.job_sources.block_detection import (
    PlatformBlockedError,
    is_still_blocked,
    mark_blocked,
    raise_if_blocked,
)


def test_raise_if_blocked_raises_on_429():
    response = SimpleNamespace(status_code=429, text="slow down")
    with pytest.raises(PlatformBlockedError):
        raise_if_blocked(response)


def test_raise_if_blocked_raises_on_captcha_keyword():
    response = SimpleNamespace(status_code=200, text="Please solve CAPTCHA")
    with pytest.raises(PlatformBlockedError):
        raise_if_blocked(response)


def test_raise_if_blocked_passes_normal_response():
    response = SimpleNamespace(status_code=200, text="<html>jobs here</html>")
    raise_if_blocked(response)


def test_raise_if_blocked_accepts_plain_string():
    with pytest.raises(PlatformBlockedError):
        raise_if_blocked("подозрительная активность обнаружена")
    raise_if_blocked("normal page content")


def test_mark_blocked_then_is_still_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        assert is_still_blocked(output_folder, "geekjob") is False

        mark_blocked(output_folder, "geekjob")

        assert is_still_blocked(output_folder, "geekjob") is True
        assert is_still_blocked(output_folder, "rabota_ru") is False


if __name__ == "__main__":
    test_raise_if_blocked_raises_on_429()
    test_raise_if_blocked_raises_on_captcha_keyword()
    test_raise_if_blocked_passes_normal_response()
    test_raise_if_blocked_accepts_plain_string()
    test_mark_blocked_then_is_still_blocked()
    print("All tests passed.")
