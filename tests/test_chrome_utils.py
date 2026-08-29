import os
import tempfile
from pathlib import Path

from src.utils.chrome_utils import clear_stale_chrome_lock


def test_no_lock_file_is_a_noop():
    with tempfile.TemporaryDirectory() as tmp:
        clear_stale_chrome_lock(Path(tmp))  # must not raise


def test_stale_lock_from_dead_pid_is_removed():
    with tempfile.TemporaryDirectory() as tmp:
        profile_dir = Path(tmp)
        dead_pid = 999999  # exceedingly unlikely to be a live PID
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            (profile_dir / name).symlink_to(f"host-{dead_pid}")

        clear_stale_chrome_lock(profile_dir)

        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            assert not (profile_dir / name).exists()


def test_live_lock_is_kept():
    with tempfile.TemporaryDirectory() as tmp:
        profile_dir = Path(tmp)
        live_pid = os.getpid()
        (profile_dir / "SingletonLock").symlink_to(f"host-{live_pid}")

        clear_stale_chrome_lock(profile_dir)

        assert (profile_dir / "SingletonLock").is_symlink()
