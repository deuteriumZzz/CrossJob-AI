from typing import Optional

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from config import LLM_API_URL, LLM_MODEL, LLM_MODEL_TYPE
from src.job_sources.llm_usage import UsageCallback, get_output_folder

_provider_override: Optional[str] = None
_model_override: Optional[str] = None
_base_url_override: Optional[str] = None

# ponytail: free/paid + актуальность ID — сверено веб-поиском 2026-08-21
# (свежие модели/цены/депрекейшены меняются быстрее, чем стоит
# перепроверять руками; если провайдер вернёт ошибку "model not
# found", это первое место для проверки). "recommended" — не всегда
# самая сильная модель, а та, что лучше всего подходит под наши
# задачи (оценка вакансии, сопроводительное письмо, разбор резюме —
# короткие структурированные ответы, не многошаговые рассуждения), с
# поправкой на скорость/цену/бесплатный лимit.
PROVIDER_MODELS: dict = {
    "openai": [
        {"id": "gpt-5", "free": False, "recommended": False},
        {"id": "gpt-4o", "free": False, "recommended": False},
        {"id": "gpt-5-mini", "free": False, "recommended": True},
        {"id": "gpt-4o-mini", "free": False, "recommended": False},
        {"id": "gpt-5-nano", "free": False, "recommended": False},
    ],
    # Groq снял llama-3.3-70b-versatile и llama-3.1-8b-instant с
    # бесплатного/developer-тира 2026-08-16 — ниже их официальная
    # замена (console.groq.com/docs/deprecations).
    "groq": [
        {"id": "openai/gpt-oss-120b", "free": True, "recommended": True},
        {
            "id": "meta-llama/llama-4-maverick-17b-128e-instruct",
            "free": True,
            "recommended": False,
        },
        {"id": "openai/gpt-oss-20b", "free": True, "recommended": False},
    ],
    # Gemini 1.5 снят с прайс-листа (заменён 2.x/3.x); 2.5-flash
    # уходит на пенсию 2026-10-16 — на замену уже есть 3.7-flash.
    "gemini": [
        {"id": "gemini-3.7-flash", "free": False, "recommended": False},
        {"id": "gemini-2.5-flash", "free": True, "recommended": True},
        {"id": "gemini-2.5-flash-lite", "free": True, "recommended": False},
    ],
    "deepseek": [
        {"id": "deepseek-reasoner", "free": False, "recommended": False},
        {"id": "deepseek-chat", "free": False, "recommended": True},
    ],
    "ollama": [
        {"id": "llama3.1", "free": True, "recommended": True},
        {"id": "qwen2.5", "free": True, "recommended": False},
        {"id": "mistral", "free": True, "recommended": False},
        {"id": "phi3", "free": True, "recommended": False},
    ],
}


def set_provider_override(
    provider: Optional[str],
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> None:
    """Переопределяет провайдера/модель LLM на весь процесс — вызывается
    один раз при старте (main()/AppContext.reload_config) из блока
    llm: в work_preferences.yaml (дашборд: иконки провайдера в
    настройках), тем же приёмом, что _output_folder в llm_usage.py.
    provider=None сбрасывает override — возврат к
    config.LLM_MODEL_TYPE по умолчанию."""
    global _provider_override, _model_override, _base_url_override
    _provider_override = provider
    _model_override = model
    _base_url_override = base_url


def get_active_provider() -> str:
    """Провайдер, который реально используется сейчас — тот же
    приоритет, что get_chat_llm() применяет к своему provider-
    аргументу, без явного per-call override. Используется для
    выбора, каким сохранённым ключом (llm_api_keys.<provider> в
    secrets.yaml) резолвить llm_api_key при старте/reload."""
    return _provider_override or LLM_MODEL_TYPE


def get_chat_llm(
    api_key: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0,
    base_url: Optional[str] = None,
) -> BaseChatModel:
    """Единая точка создания chat-LLM вместо ChatOpenAI(...),
    захардкоженного в 8 разных местах. Провайдер/модель/base_url:
    явный аргумент > set_provider_override() (дашборд) >
    config.LLM_MODEL_TYPE/LLM_MODEL/LLM_API_URL (дефолт из файла).
    Модель/base_url из config.py используются только когда
    итоговый провайдер совпадает с config.LLM_MODEL_TYPE — иначе
    переключение провайдера без явной модели протекало бы моделью
    другого провайдера (например gpt-4o-mini в запрос к Groq).
    Импорты провайдер-специфичных пакетов — внутри веток, чтобы
    пользователь ставил только то, чем реально пользуется (см.
    requirements.txt/GUIDE.md)."""
    resolved_provider = provider or _provider_override or LLM_MODEL_TYPE
    is_config_default = resolved_provider == LLM_MODEL_TYPE
    if model is None:
        model = _model_override or (LLM_MODEL if is_config_default else None)
    if base_url is None:
        base_url = _base_url_override or (
            LLM_API_URL or None if is_config_default else None
        )
    provider = resolved_provider

    if provider == "groq":
        from langchain_groq import ChatGroq

        resolved_model = model or "openai/gpt-oss-120b"
        llm: BaseChatModel = ChatGroq(
            model=resolved_model,
            api_key=SecretStr(api_key),
            temperature=temperature,
        )
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        resolved_model = model or "gemini-2.5-flash"
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
