import json
from datetime import timedelta

from less import assist
from less.ai import AIError, AIResult
from less.budget import daily_usage, local_today
from less.config import settings
from less.db import Session
from less.models import AssistRun, RuntimeState, now
from less.pipeline import execute_normalize, queue_normalize, recover_interrupted, resume_ai
from test_briefs import prepared
from test_editorial import Editor
from test_pipeline import Success


def proposal():
    return {
        "event": {
            "title": "Fixture queue release",
            "subject": "Authors",
            "action": "release",
            "object": "queue",
            "scope": "Fixture",
            "event_version": None,
            "happened_at": None,
        },
        "claims": [
            {
                "text": "Authors released queue",
                "kind": "reported_claim",
                "paragraph_ids": ["p0001"],
                "quote": "The release adds a task queue.",
            }
        ],
        "uncertain": False,
        "limitations": ["Publisher only"],
    }


class Fake:
    def __init__(self, output):
        self.output = output

    def execute(self, material):
        return AIResult(json.dumps(self.output), {})


def test_event_draft_is_idempotent_and_never_marks_evidence_verified(database):
    e = Editor()
    run = assist.queue("event", e.version_id)
    assert assist.queue("event", e.version_id).id == run.id
    assist.execute(run.id, Fake(proposal()))
    response = e.client.post(f"/api/assist/{run.id}/event", json={"actor": "Fixture editor"})
    assert response.status_code == 200, response.text
    eid = response.json()["id"]
    assert (
        e.client.post(f"/api/assist/{run.id}/event", json={"actor": "Fixture editor"}).json()["id"]
        == eid
    )
    detail = e.client.get(f"/api/editorial/events/{eid}").json()
    assert (
        detail["event"]["quality_status"] == "pending"
        and detail["event"]["value_status"] == "pending"
    )
    assert detail["evidence"][0]["status"] == "unchecked"
    assert detail["reviews"] == []


def test_invalid_quotes_preserved_but_cannot_be_adopted(database):
    e = Editor()
    run = assist.queue("event", e.version_id)
    invalid = proposal()
    invalid["claims"][0]["quote"] = "Invented productivity claim"
    assist.execute(run.id, Fake(invalid))
    with Session() as db:
        saved = db.get(AssistRun, run.id)
        assert saved.status == "failed" and saved.raw_output and saved.output is None
    assert (
        e.client.post(f"/api/assist/{run.id}/event", json={"actor": "Fixture"}).status_code == 422
    )


def test_value_or_gate_ranking_ignores_stale_revision(database):
    e = Editor()
    e.link()
    run = assist.queue("value", event_ids=[e.id])
    value = {
        "important": 0,
        "useful": 2,
        "important_reason": "Bounded change only",
        "useful_reason": "Can test queue workflows",
        "uncertain": False,
        "citations": [
            {
                "version_id": e.version_id,
                "paragraph_ids": ["p0001"],
                "quote": "The release adds a task queue.",
            }
        ],
        "limitations": ["Unverified efficacy"],
    }
    assist.execute(run.id, Fake(value))
    rows = e.client.get("/api/assist/candidates").json()["rows"]
    assert rows[0]["selection"] == "candidate"
    assert e.detail()["event"]["value_status"] == "pending"
    e.claim()
    assert e.client.get("/api/assist/candidates").json()["rows"] == []
    assert assist.queue("value", event_ids=[e.id]).id != run.id


def test_assistance_shares_daily_budget_with_normalization(database, monkeypatch):
    e = Editor()
    monkeypatch.setattr(settings(), "ai_daily_limit", 1)
    normal = queue_normalize(e.version_id)
    execute_normalize(normal, Success())
    run = assist.queue("event", e.version_id)
    assist.execute(run.id, Fake(proposal()))
    with Session() as db:
        assert db.get(AssistRun, run.id).status == "budget_wait"
        assert db.get(AssistRun, run.id).attempts == 0
        assert daily_usage(db, local_today())["used"] == 1


def test_quota_pause_recovery_and_attempt_history(database):
    e = Editor()
    run = assist.queue("event", e.version_id)

    class Quota:
        def execute(self, material):
            raise AIError("quota", "Fixture quota")

    assist.execute(run.id, Quota())
    with Session() as db:
        assert db.get(RuntimeState, "ai").value["paused"]
        assert db.get(AssistRun, run.id).status == "blocked"
    resume_ai("Fixture")
    assist.execute(run.id, Fake(proposal()))
    with Session() as db:
        saved = db.get(AssistRun, run.id)
        assert saved.status == "succeeded" and len(saved.attempts_log) == 2
        assert daily_usage(db, local_today())["used"] == 2
        saved.status = "running"
        saved.started_at = now() - timedelta(seconds=settings().codex_timeout + 61)
        db.commit()
    recover_interrupted()
    with Session() as db:
        assert db.get(AssistRun, run.id).status == "retryable"


def test_brief_output_must_cover_critical_claims(database):
    e, content = prepared()
    run = assist.queue("brief", event_ids=[e.id])
    assist.execute(run.id, Fake(content))
    with Session() as db:
        assert db.get(AssistRun, run.id).status == "succeeded"
    invalid = {**content, "facts": [{"claim_id": "invented", "evidence_ids": ["invented"]}]}
    import pytest

    with pytest.raises(ValueError):
        assist.validate(json.dumps(invalid), "brief", run.input)


def test_pair_requires_quotes_from_both_distinct_originals():
    payload = {
        "events": [
            {
                "materials": [
                    {"version_id": "a", "paragraphs": [{"id": "p1", "text": "Left original"}]}
                ]
            },
            {
                "materials": [
                    {"version_id": "b", "paragraphs": [{"id": "p1", "text": "Right original"}]}
                ]
            },
        ]
    }
    value = {
        "verdict": "uncertain",
        "reason": "Fixture",
        "conflicts": [],
        "limitations": [],
        "citations": [{"version_id": "a", "paragraph_ids": ["p1"], "quote": "Left original"}],
    }
    import pytest

    with pytest.raises(ValueError):
        assist.validate(json.dumps(value), "pair", payload)
    value["citations"].append(
        {"version_id": "b", "paragraph_ids": ["p1"], "quote": "Right original"}
    )
    assert assist.validate(json.dumps(value), "pair", payload)["verdict"] == "uncertain"


def test_exclusion_audit_is_frozen_blind_and_preserves_corrections(database):
    e = Editor()
    e.link()
    run = assist.queue("value", event_ids=[e.id])
    output = {
        "important": 0,
        "useful": 1,
        "important_reason": "Narrow update",
        "useful_reason": "MACHINE_REASON",
        "uncertain": False,
        "citations": [
            {
                "version_id": e.version_id,
                "paragraph_ids": ["p0001"],
                "quote": "The release adds a task queue.",
            }
        ],
        "limitations": [],
    }
    assist.execute(run.id, Fake(output))
    created = e.client.post(
        "/api/assist/audits",
        json={"actor": "Fixture editor", "seed": "fixed", "pool": "excluded", "target_count": 20},
    )
    assert created.status_code == 201, created.text
    path = f"/api/assist/audits/{created.json()['id']}"
    before = e.client.get(path).json()
    assert before["samples"][0]["proposal"] is None
    assert before["population"] == 1 and len(before["samples"]) == 1
    e.claim()  # A later event edit cannot rewrite this fixed evaluation.
    assert e.client.get(path).json()["samples"][0]["input"] == before["samples"][0]["input"]
    body = {
        "actor": "Fixture editor",
        "run_id": run.id,
        "expected_revision": 0,
        "verdict": "value",
        "important_reason": "Small scope",
        "useful_reason": "Useful bounded workflow",
        "original_checked": True,
    }
    assert (
        e.client.post(path + "/reviews", json={**body, "original_checked": False}).status_code
        == 422
    )
    assert e.client.post(path + "/reviews", json=body).status_code == 201
    assert e.client.post(path + "/reviews", json=body).status_code == 422
    assert (
        e.client.post(
            path + "/reviews", json={**body, "expected_revision": 1, "verdict": "uncertain"}
        ).status_code
        == 201
    )
    after = e.client.get(path).json()
    assert after["blind_counts"]["value"] == 1 and after["latest_counts"]["uncertain"] == 1
    assert after["samples"][0]["proposal"]["useful_reason"] == "MACHINE_REASON"
    assert e.detail()["reviews"] == []
    from less.validation import report

    assert report(local_today())["editorial_activity"]["machine_excluded"] == 1
