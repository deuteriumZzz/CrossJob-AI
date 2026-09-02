from src.job_sources.linkedin.answerer import _options_hint


def test_options_hint_lists_options_when_given():
    hint = _options_hint(["Yes", "No"], None)
    assert "Yes" in hint and "No" in hint


def test_options_hint_mentions_char_limit_for_short_text_field():
    hint = _options_hint(None, 20)
    assert "20" in hint


def test_options_hint_empty_when_neither_given():
    assert _options_hint(None, None) == ""


def test_options_hint_prefers_options_over_max_length():
    # select/radio branches never pass both — options wins if they did.
    hint = _options_hint(["Yes", "No"], 20)
    assert "Yes" in hint
    assert "at most 20" not in hint


if __name__ == "__main__":
    test_options_hint_lists_options_when_given()
    test_options_hint_mentions_char_limit_for_short_text_field()
    test_options_hint_empty_when_neither_given()
    test_options_hint_prefers_options_over_max_length()
    print("All tests passed.")
