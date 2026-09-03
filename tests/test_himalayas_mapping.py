from src.job_sources.himalayas.mapping import parse_search_html
from src.job_sources.himalayas.search import _slugify


def _card(company_slug, job_slug, title, company_name, location=None):
    """Форма карточки поиска, подтверждённая вживую 2026-09-02: на
    каждой карточке ДВЕ ссылки на вакансию — невидимый оверлей на всю
    карточку (текст только для скринридера "View job", идёт первым в
    DOM) и отдельная ссылка на заголовок с реальным текстом вакансии."""
    href = f"/companies/{company_slug}/jobs/{job_slug}"
    flag_html = (
        f'<div><img data-testid="circle-country-flag"><span>'
        f"{location}</span></div>"
        if location
        else ""
    )
    return f"""
    <article>
      <a class="absolute inset-0" href="{href}"><span class="sr-only">View job</span></a>
      {flag_html}
      <a href="{href}"><span>{title}</span></a>
      <a href="/companies/{company_slug}">{company_name}</a>
      <a href="/companies/{company_slug}/salaries">{company_name}'s Salaries</a>
      <a href="/signup/talent?action=save-job:{company_slug}:{job_slug}">Sign up to save this job</a>
    </article>
    """


SEARCH_HTML = _card(
    "acme",
    "senior-python-developer",
    "Senior Python Developer",
    "Acme Inc",
    "United States only",
) + _card(
    "beta-corp",
    "backend-engineer",
    "Backend Engineer",
    "Beta Corp",
)


def test_parse_search_html_prefers_real_title_over_view_job_overlay():
    jobs = parse_search_html(SEARCH_HTML)
    assert [j.external_id for j in jobs] == [
        "acme/senior-python-developer",
        "beta-corp/backend-engineer",
    ]
    first = jobs[0]
    assert first.role == "Senior Python Developer"
    assert first.company == "Acme Inc"
    assert first.location == "United States only"
    assert first.link == (
        "https://himalayas.app/companies/acme/jobs/senior-python-developer"
    )
    assert first.source == "himalayas"
    assert first.apply_method == "himalayas_manual"


def test_parse_search_html_missing_flag_gives_empty_location():
    jobs = parse_search_html(SEARCH_HTML)
    second = jobs[1]
    assert second.role == "Backend Engineer"
    assert second.location == ""


def test_parse_search_html_dedupes_repeated_cards():
    jobs = parse_search_html(SEARCH_HTML + SEARCH_HTML)
    assert len(jobs) == 2


def test_parse_search_html_ignores_articles_without_job_links():
    jobs = parse_search_html(
        '<article><a href="/companies/acme">Acme</a></article>'
    )
    assert jobs == []


def test_slugify_normalizes_position():
    assert _slugify("Software Engineer") == "software-engineer"
    assert _slugify("  C++ / Backend  ") == "c-backend"
