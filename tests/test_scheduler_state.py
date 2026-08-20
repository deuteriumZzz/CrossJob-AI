import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from src.scheduler_state import get_next_run, load_state, record_run_result


def test_get_next_run_is_none_before_first_run():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        assert get_next_run(output_folder, "headhunter") is None


def test_record_run_result_then_get_next_run():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        run_at = datetime(2026, 8, 20, 10, 0, 0)
        next_run = run_at + timedelta(hours=3)

        record_run_result(output_folder, "headhunter", "ok", next_run, run_at)

        assert get_next_run(output_folder, "headhunter") == next_run
        state = load_state(output_folder)
        assert state["headhunter"]["status"] == "ok"
        assert state["headhunter"]["last_error"] is None


def test_record_run_result_stores_error_and_keeps_other_sources():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        run_at = datetime(2026, 8, 20, 10, 0, 0)
        next_run = run_at + timedelta(hours=3)

        record_run_result(output_folder, "headhunter", "ok", next_run, run_at)
        record_run_result(
            output_folder,
            "superjob",
            "error",
            next_run,
            run_at,
            error="boom",
        )

        state = load_state(output_folder)
        assert state["headhunter"]["status"] == "ok"
        assert state["superjob"]["status"] == "error"
        assert state["superjob"]["last_error"] == "boom"


if __name__ == "__main__":
    test_get_next_run_is_none_before_first_run()
    test_record_run_result_then_get_next_run()
    test_record_run_result_stores_error_and_keeps_other_sources()
    print("All tests passed.")
