import tempfile
from pathlib import Path

import main
from src.job import Job
from src.job_sources.contact_book import ContactBook, contacts_from_text
from src.job_sources.hr_replies import DraftStore
from src.job_sources.telegram_conversations import TelegramConversations
from src.webui import api
from tests.test_webui_api import client  # noqa: F401  (fixture)


def test_contacts_from_text():
    text = (
        "Пишите @anna_hr или на hr [at] acme [dot] ru, анкета: "
        "t.me/acme_jobs_bot. "
        "Профиль: https://www.linkedin.com/in/anna-k/ . Почта anna@acme.io. "
        "Канал @python_jobs_channel"
    )
    found = {
        (c["kind"], c["value"])
        for c in contacts_from_text(text, exclude=("python_jobs_channel",))
    }
    assert found == {
        ("email", "hr@acme.ru"),
        ("email", "anna@acme.io"),
        ("telegram", "anna_hr"),
        ("telegram", "acme_jobs_bot"),
        ("linkedin", "https://www.linkedin.com/in/anna-k"),
    }
    # "@acme" внутри адреса — не Telegram
    assert ("telegram", "acme") not in found


def test_contact_book_merges_by_company_and_dedupes():
    with tempfile.TemporaryDirectory() as tmp:
        book = ContactBook(Path(tmp))
        key = book.add(
            "ООО «Acme»",
            [{"kind": "email", "value": "HR@acme.ru", "source": "a"}],
            vacancy={"title": "Dev", "link": "https://j/1", "source": "hh"},
        )
        assert (
            book.add(
                "Acme",
                [
                    {"kind": "email", "value": "hr@acme.ru", "source": "b"},
                    {"kind": "telegram", "value": "anna_hr", "source": "b"},
                ],
                vacancy={
                    "title": "Dev",
                    "link": "https://j/1",
                    "source": "hh",
                },
            )
            == key
        )
        card = book.get(key)
        assert [c["value"] for c in card["contacts"]] == [
            "HR@acme.ru",
            "anna_hr",
        ]
        assert len(card["vacancies"]) == 1
        # пост без компании — отдельная карточка по контакту
        assert (
            book.add(
                "", [{"kind": "telegram", "value": "solo_hr", "source": "c"}]
            )
            == "@solo_hr"
        )
        assert book.add("", []) == ""


def test_collect_telegram_post_fills_job_and_book(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(
            main,
            "parse_post",
            lambda text, key: {
                "company": "Acme",
                "role": "Python Backend Developer",
                "salary": "от 250 000 ₽",
            },
        )
        job = Job(
            role="🔥 Вакансия!!!",
            source="telegram",
            link="https://t.me/geekjobs/5",
            description="Acme ищет Python Backend. Пишите @anna_hr или "
            "jobs@acme.ru. #geekjobs @geekjobs",
        )
        params = {"outputFileDirectory": Path(tmp)}
        # ИИ-проверка выключена — пост разобран, но в Базу ничего: контакты
        # из постов попадают туда только после проверки или отправки.
        assert main._collect_telegram_post(params, "key", job, "geekjobs")
        assert (job.company, job.role, job.salary) == (
            "Acme",
            "Python Backend Developer",
            "от 250 000 ₽",
        )
        assert ContactBook(Path(tmp)).all() == {}

        # Проверка включена: в Базу — только email, выбранный ИИ; @anna_hr
        # остаётся в посте до отправки сообщения.
        params["telegram"] = {"llm_vacancy_filter": True}
        checked = []
        monkeypatch.setattr(
            main,
            "_llm_check_post",
            lambda text, key, emails: checked.append(emails)
            or (True, "jobs@acme.ru"),
        )
        assert main._collect_telegram_post(params, "key", job, "geekjobs")
        assert checked == [["jobs@acme.ru"]]
        (card,) = ContactBook(Path(tmp)).all().values()
        assert [c["value"] for c in card["contacts"]] == ["jobs@acme.ru"]
        assert card["contacts"][0]["source"] == "пост в @geekjobs"
        assert card["vacancies"][0]["text"].startswith("Acme ищет")

        # «Не вакансия» (резюме, реклама) — пост пропускается, База не растёт.
        monkeypatch.setattr(
            main, "_llm_check_post", lambda text, key, emails: (False, "")
        )
        assert not main._collect_telegram_post(params, "key", job, "geekjobs")
        assert len(ContactBook(Path(tmp)).all()) == 1


def test_contacts_api_status_backfill_and_draft(
    client, monkeypatch  # noqa: F811
):
    ctx = api.get_ctx()
    ctx.applied_log.record(
        Job(
            role="Dev",
            company="Multiply",
            link="https://j/m",
            source="direct",
            external_id="m",
        ),
        "",
        "",
        "dry_run",
        7,
        [],
        contacts=["jobs@multiply.cloud"],
    )
    cards = client.get(
        "/api/contacts"
    ).json()  # первый вызов переносит старые контакты
    assert [(c["company"], c["status"]) for c in cards] == [
        ("Multiply", "new")
    ]

    book = ContactBook(ctx.output_folder)
    book.add(
        "Acme",
        [{"kind": "telegram", "value": "anna_hr", "source": "пост"}],
        vacancy={
            "title": "Python Dev",
            "link": "https://t.me/x/1",
            "source": "telegram",
            "text": "Ищем Python-разработчика",
        },
    )
    TelegramConversations(
        ctx.output_folder / "telegram_conversations.json"
    ).record_outbound("anna_hr", "Привет", "https://t.me/x/1")
    statuses = {
        c["company"]: c["status"] for c in client.get("/api/contacts").json()
    }
    assert statuses == {"Multiply": "new", "Acme": "written"}

    monkeypatch.setattr(
        api,
        "generate_first_message",
        lambda *a: {"subject": "Dev — Application", "text": "Hello"},
    )
    (ctx.config["dataFolder"] / "resume.pdf").write_bytes(b"%PDF-fake")
    res = client.post(
        "/api/contacts/draft",
        json={
            "key": "multiply",
            "kind": "email",
            "value": "jobs@multiply.cloud",
        },
    ).json()
    draft = DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE).get(
        res["code"]
    )
    assert (draft["channel"], draft["subject"], draft["job_link"]) == (
        "email",
        "Dev — Application",
        "https://j/m",
    )
    statuses = {
        c["company"]: c["status"] for c in client.get("/api/contacts").json()
    }
    assert statuses["Multiply"] == "draft"
    assert (
        client.post(
            "/api/contacts/draft",
            json={"key": "multiply", "kind": "linkedin", "value": "x"},
        ).status_code
        == 400
    )


def test_contact_draft_routes_resume_by_language_and_404s_when_missing(
    client, monkeypatch  # noqa: F811
):
    """Тот же баг, что был в тренажёре интервью и кнопке "📎 Резюме" в
    Telegram: /api/contacts/draft жёстко зашивал resume.pdf независимо
    от языка компании. Международная карточка (не РФ/СНГ) должна
    получить resume_linkedin.pdf, а без резюме вообще — понятную 404,
    не "ИИ не ответил"."""
    ctx = api.get_ctx()
    book = ContactBook(ctx.output_folder)
    key = book.add(
        "GlobalTech Inc",
        [{"kind": "email", "value": "jobs@globaltech.io", "source": "site"}],
        website="globaltech.io",
        vacancy={
            "title": "Python Backend Engineer",
            "link": "https://globaltech.io/careers/1",
            "source": "direct",
            "text": "We are looking for a Python backend engineer.",
        },
    )

    # Резюме вообще не загружено — понятная ошибка, не 502 "ИИ не ответил".
    res = client.post(
        "/api/contacts/draft",
        json={"key": key, "kind": "email", "value": "jobs@globaltech.io"},
    )
    assert res.status_code == 404
    assert "резюме" in res.json()["detail"].lower()

    resumes_used = []
    monkeypatch.setattr(
        api,
        "generate_first_message",
        lambda resume, *a: resumes_used.append(Path(resume).name)
        or {"subject": "Application", "text": "Hello"},
    )
    (ctx.config["dataFolder"] / "resume_linkedin.pdf").write_bytes(
        b"%PDF-fake-en"
    )
    res = client.post(
        "/api/contacts/draft",
        json={"key": key, "kind": "email", "value": "jobs@globaltech.io"},
    )
    assert res.status_code == 200
    assert resumes_used == ["resume_linkedin.pdf"]
    draft = DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE).get(
        res.json()["code"]
    )
    assert draft["russian"] is False
    assert draft["resume"] == "resume_linkedin.pdf"


def test_dossier_collects_from_site_pages(monkeypatch):
    import httpx

    from src.direct import dossier

    pages = {
        "https://acme.io": "<style>@media x{}</style><a "
        'href="/careers">Careers</a>'
        '<a href="https://other.com/jobs">x</a>',
        "https://acme.io/careers": "Write jobs@acme.io or <a "
        'href="https://t.me/acme_hr">TG</a>'
        ' <a href="https://www.linkedin.com/in/anna-acme/">Anna</a>',
    }

    def fake_get(url, **kw):
        if url not in pages:
            raise httpx.ConnectError("nope")
        return httpx.Response(
            200, text=pages[url], request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(dossier.httpx, "get", fake_get)
    card = {
        "company": "Acme",
        "website": "",
        "contacts": [
            {"kind": "email", "value": "x@gmail.com"},
            {"kind": "email", "value": "old@acme.io"},
        ],
        "vacancies": [],
    }
    assert dossier.candidate_websites(card) == ["acme.io"]
    result = dossier.collect_dossier(card)
    assert result["website"] == "https://acme.io"
    found = {(c["kind"], c["value"], c["source"]) for c in result["contacts"]}
    assert found == {
        ("email", "jobs@acme.io", "сайт: /careers"),
        ("telegram", "acme_hr", "сайт: /careers"),
        (
            "linkedin",
            "https://www.linkedin.com/in/anna-acme",
            "сайт: /careers",
        ),
    }


def test_dossier_reports_hunter_api_errors(monkeypatch):
    """Раньше любая ошибка Hunter (неверный ключ, исчерпанный лимит,
    сеть) глушилась except httpx.HTTPError: pass — "+0 контактов"
    выглядело неотличимо от "у компании правда нет HR-почт в Hunter"."""
    import httpx

    from src.direct import dossier

    monkeypatch.setattr(
        dossier.httpx,
        "get",
        lambda url, **kw: httpx.Response(
            200, text="", request=httpx.Request("GET", url)
        ),
    )
    card = {
        "company": "Acme",
        "website": "https://acme.io",
        "contacts": [],
        "vacancies": [],
    }

    def raise_status(status):
        def _raise(domain, key):
            request = httpx.Request(
                "GET", "https://api.hunter.io/v2/email-count"
            )
            response = httpx.Response(status, request=request)
            raise httpx.HTTPStatusError(
                str(status), request=request, response=response
            )

        return _raise

    monkeypatch.setattr(dossier, "hunter_hr_contacts", raise_status(401))
    result = dossier.collect_dossier(card, hunter_key="bad-key")
    assert "ключ" in result["hunter_error"]

    monkeypatch.setattr(dossier, "hunter_hr_contacts", raise_status(429))
    result = dossier.collect_dossier(card, hunter_key="a-key")
    assert "лимит" in result["hunter_error"]

    monkeypatch.setattr(
        dossier,
        "hunter_hr_contacts",
        lambda domain, key: (_ for _ in ()).throw(httpx.ConnectError("nope")),
    )
    result = dossier.collect_dossier(card, hunter_key="a-key")
    assert "сеть" in result["hunter_error"]

    # Без ключа Hunter вообще не спрашиваем — не сообщать пустую ошибку.
    monkeypatch.setattr(dossier, "hunter_hr_contacts", raise_status(401))
    result = dossier.collect_dossier(card, hunter_key="")
    assert result["hunter_error"] == ""


def test_todo_and_find_hr(client, monkeypatch):  # noqa: F811
    ctx = api.get_ctx()
    assert client.get("/api/todo").json()["items"] == []

    ctx.applied_log.record(
        Job(
            role="Python Dev",
            company="Acme",
            link="https://hh.ru/vacancy/1",
            source="headhunter",
            external_id="1",
        ),
        "",
        "",
        "applied",
        8,
        [],
    )
    ctx.applied_log.update_reply_state(
        "headhunter", "1", "Приглашение на интервью"
    )
    DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE).add(
        "hr_anna", "Ответ", "reply", ""
    )

    todo = client.get("/api/todo").json()
    ids = {i["id"]: i for i in todo["items"]}
    assert ids["drafts"]["count"] == 1 and ids["drafts"]["view"] == "replies"
    assert ids["interviews"]["count"] == 1
    assert "replies" not in ids  # интервью — своей строкой, не «новый ответ»
    assert todo["badges"]["replies"] == 1

    monkeypatch.setattr(
        api,
        "collect_dossier",
        lambda card, key: {
            "website": "https://acme.io",
            "contacts": [
                {
                    "kind": "email",
                    "value": "jobs@acme.io",
                    "source": "сайт: /careers",
                    "source_url": "https://acme.io/careers",
                }
            ],
        },
    )
    res = client.post(
        "/api/contacts/from-application",
        json={"source": "headhunter", "external_id": "1"},
    ).json()
    assert res == {"key": "acme", "added": 1, "message": ""}
    card = ContactBook(ctx.output_folder).get("acme")
    assert card["website"] == "https://acme.io"
    assert card["vacancies"][0]["source"] == "headhunter"
    assert client.get("/api/outreach/summary").json()["available"] == 1

    monkeypatch.setattr(
        api,
        "collect_dossier",
        lambda card, key: {"website": "", "contacts": []},
    )
    ctx.applied_log.record(
        Job(
            role="Dev",
            company="NoSite",
            link="https://hh.ru/vacancy/2",
            source="headhunter",
            external_id="2",
        ),
        "",
        "",
        "applied",
        8,
        [],
    )
    res = client.post(
        "/api/contacts/from-application",
        json={"source": "headhunter", "external_id": "2"},
    ).json()
    assert (
        res["key"] == "nosite" and "Сайт компании не найден" in res["message"]
    )


def test_classify_error_does_not_mistake_stack_addresses_for_401():
    raw = (
        "Message: timeout: Timed out receiving message from renderer: 75.000\n"
        "Stacktrace:\n0   chromedriver   0x00000001072ac93a chromedriver + "
        "4098362\n"
        "1   chromedriver   0x0000000106f401f5 chromedriver + 442869"
    )
    assert "не загрузилась" in api._classify_error(raw)["summary"]
    assert (
        "API-ключ"
        not in api._classify_error("stack 0x0000000106f401f5")["summary"]
    )
    assert (
        "API-ключ"
        in api._classify_error("Error code: 401 - invalid key")["summary"]
    )
    assert (
        "Chrome закрылся"
        in api._classify_error(
            "Message: invalid session id: session deleted as the browser "
            "has closed the connection"
        )["summary"]
    )
