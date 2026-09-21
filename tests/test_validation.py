from collections import Counter
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from less.api import app
from less.budget import daily_usage, day_bounds, local_today
from less.collector import save_material
from less.config import settings
from less.db import Session
from less.models import (
    FieldReview,
    HumanReview,
    ItemVersion,
    NormalizeRun,
    Source,
    SourceCheck,
    ValidationSample,
    WorkSession,
    now,
)
from less.pipeline import execute_normalize, queue_normalize
from less.validation import (
    create_batch,
    prepare_batch,
    quality_totals,
    report,
    start_session,
    stop_session,
)
from sqlalchemy import func, select
from test_pipeline import Failure, Success, material, source, version


def prepared_sample():
    vid = version()
    batch_id = create_batch(30, "test-operator")
    assert prepare_batch(batch_id, "test-operator", 30) == 1
    assert prepare_batch(batch_id, "test-operator", 30) == 0
    with Session() as db:
        sample = db.scalar(select(ValidationSample))
        sid, rid = sample.id, sample.run_id
    execute_normalize(rid, Success())
    return vid, sid, rid


def test_stratified_sample_freezes_distinct_items_without_filtering_for_ai(database):
    with Session() as db:
        for n in range(3):
            db.add(
                Source(
                    id=f"source-{n}",
                    name=f"Source {n}",
                    node_url="https://example.com",
                    feed_url="https://example.com/feed",
                    role="Primary",
                    topics=[],
                    coverage=[],
                    authority="test",
                    bias="test",
                )
            )
        db.commit()
        for n in range(3):
            for i in range(15):
                save_material(db, f"source-{n}", {**material(), "url": f"https://example.com/{i}"})
        db.commit()
        changed, _ = save_material(
            db,
            "source-0",
            {
                **material(),
                "url": "https://example.com/0",
                "text": material()["text"] + "\nChanged.",
            },
        )
        db.commit()
        changed_id = changed.id
    bid = create_batch(30, "test-operator")
    client = TestClient(app)
    detail = client.get(f"/api/validation/batches/{bid}").json()
    assert detail["batch"]["population_count"] == 45
    assert detail["batch"]["sample_count"] == 30
    assert Counter(s["source_name"] for s in detail["samples"]) == {
        f"Source {n}": 10 for n in range(3)
    }
    assert all(s["run_id"] is None for s in detail["samples"])
    # Taking the whole population always includes its latest version and no duplicates.
    all_id = create_batch(100, "test-operator")
    with Session() as db:
        rows = db.execute(
            select(ValidationSample.version_id, ItemVersion.item_id)
            .join(ItemVersion)
            .where(ValidationSample.batch_id == all_id)
        ).all()
        assert len(rows) == len({item for _, item in rows}) == 45
        assert changed_id in {vid for vid, _ in rows}
        assert db.scalar(select(func.count()).select_from(NormalizeRun)) == 0
        assert db.scalar(select(func.count()).select_from(HumanReview)) == 0


def test_field_reviews_validate_original_exact_run_and_preserve_history(database):
    _, sid, rid = prepared_sample()
    client = TestClient(app)
    detail = client.get(f"/api/validation/samples/{sid}").json()
    fields = [{"key": f["key"], "verdict": "not_checked", "note": ""} for f in detail["fields"]]
    body = {
        "run_id": rid,
        "reviewer": "test-editor",
        "fields": fields,
        "note": "Test fixture only",
        "original_checked": True,
    }
    endpoint = f"/api/validation/samples/{sid}/reviews"
    assert client.post(endpoint, json=body).status_code == 422
    fields[0]["verdict"] = "correct"
    assert client.post(endpoint, json={**body, "original_checked": False}).status_code == 422
    assert client.post(endpoint, json={**body, "fields": fields[:-1]}).status_code == 422
    assert client.post(endpoint, json={**body, "fields": fields + [fields[0]]}).status_code == 422
    fields[0]["verdict"] = "unknown_correct"
    assert client.post(endpoint, json=body).status_code == 422
    fields[0]["verdict"] = "incorrect"
    assert client.post(endpoint, json=body).status_code == 422
    fields[0]["note"] = "Test discrepancy in title"
    fields[1]["verdict"] = "unknown_correct"
    assert client.post(endpoint, json=body).status_code == 201
    with Session() as db:
        q = quality_totals(db)
        assert (q["checked_fields"], q["correct_fields"], q["accuracy"]) == (2, 1, 0.5)
        assert q["fully_reviewed_samples"] == 0
    for field in fields:
        field["verdict"] = "correct"
    assert client.post(endpoint, json=body).status_code == 201
    rerun = client.post(
        f"/api/validation/samples/{sid}/rerun", json={"actor": "test-editor"}
    ).json()["id"]
    assert client.post(endpoint, json=body).status_code == 422
    execute_normalize(rerun, Success())
    # Identical field structure must not allow a stale form to attach to the new run.
    assert client.post(endpoint, json=body).status_code == 422
    assert client.post(endpoint, json={**body, "run_id": rerun}).status_code == 201
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(FieldReview)) == 3
        assert db.scalar(select(func.count()).select_from(HumanReview)) == 0
        assert quality_totals(db)["fully_reviewed_samples"] == 1
        assert quality_totals(db)["checked_fields"] == len(fields)
    history = client.get(f"/api/validation/samples/{sid}").json()["reviews"]
    assert {r["run_id"] for r in history} == {rid, rerun}


def test_budget_counts_failures_and_resets_on_local_day(database, monkeypatch):
    monkeypatch.setattr(settings(), "ai_daily_limit", 1)
    vid = version()
    rid = queue_normalize(vid)
    execute_normalize(rid, Failure("timeout"))
    another = queue_normalize(vid, force=True)

    class MustNotCall:
        def execute(self, material):
            raise AssertionError("Daily limit must stop invocation")

    execute_normalize(another, MustNotCall())
    with Session() as db:
        assert daily_usage(db, local_today())["used"] == 1
        run = db.get(NormalizeRun, another)
        assert run.status == "budget_wait" and run.attempts == 0
        tomorrow = run.next_attempt_at
    monkeypatch.setattr("less.pipeline.local_today", lambda: local_today(tomorrow))
    monkeypatch.setattr("less.pipeline.now", lambda: tomorrow + timedelta(seconds=1))
    monkeypatch.setattr("less.attempts.now", lambda: tomorrow + timedelta(seconds=1))
    execute_normalize(another, Success())
    with Session() as db:
        assert db.get(NormalizeRun, another).status == "succeeded"
        assert daily_usage(db, local_today(tomorrow))["used"] == 1


def test_budget_legacy_is_conservative_and_disclosed(database):
    rid = queue_normalize(version())
    with Session() as db:
        run = db.get(NormalizeRun, rid)
        run.started_at, run.attempts = now(), 2
        db.commit()
        assert daily_usage(db, local_today())["legacy_estimated"] == 2
        assert daily_usage(db, local_today())["used"] == 2
    start, end = day_bounds(date(2026, 9, 20))
    assert start.isoformat() == "2026-09-19T16:00:00+00:00"
    assert end - start == timedelta(days=1)


def test_report_separates_manual_and_includes_missing_scheduler_slots(database):
    day = date(2026, 9, 10)
    start, end = day_bounds(day)
    cutoff = start + timedelta(hours=15)
    with Session() as db:
        source(db, next_due_at=start + timedelta(hours=6), interval_hours=6)
        db.add_all(
            [
                SourceCheck(
                    source_id="test-source",
                    slot=start.isoformat(),
                    scheduled_at=start,
                    status="succeeded",
                    finished_at=start + timedelta(minutes=1),
                ),
                SourceCheck(
                    source_id="test-source",
                    slot="manual:test",
                    scheduled_at=start + timedelta(hours=1),
                    status="succeeded",
                    finished_at=start + timedelta(hours=1, minutes=1),
                ),
            ]
        )
        db.commit()
    r = report(day, at=cutoff)
    assert (r["succeeded"], r["planned"], r["unrecorded_due"], r["manual_checks"]) == (1, 3, 2, 1)
    assert r["success_rate"] == 1 / 3 and not r["closed"]
    assert r["sources"][0]["planned"] == 3
    assert r["quality"]["accuracy"] is None
    assert r["cost"] is None and r["later_stages"]["candidates"] is None
    assert r["later_stages"]["events"] == 0 and r["later_stages"]["published_briefs"] == 0
    assert report(day, at=end)["closed"]


def test_work_sessions_require_scope_counts_and_do_not_fabricate_baseline(database):
    client = TestClient(app)
    with Session() as db:
        source(db, next_due_at=now() + timedelta(days=1))
    body = {
        "reviewer": "test-editor",
        "mode": "baseline",
        "category": "review",
        "source_ids": ["test-source"],
        "criteria": "Test scope",
    }
    assert client.post("/api/validation/sessions", json=body).status_code == 422
    body["category"] = "screening"
    assert (
        client.post(
            "/api/validation/sessions", json={**body, "source_ids": ["unknown"]}
        ).status_code
        == 422
    )
    created = client.post("/api/validation/sessions", json=body)
    assert created.status_code == 201
    assert client.post("/api/validation/sessions", json=body).status_code == 422
    sid = created.json()["id"]
    assert report(local_today())["baseline_sessions"] == 0
    with pytest.raises(ValueError):
        stop_session(sid, 1, 2, 0, "test")
    stop_session(sid, 5, 2, 1, "test selection")
    with pytest.raises(ValueError):
        stop_session(sid, 5, 2, 1, "overwrite")
    assert report(local_today())["baseline_sessions"] == 1
    assert client.get("/api/validation/report").status_code == 200
    assert "实际费用 | 未知" in client.get("/api/validation/report.md").text
    assert (
        client.get(f"/api/validation/report?day={local_today() + timedelta(days=1)}").status_code
        == 422
    )


def test_session_durations_split_at_local_midnight(database):
    with Session() as db:
        source(db, next_due_at=now() + timedelta(days=1))
    session = start_session("test-editor", "system", "review", ["test-source"], "Test scope")
    day = date(2026, 9, 10)
    _, end = day_bounds(day)
    with Session() as db:
        row = db.get(WorkSession, session.id)
        row.started_at, row.ended_at = end - timedelta(minutes=10), end + timedelta(minutes=20)
        db.commit()
    assert report(day)["work_seconds"] == {"system": 600}
    assert report(day + timedelta(days=1))["work_seconds"] == {"system": 1200}
