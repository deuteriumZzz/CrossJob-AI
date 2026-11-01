"""Каждый вызов ИИ (со всеми фолбэками) ограничен общим сроком — 1.11 один
вызов висел 25+ минут, и ход Wellfound держал все площадки."""

import time

import pytest
from langchain_core.runnables import RunnableLambda

from src.job_sources import llm_provider


def _chain(fn):
    return llm_provider._ChatModelWithFallbacks(
        runnable=RunnableLambda(fn), fallbacks=[RunnableLambda(fn)]
    )


def test_hung_call_times_out(monkeypatch):
    monkeypatch.setattr(llm_provider, "LLM_CALL_DEADLINE_SECONDS", 0.2)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        _chain(lambda _x: time.sleep(5)).invoke("q")
    assert time.monotonic() - started < 2


def test_normal_call_and_errors_pass_through():
    assert _chain(lambda x: x + "!").invoke("ok") == "ok!"

    def boom(_x):
        raise ValueError("bad")

    with pytest.raises(ValueError):
        _chain(boom).invoke("q")
