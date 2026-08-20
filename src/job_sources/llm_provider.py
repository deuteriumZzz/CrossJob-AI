from typing import Optional

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr


def get_chat_llm(
    api_key: str,
    provider: str = "openai",
    model: Optional[str] = None,
    temperature: float = 0,
    base_url: Optional[str] = None,
) -> BaseChatModel:
    """Единая точка создания chat-LLM вместо ChatOpenAI(...),
    захардкоженного в 6 разных местах — provider/model берутся из
    config.LLM_MODEL_TYPE/LLM_MODEL, так что переключение на
    Groq/DeepSeek/Gemini/Ollama правится в одном файле (config.py),
    а не в самих модулях. Импорты провайдер-специфичных пакетов —
    внутри веток, чтобы пользователь ставил только то, чем реально
    пользуется (см. requirements.txt/GUIDE.md)."""
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=model or "llama-3.3-70b-versatile",
            api_key=SecretStr(api_key),
            temperature=temperature,
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model or "gemini-1.5-flash",
            google_api_key=SecretStr(api_key),
            temperature=temperature,
        )
    if provider == "deepseek":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or "deepseek-chat",
            api_key=SecretStr(api_key),
            base_url=base_url or "https://api.deepseek.com",
            temperature=temperature,
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model or "llama3",
            base_url=base_url,
            temperature=temperature,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model or "gpt-4o-mini",
        api_key=SecretStr(api_key),
        temperature=temperature,
    )
