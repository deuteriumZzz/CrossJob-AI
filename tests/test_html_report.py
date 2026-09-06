from src.job_sources.html_report import render_applications_html


def _entry(status: str, external_id: str) -> dict:
    return {
        "applied_at": "2026-09-07T00:00:00+00:00",
        "source": "linkedin",
        "company": "Acme",
        "link": f"https://example.com/{external_id}",
        "title": "Python Developer",
        "salary": "",
        "company_url": "",
        "status": status,
        "score": 8,
        "gaps": [],
        "cover_letter": "",
    }


def test_skipped_easy_apply_failed_goes_into_skipped_bucket():
    entries = [
        _entry("applied", "1"),
        _entry("skipped_low_fit", "2"),
        _entry("skipped_easy_apply_failed", "3"),
    ]
    html = render_applications_html(entries, {"day": 1, "week": 1, "month": 1})

    assert "1 записей" in html
    assert "2 пропущено" in html
    assert 'status-skipped_easy_apply_failed' in html


if __name__ == "__main__":
    test_skipped_easy_apply_failed_goes_into_skipped_bucket()
    print("All tests passed.")
