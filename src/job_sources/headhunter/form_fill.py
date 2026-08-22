from __future__ import annotations

import time
from typing import Optional, cast

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field
from selenium.webdriver.common.by import By

from src.job import Job
from src.job_sources.llm_provider import get_chat_llm

PAGE_LOAD_WAIT_SECONDS = 3
OTHER_OPTION_SENTINEL = "__other_option__"


class ScrapedQuestion:
    def __init__(self, index: int, text: str, kind: str, options: list[str]):
        self.index = index
        self.text = text
        self.kind = kind  # "text" | "radio" | "checkbox"
        self.options = options


def scrape_form_questions(driver) -> list[ScrapedQuestion]:
    """Читает вопросы Google-формы через ARIA-роли (role=listitem/
    heading/radio/checkbox) — подтверждено прямым просмотром живой
    формы: у Google Forms нет человекочитаемых классов, но ARIA-
    разметка стабильна и одинакова для любого набора вопросов."""
    items = driver.find_elements(By.CSS_SELECTOR, '[role="listitem"]')
    questions = []
    for i, item in enumerate(items):
        headings = item.find_elements(By.CSS_SELECTOR, '[role="heading"]')
        if not headings:
            continue
        text = headings[0].text.strip().rstrip("*").strip()
        if not text:
            continue

        radios = item.find_elements(By.CSS_SELECTOR, '[role="radio"]')
        checks = item.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
        if radios:
            options = [
                r.get_attribute("aria-label")
                for r in radios
                if r.get_attribute("aria-label") != OTHER_OPTION_SENTINEL
            ]
            questions.append(ScrapedQuestion(i, text, "radio", options))
        elif checks:
            options = [
                c.get_attribute("aria-label")
                for c in checks
                if c.get_attribute("aria-label") != OTHER_OPTION_SENTINEL
            ]
            questions.append(ScrapedQuestion(i, text, "checkbox", options))
        else:
            questions.append(ScrapedQuestion(i, text, "text", []))
    return questions


class _FormAnswerItem(BaseModel):
    index: int = Field(description="Индекс вопроса, как в списке вопросов")
    text_answer: Optional[str] = Field(
        default=None,
        description=(
            "Ответ для открытого текстового вопроса. Оставить пустым "
            "для radio/checkbox."
        ),
    )
    selected_options: Optional[list[str]] = Field(
        default=None,
        description=(
            "Один или несколько вариантов ИЗ предложенного списка "
            "options для radio/checkbox вопроса, дословно как они "
            "написаны. Оставить пустым для текстовых вопросов."
        ),
    )


class _FormAnswers(BaseModel):
    answers: list[_FormAnswerItem]


def questions_to_dicts(questions: list[ScrapedQuestion]) -> list[dict]:
    return [
        {
            "index": q.index,
            "text": q.text,
            "kind": q.kind,
            "options": q.options,
        }
        for q in questions
    ]


def dicts_to_questions(dicts: list[dict]) -> list[ScrapedQuestion]:
    return [
        ScrapedQuestion(d["index"], d["text"], d["kind"], d["options"])
        for d in dicts
    ]


def answers_to_dicts(answers: dict[int, _FormAnswerItem]) -> list[dict]:
    return [a.model_dump() for a in answers.values()]


def dicts_to_answers(dicts: list[dict]) -> dict[int, _FormAnswerItem]:
    items = [_FormAnswerItem(**d) for d in dicts]
    return {a.index: a for a in items}


def format_questions_and_answers(
    questions: list[ScrapedQuestion], answers: dict[int, _FormAnswerItem]
) -> str:
    lines = []
    for q in questions:
        a = answers.get(q.index)
        value = (
            (a.text_answer or (", ".join(a.selected_options or [])))
            if a
            else "(нет ответа)"
        )
        lines.append(f"{q.text}\n→ {value}")
    return "\n\n".join(lines)


def draft_form_answers(
    questions: list[ScrapedQuestion],
    job: Job,
    resume_text: str,
    llm_api_key: str,
) -> dict[int, _FormAnswerItem]:
    """Черновик ответов на вопросы формы — LLM выбирает только из уже
    предложенных вариантов (options), никогда не придумывает свой
    вариант "Другое" сама: угадывать формулировку кастомного ответа
    рискованнее, чем выбрать ближайший существующий пункт."""
    questions_block = "\n".join(
        f"{q.index}. [{q.kind}] {q.text}"
        + (f" Варианты: {q.options}" if q.options else "")
        for q in questions
    )
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0.2))
    structured = llm.with_structured_output(_FormAnswers)
    result = cast(
        _FormAnswers,
        structured.invoke(
            "Ты помогаешь кандидату заполнить анкету работодателя перед "
            "откликом на вакансию. Используй его резюме и описание "
            "вакансии, чтобы честно и по существу ответить на каждый "
            "вопрос ниже. Для вопросов с вариантами (radio/checkbox) "
            "выбери из предложенного списка options дословно — не "
            "придумывай новый вариант. Для текстовых вопросов пиши "
            "кратко и по делу, от первого лица.\n\n"
            f"## Вакансия: {job.role} в {job.company}\n{job.description}\n\n"
            f"## Резюме кандидата:\n{resume_text}\n\n"
            f"## Вопросы анкеты:\n{questions_block}"
        ),
    )
    return {a.index: a for a in result.answers}


def fill_form(
    driver,
    questions: list[ScrapedQuestion],
    answers: dict[int, _FormAnswerItem],
) -> None:
    """Заполняет форму по уже сгенерированным ответам — submit НЕ
    нажимает, это отдельный шаг после подтверждения пользователем."""
    items = driver.find_elements(By.CSS_SELECTOR, '[role="listitem"]')
    for q in questions:
        answer = answers.get(q.index)
        if answer is None or q.index >= len(items):
            continue
        item = items[q.index]

        if q.kind == "text":
            if not answer.text_answer:
                continue
            inputs = item.find_elements(
                By.CSS_SELECTOR, 'input[type="text"], textarea'
            )
            if inputs:
                inputs[0].send_keys(answer.text_answer)
        elif q.kind == "radio":
            if not answer.selected_options:
                continue
            radios = item.find_elements(By.CSS_SELECTOR, '[role="radio"]')
            for r in radios:
                if r.get_attribute("aria-label") == answer.selected_options[0]:
                    r.click()
                    break
        elif q.kind == "checkbox":
            if not answer.selected_options:
                continue
            checks = item.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
            wanted = set(answer.selected_options)
            for c in checks:
                if c.get_attribute("aria-label") in wanted:
                    c.click()
                    time.sleep(0.2)
