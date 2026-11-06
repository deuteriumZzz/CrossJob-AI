from __future__ import annotations

import re
import sys
import time
from typing import Callable

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from src.logging import logger
from src.utils.chrome_utils import is_shown

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
_SELECT_ALL = Keys.COMMAND if sys.platform == "darwin" else Keys.CONTROL

# Живьём 2026-11-06 (Битрикс24, vacancy_response): radio прозрачные
# (opacity 0) — Selenium считал их невидимыми, бот не отвечал ни на один
# вариант, и HH не принимал форму. У textarea нет <label for> — бот не
# видел вопроса, и AI ответил сопроводительным на «В каком городе вы
# проживаете?». Вопрос — ближайший предок с текстом (минус подписи
# вариантов/текущий ответ), варианты — подписи radio.
_QUESTIONS_JS = r"""
const textOf = (el, minus) => {
  for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
    let t = n.innerText || '';
    for (const m of minus) if (m) t = t.split(m).join('');
    if (t.trim()) return t.trim();
  }
  return '';
};
const groups = {};
// Галочки «выберите несколько» (вживую 6.11, МТС) — только вопросы анкеты
// (task_*), отвечаем одним вариантом; «Свой вариант» требует текста — не берём.
const label = r => ((r.labels && r.labels[0]) || r.parentElement).innerText.trim();
for (const r of document.querySelectorAll('input[type="radio"], input[type="checkbox"][name^="task_"]'))
  (groups[r.name] = groups[r.name] || []).push(r);
const radios = Object.values(groups).map(all => {
  const els = all.filter(r => !/свой вариант|own variant/i.test(label(r)));
  const opts = els.map(label);
  let top = all[0].parentElement;
  while (top.parentElement && top.parentElement.querySelectorAll('input[type="radio"], input[type="checkbox"]').length === all.length)
    top = top.parentElement;
  let q = top.innerText;
  for (const o of opts) q = q.split(o).join('');
  return {q: (q.trim() || textOf(top, opts)).slice(0, 500), opts, els, checked: all.some(r => r.checked)};
});
const texts = [...document.querySelectorAll('textarea, input[type="text"]')]
  .filter(t => t.offsetParent !== null)
  .map(t => ({q: textOf(t, [t.value]).slice(0, 500), el: t}));
return {radios, texts};
"""


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
    blocks = [b for b in blocks if is_shown(b)]
    if not blocks:
        return False

    logger.info(
        f"Обнаружен тест/анкета вакансии ({len(blocks)} блок(ов)) — "
        "отвечаем эвристикой/AI, см. docstring answer_vacancy_test_if_present "
        "про статус селекторов."
    )
    for block in blocks:
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
    free_text_fields = [f for f in free_text_fields if is_shown(f)]
    if not free_text_fields:
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
    # Слово «да», не подстрока: «Не работал ранее с данными языками».
    yes_option = next(
        (o for o in options if re.search(r"\bда\b", (o.text or "").lower())),
        None,
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
    живым скриншотом пользователя. Вопросы и варианты — _QUESTIONS_JS.
    Вариант выбирает AI; не выбрал/не совпало — группа остаётся пустой,
    HH форму не примет, и apply() честно не засчитает отклик (без
    угадывания «да»/середины, как в модалке). Текстовые поля HH хранит
    черновиком между попытками — старый ответ стираем, а не дописываем.

    True — кнопку отправки нашли и нажали. Ушёл ли отклик, решает
    HeadHunterBrowserClient._responded по странице вакансии."""
    if VACANCY_RESPONSE_URL_MARKER not in driver.current_url:
        return False

    logger.info(
        "HH перевёл на отдельную страницу анкеты отклика "
        f"({driver.current_url}) — отвечаем на вопросы через AI."
    )

    questions = driver.execute_script(_QUESTIONS_JS) or {}
    for group in questions.get("radios") or []:
        _answer_radio_group(driver, group, ai_answer_fn)
    for text in questions.get("texts") or []:
        field = text["el"]
        try:
            if field.get_attribute("value"):
                field.send_keys(_SELECT_ALL, "a")
                field.send_keys(Keys.BACKSPACE)
        except Exception as e:
            logger.warning(f"Не удалось стереть старый ответ анкеты: {e}")
        _answer_free_text(field, text["q"], ai_answer_fn)

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


def _answer_radio_group(
    driver, group: dict, ai_answer_fn: Callable[[str], str] | None
) -> None:
    if group.get("checked") or ai_answer_fn is None:
        return
    options = group["opts"]
    try:
        numbered = "\n".join(f"{i}. {o}" for i, o in enumerate(options, 1))
        reply = ai_answer_fn(
            f"{group['q']}\nВарианты ответа:\n{numbered}\n"
            "Ответьте только номером одного варианта, без пояснений."
        )
    except Exception as e:
        logger.warning(f"AI не смог выбрать вариант анкеты: {e}")
        return
    index = _pick_option(reply or "", options)
    if index is None:
        logger.warning(
            f"Ответ AI {reply!r} не совпал ни с одним вариантом вопроса "
            f"{group['q'][:80]!r} — вопрос без ответа, HH форму не примет."
        )
        return
    driver.execute_script("arguments[0].click();", group["els"][index])


def _pick_option(reply: str, options: list[str]) -> int | None:
    """Индекс варианта: точное совпадение, текст варианта в ответе (AI
    любит добавить пояснение) или голый номер «2»/«2.». Номер из прозы
    («у меня 4 года») не угадываем — вопрос останется без ответа."""
    number = re.fullmatch(r"\s*(\d{1,2})[.)]?\s*", reply)
    if number and 1 <= int(number.group(1)) <= len(options):
        return int(number.group(1)) - 1

    def norm(text: str) -> str:
        return re.sub(r"[–—]", "-", text).strip().strip(".").lower()

    answer = norm(reply)
    normalized = [norm(o) for o in options]
    if answer in normalized:
        return normalized.index(answer)
    hits = [
        (answer.find(o), i) for i, o in enumerate(normalized) if o and o in answer
    ]
    return min(hits)[1] if hits else None


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
