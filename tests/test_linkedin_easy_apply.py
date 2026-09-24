from unittest.mock import MagicMock, patch

from selenium.common.exceptions import StaleElementReferenceException

from src.job_sources.linkedin.easy_apply import _click, run_easy_apply


def test_click_skips_element_that_goes_stale_during_visibility_check():
    """Между find_elements() и is_displayed() узел может протухнуть на
    живой SPA-странице (подтверждено живым прогоном) — раньше это
    исключение вылетало необработанным прямо из _click, обрывая весь
    прогон run_easy_apply/search_and_apply_linkedin на текущей
    вакансии вместо пропуска одного протухшего узла."""
    stale_el = MagicMock()
    stale_el.is_displayed.side_effect = StaleElementReferenceException("stale")

    good_el = MagicMock()
    good_el.is_displayed.return_value = True

    driver = MagicMock()
    driver.find_elements.return_value = [stale_el, good_el]

    assert _click(driver, "//button") is True
    good_el.click.assert_called_once()


def test_run_easy_apply_retries_button_click_before_giving_up():
    """SPA-рендер вакансии не всегда успевает за 2с — один sleep+click
    ложно скипал хорошо подходящие вакансии. Проверяем, что при
    отсутствующей кнопке даётся несколько попыток, а не одна."""
    job = MagicMock()
    job.link = "https://www.linkedin.com/jobs/view/123/"

    driver = MagicMock()
    driver.find_elements.return_value = []  # no "No longer accepting" text

    with patch(
        "src.job_sources.linkedin.easy_apply._click", return_value=False
    ) as fake_click, patch("src.job_sources.linkedin.easy_apply.time.sleep"):
        submitted, reason = run_easy_apply(
            driver,
            job,
            "resume.pdf",
            "resume text",
            "profile text",
            "cover letter",
            "llm-api-key",
            dry_run=True,
        )

    assert submitted is False
    assert reason == "no_button"
    assert fake_click.call_count == 8


def test_run_easy_apply_recognizes_closed_posting():
    """Вакансия могла быть открыта в момент поиска и закрыться к
    моменту отклика ("No longer accepting applications" прямо на
    странице, подтверждено живьём 2026-09-12) — это не баг разбора
    формы, отдельное сообщение в логе вместо общего "no button"."""
    job = MagicMock()
    job.link = "https://www.linkedin.com/jobs/view/123/"

    driver = MagicMock()
    driver.find_elements.return_value = [MagicMock()]  # "No longer accepting"

    with patch(
        "src.job_sources.linkedin.easy_apply._click", return_value=False
    ), patch("src.job_sources.linkedin.easy_apply.time.sleep"), patch(
        "src.job_sources.linkedin.easy_apply.logger"
    ) as fake_logger:
        submitted, reason = run_easy_apply(
            driver,
            job,
            "resume.pdf",
            "resume text",
            "profile text",
            "cover letter",
            "llm-api-key",
            dry_run=True,
        )

    assert submitted is False
    assert reason == "closed"
    fake_logger.warning.assert_not_called()
    assert "no longer accepting" in fake_logger.info.call_args[0][0].lower()


def test_run_easy_apply_scrapes_and_applies_answers_per_step():
    """Один шаг формы — один вызов scrape/draft/apply на dynamic_form,
    не жёстко прописанные паттерны по типам полей (см. историю в
    dynamic_form.py). submit жмётся сразу же (find_element на форму
    возвращает MagicMock без реальных <p> — scrape_visible_fields
    вернёт пустой список полей естественно, без моков на неё)."""
    job = MagicMock()
    job.link = "https://www.linkedin.com/jobs/view/123/"
    job.role = "Backend Engineer"
    job.company = "Acme"

    driver = MagicMock()
    driver.find_element.return_value = MagicMock()  # MODAL_SELECTOR match
    driver.find_elements.return_value = []  # no <p> tags -> no fields

    click_sequence = [True, True]  # Easy Apply button, then Submit

    def fake_click(driver_arg, xpath):
        return click_sequence.pop(0) if click_sequence else False

    with patch(
        "src.job_sources.linkedin.easy_apply._click", side_effect=fake_click
    ), patch("src.job_sources.linkedin.easy_apply.time.sleep"), patch(
        "src.job_sources.linkedin.easy_apply.draft_answers"
    ) as fake_draft:
        submitted, reason = run_easy_apply(
            driver,
            job,
            "resume.pdf",
            "resume text",
            "profile text",
            "cover letter",
            "llm-api-key",
            dry_run=True,
        )

    assert submitted is True
    assert reason == ""
    fake_draft.assert_not_called()  # no fields scraped -> no LLM call


def test_run_easy_apply_reports_stuck_reason_when_no_next_or_submit():
    """Форма без Submit и без Next/Review на текущем шаге — не race
    condition (вакансию не закрыли), а реально непройденная форма.
    Статус должен отличаться от "closed", чтобы дашборд не путал
    сломанную форму с нормальным устареванием вакансии."""
    job = MagicMock()
    job.link = "https://www.linkedin.com/jobs/view/123/"
    job.role = "Backend Engineer"
    job.company = "Acme"

    driver = MagicMock()
    driver.find_element.return_value = MagicMock()  # MODAL_SELECTOR match
    driver.find_elements.return_value = []  # no <p> tags -> no fields

    click_sequence = [True]  # Easy Apply button only — no Submit, no Next

    def fake_click(driver_arg, xpath):
        return click_sequence.pop(0) if click_sequence else False

    with patch(
        "src.job_sources.linkedin.easy_apply._click", side_effect=fake_click
    ), patch("src.job_sources.linkedin.easy_apply.time.sleep"):
        submitted, reason = run_easy_apply(
            driver,
            job,
            "resume.pdf",
            "resume text",
            "profile text",
            "cover letter",
            "llm-api-key",
            dry_run=True,
        )

    assert submitted is False
    assert reason == "stuck"


if __name__ == "__main__":
    test_click_skips_element_that_goes_stale_during_visibility_check()
    test_run_easy_apply_retries_button_click_before_giving_up()
    test_run_easy_apply_scrapes_and_applies_answers_per_step()
    test_run_easy_apply_reports_stuck_reason_when_no_next_or_submit()
    print("All tests passed.")
