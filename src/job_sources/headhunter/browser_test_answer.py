from __future__ import annotations

from typing import Callable

from selenium.webdriver.common.by import By

from src.logging import logger

# ponytail: селекторы НЕ подтверждены прямым просмотром живой страницы
# (нет доступа к вакансии с прикреплённым тестом на живом аккаунте) —
# та же конвенция, что у browser_replies.py/bump_resume: широкие *=
# подстроковые совпадения вместо точных data-qa, деградация до "тест не
# найден" вместо падения, если разметка не совпала.
_QUESTION_BLOCK_SELECTOR = (
    '[data-qa*="test-question"], [data-qa*="vacancy-response-popup-test"]'
)
_OPTION_SELECTOR = 'input[type="radio"], input[type="checkbox"], label'
_FREE_TEXT_SELECTOR = 'textarea, input[type="text"]'


def answer_vacancy_test_if_present(
    driver, ai_answer_fn: Callable[[str], str] | None = None
) -> bool:
    """Обнаруживает модалку теста/анкеты вакансии после клика
    "Откликнуться" и пытается ответить на каждый вопрос. Возвращает
    True, если тест был найден (попытка ответа сделана, не обязательно
    успешная — см. per-question логирование), False — если модалки нет
    и обычный флоу отклика (письмо/submit) продолжается как раньше.

    Эвристика для вопросов с вариантами ответа перенесена из
    hh-applicant-tool (operations/apply_vacancies.py:_solve_vacancy_test) —
    единственная часть их логики теста, которую стоило перенести:
    сам автор называл её грубым приближением, не надёжной логикой,
    держим тот же статус здесь."""
    blocks = driver.find_elements(By.CSS_SELECTOR, _QUESTION_BLOCK_SELECTOR)
    if not blocks or not blocks[0].is_displayed():
        return False

    logger.info(
        f"Обнаружен тест/анкета вакансии ({len(blocks)} блок(ов)) — "
        "отвечаем эвристикой/AI, см. docstring answer_vacancy_test_if_present "
        "про статус селекторов."
    )
    for block in blocks:
        if block.is_displayed():
            _answer_one_question(block, ai_answer_fn)
    return True


def _answer_one_question(
    block, ai_answer_fn: Callable[[str], str] | None
) -> None:
    options = block.find_elements(By.CSS_SELECTOR, _OPTION_SELECTOR)
    if options:
        _answer_multiple_choice(options)
        return

    free_text_fields = block.find_elements(
        By.CSS_SELECTOR, _FREE_TEXT_SELECTOR
    )
    if not free_text_fields or not free_text_fields[0].is_displayed():
        logger.warning(
            "Вопрос теста вакансии без узнаваемых полей ответа — "
            "пропускаем (см. ponytail про непроверенные селекторы)."
        )
        return
    _answer_free_text(free_text_fields[0], block.text or "", ai_answer_fn)


def _answer_multiple_choice(options: list) -> None:
    # ponytail: эвристика в лоб из hh-applicant-tool — предпочесть вариант
    # со словом "да", иначе средний по счёту (автор: "по статистике
    # правильный ответ чаще посередине" — не доказано, просто fallback).
    yes_option = next(
        (o for o in options if "да" in (o.text or "").strip().lower()), None
    )
    chosen = yes_option or options[len(options) // 2]
    try:
        chosen.click()
    except Exception as e:
        logger.warning(f"Не удалось выбрать вариант ответа теста: {e}")


def _answer_free_text(
    field, question_text: str, ai_answer_fn: Callable[[str], str] | None
) -> None:
    # Сторонние ссылки в вопросе теста никогда не обрабатываем
    # автоматически — то же правило, что у find_external_link для
    # внешних форм в чате (browser_replies.py): не вводим данные туда,
    # куда пользователь явно не согласился.
    if "://" in question_text:
        logger.info(
            "Вопрос теста вакансии содержит внешнюю ссылку — не отвечаем "
            "автоматически."
        )
        return

    answer = "Да"
    if ai_answer_fn is not None:
        try:
            ai_answer = ai_answer_fn(question_text)
            if ai_answer:
                answer = ai_answer
        except Exception as e:
            logger.warning(f"AI не смог ответить на вопрос теста: {e}")

    try:
        field.send_keys(answer)
    except Exception as e:
        logger.warning(f"Не удалось ввести ответ на вопрос теста: {e}")
