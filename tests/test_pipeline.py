from datetime import timedelta

from fastapi.testclient import TestClient
from less.ai import AIError, AIResult
from less.api import app
from less.collector import collect, save_material
from less.config import settings
from less.db import Session
from less.models import HumanReview, Item, ItemVersion, NormalizeRun, Source, SourceCheck, now
from less.pipeline import (
    ai_state,
    execute_normalize,
    queue_normalize,
    recover_interrupted,
    resume_ai,
)
from less.storage import read_blob
from less.tasks import schedule_due
from sqlalchemy import func, select
from test_extraction import output


def source(db, **overrides):
    value = Source(
        id="test-source",
        name="Test",
        node_url="https://example.com/",
        feed_url="https://example.com/feed",
        role="Primary",
        topics=["Agents"],
        coverage=["Builders"],
        authority="Test fixture",
        bias="Test fixture",
        **overrides,
    )
    db.add(value)
    db.commit()
    return value


def material():
    return {
        "url": "https://example.com/release",
        "title": "Task queue release",
        "author": None,
        "published_at": None,
        "text": "The release adds a task queue.\nThe authors have not evaluated productivity.",
        "raw": b"<p>The release adds a task queue.</p>",
        "acquisition": "test-fixture",
        "limitations": [],
    }


def version():
    with Session() as db:
        s = source(db)
        value, _ = save_material(db, s.id, material())
        db.commit()
        return value.id


class Success:
    def execute(self, material):
        return AIResult(output(), {"executor": "test-double", "cost": None})


class Failure:
    def __init__(self, code):
        self.code = code

    def execute(self, material):
        raise AIError(self.code, f"Test error: {self.code}")


def test_idempotency_versions_and_snapshot(database):
    with Session() as db:
        s = source(db)
        first, created = save_material(db, s.id, material())
        db.commit()
        assert created
        repeated, created = save_material(
            db, s.id, {**material(), "url": "https://example.com/release?utm_source=x"}
        )
        db.commit()
        assert not created and repeated.id == first.id
        updated, created = save_material(
            db, s.id, {**material(), "text": material()["text"] + "\nA correction."}
        )
        db.commit()
        assert created and updated.id != first.id
        assert db.scalar(select(func.count()).select_from(Item)) == 1
        assert db.scalar(select(func.count()).select_from(ItemVersion)) == 2
        assert read_blob(first.snapshot_path) == material()["raw"]


def test_invalid_ai_and_review_gate_preserve_history(database):
    vid = version()
    run_id = queue_normalize(vid)
    assert queue_normalize(vid) == run_id
    client = TestClient(app)
    body = {
        "run_id": run_id,
        "reviewer": "Test editor",
        "decision": "accepted",
        "note": "Checked original",
    }
    assert client.post(f"/api/versions/{vid}/reviews", json=body).status_code == 409
    execute_normalize(run_id, Success())
    assert client.post(f"/api/versions/{vid}/reviews", json=body).status_code == 201
    rerun = queue_normalize(vid, force=True)

    class Invalid:
        def execute(self, material):
            return AIResult(output("Invented quotation."), {})

    execute_normalize(rerun, Invalid())
    with Session() as db:
        assert db.get(NormalizeRun, rerun).status == "failed"
        assert db.get(NormalizeRun, rerun).raw_output
        assert db.scalar(select(HumanReview)).run_id == run_id
        assert db.get(NormalizeRun, run_id).status == "succeeded"
    assert client.post("/api/briefs/publish", json={}).status_code == 405
    response = client.get(f"/api/versions/{vid}")
    assert response.status_code == 200
    assert len(response.json()["reviews"]) == 1
    assert len(response.json()["runs"]) == 2


def test_quota_pause_resume_and_bounded_retries(database):
    vid = version()
    rid = queue_normalize(vid)
    execute_normalize(rid, Failure("quota"))
    with Session() as db:
        assert ai_state(db)["paused"]
        assert db.get(NormalizeRun, rid).status == "blocked"
    execute_normalize(rid, Success())
    resume_ai("test-editor")
    for _ in range(settings().max_attempts):
        with Session() as db:
            db.get(NormalizeRun, rid).next_attempt_at = now()
            db.commit()
        execute_normalize(rid, Failure("timeout"))
    with Session() as db:
        assert not ai_state(db)["paused"]
        assert db.get(NormalizeRun, rid).status == "failed"
        assert db.get(NormalizeRun, rid).attempts == settings().max_attempts
        history = db.get(NormalizeRun, rid).attempts_log
        assert history[0]["status"] == "blocked"
        assert history[-1]["status"] == "failed"
        assert len(history) == settings().max_attempts + 1


def test_interruption_recovery(database):
    rid = queue_normalize(version())
    with Session() as db:
        run = db.get(NormalizeRun, rid)
        run.status, run.attempts = "running", 1
        run.started_at = now() - timedelta(hours=2)
        db.commit()
    recover_interrupted()
    with Session() as db:
        assert db.get(NormalizeRun, rid).status == "retryable"
    execute_normalize(rid, Success())
    with Session() as db:
        assert db.get(NormalizeRun, rid).status == "succeeded"


def test_scheduler_records_missed_slots_without_double_counting(database):
    at = now()
    with Session() as db:
        source(db, next_due_at=at - timedelta(hours=13), interval_hours=6)
    schedule_due(at)
    schedule_due(at)
    with Session() as db:
        records = db.scalars(select(SourceCheck)).all()
        assert len(records) == 3
        assert sorted(c.status for c in records) == ["missed", "missed", "pending"]


def test_empty_feed_vs_parse_failure(database, monkeypatch):
    with Session() as db:
        s = source(db)
        check = SourceCheck(source_id=s.id, slot="test-empty")
        db.add(check)
        db.commit()
        cid = check.id
    empty_feed = b'<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title><link>https://example.com</link><description>Test</description></channel></rss>'
    monkeypatch.setattr("less.collector.fetch", lambda client, url: empty_feed)
    collect(cid)
    with Session() as db:
        assert db.get(SourceCheck, cid).status == "succeeded"
        assert db.get(SourceCheck, cid).item_count == 0
        bad = SourceCheck(source_id="test-source", slot="test-bad")
        db.add(bad)
        db.commit()
        bid = bad.id
    monkeypatch.setattr("less.collector.fetch", lambda client, url: b"<html>Not a feed</html>")
    collect(bid)
    with Session() as db:
        assert db.get(SourceCheck, bid).status == "retryable"
        assert db.get(SourceCheck, bid).attempts == 1


def test_local_api_rejects_cross_origin_mutation(database):
    client = TestClient(app)
    assert (
        client.post(
            "/api/ai/resume", json={"actor": "test"}, headers={"Origin": "https://external.example"}
        ).status_code
        == 403
    )
    assert client.post("/api/ai/resume", data={"actor": "test"}).status_code == 415
