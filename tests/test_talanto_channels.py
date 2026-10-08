"""Каналы из вакансий Talanto идут в список парсера, личные адреса — нет."""

import json

import yaml

from src.job_sources.talanto.channels import (
    CACHE_FILE,
    route_telegram_handles,
)


class _FakeClient:
    kinds = {"jobs_it": "channel", "recruiter_anna": "person"}
    asked: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def entity_kind(self, name):
        _FakeClient.asked.append(name)
        return self.kinds.get(name, "missing")


def _setup(tmp_path, channels=("old_channel",)):
    data = tmp_path / "data"
    output = data / "output"
    output.mkdir(parents=True)
    (output / ".telegram_session.session").write_text("x")
    (data / "secrets.yaml").write_text(
        yaml.safe_dump({"telegram": {"api_id": 1, "api_hash": "h"}})
    )
    (data / "work_preferences.yaml").write_text(
        "telegram:\n  channels:\n"
        + "".join(f"  - {c}\n" for c in channels)
        + "  auto_message: false\n"
    )
    return {
        "dataFolder": data,
        "outputFileDirectory": output,
        "secretsFile": data / "secrets.yaml",
        "telegram": {"channels": list(channels)},
    }


def test_channel_is_added_person_is_not(tmp_path):
    params = _setup(tmp_path)
    _FakeClient.asked = []
    added = route_telegram_handles(
        params,
        ["jobs_it", "recruiter_anna", "old_channel", "jobs_it"],
        client_factory=_FakeClient,
    )
    assert added == ["jobs_it"]
    cfg = yaml.safe_load(
        (params["dataFolder"] / "work_preferences.yaml").read_text()
    )
    assert cfg["telegram"]["channels"] == ["old_channel", "jobs_it"]
    assert cfg["telegram"]["auto_message"] is False
    # уже известный канал не спрашиваем, дубль — один раз
    assert sorted(_FakeClient.asked) == ["jobs_it", "recruiter_anna"]
    cache = json.loads(
        (params["outputFileDirectory"] / CACHE_FILE).read_text()
    )
    assert cache == {"jobs_it": "channel", "recruiter_anna": "person"}


def test_cached_answers_are_not_asked_again(tmp_path):
    params = _setup(tmp_path)
    (params["outputFileDirectory"] / CACHE_FILE).write_text(
        json.dumps({"jobs_it": "channel", "recruiter_anna": "person"})
    )
    _FakeClient.asked = []
    added = route_telegram_handles(
        params, ["jobs_it", "recruiter_anna"], client_factory=_FakeClient
    )
    assert added == ["jobs_it"] and _FakeClient.asked == []


def test_without_telegram_login_nothing_happens(tmp_path):
    params = _setup(tmp_path)
    (params["outputFileDirectory"] / ".telegram_session.session").unlink()
    assert route_telegram_handles(params, ["jobs_it"]) == []


def test_talanto_contacts_have_their_own_source_group():
    from src.webui.api import _source_group, _source_kind

    assert _source_group("Talanto: контакты") == "Talanto"
    assert _source_kind("Talanto: текст вакансии") == "talanto"
    assert _source_kind("Сайты компаний (x)") == "sites"
    assert _source_kind("посты") == "vacancy"
