from fastapi.testclient import TestClient
from less.api import app
from less.db import Session
from less.models import AuditLog, EditorialEvent, EditorialReview
from sqlalchemy import func, select
from test_pipeline import version


class Editor:
    def __init__(self):
        self.client = TestClient(app)
        self.version_id = version()
        response = self.client.post(
            "/api/editorial/events",
            json={
                "actor": "test-editor",
                "title": "Test task queue release",
                "subject": "Test authors",
                "action": "release",
                "object": "task queue",
                "scope": "Test fixture, not real content",
            },
        )
        assert response.status_code == 201, response.text
        self.id = response.json()["id"]
        self.base = f"/api/editorial/events/{self.id}"

    def detail(self):
        response = self.client.get(self.base)
        assert response.status_code == 200, response.text
        return response.json()

    def post(self, path, body, status=201):
        response = self.client.post(
            self.base + path,
            json={
                "actor": "test-editor",
                "revision": self.detail()["event"]["revision"],
                "reason": "Explicit fixture review",
                **body,
            },
        )
        assert response.status_code == status, response.text
        return response.json()

    def link(self):
        return self.post(
            "/members", {"version_id": self.version_id, "paragraph_ids": ["p0001", "p0002"]}, 200
        )

    def claim(self):
        return self.post(
            "/claims",
            {"text": "Authors released a task queue", "kind": "fact_candidate", "critical": True},
        )["id"]

    def evidence(self, claim, direction="supporting"):
        return self.post(
            "/evidence",
            {
                "claim_id": claim,
                "version_id": self.version_id,
                "paragraph_ids": ["p0001"],
                "quote": "The release adds a task queue.",
                "direction": direction,
                "rationale": "Directly describes the release",
                "source_root": "https://example.com/release",
                "limitations": "Publisher description; no independent productivity evaluation",
            },
        )["id"]

    def verify(self, evidence):
        self.post(
            f"/evidence/{evidence}/review", {"status": "verified", "original_checked": True}, 200
        )

    def value(self):
        return self.post(
            "/value",
            {
                "status": "passed",
                "important": False,
                "useful": True,
                "useful_reason": "Can test a bounded task queue workflow",
            },
        )


def test_important_or_useful_is_independent_from_quality(database):
    e = Editor()
    e.value()
    assert e.detail()["event"]["value_status"] == "passed"
    assert e.detail()["event"]["quality_status"] == "pending"
    e.post("/decision", {"status": "selected"}, 422)
    e.post("/quality", {"status": "passed", "gaps": []}, 422)
    e.post("/value", {"status": "passed", "important": False, "useful": False}, 422)
    e.post("/value", {"status": "passed", "important": True, "useful": False}, 422)
    e.post(
        "/value",
        {
            "status": "rejected",
            "important": True,
            "useful": False,
            "important_reason": "Already accepted value",
        },
        422,
    )
    e.post("/quality", {"status": "pending", "gaps": ["No original evidence yet"]})
    e.post("/decision", {"status": "deferred"})
    assert e.detail()["event"]["value_status"] == "passed"


def test_evidence_location_membership_and_verification_are_required(database):
    e = Editor()
    cid = e.claim()
    body = {
        "claim_id": cid,
        "version_id": e.version_id,
        "paragraph_ids": ["p0001"],
        "quote": "The release adds a task queue.",
        "direction": "supporting",
        "rationale": "Fixture",
        "source_root": "publisher",
        "limitations": "Publisher only",
    }
    e.post("/evidence", body, 422)
    e.post("/members", {"version_id": e.version_id, "paragraph_ids": ["invented"]}, 422)
    e.link()
    e.post("/evidence", {**body, "quote": "Invented fact."}, 422)
    e.post("/evidence", {**body, "paragraph_ids": ["p0001", "p0001"]}, 422)
    eid = e.post("/evidence", body)["id"]
    e.post("/quality", {"status": "passed", "gaps": []}, 422)
    e.post(f"/evidence/{eid}/review", {"status": "verified", "original_checked": False}, 422)
    e.verify(eid)
    e.value()
    e.post("/quality", {"status": "passed", "gaps": ["Still missing key conditions"]}, 422)
    e.post("/quality", {"status": "passed", "gaps": []})
    e.post("/decision", {"status": "selected"})
    assert e.detail()["event"]["decision"] == "selected"
    assert e.detail()["verified_source_roots"] == 1
    # No publishing route has been introduced as a shortcut around future Brief approval.
    assert e.client.post("/api/briefs/publish", json={}).status_code == 404


def test_context_is_not_support_and_counter_evidence_cannot_be_ignored(database):
    e = Editor()
    e.link()
    cid = e.claim()
    context = e.evidence(cid, "context")
    e.verify(context)
    e.post("/quality", {"status": "passed", "gaps": []}, 422)
    support = e.evidence(cid)
    e.verify(support)
    counter = e.evidence(cid, "counter")
    e.post("/quality", {"status": "passed", "gaps": []}, 422)
    e.post(
        "/quality",
        {
            "status": "passed",
            "gaps": [],
            "conflict_resolutions": {
                counter: "Scope narrowed to availability; no productivity claim"
            },
        },
    )
    # Three relations to the same publisher are one registered root, not independent witnesses.
    assert e.detail()["verified_source_roots"] == 1


def test_membership_changes_reset_gates_and_preserve_evidence_and_reviews(database):
    e = Editor()
    e.link()
    cid = e.claim()
    evidence = e.evidence(cid)
    e.verify(evidence)
    e.value()
    e.post("/quality", {"status": "passed", "gaps": []})
    e.post("/decision", {"status": "selected"})
    old = e.detail()
    member = old["members"][0]["id"]
    e.post(f"/members/{member}/unlink", {}, 200)
    changed = e.detail()
    assert (
        changed["event"]["value_status"]
        == changed["event"]["quality_status"]
        == changed["event"]["decision"]
        == "pending"
    )
    assert changed["evidence"][0]["status"] == "needs_review"
    assert len(changed["reviews"]) == 3
    e.post(f"/evidence/{evidence}/review", {"status": "verified", "original_checked": True}, 422)
    e.link()
    assert e.detail()["members"][0]["id"] == member
    assert e.detail()["evidence"][0]["status"] == "needs_review"
    stale = e.client.post(
        e.base + "/decision",
        json={
            "actor": "test-editor",
            "revision": old["event"]["revision"],
            "status": "rejected",
            "reason": "Outdated screen",
        },
    )
    assert stale.status_code == 422
    e.post("/members", {"version_id": e.version_id, "paragraph_ids": ["p0002"]}, 422)
    assert any(h["action"] == "event-unlink" for h in e.detail()["history"])


def test_event_edits_preserve_previous_skeleton_and_isolate_other_events(database):
    e = Editor()
    e.link()
    before = e.detail()["event"]
    body = {
        k: before[k]
        for k in ("title", "subject", "action", "object", "scope", "happened_at", "event_version")
    }
    response = e.client.patch(
        e.base,
        json={
            **body,
            "title": "Corrected title",
            "revision": before["revision"],
            "actor": "test-editor",
            "reason": "Original title exceeded scope",
        },
    )
    assert response.status_code == 200
    assert response.json()["revision"] == before["revision"] + 1
    response = e.client.post("/api/editorial/events", json={**body, "actor": "test-editor"})
    other = response.json()["id"]
    cid = e.claim()
    invalid = e.client.post(
        f"/api/editorial/events/{other}/evidence",
        json={
            "actor": "test-editor",
            "revision": 1,
            "reason": "wrong event",
            "claim_id": cid,
            "version_id": e.version_id,
            "paragraph_ids": ["p0001"],
            "quote": "The release adds a task queue.",
            "direction": "supporting",
            "rationale": "Fixture",
            "source_root": "publisher",
            "limitations": "Fixture",
        },
    )
    assert invalid.status_code == 422
    with Session() as db:
        edit = db.scalar(select(AuditLog).where(AuditLog.action == "event-edit"))
        assert edit.detail["previous"]["title"] == before["title"]
        assert db.scalar(select(func.count()).select_from(EditorialEvent)) == 2
        assert db.scalar(select(func.count()).select_from(EditorialReview)) == 0
    result = e.client.get("/api/editorial/events?limit=1").json()
    assert result["total"] == 2 and len(result["events"]) == 1
