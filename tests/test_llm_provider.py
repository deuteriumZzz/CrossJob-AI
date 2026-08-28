from pathlib import Path

import pytest

from src.job_sources import llm_usage
from src.job_sources.llm_provider import (
    PROVIDER_MODELS,
    _build_fallback_llms,
    get_active_provider,
    get_chat_llm,
    set_fallback_base_urls,
    set_fallback_enabled,
    set_fallback_keys,
    set_fallback_mode,
    set_provider_override,
)


@pytest.fixture(autouse=True)
def _reset_fallback_state():
    yield
    set_fallback_keys(None)
    set_fallback_base_urls(None)
    set_fallback_mode(None)
    set_fallback_enabled(None)


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


def test_nvidia_provider_uses_nvidia_base_url():
    llm = get_chat_llm("nvapi-test", provider="nvidia")
    assert llm.model_name == "meta/llama-3.3-70b-instruct"
    assert llm.openai_api_base == "https://integrate.api.nvidia.com/v1"


def test_openrouter_provider_uses_openrouter_base_url():
    llm = get_chat_llm("sk-or-test", provider="openrouter")
    assert llm.model_name == "minimax/minimax-m3:free"
    assert llm.openai_api_base == "https://openrouter.ai/api/v1"


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
    for provider in (
        "openai",
        "groq",
        "gemini",
        "deepseek",
        "nvidia",
        "openrouter",
        "mistral",
        "cohere",
        "huggingface",
        "ollama_cloud",
        "llm7",
        "cloudflare",
        "vercel",
        "ollama",
    ):
        models = PROVIDER_MODELS[provider]
        assert models
        assert all(
            "id" in m and "free" in m and "recommended" in m for m in models
        )
        # Ровно одна рекомендованная модель на провайдера — иначе
        # корону в UI получит первая по списку, а не задуманная.
        assert sum(m["recommended"] for m in models) == 1


def test_new_openai_compatible_providers_use_own_base_url():
    for provider, expected_base_url in (
        ("mistral", "https://api.mistral.ai/v1"),
        ("cohere", "https://api.cohere.ai/compatibility/v1"),
        ("huggingface", "https://router.huggingface.co/v1"),
        ("ollama_cloud", "https://ollama.com/v1"),
        ("llm7", "https://api.llm7.io/v1"),
        ("vercel", "https://ai-gateway.vercel.sh/v1"),
    ):
        llm = get_chat_llm("test-key", provider=provider)
        assert llm.openai_api_base == expected_base_url


def test_cloudflare_requires_base_url():
    """account_id живёт в URL, не в ключе — без явного base_url
    нечего подставить по умолчанию (в отличие от остальных
    провайдеров), поэтому это должно падать, а не тихо уйти на
    api.openai.com с чужим ключом."""
    with pytest.raises(ValueError):
        get_chat_llm("test-key", provider="cloudflare")


def test_cloudflare_uses_given_base_url():
    llm = get_chat_llm(
        "test-key",
        provider="cloudflare",
        base_url="https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1",
    )
    assert (
        llm.openai_api_base
        == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1"
    )


def test_fallback_uses_configured_provider_base_url():
    """set_fallback_base_urls() должен долетать до каждой модели
    Cloudflare в цепочке фолбэка, не только до основной модели."""
    set_fallback_mode("free")
    set_fallback_keys({"cloudflare": "cf-test-key"})
    set_fallback_base_urls(
        {"cloudflare": "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1"}
    )
    fallbacks = _build_fallback_llms("openai", temperature=0)
    assert fallbacks
    for llm in fallbacks:
        assert (
            llm.openai_api_base
            == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1"
        )


def test_fallback_depth_tries_every_free_model_of_a_provider():
    """Раньше на 429 конкретно у recommended-модели цепочка сразу
    прыгала на другого провайдера, хотя у текущего провайдера были
    ещё свободные бесплатные модели (Groq лимитирует TPM per-model,
    не per-account) — теперь фолбэк должен перебрать их все."""
    set_fallback_mode("free")
    set_fallback_keys({"groq": "gsk-test"})
    pytest.importorskip("langchain_groq")
    fallbacks = _build_fallback_llms("openai", temperature=0)
    free_groq_models = [m["id"] for m in PROVIDER_MODELS["groq"] if m["free"]]
    assert len(fallbacks) == len(free_groq_models)
    assert [llm.model_name for llm in fallbacks] == free_groq_models


if __name__ == "__main__":
    test_default_provider_is_openai()
    test_openai_provider_uses_given_model()
    test_deepseek_provider_uses_deepseek_base_url()
    test_nvidia_provider_uses_nvidia_base_url()
    test_openrouter_provider_uses_openrouter_base_url()
    test_new_openai_compatible_providers_use_own_base_url()
    test_fallback_depth_tries_every_free_model_of_a_provider()
    print("All tests passed.")
