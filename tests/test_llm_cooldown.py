"""После отказа провайдера по лимиту вызовы на время идут к запасному."""

from types import SimpleNamespace

from src.job_sources import llm_usage
from src.job_sources.llm_provider import _prefer_available
from src.job_sources.llm_usage import (
    UsageCallback,
    mark_provider_rate_limited,
    provider_in_cooldown,
)


def _llm(provider):
    return SimpleNamespace(
        name=provider,
        callbacks=[SimpleNamespace(provider=provider)],
    )


def setup_function(_):
    llm_usage._cooldown_until.clear()


def test_available_primary_is_kept():
    primary, fallbacks = _prefer_available(
        _llm("gemini"), [_llm("groq"), _llm("mistral")]
    )
    assert primary.name == "gemini"
    assert [f.name for f in fallbacks] == ["groq", "mistral"]


def test_rate_limited_primary_goes_to_the_end():
    mark_provider_rate_limited("gemini")
    assert provider_in_cooldown("gemini")
    primary, fallbacks = _prefer_available(
        _llm("gemini"), [_llm("groq"), _llm("mistral")]
    )
    assert primary.name == "groq"
    assert [f.name for f in fallbacks] == ["mistral", "gemini"]


def test_all_cooling_down_keeps_original_order():
    for name in ("gemini", "groq"):
        mark_provider_rate_limited(name)
    primary, fallbacks = _prefer_available(_llm("gemini"), [_llm("groq")])
    assert primary.name == "gemini" and [f.name for f in fallbacks] == ["groq"]


def test_unknown_provider_or_no_fallbacks_is_untouched():
    mark_provider_rate_limited("gemini")
    primary, fallbacks = _prefer_available(_llm("gemini"), [])
    assert primary.name == "gemini" and fallbacks == []
    bare = SimpleNamespace(name="x")
    primary, fallbacks = _prefer_available(bare, [_llm("groq")])
    assert primary is bare


def test_rate_limit_error_starts_cooldown_other_errors_do_not(tmp_path):
    callback = UsageCallback(tmp_path, "gemini", "m")
    callback.on_llm_error(RuntimeError("500 server error"), run_id=None)
    assert not provider_in_cooldown("gemini")
    callback.on_llm_error(
        RuntimeError("429 RESOURCE_EXHAUSTED quota"), run_id=None
    )
    assert provider_in_cooldown("gemini")
