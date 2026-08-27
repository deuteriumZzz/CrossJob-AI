from __future__ import annotations

import time
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

# Подтверждено на живом скриншоте пользователя: некоторые вакансии
# уводят с "Откликнуться" не в модалку на той же странице, а на
# отдельную "Vacancy response" / "Answer the questions" по этому URL —
# в отличие от _QUESTION_BLOCK_SELECTOR, разметку полей внутри самой
# страницы никто не подтверждал, поэтому answer_full_page_questionnaire
# ниже опирается на URL и HTML-семантику (name у radio, label[for]),
# а не на догаданные data-qa/классы hh.
VACANCY_RESPONSE_URL_MARKER = "/applicant/vacancy_response"
_SUBMIT_BUTTON_TEXT_MARKERS = ("respond", "откликнуться", "отправить", "send")


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


def answer_full_page_questionnaire(
    driver, ai_answer_fn: Callable[[str], str] | None = None
) -> bool:
    """Отвечает на анкету на отдельной странице .../applicant/
    vacancy_response (см. VACANCY_RESPONSE_URL_MARKER) — детект по
    URL, а не по разметке, потому что сам переход туда подтверждён
    живым скриншотом пользователя, а вёрстка полей внутри — нет.
    Группирует radio-инпуты по стандартному HTML-атрибуту name (одна
    группа = один вопрос) и находит текст вопроса для textarea/
    input[text] через <label for=...> — то есть переиспользует ту же
    эвристику ответов (_answer_multiple_choice/_answer_free_text), что
    и модалка теста, только определяет вопросы иначе.

    Возвращает True, только если реально нашли и нажали кнопку
    отправки по видимому тексту — иначе False, чтобы вызывающий код
    (apply()) не считал отклик отправленным, пока форма не отправлена
    на самом деле."""
    if VACANCY_RESPONSE_URL_MARKER not in driver.current_url:
        return False

    logger.info(
        "HH перевёл на отдельную страницу анкеты отклика "
        f"({driver.current_url}) — отвечаем на вопросы эвристикой/AI."
    )

    for options in _group_radio_options_by_name(driver):
        _answer_multiple_choice(options)

    for field in driver.find_elements(By.CSS_SELECTOR, _FREE_TEXT_SELECTOR):
        if not field.is_displayed():
            continue
        question_text = _label_text_for(driver, field)
        _answer_free_text(field, question_text, ai_answer_fn)

    submit = _find_button_by_visible_text(driver, _SUBMIT_BUTTON_TEXT_MARKERS)
    if submit is None:
        logger.warning(
            "Анкета отклика на "
            f"{driver.current_url} заполнена, но кнопка отправки не "
            "найдена по тексту — отклик мог не уйти, проверьте вручную."
        )
        return False

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});", submit
    )
    driver.execute_script("arguments[0].click();", submit)
    time.sleep(1.5)
    return True


class _RadioOption:
    """<input type=radio> сам по себе не имеет .text (это не текстовый
    контент) — _answer_multiple_choice ищет "да" именно по .text,
    поэтому без обёртки эвристика "предпочесть да" никогда бы не
    сработала на настоящих radio-инпутах. click() бьёт по самому
    радио, а не по label — оба варианта валидны в HTML, но так
    исключается двойной toggle, если label визуально не оборачивает
    инпут."""

    def __init__(self, driver, radio):
        self._radio = radio
        self.text = _label_text_for(driver, radio)

    def click(self) -> None:
        self._radio.click()


def _group_radio_options_by_name(driver) -> list[list]:
    groups: dict[str, list] = {}
    for radio in driver.find_elements(
        By.CSS_SELECTOR, 'input[type="radio"]'
    ):
        if not radio.is_displayed():
            continue
        name = radio.get_attribute("name") or ""
        groups.setdefault(name, []).append(_RadioOption(driver, radio))
    return list(groups.values())


def _label_text_for(driver, field) -> str:
    """Текст вопроса/варианта ответа для произвольного поля (radio,
    textarea, input[text]) — пробует по нарастающей: явную связку
    label[for=id], затем ближайший <label>-предок (частый паттерн для
    radio: <label><input type=radio> Да</label>), и только в конце —
    ближайший предшествующий текстовый узел через JS (для полей без
    явной связки, например текстового вопроса перед textarea)."""
    field_id = field.get_attribute("id")
    if field_id:
        labels = driver.find_elements(
            By.CSS_SELECTOR, f'label[for="{field_id}"]'
        )
        if labels:
            return labels[0].text.strip()
    try:
        ancestor_labels = field.find_elements(
            By.XPATH, "./ancestor::label[1]"
        )
        if ancestor_labels:
            return ancestor_labels[0].text.strip()
    except Exception:
        pass
    try:
        return (
            driver.execute_script(
                "let n = arguments[0];"
                "while (n && !n.previousElementSibling && n.parentElement)"
                " { n = n.parentElement; }"
                "return n && n.previousElementSibling"
                " ? n.previousElementSibling.innerText : '';",
                field,
            )
            or ""
        ).strip()
    except Exception:
        return ""


def _find_button_by_visible_text(driver, needles: tuple[str, ...]):
    for el in driver.find_elements(
        By.CSS_SELECTOR, 'button, a[role="button"]'
    ):
        if not el.is_displayed():
            continue
        text = (el.text or "").strip().lower()
        if any(needle in text for needle in needles):
            return el
    return None
