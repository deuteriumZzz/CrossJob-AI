"""Execute the Telegram post UI regression tests against the real JS."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_telegram_posts_ui_behavior():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to execute the UI regression tests")
    result = subprocess.run(
        [
            node,
            "--test",
            str(Path(__file__).with_name("telegram_posts_ui.test.cjs")),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_telegram_messenger_ui_behavior():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to execute the UI regression tests")
    result = subprocess.run(
        [
            node,
            "--test",
            str(
                Path(__file__).with_name("telegram_messenger_layout.test.cjs")
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
