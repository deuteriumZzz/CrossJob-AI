from unittest.mock import MagicMock, patch

import httpx

from src.job_sources.github_context import fetch_github_summary


def test_fetch_github_summary_formats_profile_and_repos():
    user_response = MagicMock()
    user_response.json.return_value = {
        "html_url": "https://github.com/octocat",
        "bio": "I build things",
    }
    repos_response = MagicMock()
    repos_response.json.return_value = [
        {"name": "spoon-knife", "language": "Python", "description": "demo"}
    ]

    mock_client = MagicMock()
    mock_client.get.side_effect = [user_response, repos_response]
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False

    with patch("httpx.Client", return_value=mock_client):
        summary = fetch_github_summary("octocat")

    assert "octocat" in summary
    assert "I build things" in summary
    assert "spoon-knife" in summary
    assert "Python" in summary


def test_fetch_github_summary_returns_empty_string_on_http_error():
    with patch("httpx.Client", side_effect=httpx.ConnectError("boom")):
        assert fetch_github_summary("octocat") == ""


if __name__ == "__main__":
    test_fetch_github_summary_formats_profile_and_repos()
    test_fetch_github_summary_returns_empty_string_on_http_error()
    print("All tests passed.")
