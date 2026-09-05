"""
Аудит резюме под конкретную вакансию — 3-шаговая LLM-цепочка (промпты
пользователя): сначала общая оценка/пробелы, затем ATS+HR-проверка (с
учётом оценки), затем переписанный раздел опыта (с учётом обеих
предыдущих). Каждый шаг — отдельный однократный вызов LLM (как в
job_fit.py), не stateful чат-сессия: вывод предыдущего шага просто
передаётся следующему как текст в промпте.
"""

from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.job_sources.llm_provider import get_chat_llm
from src.libs.resume_and_cover_builder.anti_ai_rules import ANTI_AI_STRUCTURE_RU

_AUDIT_PROMPT = ChatPromptTemplate.from_template(
    """
Отвечай только на русском языке.

Выступи в роли старшего рекрутера именно этой компании.
Проанализируй моё резюме относительно описания этой вакансии.

Дай мне:

1. Оценку соответствия от 0 до 100
2. Пять главных отсутствующих ключевых слов, которые будет искать ATS
3. Три тревожных сигнала, которые менеджер по найму заметит менее чем за 10 секунд
4. Какие разделы сильные и почему
5. Какие разделы слабые и почему
6. Как моё резюме выглядит в сравнении с резюме сильного кандидата на эту роль

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

СНАЧАЛА: Выступи в роли фильтра ATS. Просканируй моё резюме и скажи:
- Пройдёт ли оно ATS для этой вакансии? (Да/Нет)
- Какие ключевые слова теперь присутствуют, а каких всё ещё не хватает?
- Есть ли проблемы с оформлением, которые запутают парсер ATS? (таблицы,
  колонки, заголовки, специальные символы, изображения)

ЗАТЕМ: Выступи в роли менеджера по найму, который за один раз читает 200
резюме. Просмотри моё резюме и скажи:
- Какие разделы ты бы пропустил(а)? Почему?
- Что заставляет остановить прокрутку — в хорошем или плохом смысле?
- В какую стопку ты бы положил(а) это резюме для этой роли: «да»,
  «возможно» или «нет»?
- Перепиши разделы, которые были бы пропущены, так, чтобы они действительно
  останавливали прокрутку.

Дай мне финальную версию резюме после применения всех исправлений.

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


def run_resume_audit(
    resume_text: str, job_description: str, llm_api_key: str
) -> str:
    """Шаг 1 — общая оценка резюме под вакансию."""
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0.3))
    chain = _AUDIT_PROMPT | llm | StrOutputParser()
    return chain.invoke(
        {"resume": resume_text, "job_description": job_description}
    )


def run_ats_hiring_manager_check(
    resume_text: str,
    job_description: str,
    audit_result: str,
    llm_api_key: str,
) -> str:
    """Шаг 2 — ATS-фильтр + менеджер по найму, с учётом шага 1."""
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0.3))
    chain = _ATS_HIRING_MANAGER_PROMPT | llm | StrOutputParser()
    return chain.invoke(
        {
            "resume": resume_text,
            "job_description": job_description,
            "audit_result": audit_result,
        }
    )


def run_rewrite_experience(
    resume_text: str,
    audit_result: str,
    ats_hiring_manager_result: str,
    llm_api_key: str,
) -> str:
    """Шаг 3 — переписанный раздел опыта, с учётом шагов 1 и 2."""
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0.3))
    chain = _REWRITE_EXPERIENCE_PROMPT | llm | StrOutputParser()
    return chain.invoke(
        {
            "resume": resume_text,
            "audit_result": audit_result,
            "ats_hiring_manager_result": ats_hiring_manager_result,
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
        "audit": audit,
        "ats_hiring_manager": ats_hiring_manager,
        "rewritten_experience": rewritten_experience,
    }
