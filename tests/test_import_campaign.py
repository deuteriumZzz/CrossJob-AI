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
    assert setup["daemon"]["ok"] is False and "Запустить" in setup["daemon"]["hint"]
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
