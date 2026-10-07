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
