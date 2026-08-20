from src.job_sources.linkedin.easy_apply import _closest_option


def test_closest_option_exact_match_case_insensitive():
    assert _closest_option("Yes", ["Yes", "No"]) == "Yes"
    assert _closest_option("yes", ["Yes", "No"]) == "Yes"


def test_closest_option_partial_match():
    assert (
        _closest_option("3-5 years", ["0-2 years", "3-5 years", "6+ years"])
        == "3-5 years"
    )


def test_closest_option_falls_back_to_first_option():
    assert (
        _closest_option(
            "something completely unrelated", ["Option A", "Option B"]
        )
        == "Option A"
    )


if __name__ == "__main__":
    test_closest_option_exact_match_case_insensitive()
    test_closest_option_partial_match()
    test_closest_option_falls_back_to_first_option()
    print("All tests passed.")
