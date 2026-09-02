from src.job_sources.wellfound.client import slugify
from src.job_sources.wellfound.mapping import (
    parse_role_page_job_ids,
    wellfound_vacancy_to_job,
)

ROLE_PAGE_HTML = """
<div class="job-card">
  <a href="/jobs/111-senior-python-developer">Senior Python Developer</a>
</div>
<div class="job-card">
  <a href="/jobs/222-backend-engineer">Backend Engineer</a>
</div>
<div class="job-card">
  <a href="/jobs/111-senior-python-developer">Senior Python Developer</a>
</div>
"""

VACANCY_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@context": "http://schema.org/",
  "@type": "JobPosting",
  "title": "Senior Python Developer",
  "hiringOrganization": {
    "@type": "Organization",
    "name": "Acme Inc",
    "sameAs": "http://acme.example",
    "location": [
      {
        "@type": "Place",
        "address": {
          "addressLocality": "San Francisco",
          "addressCountry": "United States"
        }
      }
    ]
  },
  "description": "<p>Nужен <b>python</b>.</p>",
  "baseSalary": {
    "@type": "MonetaryAmount",
    "currency": "USD",
    "value": {"@type": "QuantitativeValue", "unitText": "YEAR",
              "minValue": 150000.0, "maxValue": 200000.0}
  }
}
</script>
</body></html>
"""


def test_parse_role_page_job_ids_dedupes():
    results = parse_role_page_job_ids(ROLE_PAGE_HTML)
    assert results == [
        ("111", "senior-python-developer"),
        ("222", "backend-engineer"),
    ]


def test_wellfound_vacancy_to_job_maps_ld_json_fields():
    job = wellfound_vacancy_to_job(
        VACANCY_HTML, "111", "senior-python-developer"
    )
    assert job.role == "Senior Python Developer"
    assert job.company == "Acme Inc"
    assert job.company_url == "http://acme.example"
    assert job.location == "San Francisco, United States"
    assert job.link == (
        "https://wellfound.com/jobs/111-senior-python-developer"
    )
    assert job.source == "wellfound"
    assert job.external_id == "111"
    assert job.apply_method == "wellfound_manual"
    assert job.salary == "150000-200000 USD/year"
    assert "python" in job.description
    assert "<" not in job.description


def test_wellfound_vacancy_to_job_missing_ld_json_degrades_gracefully():
    job = wellfound_vacancy_to_job("<html></html>", "111", "some-slug")
    assert job.link == "https://wellfound.com/jobs/111-some-slug"
    assert job.source == "wellfound"
    assert job.role == ""


def test_slugify_normalizes_position():
    assert slugify("Python Developer") == "python-developer"
    assert slugify("  C++ / Backend  ") == "c-backend"
