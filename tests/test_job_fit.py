from src.job_sources.job_fit import FitAssessment, classify_fit


def test_classify_fit_below_min_score_is_skip():
    assert classify_fit(1, min_score=4, good_score=7) == "skip"
    assert classify_fit(3, min_score=4, good_score=7) == "skip"


def test_classify_fit_between_min_and_good_is_weak():
    assert classify_fit(4, min_score=4, good_score=7) == "weak"
    assert classify_fit(6, min_score=4, good_score=7) == "weak"


def test_classify_fit_at_or_above_good_score_is_good():
    assert classify_fit(7, min_score=4, good_score=7) == "good"
    assert classify_fit(10, min_score=4, good_score=7) == "good"


def test_fit_assessment_defaults_to_empty_gaps():
    assert FitAssessment(score=8).gaps == []


def test_fit_assessment_rejects_out_of_range_score():
    try:
        FitAssessment(score=11)
        assert False, "expected a validation error"
    except Exception:
        pass


if __name__ == "__main__":
    test_classify_fit_below_min_score_is_skip()
    test_classify_fit_between_min_and_good_is_weak()
    test_classify_fit_at_or_above_good_score_is_good()
    test_fit_assessment_defaults_to_empty_gaps()
    test_fit_assessment_rejects_out_of_range_score()
    print("All tests passed.")
