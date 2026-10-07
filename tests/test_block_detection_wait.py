from unittest.mock import MagicMock, patch

import pytest

from src.job_sources import block_detection
from src.job_sources.block_detection import (
    PlatformBlockedError,
    raise_if_blocked_after_wait,
)


def test_cloudflare_interstitial_that_clears_is_not_a_block():
    texts = iter(["Ray ID: abc", "Ray ID: abc", "Python Developer jobs"])
    with patch.object(
        block_detection, "visible_text", side_effect=lambda d: next(texts)
    ), patch.object(block_detection.time, "sleep"):
        raise_if_blocked_after_wait(MagicMock())  # не бросает


def test_persistent_block_still_raises_after_wait():
    with patch.object(
        block_detection, "visible_text", return_value="Ray ID: abc"
    ), patch.object(block_detection.time, "sleep"), patch.object(
        block_detection.time, "monotonic", side_effect=[0, 10, 100]
    ):
        with pytest.raises(PlatformBlockedError):
            raise_if_blocked_after_wait(MagicMock(), seconds=45)
