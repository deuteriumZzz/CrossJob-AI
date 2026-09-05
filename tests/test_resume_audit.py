from src.job_sources.resume_audit import (
    AtsHiringManagerCheck,
    ResumeAuditScore,
    _format_ats_check_for_context,
    _format_audit_for_context,
)


def test_format_audit_for_context_includes_all_nonempty_fields():
    audit = ResumeAuditScore(
        match_score=72,
        missing_keywords=["Kubernetes", "Terraform"],
        red_flags=["Нет цифр в разделе опыта"],
        strong_sections=["Опыт: конкретные проекты"],
        weak_sections=["Summary: слишком общий"],
        comparison_note="Слабее, чем у типичного сильного кандидата.",
    )
    text = _format_audit_for_context(audit)
    assert "72/100" in text
    assert "Kubernetes, Terraform" in text
    assert "Нет цифр в разделе опыта" in text
    assert "Summary: слишком общий" in text
    assert "Слабее, чем у типичного сильного кандидата." in text


def test_format_audit_for_context_skips_empty_lists():
    audit = ResumeAuditScore(
        match_score=40,
        missing_keywords=[],
        red_flags=[],
        strong_sections=[],
        weak_sections=[],
        comparison_note="",
    )
    text = _format_audit_for_context(audit)
    assert text == "Оценка соответствия: 40/100"


def test_format_ats_check_for_context():
    check = AtsHiringManagerCheck(
        ats_pass=False,
        keywords_present=["Python"],
        keywords_missing=["Docker"],
        formatting_issues=["Таблица в разделе навыков"],
        hiring_manager_bucket="возможно",
        skip_reasons=["Summary без конкретики"],
    )
    text = _format_ats_check_for_context(check)
    assert "не пройдёт" in text
    assert "Docker" in text
    assert "Таблица в разделе навыков" in text
    assert "возможно" in text
    assert "Summary без конкретики" in text


def demo() -> None:
    test_format_audit_for_context_includes_all_nonempty_fields()
    test_format_audit_for_context_skips_empty_lists()
    test_format_ats_check_for_context()
    print("ok")


if __name__ == "__main__":
    demo()
