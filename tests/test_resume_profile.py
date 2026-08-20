from src.job_sources.resume_profile import _parse_positions


def test_parse_positions_strips_bullets_and_blank_lines():
    output = "- Python разработчик\n• Backend Engineer\n\nData Engineer\n"
    assert _parse_positions(output) == [
        "Python разработчик",
        "Backend Engineer",
        "Data Engineer",
    ]


def test_parse_positions_handles_empty_output():
    assert _parse_positions("") == []


if __name__ == "__main__":
    test_parse_positions_strips_bullets_and_blank_lines()
    test_parse_positions_handles_empty_output()
    print("All tests passed.")
