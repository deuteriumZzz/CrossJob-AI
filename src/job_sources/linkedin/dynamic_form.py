"""Динамическое чтение и заполнение шага формы Easy Apply — вместо
жёстко прописанных под конкретную разметку LinkedIn паттернов
(componentkey, конкретные атрибуты и т.п.), которые ломались при
каждом изменении вёрстки (см. историю easy_apply.py). Здесь код только
СОБИРАЕТ структуру видимых полей (какой тип, какой текст вопроса, какие
варианты) — а что вписать в каждое поле решает LLM одним батч-вызовом
на всю текущую страницу формы, как уже сделано для Google-форм
HeadHunter в src/job_sources/headhunter/form_fill.py (тот же паттерн:
ScrapedX + pydantic-схема ответов + with_structured_output).

Один LLM-вызов на ШАГ (страницу) формы, не на каждое поле — LinkedIn
показывает вопросы порциями по страницам (в отличие от HH, где вся
форма видна сразу), поэтому вызывающий код (easy_apply.run_easy_apply)
зовёт scrape/draft/apply на каждой странице отдельно, уже после
перехода на неё."""

from __future__ import annotations

import re
import time
from typing import Optional, cast

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from src.job import Job
from src.job_sources.llm_provider import get_chat_llm
from src.logging import logger

# ponytail: заголовки шагов формы сидят в тех же <p>, что и вопросы, и
# их родитель на живой форме иногда тоже "содержит поле" где-то в
# поддереве ниже по разметке — без этого фильтра заголовок шага
# распознавался как отдельный "вопрос" (подтверждено живьём 2026-09-09,
# "Contact info"/"Additional Questions" уходили в LLM как вопросы).
NON_QUESTION_LABELS = {
    "contact info",
    "resume",
    "additional questions",
    "work authorization",
    "review",
}
PAGE_COUNTER_RE = re.compile(r"^\d+/\d+ pages$")


class ScrapedField:
    def __init__(
        self,
        index: int,
        text: str,
        kind: str,
        options: list[str],
        element,
        max_length: Optional[int] = None,
    ):
        self.index = index
        self.text = text
        self.kind = kind  # "text" | "select" | "radio" | "checkbox"
        self.options = options
        self.element = element
        self.max_length = max_length


def _radio_label(driver, radio) -> str:
    """ponytail: aria-label на самом [role='radio']/checkbox иногда
    возвращает текст ВОПРОСА (группы), а не варианта ответа (Yes/No) —
    подтверждено живьём 2026-09-09 (оба радио в паре Yes/No отдавали
    одинаковый aria-label, совпадающий с текстом вопроса).
    aria-labelledby (ссылка на отдельный элемент с текстом варианта)
    пробуем первым; aria-label остаётся фолбэком для вакансий, где он
    всё же верный."""
    labelledby = radio.get_attribute("aria-labelledby")
    if labelledby:
        for label_id in labelledby.split():
            try:
                text = driver.find_element(By.ID, label_id).text.strip()
            except Exception:
                continue
            if text:
                return text
    return (radio.get_attribute("aria-label") or "").strip()


def _label_text_for(driver, field) -> str:
    """Обычные <label for=id> достаточно распространены в формах
    LinkedIn/сторонних ATS, но не гарантированы — placeholder как
    фолбэк покрывает случай, когда его нет (см. "Location (city)":
    placeholder "Enter city or location" присутствует независимо от
    разметки лейбла)."""
    field_id = field.get_attribute("id")
    if field_id:
        labels = driver.find_elements(
            By.CSS_SELECTOR, f'label[for="{field_id}"]'
        )
        if labels:
            text = labels[0].text.strip()
            if text:
                return text.rstrip("*").strip()
    return (field.get_attribute("placeholder") or "").strip()


def _field_max_length(field) -> Optional[int]:
    """HTML `maxlength` поля, если он есть и валиден (подтверждено
    живьём — короткие поля вроде "hours per week"/"compensation" на
    LinkedIn часто ограничены 20-200 символами, счётчик "0/20" виден
    прямо в форме)."""
    raw = field.get_attribute("maxlength")
    if raw and raw.isdigit():
        return int(raw)
    return None


def _fill_text_field(driver, field, value: str) -> None:
    """ponytail: некоторые текстовые поля (например "Location (city)")
    на деле автокомплит — LinkedIn считает поле пустым/невалидным, пока
    не выбран вариант из выпадающего списка, даже если текст уже
    напечатан (подтверждено живьём 2026-09-09). Печатаем как раньше, и
    если следом появился listbox с подсказками — берём первую; для
    обычных полей listbox просто не появится, и это no-op."""
    field.send_keys(value)
    time.sleep(0.6)
    try:
        listbox_id = field.get_attribute(
            "aria-controls"
        ) or field.get_attribute("aria-owns")
        options = []
        if listbox_id:
            options = driver.find_elements(
                By.CSS_SELECTOR, f"#{listbox_id} [role='option']"
            )
        if not options:
            options = driver.find_elements(
                By.CSS_SELECTOR, "[role='listbox'] [role='option']"
            )
        for option in options:
            if option.is_displayed():
                driver.execute_script("arguments[0].click();", option)
                return
    except Exception as e:
        logger.debug(f"_fill_text_field autocomplete select failed: {e}")


def _closest_option(answer: str, options: list) -> str:
    answer_lower = answer.strip().lower()
    for option in options:
        if option.lower() == answer_lower:
            return option
    for option in options:
        if option.lower() in answer_lower or answer_lower in option.lower():
            return option
    return options[0]


TEXT_INPUT_SELECTOR = "input, textarea"
# ponytail: allowlist по конкретным type='text'/'tel'/... не находил
# поля вообще без атрибута type (браузер по умолчанию считает такой
# <input> текстовым, но CSS-селектор по значению атрибута — нет) —
# подтверждено живьём 2026-09-10: "Location (city)" и всё остальное на
# той же странице оставались невидимыми, scrape_visible_fields находил
# 0 полей на шаге, форма зависала на "stuck (no Next/Submit)" без
# единой причины в логе. Denylist конкретных НЕ-текстовых типов
# переживает такой случай сам, не требуя знать заранее, что за тип у
# конкретного поля.
NON_TEXT_INPUT_TYPES = {
    "checkbox",
    "radio",
    "file",
    "hidden",
    "submit",
    "button",
    "image",
    "reset",
    "range",
    "color",
}


def _text_like_inputs(container) -> list:
    results = []
    for el in container.find_elements(By.CSS_SELECTOR, TEXT_INPUT_SELECTOR):
        if el.tag_name.lower() == "textarea":
            results.append(el)
            continue
        input_type = (el.get_attribute("type") or "text").lower()
        if input_type not in NON_TEXT_INPUT_TYPES:
            results.append(el)
    return results


def scrape_visible_fields(driver, form) -> list[ScrapedField]:
    """Собирает все видимые незаполненные вопросы ТЕКУЩЕЙ страницы
    формы — не по конкретным атрибутам, а по факту разметки (есть ли
    рядом с текстом вопроса select/radio/checkbox/text-поле). Что
    вписать в каждое поле — решает LLM в draft_answers, не эта
    функция: здесь только структура (текст вопроса, тип, варианты).

    Два независимых прохода: (1) вопросы с текстом в <p> — обычный
    случай на шаге "Additional Questions"; (2) обязательные текстовые
    поля БЕЗ своего <p> (например "Location (city)" на шаге Contact
    Info — там текст вопроса лежит в обычном <label>/placeholder, не
    в <p>). claimed_elements не даёт полю из (1) попасть туда же
    повторно через (2)."""
    fields: list[ScrapedField] = []
    seen_parents: set = set()
    claimed_elements: set = set()
    index = 0

    for p in form.find_elements(By.TAG_NAME, "p"):
        text = p.text.strip()
        if (
            not text
            or text.rstrip("*").strip().lower() in NON_QUESTION_LABELS
            or PAGE_COUNTER_RE.match(text)
        ):
            continue
        try:
            parent = p.find_element(By.XPATH, "..")
        except Exception:
            continue
        if parent.id in seen_parents:
            continue
        question = text.rstrip("*").strip()
        if not question:
            continue

        selects = parent.find_elements(By.TAG_NAME, "select")
        if selects:
            options = [
                o.text.strip()
                for o in Select(selects[0]).options
                if o.text.strip()
            ]
            if options:
                seen_parents.add(parent.id)
                claimed_elements.add(selects[0].id)
                fields.append(
                    ScrapedField(
                        index, question, "select", options, selects[0]
                    )
                )
                index += 1
            continue

        radios = parent.find_elements(By.CSS_SELECTOR, "[role='radio']")
        if radios:
            labels = [_radio_label(driver, r) for r in radios]
            labels = [label for label in labels if label and label != question]
            if labels:
                seen_parents.add(parent.id)
                fields.append(
                    ScrapedField(index, question, "radio", labels, parent)
                )
                index += 1
            continue

        checkboxes = parent.find_elements(
            By.CSS_SELECTOR, "input[type='checkbox']"
        )
        if checkboxes:
            labels = [_radio_label(driver, c) for c in checkboxes]
            labels = [label for label in labels if label and label != question]
            if labels:
                seen_parents.add(parent.id)
                fields.append(
                    ScrapedField(index, question, "checkbox", labels, parent)
                )
                index += 1
            continue

        text_inputs = _text_like_inputs(parent)
        if text_inputs:
            field = text_inputs[0]
            if field.is_displayed() and not field.get_attribute("value"):
                seen_parents.add(parent.id)
                claimed_elements.add(field.id)
                fields.append(
                    ScrapedField(
                        index,
                        question,
                        "text",
                        [],
                        field,
                        max_length=_field_max_length(field),
                    )
                )
                index += 1
            continue

    for field in _text_like_inputs(form):
        if field.id in claimed_elements:
            continue
        if not field.is_displayed() or field.get_attribute("value"):
            continue
        is_required = (
            field.get_attribute("required") is not None
            or field.get_attribute("aria-required") == "true"
        )
        if not is_required:
            continue
        question = _label_text_for(driver, field)
        if not question:
            continue
        fields.append(
            ScrapedField(
                index,
                question,
                "text",
                [],
                field,
                max_length=_field_max_length(field),
            )
        )
        index += 1

    return fields


class _FieldAnswer(BaseModel):
    index: int = Field(description="Индекс поля, как в списке form fields")
    text_answer: Optional[str] = Field(
        default=None,
        description=(
            "Ответ для текстового поля. Пусто для select/radio/checkbox."
        ),
    )
    selected_option: Optional[str] = Field(
        default=None,
        description=(
            "Один вариант ИЗ предложенного списка options, дословно как "
            "он написан. Пусто для текстовых полей."
        ),
    )


class _FieldAnswers(BaseModel):
    answers: list[_FieldAnswer]


def draft_answers(
    fields: list[ScrapedField],
    job: Job,
    resume_text: str,
    profile_text: str,
    cover_letter: str,
    llm_api_key: str,
) -> dict[int, _FieldAnswer]:
    """Один батч-вызов LLM на все поля текущей страницы формы —
    выбирает варианты только из уже предложенного списка options
    (никогда не придумывает свой "Другое"), как и form_fill.py для
    HeadHunter."""
    if not fields:
        return {}

    fields_block = "\n".join(
        f"{f.index}. [{f.kind}] {f.text}"
        + (f" Options: {f.options}" if f.options else "")
        + (f" (max {f.max_length} characters)" if f.max_length else "")
        for f in fields
    )
    llm = cast(BaseChatModel, get_chat_llm(llm_api_key, temperature=0.2))
    structured = llm.with_structured_output(_FieldAnswers)
    result = cast(
        _FieldAnswers,
        structured.invoke(
            "You are filling out a LinkedIn Easy Apply screening form on "
            "behalf of the candidate. Answer every field below briefly and "
            "honestly, using only facts from the resume/profile below — do "
            "not invent facts that aren't there. Always answer in English, "
            "regardless of what language the resume, profile, or job "
            "title/company happen to be in. For select/radio/checkbox "
            "fields, pick exactly one option from the given list, written "
            "exactly as shown — never invent a new option. For text "
            "fields, respect any character limit shown — be extremely "
            "brief when a limit is given. If a field asks for a cover "
            "letter, a motivation statement, or 'why are you interested "
            "in this role' — reuse the pre-written cover letter below "
            "(trimmed to fit any limit) instead of writing a new one.\n\n"
            f"## Job: {job.role} at {job.company}\n{job.description}\n\n"
            f"## Candidate resume:\n{resume_text}\n\n"
            f"## Candidate profile:\n{profile_text}\n\n"
            f"## Pre-written cover letter for this job:\n{cover_letter}\n\n"
            f"## Form fields:\n{fields_block}"
        ),
    )
    return {a.index: a for a in result.answers}


def check_required_consent_checkboxes(driver, form) -> None:
    """ponytail: обязательные чекбоксы-подтверждения ("I agree to be
    contacted", "I certify the above is true" и т.п.) часто идут БЕЗ
    вопроса в <p> — просто текст рядом с чекбоксом. Ни p-цикл, ни
    text-цикл в scrape_visible_fields их не видят (оба заточены под
    вопросы с текстом), LinkedIn не пускал дальше по валидации без
    единой причины в логе — форма зависала на "stuck (no Next/Submit)"
    (подтверждено по логам демона 2026-09-09: 3 из 3 реальных вакансий
    в одном заходе упёрлись сюда без единого краша). Единственное
    честное действие тут — отметить: это гейт, не вопрос с выбором,
    отказ не пропустит дальше вне зависимости от ответа."""
    for checkbox in form.find_elements(
        By.CSS_SELECTOR, "input[type='checkbox']"
    ):
        try:
            if not checkbox.is_displayed() or checkbox.is_selected():
                continue
        except Exception:
            continue
        is_required = (
            checkbox.get_attribute("required") is not None
            or checkbox.get_attribute("aria-required") == "true"
        )
        if not is_required:
            continue
        try:
            driver.execute_script("arguments[0].click();", checkbox)
        except Exception as e:
            logger.debug(f"check_required_consent_checkboxes failed: {e}")


def apply_answers(
    driver, fields: list[ScrapedField], answers: dict[int, _FieldAnswer]
) -> None:
    """Заполняет форму по уже сгенерированным ответам — не решает, что
    писать (это уже сделано в draft_answers), только применяет."""
    for f in fields:
        answer = answers.get(f.index)
        if answer is None:
            continue

        if f.kind == "select":
            if not answer.selected_option:
                continue
            options = [
                o.text.strip()
                for o in Select(f.element).options
                if o.text.strip()
            ]
            if options:
                Select(f.element).select_by_visible_text(
                    _closest_option(answer.selected_option, options)
                )

        elif f.kind == "radio":
            if not answer.selected_option:
                continue
            chosen = _closest_option(answer.selected_option, f.options)
            radios = f.element.find_elements(By.CSS_SELECTOR, "[role='radio']")
            labels = [_radio_label(driver, r) for r in radios]
            for radio, label in zip(radios, labels):
                if label == chosen:
                    driver.execute_script("arguments[0].click();", radio)
                    break

        elif f.kind == "checkbox":
            if not answer.selected_option:
                continue
            chosen = _closest_option(answer.selected_option, f.options)
            checkboxes = f.element.find_elements(
                By.CSS_SELECTOR, "input[type='checkbox']"
            )
            labels = [_radio_label(driver, c) for c in checkboxes]
            for checkbox, label in zip(checkboxes, labels):
                if label == chosen and not checkbox.is_selected():
                    driver.execute_script("arguments[0].click();", checkbox)
                    break

        elif f.kind == "text":
            if not answer.text_answer:
                continue
            try:
                _fill_text_field(driver, f.element, answer.text_answer)
            except Exception as e:
                logger.debug(f"apply_answers text fill failed: {e}")
