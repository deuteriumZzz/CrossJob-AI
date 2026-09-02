import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from src.logging import logger

# ponytail: сверено на живой залогиненной сессии (2026-08-23, реальная
# 5-шаговая форма Easy Apply: Contact info → Resume → Additional
# Questions → Work authorization → Review). LinkedIn использует
# CSS-in-JS с хэшированными классами, которые меняются от сборки к
# сборке — по ним ничего не селектится стабильно, поэтому везде ниже
# либо атрибуты (role=, aria-label=, componentkey=), либо видимый
# текст кнопки. EASY_APPLY_BUTTON_XPATH/DISMISS_XPATH/DISCARD_XPATH
# подтверждены как есть, без изменений — остальное ниже было неверным
# и переписано по факту.
EASY_APPLY_BUTTON_XPATH = (
    "//button[contains(@class,'jobs-apply-button') or "
    ".//span[contains(text(),'Easy Apply')]]"
)
# Кнопки "Next"/"Review"/"Submit application" не имеют aria-label
# вообще (подтверждено — было null на живой форме), только видимый
# текст — раньше матчилось по несуществующему aria-label и НИКОГДА не
# срабатывало.
NEXT_OR_REVIEW_XPATH = (
    "//button[normalize-space(.)='Next' or normalize-space(.)='Review']"
)
SUBMIT_XPATH = "//button[normalize-space(.)='Submit application']"
DISMISS_XPATH = "//button[@aria-label='Dismiss']"
DISCARD_XPATH = "//button[contains(.,'Discard')]"
# Нативный <dialog>, не div.jobs-easy-apply-modal/div[role='dialog']
# (подтверждено — старый селектор не находит ничего на текущей
# разметке).
MODAL_SELECTOR = "dialog[data-testid='dialog']"
MAX_STEPS = 12


def run_easy_apply(
    driver, job, resume_pdf_path, answerer, dry_run: bool
) -> bool:
    """Проводит кандидата через многошаговую форму Easy Apply. Возвращает
    True, если отклик отправлен (или был бы отправлен, в dry-run режиме);
    False — если форма упёрлась в то, что нельзя безопасно обработать:
    вакансия пропускается, а не обрабатывается наугад."""
    driver.get(job.link)
    time.sleep(2)

    if not _click(driver, EASY_APPLY_BUTTON_XPATH):
        logger.warning(f"No Easy Apply button on {job.link}, skipping.")
        return False
    time.sleep(2)

    for _ in range(MAX_STEPS):
        # ponytail: подтверждено вживую — те же функции на той же
        # зависавшей вакансии прошли все шаги чисто, когда между ними
        # естественно появлялась пара сотен мс на чтение/парсинг DOM
        # для диагностики; без этой паузы (голый цикл) та же вакансия
        # зависала. Небольшой sleep здесь воспроизводит это "время на
        # осмотреться" перед тем, как цикл снова начнёт что-то кликать.
        time.sleep(0.8)
        _upload_resume_if_present(driver, resume_pdf_path)
        _set_phone_country_code_if_present(driver)

        if not _answer_visible_questions(driver, answerer):
            logger.warning(
                f"Unrecognized question type on {job.link} — "
                "skipping to be safe."
            )
            _dismiss(driver)
            return False

        if _click(driver, SUBMIT_XPATH):
            if dry_run:
                logger.info(
                    f"[dry run] Would submit Easy Apply: {job.role} "
                    f"at {job.company}"
                )
                _dismiss(driver)
            else:
                time.sleep(1)
            return True

        if not _click(driver, NEXT_OR_REVIEW_XPATH):
            logger.warning(
                f"Easy Apply stuck (no Next/Submit) on {job.link} — skipping."
            )
            _dismiss(driver)
            return False
        # ponytail: 1.5с изначально — недостаточно, живой прогон
        # несколько раз подряд зависал на шаге "Resume" сразу после
        # перехода; похоже на гонку между переходом шага и следующей
        # попыткой взаимодействия. Не гарантия, а снижение
        # вероятности; если снова начнёт зависать — увеличивать ещё.
        time.sleep(4)

    logger.warning(
        f"Easy Apply exceeded {MAX_STEPS} steps on {job.link} — skipping."
    )
    _dismiss(driver)
    return False


def _click(driver, xpath: str) -> bool:
    try:
        el = driver.find_element(By.XPATH, xpath)
        if not el.is_displayed():
            return False
        el.click()
        return True
    except Exception:
        return False


def _dismiss(driver) -> None:
    if _click(driver, DISMISS_XPATH):
        time.sleep(0.5)
        _click(driver, DISCARD_XPATH)


def _set_phone_country_code_if_present(driver) -> None:
    """Подтверждено на живой сессии: телефон на шаге "Contact info"
    уже верно предзаполнен из профиля (реальный российский номер),
    но соседний <select> с кодом страны дефолтится не по номеру, а
    по локации из резюме (Bali, Indonesia в resume_linkedin.pdf) —
    без явной правки остаётся Indonesia (+62) при российском номере,
    что делает контакт нерабочим целиком. Кандидат всегда российский,
    код страны жёстко "ru" — это гражданство/номер, а не страна
    поиска вакансий (см. RESUME_PDF_LINKEDIN/f_WT/geoId в
    search.py — те про локацию вакансии, это поле про телефон).
    Отличаем от email-select'а (у него всего 1 option) по количеству
    опций — у списка стран их 250+."""
    for select_el in driver.find_elements(By.TAG_NAME, "select"):
        options = select_el.find_elements(By.TAG_NAME, "option")
        if len(options) < 50:
            continue
        try:
            Select(select_el).select_by_value("ru")
        except Exception:
            pass
        break


def _upload_resume_if_present(driver, resume_pdf_path) -> None:
    """Подтверждено на живой сессии: на шаге "Resume" нет готового
    <input type=file> в разметке — он появляется в DOM только после
    клика на кнопку "Upload resume". execute_script — синтетический
    (untrusted) клик, а не driver-native btn.click(): trusted-клик
    иногда открывает НАСТОЯЩИЙ системный диалог выбора файла
    (подтверждено пользователем вживую), который Selenium закрыть не
    может — untrusted-клик такого не делает ни разу за все живые
    проверки. Кликаем на "Upload resume" каждый раз, когда кнопка
    видна, не проверяя заранее наличие input — пробовали пропускать
    повторный клик, если input уже в DOM, но именно это давало
    зависания (input мог "протухнуть" между перерендерами шага, и
    send_keys в него не долетал до React)."""
    for btn in driver.find_elements(
        By.XPATH, "//button[normalize-space(.)='Upload resume']"
    ):
        if btn.is_displayed():
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1)
            break
    for file_input in driver.find_elements(
        By.CSS_SELECTOR, "input[type='file']"
    ):
        try:
            file_input.send_keys(str(resume_pdf_path))
        except Exception:
            pass


def _answer_visible_questions(driver, answerer) -> bool:
    """Группа вопроса — [componentkey^="ea_focus_"] (подтверждено
    живьём на шаге "Additional Questions"): текст вопроса — первый
    <p> внутри группы (не <label> — labels пустые, текст радио-опций
    лежит в aria-label самого элемента role=radio, а не в label рядом
    с input, как раньше предполагалось). select/checkbox — не
    встречены живьём ни на одной реальной вакансии, оставлены как
    best-effort фолбэк на случай других форм."""
    try:
        form = driver.find_element(By.CSS_SELECTOR, MODAL_SELECTOR)
    except Exception:
        return True

    groups = form.find_elements(By.CSS_SELECTOR, "[componentkey^='ea_focus_']")
    for group in groups:
        try:
            question = group.find_element(By.TAG_NAME, "p").text.strip()
        except Exception:
            question = ""
        if not question:
            continue
        question = question.rstrip("*").strip()

        selects = group.find_elements(By.TAG_NAME, "select")
        if selects:
            select = Select(selects[0])
            options = [
                o.text.strip() for o in select.options if o.text.strip()
            ]
            if options:
                select.select_by_visible_text(
                    _closest_option(
                        answerer.answer(question, options), options
                    )
                )
            continue

        radios = group.find_elements(By.CSS_SELECTOR, "[role='radio']")
        if radios:
            radio_labels = [
                r.get_attribute("aria-label") or "" for r in radios
            ]
            radio_labels = [label for label in radio_labels if label]
            if not radio_labels:
                return False
            chosen = _closest_option(
                answerer.answer(question, radio_labels), radio_labels
            )
            for radio, radio_label in zip(radios, radio_labels):
                if radio_label == chosen:
                    driver.execute_script("arguments[0].click();", radio)
                    break
            continue

        checkboxes = group.find_elements(
            By.CSS_SELECTOR, "input[type='checkbox']"
        )
        if checkboxes:
            for checkbox in checkboxes:
                if not checkbox.is_selected():
                    driver.execute_script("arguments[0].click();", checkbox)
            continue

        text_inputs = group.find_elements(
            By.CSS_SELECTOR,
            "input[type='text'], input[type='tel'], "
            "input[type='number'], input[type='email'], textarea",
        )
        if text_inputs:
            field = text_inputs[0]
            if not field.get_attribute("value"):
                field.send_keys(
                    answerer.answer(
                        question, max_length=_field_max_length(field)
                    )
                )
            continue

        return False

    return True


def _field_max_length(field) -> Optional[int]:
    """HTML `maxlength` поля, если он есть и валиден (подтверждено
    живьём — короткие поля на LinkedIn вроде "hours per week"/
    "compensation" ограничены 20-200 символами, счётчик "0/20" виден
    прямо в форме)."""
    raw = field.get_attribute("maxlength")
    if raw and raw.isdigit():
        return int(raw)
    return None


def _closest_option(answer: str, options: list) -> str:
    answer_lower = answer.strip().lower()
    for option in options:
        if option.lower() == answer_lower:
            return option
    for option in options:
        if option.lower() in answer_lower or answer_lower in option.lower():
            return option
    return options[0]
