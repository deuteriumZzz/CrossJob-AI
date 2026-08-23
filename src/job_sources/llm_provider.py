from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.runnables.fallbacks import RunnableWithFallbacks
from pydantic import SecretStr

from config import LLM_API_URL, LLM_MODEL, LLM_MODEL_TYPE
from src.job_sources.llm_usage import UsageCallback, get_output_folder

_provider_override: Optional[str] = None
_model_override: Optional[str] = None
_base_url_override: Optional[str] = None
_fallback_keys: dict = {}
_fallback_mode: str = "auto"  # "auto" | "free" | "paid"
_fallback_enabled: bool = True

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
    # gemini-2.5-flash отключён для новых аккаунтов (подтверждено
    # живым вызовом 2026-08-22: 404 "no longer available to new
    # users", Google предлагает 3.6-flash) — обновлено на актуальную
    # линейку. 3.6-flash доступен на бесплатном тарифе (~15 RPM/1500
    # RPD, проверено вручную живым ключом).
    "gemini": [
        {"id": "gemini-3.6-flash", "free": True, "recommended": True},
        {"id": "gemini-3.7-flash", "free": False, "recommended": False},
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


def set_fallback_keys(keys: Optional[dict]) -> None:
    """Ключи остальных настроенных провайдеров (secrets.yaml:
    llm_api_keys.<provider>), кроме активного — вызывается один раз
    при старте вместе с set_provider_override(), тем же приёмом.
    get_chat_llm() оборачивает основную модель в них через
    .with_fallbacks(): 429/insufficient_quota от одного провайдера
    не блокирует прогон на минуты ретраями, а сразу уходит на
    следующий настроенный ключ. См. set_fallback_mode() — бесплатная
    и платная цепочки не смешиваются, а выбираются отдельно."""
    global _fallback_keys
    _fallback_keys = dict(keys or {})


def set_fallback_mode(mode: Optional[str]) -> None:
    """ "free" — в фолбэк идут только бесплатные модели настроенных
    провайдеров (переключение никогда не начнёт неожиданно тратить
    деньги); "paid" — только платные; "auto" (по умолчанию) — все
    настроенные провайдеры, бесплатные впереди платных. Задаётся
    через llm.mode в work_preferences.yaml (дашборд — рядом с
    выбором провайдера), тем же приёмом, что set_provider_override()."""
    global _fallback_mode
    _fallback_mode = mode or "auto"


def set_fallback_enabled(enabled: Optional[bool]) -> None:
    """False — использовать строго один выбранный провайдер, без
    переключения на другие ключи из secrets.yaml при ошибке/лимите
    (то, что ключа у другого провайдера вовсе нет, и так само по
    себе исключает его из цепочки — этот флаг про другой случай:
    пользователь явно не хочет уходить с выбранного провайдера, даже
    если ключ другого настроен). По умолчанию True — прежнее
    поведение. Задаётся через llm.fallback_enabled в
    work_preferences.yaml (дашборд — рядом с выбором провайдера)."""
    global _fallback_enabled
    _fallback_enabled = True if enabled is None else bool(enabled)


def _recommended_model(provider: str) -> Optional[dict]:
    models = PROVIDER_MODELS.get(provider) or []
    return next((m for m in models if m.get("recommended")), None) or (
        models[0] if models else None
    )


def _default_model_id(provider: str) -> str:
    """Всегда возвращает id модели — тонкая обёртка над
    _recommended_model() для мест, которым нужна именно строка, а не
    Optional[dict] (пустая строка недостижима на практике: 5
    провайдеров ниже все со своим непустым списком в PROVIDER_MODELS,
    но mypy этого не знает статически)."""
    model = _recommended_model(provider)
    return model["id"] if model else ""


def _build_llm(
    provider: str,
    api_key: str,
    model: Optional[str],
    base_url: Optional[str],
    temperature: float,
) -> tuple[BaseChatModel, str]:
    """Провайдер-специфичное создание chat-модели — вынесено из
    get_chat_llm(), чтобы одна и та же логика строила и основную
    модель, и каждый фолбэк в _build_fallback_llms(). Модель по
    умолчанию берётся из PROVIDER_MODELS (_recommended_model), а не
    захардкожена по месту — иначе дефолт и таблица PROVIDER_MODELS
    расходятся при обновлении одного без другого (так уже было с
    gemini-2.5-flash, снятым с публичного доступа — см. комментарий
    там). max_retries=0 — подтверждено живым прогоном: SDK-клиенты
    сами ретраят 429 с backoff по 10-30с ПЕРЕД тем, как исключение
    дойдёт до .with_fallbacks(), из-за чего переключение на другого
    провайдера ждало минуты вместо секунд."""
    if provider == "groq":
        from langchain_groq import ChatGroq

        resolved_model = model or _default_model_id(provider)
        return (
            ChatGroq(
                model=resolved_model,
                api_key=SecretStr(api_key),
                temperature=temperature,
                max_retries=0,
            ),
            resolved_model,
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        resolved_model = model or _default_model_id(provider)
        return (
            ChatGoogleGenerativeAI(
                model=resolved_model,
                google_api_key=SecretStr(api_key),
                temperature=temperature,
                max_retries=0,
            ),
            resolved_model,
        )
    if provider == "deepseek":
        from langchain_openai import ChatOpenAI

        resolved_model = model or _default_model_id(provider)
        return (
            ChatOpenAI(
                model=resolved_model,
                api_key=SecretStr(api_key),
                base_url=base_url or "https://api.deepseek.com",
                temperature=temperature,
                max_retries=0,
            ),
            resolved_model,
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        resolved_model = model or _default_model_id(provider)
        return (
            ChatOllama(
                model=resolved_model,
                base_url=base_url,
                temperature=temperature,
            ),
            resolved_model,
        )
    from langchain_openai import ChatOpenAI

    resolved_model = model or _default_model_id("openai")
    return (
        ChatOpenAI(
            model=resolved_model,
            api_key=SecretStr(api_key),
            temperature=temperature,
            max_retries=0,
        ),
        resolved_model,
    )


def _build_fallback_llms(
    exclude_provider: str, temperature: float
) -> list[BaseChatModel]:
    if not _fallback_enabled:
        return []
    others = [p for p in _fallback_keys if p != exclude_provider]

    if _fallback_mode == "free":
        others = [
            p for p in others if (_recommended_model(p) or {}).get("free")
        ]
    elif _fallback_mode == "paid":
        others = [
            p for p in others if not (_recommended_model(p) or {}).get("free")
        ]
    else:
        others.sort(
            key=lambda p: not (_recommended_model(p) or {}).get("free", False)
        )

    fallbacks = []
    for provider in others:
        api_key = _fallback_keys.get(provider)
        if not api_key:
            continue
        try:
            llm, resolved_model = _build_llm(
                provider, api_key, None, None, temperature
            )
        except Exception:
            continue
        output_folder = get_output_folder()
        if output_folder is not None:
            llm.callbacks = [
                UsageCallback(output_folder, provider, resolved_model)
            ]
        fallbacks.append(llm)
    return fallbacks


class _ChatModelWithFallbacks(RunnableWithFallbacks):
    """RunnableWithFallbacks.__getattr__ (общий Runnable-прокси)
    падает на Python 3.9 при вызове with_structured_output()
    (job_fit.py:score_job_fit): typing.get_type_hints() внутри
    _returns_runnable() не резолвит синтаксис "X | Y" в тайп-хинтах
    свежего langchain-core на 3.9 — подтверждено живым падением
    (TypeError: unsupported operand type(s) for |). with_structured_
    output переопределён здесь вручную в обход этой генерик-проверки:
    применяет её к основной модели и к каждому фолбэку, оборачивая
    результат в новый экземпляр того же класса."""

    def with_structured_output(self, *args, **kwargs):
        return _ChatModelWithFallbacks(
            runnable=self.runnable.with_structured_output(*args, **kwargs),
            fallbacks=[
                f.with_structured_output(*args, **kwargs)
                for f in self.fallbacks
            ],
            exceptions_to_handle=self.exceptions_to_handle,
            exception_key=self.exception_key,
        )


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
) -> Runnable:
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
    if resolved_provider not in PROVIDER_MODELS:
        resolved_provider = "openai"
    provider = resolved_provider
    llm, resolved_model = _build_llm(
        provider, api_key, model, base_url, temperature
    )

    output_folder = get_output_folder()
    if output_folder is not None:
        llm.callbacks = [
            UsageCallback(output_folder, provider, resolved_model)
        ]

    fallbacks = _build_fallback_llms(provider, temperature)
    result: Runnable = llm
    if fallbacks:
        result = _ChatModelWithFallbacks(runnable=llm, fallbacks=fallbacks)
    return result
