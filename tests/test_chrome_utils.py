import os
import subprocess
import tempfile
import time
from pathlib import Path

from src.utils.chrome_utils import clear_profile_cache, clear_stale_chrome_lock


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


def test_clear_profile_cache_removes_cache_dirs_but_keeps_session():
    with tempfile.TemporaryDirectory() as tmp:
        profile_dir = Path(tmp)
        for rel in ("Default/Cache", "Default/Code Cache", "Default/GPUCache"):
            d = profile_dir / rel
            d.mkdir(parents=True)
            (d / "data_0").write_bytes(b"x" * 1024)
        (profile_dir / "Default").mkdir(exist_ok=True)
        (profile_dir / "Default" / "Cookies").write_bytes(b"session-data")

        clear_profile_cache(profile_dir)

        for rel in ("Default/Cache", "Default/Code Cache", "Default/GPUCache"):
            assert not (profile_dir / rel).exists()
        cookies = profile_dir / "Default" / "Cookies"
        assert cookies.read_bytes() == b"session-data"


def test_clear_profile_cache_missing_dirs_is_a_noop():
    with tempfile.TemporaryDirectory() as tmp:
        clear_profile_cache(Path(tmp))  # must not raise


def test_force_kills_live_pid_and_removes_lock():
    with tempfile.TemporaryDirectory() as tmp:
        profile_dir = Path(tmp)
        proc = subprocess.Popen(["sleep", "30"])
        try:
            (profile_dir / "SingletonLock").symlink_to(f"host-{proc.pid}")

            clear_stale_chrome_lock(profile_dir, force=True)

            for _ in range(50):
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            assert proc.poll() is not None, "process was not killed"
            assert not (profile_dir / "SingletonLock").exists()
        finally:
            proc.wait(timeout=5)
