from pathlib import Path

import pytest

from src.job_sources import llm_usage
from src.job_sources.llm_provider import (
    PROVIDER_MODELS,
    get_active_provider,
    get_chat_llm,
    set_provider_override,
)


@pytest.fixture(autouse=True)
def _reset_provider_override():
    yield
    set_provider_override(None)


def test_default_provider_is_openai():
    llm = get_chat_llm("sk-test")
    assert type(llm).__name__ == "ChatOpenAI"
    assert llm.model_name == "gpt-4o-mini"


def test_no_usage_callback_when_output_folder_unset():
    llm_usage.set_output_folder(None)
    llm = get_chat_llm("sk-test")
    assert not llm.callbacks


def test_usage_callback_attached_when_output_folder_set():
    llm_usage.set_output_folder(Path("/tmp/example"))
    try:
        llm = get_chat_llm("sk-test", model="gpt-4o")
        assert len(llm.callbacks) == 1
        callback = llm.callbacks[0]
        assert callback.provider == "openai"
        assert callback.model == "gpt-4o"
        assert callback.output_folder == Path("/tmp/example")
    finally:
        llm_usage.set_output_folder(None)


def test_openai_provider_uses_given_model():
    llm = get_chat_llm("sk-test", provider="openai", model="gpt-4o")
    assert llm.model_name == "gpt-4o"


def test_deepseek_provider_uses_deepseek_base_url():
    llm = get_chat_llm("sk-test", provider="deepseek")
    assert llm.model_name == "deepseek-chat"
    assert llm.openai_api_base == "https://api.deepseek.com"


def test_groq_provider_requires_langchain_groq():
    pytest.importorskip("langchain_groq")
    llm = get_chat_llm("gsk-test", provider="groq")
    assert type(llm).__name__ == "ChatGroq"


def test_gemini_provider_requires_langchain_google_genai():
    pytest.importorskip("langchain_google_genai")
    llm = get_chat_llm("gemini-test", provider="gemini")
    assert type(llm).__name__ == "ChatGoogleGenerativeAI"


def test_ollama_provider_requires_langchain_ollama():
    pytest.importorskip("langchain_ollama")
    llm = get_chat_llm(
        "", provider="ollama", base_url="http://localhost:11434"
    )
    assert type(llm).__name__ == "ChatOllama"


def test_provider_override_switches_default_provider():
    set_provider_override("groq")
    pytest.importorskip("langchain_groq")
    llm = get_chat_llm("gsk-test")
    assert type(llm).__name__ == "ChatGroq"


def test_provider_override_does_not_leak_config_model():
    """Переключение провайдера без явной модели не должно протекать
    моделью другого провайдера (config.LLM_MODEL == 'gpt-4o-mini')."""
    set_provider_override("groq")
    pytest.importorskip("langchain_groq")
    llm = get_chat_llm("gsk-test")
    assert llm.model_name != "gpt-4o-mini"
    assert llm.model_name == "openai/gpt-oss-120b"


def test_provider_override_with_explicit_model():
    set_provider_override("groq", "custom-model")
    pytest.importorskip("langchain_groq")
    llm = get_chat_llm("gsk-test")
    assert llm.model_name == "custom-model"


def test_explicit_call_argument_wins_over_override():
    set_provider_override("groq")
    llm = get_chat_llm("sk-test", provider="openai", model="gpt-4o")
    assert type(llm).__name__ == "ChatOpenAI"
    assert llm.model_name == "gpt-4o"


def test_provider_override_reset_returns_to_config_default():
    set_provider_override("groq")
    set_provider_override(None)
    llm = get_chat_llm("sk-test")
    assert type(llm).__name__ == "ChatOpenAI"
    assert llm.model_name == "gpt-4o-mini"


def test_get_active_provider_defaults_to_config():
    assert get_active_provider() == "openai"


def test_get_active_provider_reflects_override():
    set_provider_override("groq")
    assert get_active_provider() == "groq"


def test_provider_models_catalog_covers_known_providers():
    for provider in ("openai", "groq", "gemini", "deepseek", "ollama"):
        models = PROVIDER_MODELS[provider]
        assert models
        assert all(
            "id" in m and "free" in m and "recommended" in m for m in models
        )
        # Ровно одна рекомендованная модель на провайдера — иначе
        # корону в UI получит первая по списку, а не задуманная.
        assert sum(m["recommended"] for m in models) == 1


if __name__ == "__main__":
    test_default_provider_is_openai()
    test_openai_provider_uses_given_model()
    test_deepseek_provider_uses_deepseek_base_url()
    print("All tests passed.")
