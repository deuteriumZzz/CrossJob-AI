"""Доказывает, что file-locking действительно защищает от гонки: до
фикса конкурентная запись в один и тот же JSON-файл из нескольких
потоков теряла часть записей (последний write побеждал предыдущие).
Каждый тест бьёт по одному и тому же файлу из N потоков одновременно
(threading.Barrier синхронизирует старт, чтобы максимизировать
пересечение) и проверяет, что ничего не потерялось."""

import tempfile
import threading
from datetime import datetime
from pathlib import Path

from src.job import Job
from src.job_sources.applied_log import AppliedLog
from src.job_sources.block_detection import is_still_blocked, mark_blocked
from src.job_sources.llm_usage import record_usage, summarize_usage
from src.scheduler_state import load_state, record_run_result

THREAD_COUNT = 12


def _run_concurrently(target, count: int = THREAD_COUNT) -> None:
    barrier = threading.Barrier(count)

    def _wrapped(i: int) -> None:
        barrier.wait(timeout=5)
        target(i)

    threads = [
        threading.Thread(target=_wrapped, args=(i,)) for i in range(count)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)


def test_applied_log_record_survives_concurrent_writers():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "applied_log.json"

        def _record(i: int) -> None:
            log = AppliedLog(path)
            job = Job(
                source="headhunter",
                external_id=str(i),
                company=f"Company {i}",
                role="QA",
                link="https://example.com",
                description="",
            )
            log.record(job, "letter", "resume-id", "dry_run", 8, [])

        _run_concurrently(_record)

        final = AppliedLog(path)
        assert len(final._data["applications"]) == THREAD_COUNT
        ids = {e["external_id"] for e in final._data["applications"]}
        assert ids == {str(i) for i in range(THREAD_COUNT)}


def test_scheduler_state_record_run_result_survives_concurrent_writers():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        now = datetime(2026, 8, 21, 12, 0, 0)

        def _record(i: int) -> None:
            record_run_result(output_folder, f"source-{i}", "ok", now, now)

        _run_concurrently(_record)

        state = load_state(output_folder)
        assert len(state) == THREAD_COUNT
        assert set(state.keys()) == {
            f"source-{i}" for i in range(THREAD_COUNT)
        }


def test_block_detection_mark_blocked_survives_concurrent_writers():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)

        def _mark(i: int) -> None:
            mark_blocked(output_folder, f"source-{i}")

        _run_concurrently(_mark)

        for i in range(THREAD_COUNT):
            assert is_still_blocked(output_folder, f"source-{i}")


def test_llm_usage_record_usage_survives_concurrent_writers():
    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)

        def _record(i: int) -> None:
            record_usage(output_folder, "openai", "gpt-4o-mini", 100, 50)

        _run_concurrently(_record)

        summary = summarize_usage(output_folder)
        assert summary["today_tokens"] == THREAD_COUNT * 150
