from typing import Optional

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src.job_sources.llm_usage import UsageCallback, get_output_folder


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

        resolved_model = model or "llama-3.3-70b-versatile"
        llm: BaseChatModel = ChatGroq(
            model=resolved_model,
            api_key=SecretStr(api_key),
            temperature=temperature,
        )
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        resolved_model = model or "gemini-1.5-flash"
        llm = ChatGoogleGenerativeAI(
            model=resolved_model,
            google_api_key=SecretStr(api_key),
            temperature=temperature,
        )
    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI

        resolved_model = model or "deepseek-chat"
        llm = ChatOpenAI(
            model=resolved_model,
            api_key=SecretStr(api_key),
            base_url=base_url or "https://api.deepseek.com",
            temperature=temperature,
        )
    elif provider == "ollama":
        from langchain_ollama import ChatOllama

        resolved_model = model or "llama3"
        llm = ChatOllama(
            model=resolved_model,
            base_url=base_url,
            temperature=temperature,
        )
    else:
        from langchain_openai import ChatOpenAI

        provider = "openai"
        resolved_model = model or "gpt-4o-mini"
        llm = ChatOpenAI(
            model=resolved_model,
            api_key=SecretStr(api_key),
            temperature=temperature,
        )

    output_folder = get_output_folder()
    if output_folder is not None:
        llm.callbacks = [
            UsageCallback(output_folder, provider, resolved_model)
        ]
    return llm
