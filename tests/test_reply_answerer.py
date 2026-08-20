from src.job_sources.reply_answerer import (
    build_hh_resume_summary,
    build_preferences_summary,
)


def test_build_preferences_summary_includes_configured_fields():
    summary = build_preferences_summary(
        {
            "salary_expectations": "200000-250000 RUR",
            "remote": True,
            "hybrid": False,
            "onsite": False,
            "locations": ["Москва", "Санкт-Петербург"],
        }
    )
    assert "200000-250000 RUR" in summary
    assert "удалённо" in summary
    assert "Москва" in summary


def test_build_preferences_summary_handles_empty_parameters():
    assert build_preferences_summary({}) == "Не указаны."


def test_build_hh_resume_summary_extracts_salary_and_skills():
    summary = build_hh_resume_summary(
        {
            "salary": {"amount": 250000, "currency": "RUR"},
            "skill_set": ["Python", "Django"],
        }
    )
    assert "250000" in summary
    assert "Python" in summary


def test_build_hh_resume_summary_handles_missing_data():
    assert build_hh_resume_summary({}) == "Недоступно."
    assert build_hh_resume_summary(None) == "Недоступно."
    assert build_hh_resume_summary({"other_field": "x"}) == "Не указано."


if __name__ == "__main__":
    test_build_preferences_summary_includes_configured_fields()
    test_build_preferences_summary_handles_empty_parameters()
    test_build_hh_resume_summary_extracts_salary_and_skills()
    test_build_hh_resume_summary_handles_missing_data()
    print("All tests passed.")
