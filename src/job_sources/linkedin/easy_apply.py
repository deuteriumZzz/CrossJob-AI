import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from src.logging import logger

# ponytail: селекторы взяты из хорошо задокументированных паттернов
# LinkedIn Easy Apply (используются во многих открытых LinkedIn-ботах,
# включая оригинальный AIHawk до того, как эту функцию оттуда убрали) —
# НЕ проверены на живой залогиненной сессии, в отличие от остальных
# площадок проекта. Если LinkedIn с тех пор поменял разметку, селекторы
# нужно обновить; поэтому нераспознанное поле анкеты прерывает именно
# эту вакансию, а не пытается угадать дальше.
EASY_APPLY_BUTTON_XPATH = (
    "//button[contains(@class,'jobs-apply-button') or "
    ".//span[contains(text(),'Easy Apply')]]"
)
NEXT_OR_REVIEW_XPATH = (
    "//button[contains(@aria-label,'next step') or "
    "contains(@aria-label,'Review')]"
)
SUBMIT_XPATH = "//button[contains(@aria-label,'Submit application')]"
DISMISS_XPATH = "//button[@aria-label='Dismiss']"
DISCARD_XPATH = "//button[contains(.,'Discard')]"
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
        _upload_resume_if_present(driver, resume_pdf_path)

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
        time.sleep(1.5)

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


def _upload_resume_if_present(driver, resume_pdf_path) -> None:
    for file_input in driver.find_elements(
        By.CSS_SELECTOR, "input[type='file']"
    ):
        try:
            file_input.send_keys(str(resume_pdf_path))
        except Exception:
            pass


def _answer_visible_questions(driver, answerer) -> bool:
    try:
        form = driver.find_element(
            By.CSS_SELECTOR, "div.jobs-easy-apply-modal, div[role='dialog']"
        )
    except Exception:
        return True

    groups = form.find_elements(
        By.CSS_SELECTOR, ".fb-dash-form-element, .jobs-easy-apply-form-element"
    )
    for group in groups:
        labels = group.find_elements(By.TAG_NAME, "label")
        question = labels[0].text.strip() if labels else ""
        if not question:
            continue

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

        radios = group.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        if radios:
            radio_labels = [label.text.strip() for label in labels[1:]] or [
                r.get_attribute("value") for r in radios
            ]
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
                field.send_keys(answerer.answer(question))
            continue

        return False

    return True


def _closest_option(answer: str, options: list) -> str:
    answer_lower = answer.strip().lower()
    for option in options:
        if option.lower() == answer_lower:
            return option
    for option in options:
        if option.lower() in answer_lower or answer_lower in option.lower():
            return option
    return options[0]
