from src.job_sources.careerist.mapping import (
    careerist_vacancy_to_job,
    parse_search_results,
)

SEARCH_HTML = """
<a class="vak_hl_ vacancyLink" href="https://careerist.ru/vakansii/python-razrabotchik-111.html">Python разработчик</a>
<a class="vak_hl_ vacancyLink" href="https://careerist.ru/vakansii/backend-engineer-222.html">Backend Engineer</a>
<a class="vak_hl_ vacancyLink" href="https://careerist.ru/vakansii/python-razrabotchik-111.html">Python разработчик</a>
"""

VACANCY_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Python разработчик",
  "hiringOrganization": {"@type": "Organization", "name": "Acme LLC"},
  "description": "<p>Нужен <b>питонист</b>.</p>",
  "baseSalary": {
    "@type": "MonetaryAmount",
    "currency": "RUR",
    "value": {"@type": "QuantitativeValue", "unitText": "MONTH",
              "minValue": 150000, "maxValue": 250000}
  },
  "jobLocation": {
    "@type": "Place",
    "address": {"addressRegion": "Москва", "addressLocality": "Крылатское"}
  }
}
</script>
</body></html>
"""


def test_parse_search_results_dedupes():
    results = parse_search_results(SEARCH_HTML)
    assert results == [
        ("111", "/vakansii/python-razrabotchik-111.html"),
        ("222", "/vakansii/backend-engineer-222.html"),
    ]


def test_careerist_vacancy_to_job_maps_ld_json_fields():
    job = careerist_vacancy_to_job(
        VACANCY_HTML, "111", "/vakansii/python-razrabotchik-111.html"
    )
    assert job.role == "Python разработчик"
    assert job.company == "Acme LLC"
    assert job.location == "Москва, Крылатское"
    assert job.link == "https://careerist.ru/vakansii/python-razrabotchik-111.html"
    assert job.source == "careerist"
    assert job.external_id == "111"
    assert job.apply_method == "careerist_manual"
    assert job.salary == "150000-250000 RUR/month"
    assert "питонист" in job.description
    assert "<" not in job.description


def test_careerist_vacancy_to_job_missing_ld_json_degrades_gracefully():
    job = careerist_vacancy_to_job("<html></html>", "111", "/vakansii/x.html")
    assert job.link == "https://careerist.ru/vakansii/x.html"
    assert job.source == "careerist"
    assert job.role == ""


if __name__ == "__main__":
    test_parse_search_results_dedupes()
    test_careerist_vacancy_to_job_maps_ld_json_fields()
    test_careerist_vacancy_to_job_missing_ld_json_degrades_gracefully()
    print("All tests passed.")
