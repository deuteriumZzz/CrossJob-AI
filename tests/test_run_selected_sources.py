import tempfile
from pathlib import Path
from unittest.mock import patch

import main
from src.scheduler_state import load_state


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


def test_scheduler_sources_includes_check_hh_replies():
    """check_hh_replies — не в ALL_SOURCES (не поиск+отклик, а отдельная
    проверка чата), но должен быть в словаре, который демон/веб-планировщик
    передаёт в Scheduler — иначе headhunter.auto_reply никогда не
    срабатывает сам по себе в фоне."""
    assert "check_hh_replies" not in dict(main.ALL_SOURCES)
    assert main.SCHEDULER_SOURCES["check_hh_replies"] is (
        main.check_headhunter_replies
    )
    assert dict(main.ALL_SOURCES).items() <= main.SCHEDULER_SOURCES.items()


def test_scheduler_sources_includes_check_sj_replies():
    """Тот же баг, что у check_hh_replies (не входил в ALL_SOURCES/
    Scheduler, поэтому не проверялся в фоне) — есть и у SuperJob:
    check_superjob_replies принимает один аргумент (parameters), а
    Scheduler.run_once() всегда зовёт source_map[name](parameters,
    llm_api_key) — поэтому в SCHEDULER_SOURCES она завёрнута в обёртку,
    игнорирующую llm_api_key."""
    assert "check_sj_replies" not in dict(main.ALL_SOURCES)

    calls = []
    with patch.object(
        main,
        "check_superjob_replies",
        side_effect=lambda parameters: calls.append(("sj", parameters)),
    ):
        main.SCHEDULER_SOURCES["check_sj_replies"]({"x": 1}, "key")

    assert calls == [("sj", {"x": 1})]


def test_run_selected_sources_dry_run_forces_auto_apply_off():
    """Дашборд — кнопка "Тестовый прогон": dry_run=True должен гасить
    auto_apply (и auto_message у telegram) для выбранных площадок в
    parameters, который видит source_fn, но не трогать оригинальный
    словарь (никаких следов в work_preferences.yaml)."""
    seen = {}

    def fake_hh(parameters, llm_api_key):
        seen["headhunter"] = parameters["headhunter"]["auto_apply"]

    def fake_tg(parameters, llm_api_key):
        seen["telegram"] = parameters["telegram"]["auto_message"]

    original = {
        "headhunter": {"auto_apply": True},
        "telegram": {"auto_message": True},
    }
    with patch.object(
        main, "ALL_SOURCES", [("headhunter", fake_hh), ("telegram", fake_tg)]
    ), patch.object(main, "wait_between_sources"):
        main.run_selected_sources(
            ["headhunter", "telegram"], original, "key", dry_run=True
        )

    assert seen == {"headhunter": False, "telegram": False}
    # Оригинальный dict не мутирован — work_preferences.yaml ни при
    # чём, следующий обычный прогон снова увидит настоящие значения.
    assert original["headhunter"]["auto_apply"] is True
    assert original["telegram"]["auto_message"] is True


def test_run_selected_sources_ignores_unknown_names():
    calls = []

    def fake(parameters, llm_api_key):
        calls.append("x")

    with patch.object(main, "ALL_SOURCES", [("x", fake)]), patch.object(
        main, "wait_between_sources"
    ):
        main.run_selected_sources(["x", "bogus"], {}, "key")

    assert calls == ["x"]


def test_run_selected_sources_records_scheduler_state_on_success():
    """Ручной запуск ("Запустить выбранные" в дашборде) должен обновлять
    .scheduler_state.json так же, как это делает Scheduler.run_once() —
    иначе карточка площадки на "Обзоре" показывает устаревший статус
    последнего ПЛАНОВОГО тика демона, даже когда ручные прогоны идут."""

    def fake_ok(parameters, llm_api_key):
        pass

    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        with patch.object(
            main, "ALL_SOURCES", [("ok", fake_ok)]
        ), patch.object(main, "wait_between_sources"):
            main.run_selected_sources(
                ["ok"], {"outputFileDirectory": output_folder}, "key"
            )

        state = load_state(output_folder)
        assert state["ok"]["status"] == "ok"
        assert state["ok"]["last_error"] is None
        assert state["ok"]["last_run"]


def test_run_selected_sources_records_scheduler_state_on_failure():
    def fake_fail(parameters, llm_api_key):
        raise RuntimeError("boom")

    with tempfile.TemporaryDirectory() as tmp:
        output_folder = Path(tmp)
        with patch.object(
            main, "ALL_SOURCES", [("fail", fake_fail)]
        ), patch.object(main, "notify"):
            main.run_selected_sources(
                ["fail"], {"outputFileDirectory": output_folder}, "key"
            )

        state = load_state(output_folder)
        assert state["fail"]["status"] == "error"
        assert "boom" in state["fail"]["last_error"]


if __name__ == "__main__":
    test_run_selected_sources_runs_only_named_sources_in_order()
    test_run_selected_sources_continues_after_one_source_fails()
    test_run_selected_sources_notifies_on_failure()
    test_run_selected_sources_dry_run_forces_auto_apply_off()
    test_run_selected_sources_ignores_unknown_names()
    test_run_selected_sources_records_scheduler_state_on_success()
    test_run_selected_sources_records_scheduler_state_on_failure()
    print("All tests passed.")
