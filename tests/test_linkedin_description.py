from unittest.mock import MagicMock, patch

from src.job import Job
from src.job_sources.linkedin import search


def _driver(html: str, heading_text: str = ""):
    driver = MagicMock()
    driver.page_source = html
    driver.execute_script.return_value = heading_text
    return driver


def test_description_from_known_selector():
    job = Job(link="https://www.linkedin.com/jobs/view/1/")
    driver = _driver(
        '<div class="jobs-description__content">Python role</div>'
    )
    with patch.object(search.time, "sleep"):
        search.load_job_description(driver, job)
    assert job.description == "Python role"


def test_description_from_heading_when_classes_changed():
    job = Job(link="https://www.linkedin.com/jobs/view/1/")
    driver = _driver("<div></div>", heading_text="About the job\nBuild APIs")
    with patch.object(search.time, "sleep"):
        search.load_job_description(driver, job)
    assert "Build APIs" in job.description


def test_empty_description_when_page_never_hydrates():
    job = Job(link="https://www.linkedin.com/jobs/view/1/")
    driver = _driver("<div></div>", heading_text="")
    ticks = iter(range(0, 1000, 5))
    with patch.object(search.time, "sleep"), patch.object(
        search.time, "monotonic", side_effect=lambda: next(ticks)
    ):
        search.load_job_description(driver, job)
    assert job.description == ""


def test_description_from_guest_page_without_opening_it_in_account():
    """8.10: залогиненная страница перестала отдавать «About the job» —
    описание берём с публичной гостевой страницы, вакансию в аккаунте
    не открываем."""
    job = Job(link="https://www.linkedin.com/jobs/view/42/", external_id="42")
    driver = _driver("<div></div>")
    response = MagicMock(
        status_code=200,
        text='<div class="show-more-less-html__markup">Build APIs</div>',
    )
    with patch.object(search.httpx, "get", return_value=response) as get:
        search.load_job_description(driver, job)
    assert job.description == "Build APIs"
    assert get.call_args.args[0].endswith("/jobPosting/42")
    driver.get.assert_not_called()


def test_falls_back_to_account_page_when_guest_fails():
    job = Job(link="https://www.linkedin.com/jobs/view/42/", external_id="42")
    driver = _driver(
        '<div class="jobs-description__content">Python role</div>'
    )
    with patch.object(
        search.httpx, "get", return_value=MagicMock(status_code=429)
    ), patch.object(search.time, "sleep"):
        search.load_job_description(driver, job)
    assert job.description == "Python role"
