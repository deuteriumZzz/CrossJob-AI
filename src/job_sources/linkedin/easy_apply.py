import time

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
) -> bool:
    """Проводит кандидата через многошаговую форму Easy Apply. Возвращает
    True, если отклик отправлен (или был бы отправлен, в dry-run режиме);
    False — если форма упёрлась в то, что нельзя безопасно обработать:
    вакансия пропускается, а не обрабатывается наугад.

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
        logger.warning(f"No Easy Apply button on {job.link}, skipping.")
        return False
    time.sleep(2)

    fields: list = []
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

        try:
            form = driver.find_element(By.CSS_SELECTOR, MODAL_SELECTOR)
        except Exception:
            form = None
        fields = []
        if form is not None:
            check_required_consent_checkboxes(driver, form)
            fields = scrape_visible_fields(driver, form)
            if fields:
                answers = draft_answers(
                    fields,
                    job,
                    resume_text,
                    profile_text,
                    cover_letter,
                    llm_api_key,
                )
                apply_answers(driver, fields, answers)

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
                f"Easy Apply stuck (no Next/Submit) on {job.link} — "
                f"skipping. Fields on this step: "
                f"{[(f.kind, f.text) for f in fields]}"
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
        f"Easy Apply exceeded {MAX_STEPS} steps on {job.link} — skipping. "
        f"Fields on last step: {[(f.kind, f.text) for f in fields]}"
    )
    _dismiss(driver)
    return False


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
