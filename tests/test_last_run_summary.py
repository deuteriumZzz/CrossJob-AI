"""Итог захода площадки виден в интерфейсе, даже когда новых вакансий нет."""

import json
from datetime import datetime

import main
import src.webui.api as api
from src.job_sources.applied_log import AppliedLog
from tests.test_webui_api import client  # noqa: F401  (fixture)


def test_zero_new_run_is_recorded_and_served_in_status(client):  # noqa: F811
    ctx = api.get_ctx()
    main._log_funnel_summary(
        "geekjob",
        AppliedLog(ctx.output_folder / "applied_log.json"),
        0,
        0,
        datetime.now().astimezone(),
        ctx.config,
    )

    saved = json.loads(
        (ctx.output_folder / ".last_run_summary.json").read_text(encoding="utf-8")
    )
    assert saved["geekjob"]["new"] == 0 and saved["geekjob"]["applied"] == 0

    sources = {s["name"]: s for s in client.get("/api/status").json()["sources"]}
    assert sources["geekjob"]["last_summary"]["new"] == 0
    assert sources["hirify"]["last_summary"] is None  # ещё не заходила
