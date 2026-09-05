"""
Аудит резюме под конкретную вакансию — 3-шаговая LLM-цепочка (промпты
пользователя): сначала общая оценка/пробелы, затем ATS+HR-проверка (с
учётом оценки), затем переписанный раздел опыта (с учётом обеих
предыдущих). Каждый шаг — отдельный однократный вызов LLM (как в
job_fit.py), не stateful чат-сессия: вывод предыдущего шага просто
передаётся следующему как текст в промпте.

Шаги 1 и 2 отдают структурированный JSON (llm.with_structured_output —
тот же приём, что _NeedsReply в reply_answerer.py), чтобы дашборд мог
нарисовать процент/бэйджи/чипы, а не парсить прозу регулярками. Шаг 3
остаётся обычным текстом — это готовый контент для копирования в
резюме, а не данные для UI.
"""

from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.job_sources.llm_provider import get_chat_llm
from src.libs.resume_and_cover_builder.anti_ai_rules import (
    ANTI_AI_STRUCTURE_RU,
)


class ResumeAuditScore(BaseModel):
    match_score: int = Field(
        description="Оценка соответствия резюме вакансии, от 0 до 100"
    )
    missing_keywords: list[str] = Field(
        description="До 5 главных отсутствующих ключевых слов, которые будет искать ATS"
    )
    red_flags: list[str] = Field(
        description="До 3 тревожных сигналов, которые менеджер по найму заметит менее чем за 10 секунд"
    )
    strong_sections: list[str] = Field(
        description="Сильные разделы резюме — каждый пункт с кратким 'почему'"
    )
    weak_sections: list[str] = Field(
        description="Слабые разделы резюме — каждый пункт с кратким 'почему'"
    )
    comparison_note: str = Field(
        description="1-2 предложения: как резюме выглядит в сравнении с резюме сильного кандидата на эту роль"
    )


class AtsHiringManagerCheck(BaseModel):
    ats_pass: bool = Field(
        description="Пройдёт ли резюме ATS-фильтр для этой вакансии"
    )
    keywords_present: list[str] = Field(
        description="Ключевые слова из вакансии, которые уже есть в резюме"
    )
    keywords_missing: list[str] = Field(
        description="Ключевые слова из вакансии, которых всё ещё не хватает"
    )
    formatting_issues: list[str] = Field(
        description="Проблемы оформления, которые запутают парсер ATS "
        "(таблицы, колонки, заголовки, спецсимволы, изображения) — "
        "пустой список, если их нет"
    )
    hiring_manager_bucket: Literal["да", "возможно", "нет"] = Field(
        description="В какую стопку менеджер по найму положит это резюме для этой роли"
    )
    skip_reasons: list[str] = Field(
        description="Какие разделы менеджер по найму пропустил бы при беглом "
        "просмотре и почему — пустой список, если пропускать нечего"
    )


_AUDIT_PROMPT = ChatPromptTemplate.from_template(
    """
Отвечай только на русском языке.

Выступи в роли старшего рекрутера именно этой компании.
Проанализируй моё резюме относительно описания этой вакансии.

Будь предельно честным. Я лучше исправлю проблемы сейчас, чем позже останусь
без ответа.

Резюме:
```
{resume}
```

Описание вакансии:
```
{job_description}
```
"""
)

_ATS_HIRING_MANAGER_PROMPT = ChatPromptTemplate.from_template(
    """
Отвечай только на русском языке.

Вот предыдущий разбор моего резюме под эту вакансию:
```
{audit_result}
```

Теперь выступи в роли двух разных специалистов:

СНАЧАЛА: Выступи в роли фильтра ATS. Просканируй моё резюме на предмет
ключевых слов вакансии и проблем с оформлением, которые запутают парсер
ATS (таблицы, колонки, заголовки, специальные символы, изображения).

ЗАТЕМ: Выступи в роли менеджера по найму, который за один раз читает 200
резюме. Определи, какие разделы он пропустил бы при беглом просмотре и в
какую стопку положил бы это резюме для этой роли.

Резюме:
```
{resume}
```

Описание вакансии:
```
{job_description}
```
"""
)

_REWRITE_EXPERIENCE_PROMPT = ChatPromptTemplate.from_template(
    """
Отвечай только на русском языке.

Вот предыдущий разбор резюме под эту вакансию:
```
{audit_result}
```

И проверка ATS и менеджером по найму:
```
{ats_hiring_manager_result}
```

Перепиши мой раздел с опытом (из резюме ниже) по этим правилам:

1. Естественно включи найденные выше отсутствующие ключевые слова, но НЕ
   вставляй их насильно. Они должны выглядеть обычной частью каждого
   пункта.
2. Удали или исправь каждый отмеченный выше тревожный сигнал.
3. Для каждого пункта используй формулу Google XYZ: «Достиг(ла) [X], что
   измеряется [Y], благодаря [Z]».
4. Начинай каждый пункт с сильного глагола действия. Никогда не используй
   «Отвечал(а) за» или «Помогал(а) с».
5. Везде, где возможно, добавь конкретные числа. Если чисел нет в исходном
   резюме, предложи реалистичные поля для заполнения и отметь их как
   [ЗАПОЛНИТЬ] — не выдумывай числа от себя.
6. Каждый пункт — не больше 1–2 строк.
7. Расположи пункты по силе результата, а не по хронологии. Самый
   впечатляющий результат — первым.

Только реальный опыт из резюме ниже — ничего не придумывай и не
приукрашивай (не дорисовывай стаж, роли или проекты, которых не было).

Резюме:
```
{resume}
```
"""
    + ANTI_AI_STRUCTURE_RU
)


def _format_audit_for_context(audit: ResumeAuditScore) -> str:
    """Сериализует структурированную оценку шага 1 обратно в читаемый
    текст — для передачи в промпты шагов 2/3 (они не работают со
    структурой напрямую)."""
    lines = [f"Оценка соответствия: {audit.match_score}/100"]
    if audit.missing_keywords:
        lines.append(
            "Отсутствующие ключевые слова: "
            + ", ".join(audit.missing_keywords)
        )
    if audit.red_flags:
        lines.append(
            "Тревожные сигналы:\n"
            + "\n".join(f"- {r}" for r in audit.red_flags)
        )
    if audit.weak_sections:
        lines.append(
            "Слабые разделы:\n"
            + "\n".join(f"- {s}" for s in audit.weak_sections)
        )
    if audit.strong_sections:
        lines.append(
            "Сильные разделы:\n"
            + "\n".join(f"- {s}" for s in audit.strong_sections)
        )
    if audit.comparison_note:
        lines.append(audit.comparison_note)
    return "\n".join(lines)


def _format_ats_check_for_context(check: AtsHiringManagerCheck) -> str:
    """Тот же приём для результата шага 2 — на вход шага 3."""
    lines = [f"ATS: {'пройдёт' if check.ats_pass else 'не пройдёт'}"]
    if check.keywords_missing:
        lines.append(
            "Всё ещё не хватает ключевых слов: "
            + ", ".join(check.keywords_missing)
        )
    if check.formatting_issues:
        lines.append(
            "Проблемы форматирования:\n"
            + "\n".join(f"- {i}" for i in check.formatting_issues)
        )
    lines.append(
        f"Менеджер по найму положил бы резюме в стопку: "
        f"{check.hiring_manager_bucket}"
    )
    if check.skip_reasons:
        lines.append(
            "Разделы, которые пропустит менеджер:\n"
            + "\n".join(f"- {r}" for r in check.skip_reasons)
        )
    return "\n".join(lines)


def run_resume_audit(
    resume_text: str, job_description: str, llm_api_key: str
) -> ResumeAuditScore:
    """Шаг 1 — общая оценка резюме под вакансию."""
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0.3))
    structured_llm = llm.with_structured_output(ResumeAuditScore)
    chain = _AUDIT_PROMPT | structured_llm
    return cast(
        ResumeAuditScore,
        chain.invoke(
            {"resume": resume_text, "job_description": job_description}
        ),
    )


def run_ats_hiring_manager_check(
    resume_text: str,
    job_description: str,
    audit_result: ResumeAuditScore,
    llm_api_key: str,
) -> AtsHiringManagerCheck:
    """Шаг 2 — ATS-фильтр + менеджер по найму, с учётом шага 1."""
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0.3))
    structured_llm = llm.with_structured_output(AtsHiringManagerCheck)
    chain = _ATS_HIRING_MANAGER_PROMPT | structured_llm
    return cast(
        AtsHiringManagerCheck,
        chain.invoke(
            {
                "resume": resume_text,
                "job_description": job_description,
                "audit_result": _format_audit_for_context(audit_result),
            }
        ),
    )


def run_rewrite_experience(
    resume_text: str,
    audit_result: ResumeAuditScore,
    ats_hiring_manager_result: AtsHiringManagerCheck,
    llm_api_key: str,
) -> str:
    """Шаг 3 — переписанный раздел опыта, с учётом шагов 1 и 2."""
    llm = get_chat_llm(llm_api_key, temperature=0.3)
    chain = _REWRITE_EXPERIENCE_PROMPT | llm | StrOutputParser()
    return chain.invoke(
        {
            "resume": resume_text,
            "audit_result": _format_audit_for_context(audit_result),
            "ats_hiring_manager_result": _format_ats_check_for_context(
                ats_hiring_manager_result
            ),
        }
    )


def run_full_resume_audit(
    resume_text: str, job_description: str, llm_api_key: str
) -> dict:
    """Прогоняет все 3 шага по порядку — каждый следующий получает
    вывод предыдущих как контекст."""
    audit = run_resume_audit(resume_text, job_description, llm_api_key)
    ats_hiring_manager = run_ats_hiring_manager_check(
        resume_text, job_description, audit, llm_api_key
    )
    rewritten_experience = run_rewrite_experience(
        resume_text, audit, ats_hiring_manager, llm_api_key
    )
    return {
        "audit": audit.model_dump(),
        "ats_hiring_manager": ats_hiring_manager.model_dump(),
        "rewritten_experience": rewritten_experience,
    }
