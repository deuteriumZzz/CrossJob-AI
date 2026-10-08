from src.direct.campaign import CampaignStore
from src.webui.api import get_outreach_sent


class _Ctx:
    def __init__(self, folder):
        self.output_folder = folder


def test_sent_log_lists_sent_and_failed_only(tmp_path):
    store = CampaignStore(tmp_path)
    cid = store.create(
        "t",
        [
            {"key": "a", "email": "a@x.io", "company": "A"},
            {"key": "b", "email": "b@x.io", "company": "B"},
            {"key": "c", "email": "c@x.io", "company": "C"},
        ],
    )
    store.update_item(cid, "a@x.io", status="sent", sent_at="2026-10-01")
    store.update_item(cid, "b@x.io", status="failed", reason="smtp")
    rows = get_outreach_sent(_Ctx(tmp_path))["items"]
    assert [r["company"] for r in rows] == ["A", "B"] or {
        r["company"] for r in rows
    } == {"A", "B"}
    assert rows[0]["status"] == "sent"


def test_mark_written_manual_roundtrip(tmp_path):
    from src.job_sources.contact_book import ContactBook
    from src.webui.api import ContactsBulk, post_contacts_bulk

    book = ContactBook(tmp_path)
    key = book.add("Acme", [{"kind": "email", "value": "hr@acme.io"}])
    ctx = _Ctx(tmp_path)
    post_contacts_bulk(ContactsBulk(keys=[key], action="mark_written"), ctx)
    assert book.all()[key]["contacts"][0]["sent_at"]
    post_contacts_bulk(ContactsBulk(keys=[key], action="unmark_written"), ctx)
    assert not book.all()[key]["contacts"][0]["sent_at"]


def test_deleting_companies_closes_their_pending_letters(tmp_path):
    from src.direct.campaign import CampaignStore
    from src.job_sources.contact_book import ContactBook
    from src.webui.api import ContactsBulk, post_contacts_bulk

    book = ContactBook(tmp_path)
    keep = book.add("Keep", [{"kind": "email", "value": "a@keep.io"}])
    drop = book.add("Drop", [{"kind": "email", "value": "b@drop.io"}])
    store = CampaignStore(tmp_path)
    cid = store.create(
        "t",
        [
            {"key": keep, "email": "a@keep.io", "company": "Keep"},
            {"key": drop, "email": "b@drop.io", "company": "Drop"},
        ],
    )
    post_contacts_bulk(
        ContactsBulk(keys=[drop], action="delete"), _Ctx(tmp_path)
    )
    items = store.get(cid)["items"]
    assert items["a@keep.io"]["status"] == "pending"
    assert items["b@drop.io"]["status"] == "skipped"
    assert "Базе" in items["b@drop.io"]["reason"]


def test_orphan_check_keeps_letters_whose_email_is_still_in_the_base(tmp_path):
    from src.direct.campaign import CampaignStore

    store = CampaignStore(tmp_path)
    cid = store.create(
        "t",
        [
            {"key": "old-key", "email": "a@x.io", "company": "A"},
            {"key": "gone", "email": "b@y.io", "company": "B"},
        ],
    )
    count, _ = store.skip_orphans({"new-key"}, {"a@x.io"})
    items = store.get(cid)["items"]
    assert count == 1
    assert items["a@x.io"]["status"] == "pending"
    assert items["b@y.io"]["status"] == "skipped"


def test_company_already_written_blocks_other_addresses(tmp_path):
    import main
    from src.direct.campaign import CampaignStore
    from src.job_sources.contact_book import ContactBook

    book = ContactBook(tmp_path)
    book.add(
        "Alfa",
        [
            {"kind": "email", "value": "a@alfa.ru"},
            {"kind": "email", "value": "b@alfa.ru"},
        ],
    )
    book.add("Solo", [{"kind": "email", "value": "c@solo.io"}])
    store = CampaignStore(tmp_path)
    cid = store.create(
        "t",
        [
            {"key": "k1", "email": "a@alfa.ru", "company": "Alfa"},
            {"key": "k2", "email": "b@alfa.ru", "company": "Alfa"},
            {"key": "k3", "email": "c@solo.io", "company": "Solo"},
        ],
    )
    assert not main._company_already_written(book, store, "b@alfa.ru")
    store.update_item(cid, "a@alfa.ru", status="sent", sent_at="2026-10-01")
    assert main._company_already_written(book, store, "b@alfa.ru")
    assert not main._company_already_written(book, store, "c@solo.io")
    assert not main._company_already_written(book, store, "a@alfa.ru")
