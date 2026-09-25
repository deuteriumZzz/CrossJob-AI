import json
import io
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import main
from src.direct import campaign as camp
from src.direct import importer
from src.job_sources.contact_book import ContactBook
from src.job_sources.hr_replies import DraftStore
from src.webui import api
from tests.test_webui_api import client  # noqa: F401  (fixture)

CSV = ("Компания;E-mail;Имя HR;Сайт;На что сделать упор\n"
       "Acme;hr@acme.io, careers@acme.io;Анна;acme.io;финтех, Python\n"
       "Beta;bad-address;;beta.io;\n"
       "Gamma;HR@acme.io;;;\n").encode("utf-8")


def _xlsx(rows):
    buf = io.BytesIO()
    shared = [v for r in rows for v in r]
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml",
                   '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   + "".join(f"<si><t>{v}</t></si>" for v in shared) + "</sst>")
        cells, i = [], 0
        for r_idx, row in enumerate(rows, start=1):
            cs = []
            for c_idx, _ in enumerate(row):
                cs.append(f'<c r="{"AB"[c_idx]}{r_idx}" t="s"><v>{i}</v></c>'); i += 1
            cells.append(f'<row r="{r_idx}">{"".join(cs)}</row>')
        z.writestr("xl/worksheets/sheet1.xml",
                   '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   + "".join(cells) + "</sheetData></worksheet>")
    return buf.getvalue()


def test_read_csv_and_xlsx_by_headers():
    table, _ = importer.read_file("list.csv", CSV)
    rows = importer.rows_from_table(table)
    assert [(r["company"], r["email"], r["name"], r["emphasis"]) for r in rows] == [
        ("Acme", "hr@acme.io", "Анна", "финтех, Python"),
        ("Beta", "bad-address", "", ""),
        ("Gamma", "hr@acme.io", "", ""),
    ]
    table, _ = importer.read_file("list.xlsx", _xlsx([["Company", "Email"], ["Delta", "jobs@delta.dev"]]))
    assert importer.rows_from_table(table)[0]["email"] == "jobs@delta.dev"


def test_preview_checks(monkeypatch):
    monkeypatch.setattr(importer, "domain_accepts_mail", lambda d: d != "nomx.io")
    rows = importer.rows_from_table(importer.read_file("list.csv", CSV)[0])
    rows.append({**rows[0], "company": "NoMX", "email": "hr@nomx.io", "row": 9})
    result = importer.preview(rows, known_emails=set(), written_emails=set())
    checks = [(i["company"], i["check"]) for i in result["items"]]
    assert checks == [("Acme", "ok"), ("Beta", "bad"), ("Gamma", "duplicate"), ("NoMX", "bad")]
    assert result["stats"]["ok"] == 1 and result["stats"]["duplicate"] == 1
    written = importer.preview(rows[:1], set(), {"hr@acme.io"})
    assert written["items"][0]["check"] == "written"


def test_free_text_drops_invented_emails(monkeypatch):
    fake = SimpleNamespace(companies=[
        SimpleNamespace(company="Acme", email="hr@acme.io", name="", website="", title="", emphasis=""),
        SimpleNamespace(company="Ghost", email="guessed@ghost.io", name="", website="", title="", emphasis=""),
    ])
    llm = SimpleNamespace(with_structured_output=lambda schema: SimpleNamespace(invoke=lambda p: fake))
    import src.job_sources.llm_provider as lp
    monkeypatch.setattr(lp, "get_chat_llm", lambda *a, **k: llm)
    rows = importer.rows_from_text("Acme пишите hr@acme.io. Ghost — без почты.", "key")
    assert [(r["company"], r["email"]) for r in rows] == [("Acme", "hr@acme.io"), ("Ghost", "")]


def _import(client, name, data):  # noqa: F811
    import time

    token = client.post("/api/import/preview", files={"file": (name, data)}).json()["token"]
    for _ in range(100):
        job = client.get(f"/api/import/preview/{token}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("импорт не закончился")


def test_big_text_import_in_chunks_keeps_every_email(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(importer, "domain_accepts_mail", lambda d: True)
    monkeypatch.setattr(importer, "CHUNK_CHARS", 60)
    calls = []

    def invoke(prompt):
        calls.append(prompt)
        if "Acme" in prompt:
            return SimpleNamespace(companies=[SimpleNamespace(
                company="Acme", email="hr@acme.io", name="Ann", website="", title="", emphasis="")])
        raise RuntimeError("LLM timeout")  # часть не разобралась — адрес всё равно не теряем

    llm = SimpleNamespace(with_structured_output=lambda schema: SimpleNamespace(invoke=invoke))
    import src.job_sources.llm_provider as lp
    monkeypatch.setattr(lp, "get_chat_llm", lambda *a, **k: llm)
    api.get_ctx().llm_api_key = "key"
    text = "Acme — пишите hr@acme.io, Анна\n" + "x" * 50 + "\nBeta Corp jobs@mail.beta.co.uk\n"
    job = _import(client, "list.txt", text.encode())
    assert job["state"] == "done" and len(calls) >= 2
    assert {(i["company"], i["email"]) for i in job["items"]} == {("Acme", "hr@acme.io"), ("Beta", "jobs@mail.beta.co.uk")}

    bad = _import(client, "scan.txt", b"   ")
    assert bad["state"] == "error" and "нет текста" in bad["detail"]


def test_import_api_and_full_campaign(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(importer, "domain_accepts_mail", lambda d: True)
    prev = _import(client, "list.csv", CSV)
    assert prev["stats"]["ok"] == 1 and prev["stats"]["bad"] == 1
    res = client.post("/api/import/commit", json={"token": prev["token"]}).json()
    assert res["companies"] == 3 and res["contacts"] == 1
    ctx = api.get_ctx()
    card = ContactBook(ctx.output_folder).get("acme")
    assert card["emphasis"] == "финтех, Python"
    assert card["contacts"][0]["source"] == "файл list.csv, строка 2"

    info = client.get("/api/campaigns").json()
    assert info["available"] == 1 and info["sources"] == {"файл list.csv": 1}
    campaign = client.post("/api/campaigns", json={"source": "файл list.csv"}).json()
    cid = campaign["id"]
    assert campaign["stats"]["pending"] == 1

    # Фоновые задачи — синхронно и без пауз.
    monkeypatch.setattr(camp.CampaignJob, "start", lambda self: self.run())
    monkeypatch.setattr(camp, "PAUSE_SECONDS", (0, 0))
    monkeypatch.setattr(main.mail_guard, "_in_window", lambda moment, s: True)  # тест не зависит от часа
    monkeypatch.setattr(main.mail_guard, "human_pause", lambda p, now=None: 0)
    monkeypatch.setattr(main, "generate_company_email",
                        lambda resume, name, position, card, contact, key: {"subject": "Python Dev Application — Ann", "text": "Hello Acme"})
    (ctx.config["dataFolder"] / "resume.pdf").write_bytes(b"%PDF")
    ctx.llm_api_key = "key"
    view = client.post(f"/api/campaigns/{cid}/prepare", json={}).json()
    assert view["stats"]["draft"] == 1
    draft = DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE).get(view["items"][0]["code"])
    assert draft["channel"] == "email" and draft["subject"].startswith("Python Dev Application")
    # Черновик виден во «Входящих» и статус контакта — «черновик».
    assert {c["company"]: c["status"] for c in client.get("/api/contacts").json()}["Acme"] == "draft"

    assert client.post(f"/api/campaigns/{cid}/send", json={}).status_code == 400  # почта не подключена
    ctx.secrets_file.write_text(
        ctx.secrets_file.read_text() + "\nemail:\n  address: me@gmail.com\n  app_password: p\n", encoding="utf-8")
    sent = []
    monkeypatch.setattr(main, "send_email", lambda creds, m: sent.append(m) or "<id>")
    view = client.post(f"/api/campaigns/{cid}/send", json={}).json()
    assert view["stats"]["sent"] == 1 and sent[0]["To"] == "hr@acme.io"
    assert sent[0].get_payload()[1].get_filename() == "resume.pdf"
    assert {c["company"]: c["status"] for c in client.get("/api/contacts").json()}["Acme"] == "written"

    # Ответ и возврат.
    monkeypatch.setattr(main, "bounced_addresses", lambda creds, emails: set())
    monkeypatch.setattr(main, "senders_replied", lambda creds, emails: {"hr@acme.io"})
    notified = []
    monkeypatch.setattr(main, "notify", lambda p, t: notified.append(t))
    main._check_campaign_mail(ctx.config, {"address": "me@gmail.com", "app_password": "p"})
    view = client.get("/api/campaigns").json()["campaigns"][0]
    assert view["stats"]["replied"] == 1 and "Acme" in notified[0]
    assert client.delete(f"/api/campaigns/{cid}").json() == {"ok": True}


def test_daily_limit_stops_campaign_and_keeps_drafts(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        store = camp.CampaignStore(out)
        cid = store.create("t", [{"key": "a", "email": "a@x.io", "company": "A"},
                                 {"key": "b", "email": "b@x.io", "company": "B"}])
        calls = []

        def step(email):
            calls.append(email)
            return "Дневной лимит писем (20) исчерпан" if email == "a@x.io" else None

        job = camp.CampaignJob(cid, "send", ["a@x.io", "b@x.io"], step, pause=False)
        job.run()
        assert calls == ["a@x.io"] and "лимит" in job.message


def test_edit_and_skip_campaign_letter(client):  # noqa: F811
    ctx = api.get_ctx()
    store = camp.CampaignStore(ctx.output_folder)
    cid = store.create("t", [{"key": "a", "email": "a@x.io", "company": "A"}])
    drafts = DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE)
    code = drafts.add("a@x.io", "old", "email", "", channel="email", subject="S", campaign=cid)
    store.update_item(cid, "a@x.io", status="draft", code=code)

    assert client.put(f"/api/hr-drafts/{code}", json={"text": "new"}).status_code == 200
    item = client.get("/api/campaigns").json()["campaigns"][0]["items"][0]
    assert item["text"] == "new" and item["subject"] == "S"

    client.post(f"/api/hr-drafts/{code}/skip")
    assert store.get(cid)["items"]["a@x.io"]["status"] == "skipped"
    assert client.put(f"/api/hr-drafts/{code}", json={"text": "x"}).status_code == 404


def test_setup_checklist_points_to_fix(client):  # noqa: F811
    setup = {c["id"]: c for c in client.get("/api/todo").json()["setup"]}
    assert "daemon" not in setup  # «Запустить бота» — состояние, а не шаг настройки
    assert list(setup)[0] == "resume" and list(setup)[-1] == "gmail"  # шаги мастера по порядку
    assert [i for i, c in setup.items() if c["required"]] == ["resume", "llm", "schedule"]
    assert setup["gmail"]["ok"] is False and setup["gmail"]["goto"] == "settings-outreach"
    assert "watch" not in setup  # без входа в Telegram пункт про каналы не показываем


def test_week_results_by_source(client):  # noqa: F811
    import json
    from datetime import datetime, timedelta

    ctx = api.get_ctx()
    now = datetime.now().astimezone()
    old = (now - timedelta(days=10)).isoformat()
    base = {"company": "C", "title": "T", "link": "", "status": "applied"}
    ctx.applied_log.path.write_text(json.dumps({"applications": [
        {**base, "source": "headhunter", "external_id": "1", "applied_at": now.isoformat(),
         "stage": "interview", "stage_at": now.isoformat()},
        {**base, "source": "headhunter", "external_id": "2", "applied_at": now.isoformat()},
        {**base, "source": "headhunter", "external_id": "3", "applied_at": old,
         "stage": "replied", "stage_at": old},
    ]}), encoding="utf-8")
    store = camp.CampaignStore(ctx.output_folder)
    cid = store.create("t", [{"key": "a", "email": "a@x.io", "company": "A"}])
    store.update_item(cid, "a@x.io", status="replied", sent_at=now.isoformat(), replied_at=now.isoformat())

    r = client.get("/api/results").json()
    assert r["week"] == {"applied": 3, "replies": 2, "interviews": 1}
    assert r["prev"] == {"applied": 1, "replies": 1, "interviews": 0}
    assert {row["source"]: row["replies"] for row in r["by_source"]} == {"headhunter": 1, "email_campaign": 1}


def test_campaign_follow_up_in_same_thread(client, monkeypatch):  # noqa: F811
    from datetime import datetime, timedelta

    ctx = api.get_ctx()
    store = camp.CampaignStore(ctx.output_folder)
    cid = store.create("t", [{"key": "a", "email": "a@x.io", "company": "A"},
                             {"key": "b", "email": "b@x.io", "company": "B"}])
    old = (datetime.now().astimezone() - timedelta(days=8)).isoformat()
    store.update_item(cid, "a@x.io", status="sent", sent_at=old, message_id="<m1>",
                      subject="Python Developer Application — Ann")
    store.update_item(cid, "b@x.io", status="sent", sent_at=datetime.now().astimezone().isoformat())
    monkeypatch.setattr(main, "notify", lambda p, t: None)
    main._draft_campaign_follow_ups(ctx.config, store, replied=set())
    main._draft_campaign_follow_ups(ctx.config, store, replied=set())  # второй раз — не дублирует

    items = {i["email"]: i for i in client.get("/api/campaigns").json()["campaigns"][0]["items"]}
    assert items["a@x.io"]["follow_up_text"] == main.FOLLOW_UP_TEXT_EN and not items["b@x.io"]["follow_up_text"]
    draft = DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE).get(items["a@x.io"]["follow_up_code"])
    assert draft["in_reply_to"] == "<m1>" and draft["subject"] == "Re: Python Developer Application — Ann"

    ctx.secrets_file.write_text(
        ctx.secrets_file.read_text() + "\nemail:\n  address: me@gmail.com\n  app_password: p\n", encoding="utf-8")
    sent = []
    monkeypatch.setattr(main, "send_email", lambda creds, m: sent.append(m) or "<m2>")
    monkeypatch.setattr(camp.CampaignJob, "start", lambda self: self.run())
    monkeypatch.setattr(camp, "PAUSE_SECONDS", (0, 0))
    view = client.post(f"/api/campaigns/{cid}/followups", json={}).json()
    assert sent[0]["In-Reply-To"] == "<m1>" and not sent[0].is_multipart()  # без вложения
    assert view["stats"]["followed_up"] == 1 and view["stats"]["sent"] == 2


def test_candidate_name_from_resume_pdf_not_template(tmp_path, monkeypatch):
    import pdfminer.high_level as hl

    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(hl, "extract_text", lambda *a, **k: "\nВологдин Дмитрий\nМужчина, 32 года\n")
    template = tmp_path / "plain_text_resume.yaml"
    template.write_text("personal_information:\n  name: '[Your Name]'\n  surname: '[Your Surname]'\n", encoding="utf-8")
    params = {"dataFolder": tmp_path, "plainTextResumeFile": template}
    assert main.is_template_resume(template)
    assert main.candidate_name(params, pdf) == "Вологдин Дмитрий"
    # PDF без узнаваемой строки-имени и шаблонный yaml — лучше пусто, чем «[Your Name]».
    monkeypatch.setattr(hl, "extract_text", lambda *a, **k: "Резюме: +7 953 000")
    assert main.candidate_name(params, pdf) == ""


def test_campaign_reply_shows_in_inbox(client):  # noqa: F811
    ctx = api.get_ctx()
    store = camp.CampaignStore(ctx.output_folder)
    cid = store.create("Осень", [{"key": "a", "email": "hr@acme.io", "company": "Acme"}])
    store.update_item(cid, "hr@acme.io", status="replied", replied_at="2026-09-20T10:00:00+00:00")
    item = next(i for i in client.get("/api/inbox").json() if i["channel"] == "email")
    assert item["company"] == "Acme" and item["stage"] == "replied" and "from%3Ahr@acme.io" in item["link"]


def test_daily_backup_keeps_a_week(tmp_path):
    from datetime import date, timedelta

    from src.utils.backup import daily_backup

    out = tmp_path / "output"
    out.mkdir()
    (out / "contact_book.json").write_text("{}", encoding="utf-8")
    start = date(2026, 9, 1)
    for i in range(10):
        daily_backup(out, start + timedelta(days=i))
    assert daily_backup(out, start + timedelta(days=9)) is None  # второй раз за день — не копируем
    days = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert len(days) == 7 and days[-1] == "2026-09-10"
    assert (tmp_path / "backups" / "2026-09-10" / "contact_book.json").exists()


def test_base_bulk_actions_export_and_domain_merge(client):  # noqa: F811
    ctx = api.get_ctx()
    book = ContactBook(ctx.output_folder)
    book.add("Acme", [{"kind": "email", "value": "hr@acme.io", "source": "файл a.csv, строка 2"}], website="acme.io")
    book.add("ACME LLC", [{"kind": "email", "value": "jobs@acme.io", "source": "пост в @chan"}])  # тот же домен
    book.add("Beta", [{"kind": "email", "value": "hr@beta.dev", "source": "текст вакансии"}])
    cards = {c["company"]: c for c in client.get("/api/contacts").json()}
    assert set(cards) == {"Acme", "Beta"} and len(cards["Acme"]["contacts"]) == 2
    assert cards["Acme"]["source_kinds"] == ["file", "telegram"] and cards["Acme"]["last"]["text"].startswith("добавлен")

    client.post("/api/contacts/bulk", json={"keys": [cards["Beta"]["key"]], "action": "skip"})
    assert {c["company"]: c["status"] for c in client.get("/api/contacts").json()}["Beta"] == "skip"
    assert client.get("/api/campaigns").json()["available"] == 1  # «не писать» в рассылку не идёт

    csv_text = client.get("/api/contacts/export").content.decode("utf-8-sig")
    assert csv_text.splitlines()[0].startswith("Компания;Email") and "не писать" in csv_text

    removed = client.post("/api/contacts/bulk", json={"keys": [cards["Acme"]["key"]], "action": "delete"}).json()["removed"]
    assert [c["company"] for c in client.get("/api/contacts").json()] == ["Beta"]
    client.post("/api/contacts/restore", json={"cards": removed})
    assert len(client.get("/api/contacts").json()) == 2

    campaign = client.post("/api/campaigns", json={"keys": [cards["Acme"]["key"]]}).json()
    assert campaign["stats"]["total"] == 1 and campaign["name"].startswith("Выбранные (1)")


def test_company_blacklist_applies_to_base(client):  # noqa: F811
    ctx = api.get_ctx()
    ContactBook(ctx.output_folder).add("ООО Ромашка", [{"kind": "email", "value": "hr@romashka.ru", "source": "текст вакансии"}])
    ctx.config["company_blacklist"] = ["Ромашка"]
    assert client.get("/api/contacts").json()[0]["status"] == "skip"
    assert client.get("/api/campaigns").json()["available"] == 0


def test_campaign_bot_buttons(client, monkeypatch):  # noqa: F811
    ctx = api.get_ctx()
    store = camp.CampaignStore(ctx.output_folder)
    cid = store.create("Осень", [{"key": "a", "email": "a@x.io", "company": "A"},
                                  {"key": "b", "email": "b@x.io", "company": "B"}])
    drafts = DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE)
    for email in ("a@x.io", "b@x.io"):
        code = drafts.add(email, "Hello", "email", "", channel="email", subject="S", campaign=cid)
        store.update_item(cid, email, status="draft", code=code)
    calls = []
    monkeypatch.setattr(main, "bot_request", lambda token, method, payload: calls.append((method, payload)) or {})
    cb = lambda data: {"id": "1", "data": data, "message": {"chat": {"id": 1}, "message_id": 5}}  # noqa: E731

    main._handle_vacancy_button(ctx.config, "", "tok", cb(f"cv:{cid}:d"))
    shown = [p for m, p in calls if m == "sendMessage"]
    assert len(shown) == 2 and shown[0]["reply_markup"]["inline_keyboard"][0][0]["text"] == "✅ Отправить"

    main._handle_vacancy_button(ctx.config, "", "tok", cb(f"x:{store.get(cid)['items']['a@x.io']['code']}"))
    assert store.get(cid)["items"]["a@x.io"]["status"] == "skipped"

    started = []
    monkeypatch.setattr(main, "start_campaign_job", lambda p, k, c, kind, *a: started.append((c, kind)))
    main._handle_vacancy_button(ctx.config, "", "tok", cb(f"cs:{cid}"))
    assert started == [(cid, "send")]


def test_activity_shows_running_work(client):  # noqa: F811
    ctx = api.get_ctx()
    cid = camp.CampaignStore(ctx.output_folder).create("Осень", [{"key": "a", "email": "a@x.io", "company": "A"}])
    job = camp.CampaignJob(cid, "send", ["a@x.io"], lambda e: None, pause=False)
    camp.CampaignJob.RUNNING[cid] = job
    api.IMPORT_JOBS["t1"] = {"state": "running", "stage": "", "done": 2, "total": 5, "filename": "big.pdf"}
    try:
        texts = [a["text"] for a in client.get("/api/activity").json()]
        assert texts == ["Отправляю письма — Осень", "Разбираю big.pdf"]
    finally:
        camp.CampaignJob.RUNNING.pop(cid, None)
        api.IMPORT_JOBS.pop("t1", None)


def test_quiet_mode_moves_routine_to_digest(tmp_path, monkeypatch):
    from datetime import datetime as real_dt

    sent = []
    monkeypatch.setattr(main, "notify_from_secrets", lambda p, t: sent.append(t))
    params = {"outputFileDirectory": tmp_path, "digest": {"quiet": True, "enabled": False, "hour": 0}}
    main.notify_routine(params, "Прогон завершён: отправлено 5 откликов")
    main.notify(params, "✉️ Ответ HR")  # важное — сразу
    assert sent == ["✉️ Ответ HR"]

    digests = []
    monkeypatch.setattr(main, "send_notification", lambda token, chat, text: digests.append(text))
    monkeypatch.setattr(main, "build_digest", lambda *a: "☀️ Сводка")
    main._maybe_send_daily_digest(params, "tok", "1")
    assert "Прогон завершён" in digests[0] and "Несрочное" in digests[0]
    assert not (tmp_path / main.QUIET_QUEUE_FILE).exists()
    main.notify_routine({**params, "digest": {}}, "без тихого режима")
    assert sent[-1] == "без тихого режима"


def test_bot_accepts_short_platform_names():
    from src.job_sources.telegram_control import parse_control_commands

    updates = [{"update_id": 1, "message": {"chat": {"id": 7}, "text": "/resume hh"}}]
    assert parse_control_commands(updates, "7") == [{"action": "resume", "source": "headhunter"}]


def test_resumes_overview(client):  # noqa: F811
    ctx = api.get_ctx()
    (ctx.config["dataFolder"] / "resume.pdf").write_bytes(b"%PDF-1")
    extra = ctx.config["dataFolder"] / "telegram"
    extra.mkdir(exist_ok=True)
    (extra / "Very_Long_Name_Backend_Developer_CV.pdf").write_bytes(b"%PDF-1")
    r = client.get("/api/resumes").json()
    assert r["primary"]["exists"] and r["primary"]["name"] == "resume.pdf"
    assert r["linkedin"] == {"exists": False}
    assert [f["name"] for f in r["extra"]] == ["Very_Long_Name_Backend_Developer_CV.pdf"]


def test_ui_files_are_not_served_stale(client):  # noqa: F811
    assert client.get("/style.css").headers.get("cache-control") == "no-cache"


def test_company_sites_collect_into_base_for_campaign(client):  # noqa: F811
    """«Сайты компаний» кладут компании в Базу: с email — сразу в рассылку,
    без email — тоже видны под фильтром «sites»."""
    ctx = api.get_ctx()
    book = ContactBook(ctx.output_folder)
    vacancy = lambda n: {"title": "Python dev", "link": f"https://x/{n}", "source": "direct"}  # noqa: E731
    book.add("Acme", [{"kind": "email", "value": "jobs@acme.io", "source": "Сайты компаний: текст вакансии"}],
             vacancy=vacancy(1))
    book.add("NoMail Inc", [], vacancy=vacancy(2))
    cards = {c["company"]: c for c in client.get("/api/contacts").json()}
    assert cards["Acme"]["source_kinds"] == ["sites"]
    assert cards["NoMail Inc"]["source_kinds"] == ["sites"]
    s = client.get("/api/direct/summary").json()
    assert (s["in_base"], s["added_week"], s["ready"]) == (2, 2, 1)
    created = client.post("/api/campaigns", json={"source": "Сайты компаний"}).json()
    assert len(created["items"]) == 1


def test_campaign_prepares_in_daily_batches(monkeypatch):
    """3 адреса при лимите 2: сегодня — 2 письма, остальное ждёт; на
    следующий день, когда порция ушла, готовится следующая."""
    with tempfile.TemporaryDirectory() as tmp:
        out, data = Path(tmp) / "out", Path(tmp) / "data"
        out.mkdir(); data.mkdir()
        (data / main.RESUME_PDF).write_bytes(b"%PDF")
        params = {"outputFileDirectory": out, "dataFolder": data, "direct": {"email_daily_limit": 2}}
        monkeypatch.setattr(camp.CampaignJob, "start", lambda self: self.run())
        monkeypatch.setattr(main, "candidate_name", lambda *a: "Ann")
        monkeypatch.setattr(main, "generate_company_email", lambda *a: {"subject": "s", "text": "t"})
        monkeypatch.setattr(main, "_notify_with_buttons", lambda *a: None)
        store = camp.CampaignStore(out)
        cid = store.create("t", [{"key": k, "email": f"{k}@x.io", "company": k} for k in "abc"])

        main.start_campaign_job(params, "key", cid, "prepare")
        stats = lambda: camp.campaign_stats(store.get(cid))  # noqa: E731
        assert (stats()["draft"], stats()["pending"]) == (2, 1)

        main._prepare_campaign_batches(params, "key")  # тот же день — ждём
        assert stats()["pending"] == 1
        for email in ("a@x.io", "b@x.io"):
            store.update_item(cid, email, status="sent")
        store.update(cid, batch_day="2000-01-01", sending=True)  # «вчера» нажали «Начать отправку»
        main._prepare_campaign_batches(params, "key")
        assert (stats()["draft"], stats()["pending"]) == (1, 0)
        # Новая порция не уходит сама — ждёт «Отправить все».
        assert store.get(cid)["sending"] is False
        started = []
        monkeypatch.setattr(main.mail_guard, "plan", lambda *a, **k: {"can_send": True})
        monkeypatch.setattr(main, "start_campaign_job", lambda *a, **k: started.append(a[3]))
        main.check_campaign_sending(params, "key")
        assert started == []


def test_markdown_table_import_skips_non_application_inboxes():
    """Таблица Markdown (как data/companies.md в byborh/careerLauncher):
    Source URL — источник контакта, а не вакансия; accessibility@ и
    accommodations@ — не для откликов."""
    md = (
        "# Big Tech Contacts\n\n"
        "| Company | Domain | Role Email | Department / Team | Location | Description | Source URL | Last Verified |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| NVIDIA | nvidia.com | `hr@nvidia.com` | For Employment | Global | GPUs. | https://nvidia.com/jobs | 2025-10-18 |\n"
        "| Disney | disney.com | Candidate.Accommodations@Disney.com | For Employment | Global | Media. | https://disney.com | 2025-11-03 |\n"
    ).encode()
    table, _ = importer.read_file("companies.md", md)
    rows = importer.rows_from_table(table)
    nvidia = rows[0]
    assert (nvidia["company"], nvidia["email"], nvidia["website"]) == ("NVIDIA", "hr@nvidia.com", "nvidia.com")
    assert nvidia["source_url"] == "https://nvidia.com/jobs" and nvidia["link"] == ""
    assert nvidia["emphasis"] == "GPUs."
    assert importer.check_email(rows[1]["email"])[0] == "bad"


def test_pdf_table_wrapped_cell_rejoins_its_row():
    """Длинный email в PDF-таблице переносится: обрывки сверху и снизу
    приклеиваются к своей строке, «name@site.» + «com» — без пробела."""
    rows = [
        (700.0, ["1", "Ann", "ann@a.com", "HR", "A"]),
        (695.0, ["", "", "very.long.name@excelencia.", "", ""]),
        (692.0, ["2", "Gita V", "", "Head TA", "Excelencia"]),
        (689.0, ["", "", "com", "", ""]),
        (684.0, ["3", "Bob", "bob@b.com", "HR", "B"]),
    ]
    merged = importer._merge_wrapped(rows, 5)
    assert [r[2] for r in merged] == ["ann@a.com", "very.long.name@excelencia.com", "bob@b.com"]
    assert merged[1][4] == "Excelencia"
    assert importer._join_cell("Lakshmi", "Radhakrishnan") == "Lakshmi Radhakrishnan"


def test_mail_guard_warmup_window_and_bounces(tmp_path):
    """Разогрев: 15 в первый день, +5 за каждый день отправки; вне рабочих
    часов и в выходные — ждём; 3 возврата за сутки — стоп."""
    from datetime import datetime, timedelta, timezone

    from src.direct import mail_guard as g

    tz = timezone(timedelta(hours=3))
    monday_noon = datetime(2026, 9, 21, 12, tzinfo=tz)
    params = {"direct": {"email_daily_limit": 50}}
    p = g.plan(params, tmp_path, monday_noon)
    assert (p["limit"], p["can_send"]) == (15, True)

    sent = {f"a{i}@x.io": {"sent_at": (monday_noon - timedelta(days=d)).isoformat()} for i, d in enumerate([1, 2, 2])}
    (tmp_path / "campaigns.json").write_text(json.dumps({"c": {"items": sent}}))
    assert g.plan(params, tmp_path, monday_noon)["limit"] == 25  # два дня отправки
    assert g.plan({"direct": {"email_daily_limit": 50, "warmup": False}}, tmp_path, monday_noon)["limit"] == 50

    evening, saturday = monday_noon.replace(hour=21), monday_noon + timedelta(days=5)
    assert not g.plan(params, tmp_path, evening)["can_send"]
    assert g.next_window(evening, g.settings(params)) == monday_noon.replace(day=22, hour=9)
    assert not g.plan(params, tmp_path, saturday)["can_send"]
    assert g.next_window(saturday, g.settings(params)).weekday() == 0

    bounced = {f"b{i}@x.io": {"bounced_at": (monday_noon - timedelta(hours=1)).isoformat()} for i in range(3)}
    (tmp_path / "campaigns.json").write_text(json.dumps({"c": {"items": {**sent, **bounced}}}))
    p = g.plan(params, tmp_path, monday_noon)
    assert not p["can_send"] and "Возвратов" in p["reason"]
    # Порог настраивается: 5 — трёх возвратов уже мало для стопа.
    assert g.plan({"direct": {"email_daily_limit": 50, "bounce_stop": 5}}, tmp_path, monday_noon)["can_send"]
    assert g.settings({"direct": {"bounce_stop": 999}})["bounce_stop"] == g.BOUNCE_STOP_MAX  # выключить нельзя
    assert g.days_needed({"limit": 15, "daily_limit": 30, "warmup": True}, 100) == 5  # 15+20+25+30+30


def test_mail_status_waiting_stopped_and_gmail_auth(client, monkeypatch):  # noqa: F811
    """Строка «Сейчас»: включённая рассылка вечером — «ждёт»; пароль Gmail
    не принят — «остановлено», новый пароль снимает стоп."""
    ctx = api.get_ctx()
    store = camp.CampaignStore(ctx.output_folder)
    cid = store.create("t", [{"key": "a", "email": "a@x.io", "company": "A"}])
    code = DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE).add("a@x.io", "Hi", "email", "", channel="email")
    store.update_item(cid, "a@x.io", status="draft", code=code)
    assert not any(a.get("state") for a in client.get("/api/activity").json())  # не включена

    store.update(cid, sending=True)
    monkeypatch.setattr(api.mail_guard, "_in_window", lambda moment, s: False)
    [item] = [a for a in client.get("/api/activity").json() if a.get("state")]
    assert item["state"] == "waiting" and "вне времени отправки" in item["text"]

    assert main._gmail_auth_failed("Не удалось отправить письмо a@x.io: (535, b'5.7.8 Username and Password not accepted')")
    store.update(cid, error="Gmail не принял пароль приложения")
    [item] = [a for a in client.get("/api/activity").json() if a.get("state")]
    assert item["state"] == "stopped" and item["goto"] == "settings-outreach"
    status = client.get("/api/campaigns").json()["mail_status"]
    assert status["state"] == "stopped" and status["waiting"] == 1

    client.post("/api/settings/outreach", json={"email_app_password": "abcd efgh ijkl mnop"})
    assert store.get(cid)["error"] == ""


def test_ai_prompt_table_columns_map_to_fields():
    """Столбцы из промта «Где взять список компаний?» раскладываются по
    полям импорта: должность — человека, ссылка — вакансия, источник —
    где опубликован email."""
    header = ["Компания", "Сайт", "Email", "Имя", "Должность", "Вакансия", "Ссылка", "Источник"]
    row = ["Acme", "acme.io", "hr@acme.io", "Анна", "HR-директор", "Python Dev", "https://acme.io/jobs/1", "https://acme.io/careers"]
    [item] = importer.rows_from_table([header, row])
    assert (item["company"], item["website"], item["email"], item["name"]) == ("Acme", "acme.io", "hr@acme.io", "Анна")
    assert (item["position"], item["title"], item["link"], item["source_url"]) == (
        "HR-директор", "Python Dev", "https://acme.io/jobs/1", "https://acme.io/careers")
    # Тот же промт по-английски (README.en.md).
    [en] = importer.rows_from_table([
        ["Company", "Website", "Email", "Name", "Position", "Vacancy", "Link", "Source"], row])
    assert (en["position"], en["title"], en["link"], en["source_url"]) == (
        item["position"], item["title"], item["link"], item["source_url"])


def test_outreach_summary_for_home_card(client):  # noqa: F811
    """Карточка «Компании и рассылка»: пустая база → 0; компания с email →
    «можно написать», новая за неделю; рассылка с черновиком — текущая."""
    s = client.get("/api/outreach/summary").json()
    assert (s["base_total"], s["available"], s["current"]) == (0, 0, None)

    ctx = api.get_ctx()
    ContactBook(ctx.output_folder).add("Acme", [{"kind": "email", "value": "hr@acme.io", "source": "файл a.csv, строка 2"}])
    s = client.get("/api/outreach/summary").json()
    assert (s["base_total"], s["available"], s["added_week_total"], s["added_week"]["file"]) == (1, 1, 1, 1)

    cid = client.post("/api/campaigns", json={}).json()["id"]
    code = DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE).add("hr@acme.io", "Hello Acme", "email", "", channel="email")
    camp.CampaignStore(ctx.output_folder).update_item(cid, "hr@acme.io", status="draft", code=code)
    cur = client.get("/api/outreach/summary").json()["current"]
    assert (cur["id"], cur["draft"], cur["drafts"][0]["text"]) == (cid, 1, "Hello Acme")

    # Письмо удалили в обход рассылки — «черновик» без текста не висит.
    DraftStore(ctx.output_folder / main.HR_DRAFTS_FILE).remove(code)
    assert client.get("/api/outreach/summary").json()["current"] is None


def test_new_companies_join_queue_first_and_auto_send(client, monkeypatch):  # noqa: F811
    """Новые компании Базы встают в очередь идущей рассылки «всем» и
    пишутся первыми; с «отправлять самому» новая порция уходит без
    просмотра — но первую порцию рассылки человек смотрит всегда."""
    ctx = api.get_ctx()
    book = ContactBook(ctx.output_folder)
    book.add("Old Co", [{"kind": "email", "value": "hr@old.io", "source": "файл a.csv, строка 2"}])
    cid = client.post("/api/campaigns", json={}).json()["id"]
    store = camp.CampaignStore(ctx.output_folder)
    assert store.get(cid)["scope"] == "all"
    assert api._absorb_new_companies(ctx) == 0  # рассылка ещё не начата

    monkeypatch.setattr(camp.CampaignJob, "start", lambda self: self.run())
    monkeypatch.setattr(main, "candidate_name", lambda *a: "Ann")
    monkeypatch.setattr(main, "generate_company_email", lambda *a: {"subject": "s", "text": "t"})
    monkeypatch.setattr(main, "_notify_with_buttons", lambda *a: None)
    (ctx.config["dataFolder"] / "resume.pdf").write_bytes(b"%PDF")
    params = {**ctx.config, "direct": {"email_daily_limit": 1, "warmup": False, "auto_send": True}}

    main.start_campaign_job(params, "key", cid, "prepare")  # первая порция
    assert store.get(cid)["sending"] is False  # первую — всегда на просмотр
    store.update_item(cid, "hr@old.io", status="sent", sent_at="2026-01-01T10:00:00+03:00")

    # Позже в Базу пришли две компании — встают в очередь, свежая первой.
    book.add("Mid Co", [{"kind": "email", "value": "hr@mid.io", "source": "файл b.csv, строка 2"}])
    book.add("New Co", [{"kind": "email", "value": "hr@new.io", "source": "файл b.csv, строка 3"}])
    book.update_contact("hr@mid.io", found_at="2026-01-01T10:00:00+03:00")  # добавлена раньше
    assert api._absorb_new_companies(ctx) == 2

    main.start_campaign_job(params, "key", cid, "prepare")
    items = store.get(cid)["items"]
    assert items["hr@new.io"]["status"] == "draft" and items["hr@mid.io"]["status"] == "pending"
    assert store.get(cid)["sending"] is True  # уйдёт сама
