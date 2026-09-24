"""Разбор поста с вакансией из Telegram-канала: у постов нет структуры
(компания, должность, зарплата — где угодно в тексте), поэтому их
достаёт LLM. Контакты — регулярками (contact_book.contacts_from_text),
чтобы ни один адрес не был "додуман" моделью."""

from __future__ import annotations

from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.job_sources.llm_provider import get_chat_llm

_PARSE_PROMPT = ChatPromptTemplate.from_template(
    """
    Это пост с вакансией из Telegram-канала. Извлеки только то, что
    написано в посте явно; если чего-то нет — пустая строка.
    - company: название компании-работодателя (не канала, не кадрового
      агентства-репостера, если работодатель назван отдельно)
    - role: должность, коротко (например "Python Backend Developer")
    - salary: зарплатная вилка как в тексте

    Пост:
    {text}
    """
)


class _Post(BaseModel):
    company: str = Field(default="", description="Компания-работодатель")
    role: str = Field(default="", description="Должность")
    salary: str = Field(default="", description="Зарплата как в тексте")


def parse_post(text: str, llm_api_key: str) -> dict:
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0))
    result = cast(
        _Post,
        llm.with_structured_output(_Post).invoke(
            _PARSE_PROMPT.format(text=text[:4000])
        ),
    )
    return {
        "company": result.company.strip(),
        "role": result.role.strip(),
        "salary": result.salary.strip(),
    }
