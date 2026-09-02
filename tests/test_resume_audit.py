from unittest.mock import patch

from src.job_sources.resume_audit import (
    _AUDIT_PROMPT,
    _ATS_HIRING_MANAGER_PROMPT,
    _REWRITE_EXPERIENCE_PROMPT,
    run_full_resume_audit,
)


def test_audit_prompt_has_expected_variables_and_rules():
    assert set(_AUDIT_PROMPT.input_variables) == {"resume", "job_description"}
    template = _AUDIT_PROMPT.messages[0].prompt.template
    assert "Отвечай только на русском" in template
    assert "Оценку соответствия от 0 до 100" in template


def test_ats_hiring_manager_prompt_has_expected_variables_and_rules():
    assert set(_ATS_HIRING_MANAGER_PROMPT.input_variables) == {
        "resume",
        "job_description",
        "audit_result",
    }
    template = _ATS_HIRING_MANAGER_PROMPT.messages[0].prompt.template
    assert "фильтра ATS" in template
    assert "менеджера по найму" in template


def test_rewrite_experience_prompt_has_expected_variables_and_rules():
    assert set(_REWRITE_EXPERIENCE_PROMPT.input_variables) == {
        "resume",
        "audit_result",
        "ats_hiring_manager_result",
    }
    template = _REWRITE_EXPERIENCE_PROMPT.messages[0].prompt.template
    assert "формулу Google XYZ" in template
    assert "ничего не придумывай" in template


def test_run_full_resume_audit_chains_steps_in_order():
    with patch(
        "src.job_sources.resume_audit.run_resume_audit",
        return_value="audit-text",
    ) as mock_audit, patch(
        "src.job_sources.resume_audit.run_ats_hiring_manager_check",
        return_value="ats-hm-text",
    ) as mock_ats_hm, patch(
        "src.job_sources.resume_audit.run_rewrite_experience",
        return_value="rewritten-text",
    ) as mock_rewrite:
        result = run_full_resume_audit("resume", "job description", "key")

    mock_audit.assert_called_once_with("resume", "job description", "key")
    mock_ats_hm.assert_called_once_with(
        "resume", "job description", "audit-text", "key"
    )
    mock_rewrite.assert_called_once_with(
        "resume", "audit-text", "ats-hm-text", "key"
    )
    assert result == {
        "audit": "audit-text",
        "ats_hiring_manager": "ats-hm-text",
        "rewritten_experience": "rewritten-text",
    }


if __name__ == "__main__":
    test_audit_prompt_has_expected_variables_and_rules()
    test_ats_hiring_manager_prompt_has_expected_variables_and_rules()
    test_rewrite_experience_prompt_has_expected_variables_and_rules()
    test_run_full_resume_audit_chains_steps_in_order()
    print("All tests passed.")
