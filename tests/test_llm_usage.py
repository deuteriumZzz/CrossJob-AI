import tempfile
import uuid
from pathlib import Path

from langchain_core.outputs import LLMResult

from src.job_sources import llm_usage


def test_record_usage_accumulates_per_day_and_model():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        llm_usage.record_usage(out, "openai", "gpt-4o-mini", 100, 50)
        llm_usage.record_usage(out, "openai", "gpt-4o-mini", 200, 100)
        llm_usage.record_usage(out, "groq", "openai/gpt-oss-120b", 10, 5)

        summary = llm_usage.summarize_usage(out)
        assert summary["today_tokens"] == 465
        assert summary["total_tokens"] == 465


def test_record_usage_ignores_zero_token_calls():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        llm_usage.record_usage(out, "openai", "gpt-4o-mini", 0, 0)
        assert not (out / ".llm_usage.json").exists()


def test_estimate_cost_usd_known_openai_model():
    cost = llm_usage.estimate_cost_usd(
        "openai", "gpt-4o-mini", 1_000_000, 1_000_000
    )
    assert cost == 0.15 + 0.60


def test_estimate_cost_usd_unknown_provider_or_model_returns_none():
    assert llm_usage.estimate_cost_usd("groq", "llama-3.3", 100, 100) is None
    assert llm_usage.estimate_cost_usd("openai", "unknown-model", 1, 1) is None


def test_summarize_usage_flags_partial_when_mixing_known_and_unknown():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        llm_usage.record_usage(out, "openai", "gpt-4o-mini", 1000, 1000)
        llm_usage.record_usage(out, "groq", "llama-3.3", 1000, 1000)

        summary = llm_usage.summarize_usage(out)
        assert summary["total_cost_usd"] is not None
        assert summary["partial"] is True


def test_summarize_usage_empty_when_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        summary = llm_usage.summarize_usage(Path(tmp))
        assert summary["today_tokens"] == 0
        assert summary["total_cost_usd"] is None
        assert summary["partial"] is False


def test_usage_callback_records_tokens_from_llm_result():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        callback = llm_usage.UsageCallback(out, "openai", "gpt-4o-mini")
        result = LLMResult(
            generations=[],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 42,
                    "completion_tokens": 8,
                }
            },
        )
        callback.on_llm_end(result, run_id=uuid.uuid4())

        summary = llm_usage.summarize_usage(out)
        assert summary["today_tokens"] == 50


def test_output_folder_getter_setter_roundtrip():
    llm_usage.set_output_folder(Path("/tmp/example"))
    try:
        assert llm_usage.get_output_folder() == Path("/tmp/example")
    finally:
        llm_usage.set_output_folder(None)
    assert llm_usage.get_output_folder() is None
