"""При сбое ИИ оценка не должна превращаться в 10/10 — иначе отклики уходят
на любые вакансии (живьём 2026-10-08)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.job import Job
from src.job_sources import job_fit
from src.job_sources.applied_log import AppliedLog
from src.job_sources.job_fit import (
    SCORING_UNAVAILABLE_GAP,
    FitAssessment,
    score_job_fit,
)


def _score_with(chain_invoke):
    chain = MagicMock()
    chain.invoke.side_effect = chain_invoke
    prompt = MagicMock()
    prompt.__or__.return_value = chain
    with patch.object(job_fit, "extract_text", return_value="resume"), patch(
        "src.job_sources.job_fit.get_chat_llm"
    ), patch.object(job_fit, "_SCORE_PROMPT", prompt), patch.object(
        job_fit, "SCORE_RETRY_PAUSES", (0.0, 0.0)
    ), patch.object(job_fit, "_ai_down_until", 0.0):
        return score_job_fit(Path("r.pdf"), Job(role="Dev"), "k"), chain


def test_ai_down_skips_next_vacancies_without_calling_ai():
    """Himalayas, 2026-11-01: 244 вакансии × 3 попытки по 180 с занимали
    демон 3+ часа. После полного отказа следующие оценки — сразу."""
    chain = MagicMock()
    chain.invoke.side_effect = RuntimeError("ИИ не ответил за 180 с")
    prompt = MagicMock()
    prompt.__or__.return_value = chain
    with patch.object(job_fit, "extract_text", return_value="resume"), patch(
        "src.job_sources.job_fit.get_chat_llm"
    ), patch.object(job_fit, "_SCORE_PROMPT", prompt), patch.object(
        job_fit, "SCORE_RETRY_PAUSES", (0.0, 0.0)
    ), patch.object(job_fit, "_ai_down_until", 0.0):
        score_job_fit(Path("r.pdf"), Job(role="Dev"), "k")
        assert chain.invoke.call_count == 3
        fit = score_job_fit(Path("r.pdf"), Job(role="Dev 2"), "k")
        assert chain.invoke.call_count == 3  # ИИ больше не дёргали
        assert fit.gaps == [SCORING_UNAVAILABLE_GAP]
        job_fit._ai_down_until = 0.0  # кулдаун прошёл
        chain.invoke.side_effect = None
        chain.invoke.return_value = FitAssessment(score=7, gaps=[])
        assert score_job_fit(Path("r.pdf"), Job(role="Dev 3"), "k").score == 7


def test_failure_after_retries_is_score_one_with_marker():
    fit, chain = _score_with(RuntimeError("429 quota"))
    assert fit.score == 1 and fit.gaps == [SCORING_UNAVAILABLE_GAP]
    assert chain.invoke.call_count == 3


def test_retry_recovers_after_a_transient_error():
    answers = iter([RuntimeError("429"), FitAssessment(score=8, gaps=[])])

    def invoke(_):
        value = next(answers)
        if isinstance(value, Exception):
            raise value
        return value

    fit, _ = _score_with(invoke)
    assert fit.score == 8


def test_unavailable_entry_is_retried_and_replaced(tmp_path):
    log = AppliedLog(tmp_path / "applied_log.json")
    job = Job(role="Dev", company="Acme", source="x", external_id="1")
    log.record(job, "", "", "skipped_low_fit", 1, [SCORING_UNAVAILABLE_GAP])
    assert "1" not in log.seen_ids("x")
    assert not log.already_applied(job)
    log.record(job, "", "", "skipped_low_fit", 2, ["не хватает опыта"])
    entries = [e for e in log._data["applications"] if e["source"] == "x"]
    assert len(entries) == 1 and entries[0]["score"] == 2
    assert "1" in log.seen_ids("x")
