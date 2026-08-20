from unittest.mock import patch

import main


def test_run_selected_sources_runs_only_named_sources_in_order():
    calls = []

    def fake_a(parameters, llm_api_key):
        calls.append("a")

    def fake_b(parameters, llm_api_key):
        calls.append("b")

    with patch.object(
        main, "ALL_SOURCES", [("a", fake_a), ("b", fake_b)]
    ), patch.object(main, "wait_between_sources") as mock_wait:
        main.run_selected_sources(["b", "a"], {}, "key")

    assert calls == ["b", "a"]
    assert mock_wait.call_count == 1


def test_run_selected_sources_continues_after_one_source_fails():
    calls = []

    def fake_ok(parameters, llm_api_key):
        calls.append("ok")

    def fake_fail(parameters, llm_api_key):
        raise RuntimeError("boom")

    with patch.object(
        main, "ALL_SOURCES", [("fail", fake_fail), ("ok", fake_ok)]
    ), patch.object(main, "wait_between_sources"):
        main.run_selected_sources(["fail", "ok"], {}, "key")

    assert calls == ["ok"]


def test_run_selected_sources_notifies_on_failure():
    def fake_fail(parameters, llm_api_key):
        raise RuntimeError("boom")

    with patch.object(
        main, "ALL_SOURCES", [("fail", fake_fail)]
    ), patch.object(main, "notify") as mock_notify:
        main.run_selected_sources(["fail"], {}, "key")

    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    assert args[0] == {}
    assert "fail" in args[1]
    assert "boom" in args[1]


def test_run_selected_sources_ignores_unknown_names():
    calls = []

    def fake(parameters, llm_api_key):
        calls.append("x")

    with patch.object(main, "ALL_SOURCES", [("x", fake)]), patch.object(
        main, "wait_between_sources"
    ):
        main.run_selected_sources(["x", "bogus"], {}, "key")

    assert calls == ["x"]


if __name__ == "__main__":
    test_run_selected_sources_runs_only_named_sources_in_order()
    test_run_selected_sources_continues_after_one_source_fails()
    test_run_selected_sources_notifies_on_failure()
    test_run_selected_sources_ignores_unknown_names()
    print("All tests passed.")
