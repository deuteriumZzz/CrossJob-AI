import pytest

from src.job_sources.llm_provider import get_chat_llm


def test_default_provider_is_openai():
    llm = get_chat_llm("sk-test")
    assert type(llm).__name__ == "ChatOpenAI"
    assert llm.model_name == "gpt-4o-mini"


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


if __name__ == "__main__":
    test_default_provider_is_openai()
    test_openai_provider_uses_given_model()
    test_deepseek_provider_uses_deepseek_base_url()
    print("All tests passed.")
