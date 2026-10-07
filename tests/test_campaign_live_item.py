from pathlib import Path

import main
from src.direct.campaign import CampaignStore


def test_live_item_is_gone_after_campaign_or_address_removed(tmp_path: Path):
    store = CampaignStore(tmp_path)
    campaign_id = store.create(
        "t",
        [
            {"key": "a", "email": "hr@a.com", "company": "A"},
            {"key": "b", "email": "hr@b.com", "company": "B"},
        ],
    )
    assert main._live_campaign_item(store, campaign_id, "hr@a.com")

    store.delete(campaign_id)

    assert main._live_campaign_item(store, campaign_id, "hr@a.com") is None
