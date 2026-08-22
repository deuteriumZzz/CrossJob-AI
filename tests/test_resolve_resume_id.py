import pytest

import main


class _FakeClient:
    def __init__(self, resumes):
        self._resumes = resumes

    def list_resumes(self):
        return self._resumes


def test_explicit_resume_id_wins_without_calling_api():
    client = _FakeClient(resumes=None)  # would blow up if called
    result = main._resolve_resume_id(client, "abc123", "headhunter")
    assert result == "abc123"


def test_single_resume_on_platform_is_auto_used():
    client = _FakeClient(resumes=[{"id": "only-one"}])
    result = main._resolve_resume_id(client, None, "headhunter")
    assert result == "only-one"


def test_multiple_resumes_raises_with_ids_listed():
    client = _FakeClient(resumes=[{"id": "first"}, {"id": "second"}])
    with pytest.raises(main.ConfigError) as exc_info:
        main._resolve_resume_id(client, None, "headhunter")
    assert "first" in str(exc_info.value)
    assert "second" in str(exc_info.value)


def test_no_resumes_on_platform_raises():
    client = _FakeClient(resumes=[])
    with pytest.raises(main.ConfigError):
        main._resolve_resume_id(client, None, "headhunter")


if __name__ == "__main__":
    test_explicit_resume_id_wins_without_calling_api()
    test_single_resume_on_platform_is_auto_used()
    test_multiple_resumes_raises_with_ids_listed()
    test_no_resumes_on_platform_raises()
    print("All tests passed.")
