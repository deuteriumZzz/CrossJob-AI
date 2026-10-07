import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from src.job_sources.linkedin.dynamic_form import (
    apply_answers,
    check_required_consent_checkboxes,
    draft_answers,
    scrape_visible_fields,
    validation_errors,
)
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
    driver,
    job,
    resume_pdf_path,
    resume_text: str,
    profile_text: str,
    cover_letter: str,
    llm_api_key: str,
    dry_run: bool,
    failure_log: Optional[Path] = None,
) -> tuple[bool, str]:
    """Проводит кандидата через многошаговую форму Easy Apply. Возвращает
    (True, "") если отклик отправлен (или был бы отправлен, в dry-run
    режиме); (False, reason) — если форма упёрлась в то, что нельзя
    безопасно обработать: вакансия пропускается, а не обрабатывается
    наугад. reason разделяет "closed" (вакансию закрыли между поиском
    и откликом — нормальный race condition, не баг) от "no_button"/
    "stuck"/"exceeded_steps" (форма действительно не прошла) — вызывающий
    код в main.py пишет их в applied_log разными статусами, чтобы
    закрытые вакансии не раздували метрику реальных сломанных форм.

    ponytail: раньше вопросы разбирались жёстко прописанными паттернами
    (componentkey, конкретные атрибуты) — LinkedIn поменял разметку
    2026-09 и всё сломал молча, без единой ошибки в логе (см. историю
    в dynamic_form.py). Теперь на каждом шаге страница читается
    динамически (scrape_visible_fields) и ответы генерирует LLM одним
    батч-вызовом на все поля этого шага (draft_answers/apply_answers) —
    переживает будущие изменения вёрстки лучше, чем привязка к
    конкретным атрибутам, дороже по времени/токенам, но именно это и
    выбрано осознанно (надёжнее и медленнее)."""
    driver.get(job.link)

    # ponytail: вакансия дошла сюда уже пройдя f_AL=true в поиске (см.
    # search.py) — Easy Apply на ней точно был. Тяжёлый SPA-рендер
    # LinkedIn не всегда укладывается в 2с, из-за чего единственная
    # попытка клика ловила кнопку до её появления в DOM и хорошо
    # подходящие вакансии ложно уходили в "No Easy Apply button".
    # Поллинг вместо одного sleep+click, пока кнопка не появится.
    clicked = False
    for _ in range(8):
        if _click(driver, EASY_APPLY_BUTTON_XPATH):
            clicked = True
            break
        time.sleep(1)
    if not clicked:
        # ponytail: подтверждено живьём 2026-09-12 — вакансия, которая
        # была открыта в момент поиска, к моменту отклика уже закрыта
        # ("No longer accepting applications" прямо на странице). Это
        # не баг разбора формы, а нормальный исход гонки между поиском
        # и откликом — отдельное сообщение в логе, чтобы не гонять
        # живой браузер заново, выясняя то же самое.
        closed = driver.find_elements(
            By.XPATH, "//*[contains(text(),'No longer accepting')]"
        )
        if closed:
            logger.info(
                f"{job.link} is no longer accepting applications, skipping."
            )
            return False, "closed"
        logger.warning(f"No Easy Apply button on {job.link}, skipping.")
        log_failure(driver, job, "no_button", 0, [], failure_log)
        return False, "no_button"
    # Подтверждено живьём 2026-10-07: кнопка есть уже на недогруженной
    # странице (серые заглушки), клик по ней тогда ничего не открывает, а
    # окно формы на загруженной странице появляется не за 2с, а за
    # несколько секунд — раньше бот смотрел на пустую страницу и писал
    # "stuck (no Next/Submit)" на ВСЕХ вакансиях. Ждём окно и, если его
    # нет, жмём кнопку ещё раз.
    for attempt in range(3):
        if _wait_for_modal(driver, 10):
            break
        logger.info(
            f"Окно Easy Apply не открылось (попытка {attempt + 1}/3) на "
            f"{job.link} — жму кнопку ещё раз."
        )
        if attempt == 1:
            # Страница могла так и не догрузиться (серые заглушки на
            # месте описания) — тогда клик не доходит до обработчика.
            # Перезагрузка и пауза, потом снова клик.
            driver.refresh()
            time.sleep(8)
        _click(driver, EASY_APPLY_BUTTON_XPATH)
    else:
        logger.warning(f"Easy Apply modal never opened on {job.link}.")
        log_failure(driver, job, "no_modal", 0, [], failure_log)
        return False, "no_modal"
    time.sleep(1)

    fields: list = []
    previous_errors: list[str] = []
    repeated_errors = 0
    for step in range(1, MAX_STEPS + 1):
        # ponytail: подтверждено вживую — те же функции на той же
        # зависавшей вакансии прошли все шаги чисто, когда между ними
        # естественно появлялась пара сотен мс на чтение/парсинг DOM
        # для диагностики; без этой паузы (голый цикл) та же вакансия
        # зависала. Небольшой sleep здесь воспроизводит это "время на
        # осмотреться" перед тем, как цикл снова начнёт что-то кликать.
        time.sleep(0.8)
        _upload_resume_if_present(driver, resume_pdf_path)
        _set_phone_country_code_if_present(driver)

        try:
            form = driver.find_element(By.CSS_SELECTOR, MODAL_SELECTOR)
        except Exception:
            form = None
        fields = []
        errors: list[str] = []
        if form is not None:
            # Ошибки, оставшиеся после прошлого "Next": исправляем именно
            # их (в том числе уже заполненные поля), а не повторяем тот
            # же ответ до лимита шагов.
            errors = validation_errors(driver, form)
            check_required_consent_checkboxes(
                driver, form, labelled=bool(errors)
            )
            fields = scrape_visible_fields(
                driver, form, include_filled=bool(errors)
            )
            if fields:
                answers = draft_answers(
                    fields,
                    job,
                    resume_text,
                    profile_text,
                    cover_letter,
                    llm_api_key,
                    errors=errors or None,
                )
                logger.info(
                    f"Easy Apply шаг {step}"
                    + (f" (ошибки формы: {errors})" if errors else "")
                    + ": "
                    + "; ".join(
                        f"[{f.kind}] {f.text[:70]!r} -> "
                        f"{_answer_text(answers[f.index])[:60]!r}"
                        for f in fields
                        if f.index in answers
                    )
                )
                apply_answers(
                    driver, fields, answers, clear_first=bool(errors)
                )
        repeated_errors = (
            repeated_errors + 1 if errors and errors == previous_errors else 0
        )
        previous_errors = errors
        if repeated_errors >= 2:
            logger.warning(
                f"Easy Apply: форма трижды отклонила ответы на {job.link}: "
                f"{errors}"
            )
            log_failure(driver, job, "validation", step, fields, failure_log)
            _dismiss(driver)
            return False, "validation"

        # dry-run: до кнопки Submit дошли — это и есть «отправили бы», но
        # НЕ нажимаем её. Раньше здесь стоял _click(SUBMIT_XPATH) и в
        # dry-run: он настоящим кликом отправлял отклик, а затем только
        # писал "Would submit" (найдено 2026-10-07 — тестовый проход ушёл
        # реальными откликами).
        if dry_run:
            if _is_displayed(driver, SUBMIT_XPATH):
                logger.info(
                    f"[dry run] Would submit Easy Apply: {job.role} "
                    f"at {job.company}"
                )
                _dismiss(driver)
                return True, ""
        elif _click(driver, SUBMIT_XPATH):
            time.sleep(1)
            return True, ""

        if not _click(driver, NEXT_OR_REVIEW_XPATH):
            logger.warning(
                f"Easy Apply stuck (no Next/Submit) on {job.link} — "
                f"skipping. Fields on this step: "
                f"{[(f.kind, f.text) for f in fields]}"
            )
            log_failure(driver, job, "stuck", step, fields, failure_log)
            _dismiss(driver)
            return False, "stuck"
        # ponytail: 1.5с изначально — недостаточно, живой прогон
        # несколько раз подряд зависал на шаге "Resume" сразу после
        # перехода; похоже на гонку между переходом шага и следующей
        # попыткой взаимодействия. Не гарантия, а снижение
        # вероятности; если снова начнёт зависать — увеличивать ещё.
        time.sleep(4)

    logger.warning(
        f"Easy Apply exceeded {MAX_STEPS} steps on {job.link} — skipping. "
        f"Fields on last step: {[(f.kind, f.text) for f in fields]}"
    )
    log_failure(driver, job, "exceeded_steps", MAX_STEPS, fields, failure_log)
    _dismiss(driver)
    return False, "exceeded_steps"


def _answer_text(answer) -> str:
    return answer.selected_option or answer.text_answer or ""


def _is_displayed(driver, xpath: str) -> bool:
    for el in driver.find_elements(By.XPATH, xpath):
        try:
            if el.is_displayed():
                return True
        except StaleElementReferenceException:
            continue
    return False


def _wait_for_modal(driver, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if driver.find_elements(By.CSS_SELECTOR, MODAL_SELECTOR):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


_ERROR_SELECTOR = (
    "[role='alert'], .artdeco-inline-feedback--error, "
    "[data-test-form-element-error-messages]"
)


def log_failure(
    driver,
    job,
    reason: str,
    step: int,
    fields: list,
    failure_log: Optional[Path],
    error: str = "",
) -> None:
    """Одна строка JSON на каждый сбой Easy Apply + скриншот рядом — в
    applied_log причина пропуска не сохраняется (всё пишется как
    skipped_easy_apply_failed), и без неё не понять, на каком шаге/поле
    форма ломается. Диагностика не должна сама ронять отклик."""
    if failure_log is None:
        return
    try:
        try:
            errors = [
                e.text.strip()
                for e in driver.find_elements(By.CSS_SELECTOR, _ERROR_SELECTOR)
                if e.text.strip()
            ]
        except Exception:
            errors = []
        shot = ""
        try:
            shots = failure_log.parent / "easy_apply_failures"
            shots.mkdir(parents=True, exist_ok=True)
            job_id = str(job.link).rstrip("/").split("/")[-1] or "job"
            shot_path = shots / f"{datetime.now():%Y%m%d_%H%M%S}_{job_id}.png"
            if driver.save_screenshot(str(shot_path)):
                shot = shot_path.name
        except Exception:
            pass
        record = {
            "at": datetime.now().astimezone().isoformat(),
            "link": job.link,
            "company": job.company,
            "role": job.role,
            "reason": reason,
            "step": step,
            "fields": [[f.kind, f.text] for f in fields],
            "errors": errors[:5],
            "error": error[:300],
            "screenshot": shot,
        }
        with failure_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"Could not record Easy Apply failure: {e}")


def _click(driver, xpath: str) -> bool:
    """find_elements (не find_element) + фильтр по видимости: во время
    перехода между шагами модалка LinkedIn может держать в DOM узел
    предыдущего шага, совпадающий с тем же xpath, но скрытый — если
    он идёт первым, старый find_element(...).is_displayed() молча
    возвращал False, хотя рабочая кнопка рядом уже видна (это и есть
    "stuck (no Next/Submit)" из логов при реально доступной кнопке).
    Отдельно ретраим на ElementClickInterceptedException (кнопка
    видна, но перекрыта анимацией — прокручиваем и жмём ещё раз) и на
    StaleElementReferenceException (узел от предыдущего рендера —
    перезапрашиваем DOM), вместо того чтобы, как раньше, глушить обе
    вместе с «кнопки нет» одним bare except."""
    for attempt in range(2):
        for el in driver.find_elements(By.XPATH, xpath):
            try:
                if not el.is_displayed():
                    continue
            except StaleElementReferenceException:
                continue
            try:
                el.click()
                return True
            except ElementClickInterceptedException:
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", el
                    )
                    el.click()
                    return True
                except Exception as e:
                    logger.debug(
                        f"_click intercepted+scroll failed on {xpath}: {e}"
                    )
            except StaleElementReferenceException:
                break
            except Exception as e:
                logger.debug(f"_click failed on {xpath}: {e}")
        time.sleep(0.5)
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
