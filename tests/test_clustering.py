from fastapi.testclient import TestClient
from less.api import app
from less.db import Session
from less.models import ClusterOperation, EventClaim, EventMember, Evidence, ItemVersion
from sqlalchemy import func, select
from test_editorial import Editor


def another(e, **changes):
    fields = {
        k: e.detail()["event"][k]
        for k in ("title", "subject", "action", "object", "scope", "event_version", "happened_at")
    }
    response = e.client.post(
        "/api/editorial/events", json={**fields, **changes, "actor": "test-editor"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def merge(e, other):
    response = e.client.post(
        "/api/editorial/clusters/merge",
        json={
            "actor": "test-editor",
            "reason": "Same release, cross-source fixture",
            "target_id": other["id"],
            "events": [
                {"id": e.id, "revision": e.detail()["event"]["revision"]},
                {"id": other["id"], "revision": other["revision"]},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def restore(e, operation, status=200):
    response = e.client.post(
        f"/api/editorial/clusters/{operation['id']}/restore",
        json={"actor": "test-editor", "reason": "Undo fixture grouping after review"},
    )
    assert response.status_code == status, response.text
    return response.json()


def test_merge_preserves_ids_mapping_and_restore_without_reapproving(database):
    e = Editor()
    e.link()
    cid = e.claim()
    evidence = e.evidence(cid)
    e.verify(evidence)
    e.value()
    e.post("/quality", {"status": "passed", "gaps": []})
    target = another(e)
    operation = merge(e, target)
    source = e.detail()
    assert source["event"]["lifecycle"] == "merged"
    assert source["event"]["redirected_to"] == target["id"]
    assert source["claims"] == []
    e.post("/claims", {"text": "Cannot edit mapped event", "kind": "reported_claim"}, 422)
    merged = e.client.get(f"/api/editorial/events/{target['id']}").json()
    assert merged["claims"][0]["id"] == cid
    assert merged["evidence"][0]["id"] == evidence
    assert merged["evidence"][0]["status"] == "needs_review"
    assert merged["cluster_operations"][0]["id"] == operation["id"]
    assert e.client.get("/api/editorial/events").json()["total"] == 1
    assert e.client.get("/api/editorial/events?include_archived=true").json()["total"] == 2
    restore(e, operation)
    restored = e.detail()
    assert restored["event"]["lifecycle"] == "active"
    assert restored["event"]["redirected_to"] is None
    assert restored["claims"][0]["id"] == cid
    assert restored["evidence"][0]["status"] == "needs_review"
    assert restored["event"]["quality_status"] == "pending"
    assert len(restored["reviews"]) == 2
    assert restored["cluster_operations"][0]["status"] == "restored"
    restore(e, operation, 422)
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(ItemVersion)) == 1
        assert db.scalar(select(func.count()).select_from(Evidence)) == 1


def test_merge_shared_version_unions_paragraphs_and_restore_retains_both_member_ids(database):
    e = Editor()
    e.post("/members", {"version_id": e.version_id, "paragraph_ids": ["p0001"]}, 200)
    source_member = e.detail()["members"][0]
    target = another(e)
    response = e.client.post(
        f"/api/editorial/events/{target['id']}/members",
        json={
            "actor": "test-editor",
            "reason": "Other paragraph",
            "revision": 1,
            "version_id": e.version_id,
            "paragraph_ids": ["p0002"],
        },
    )
    assert response.status_code == 200
    target = response.json()
    operation = merge(e, target)
    merged = e.client.get(f"/api/editorial/events/{target['id']}").json()
    assert len(merged["members"]) == 1
    assert set(merged["members"][0]["paragraph_ids"]) == {"p0001", "p0002"}
    restore(e, operation)
    assert e.detail()["members"][0]["id"] == source_member["id"]
    assert e.detail()["members"][0]["paragraph_ids"] == ["p0001"]
    restored = e.client.get(f"/api/editorial/events/{target['id']}").json()
    assert restored["members"][0]["paragraph_ids"] == ["p0002"]


def test_restore_refuses_to_overwrite_later_content_and_multi_event_change_is_atomic(database):
    e = Editor()
    e.link()
    target = another(e)
    operation = merge(e, target)
    response = e.client.post(
        f"/api/editorial/events/{target['id']}/claims",
        json={
            "actor": "test-editor",
            "reason": "New finding after merge",
            "revision": operation["after_revisions"][target["id"]],
            "text": "A later finding",
            "kind": "reported_claim",
        },
    )
    assert response.status_code == 201
    restore(e, operation, 422)
    with Session() as db:
        assert db.get(ClusterOperation, operation["id"]).status == "applied"
        assert db.scalar(select(EventClaim.text)) == "A later finding"
    assert e.detail()["event"]["lifecycle"] == "merged"
    invalid = e.client.post(
        "/api/editorial/clusters/merge",
        json={
            "actor": "test-editor",
            "reason": "Invalid duplicate",
            "target_id": target["id"],
            "events": [target, target],
        },
    )
    assert invalid.status_code == 422


def test_split_moves_claims_and_evidence_and_restores_new_event_to_readonly_mapping(database):
    e = Editor()
    e.link()
    cid = e.claim()
    evidence = e.evidence(cid)
    e.verify(evidence)
    fields = {
        k: e.detail()["event"][k]
        for k in ("title", "subject", "action", "object", "scope", "happened_at", "event_version")
    }
    operation = e.post(
        "/split",
        {
            "member_ids": [e.detail()["members"][0]["id"]],
            "claim_ids": [cid],
            "target": {**fields, "title": "Independent evaluation"},
        },
    )
    created = operation["created_event_ids"][0]
    detail = e.client.get(f"/api/editorial/events/{created}").json()
    assert detail["claims"][0]["id"] == cid and detail["evidence"][0]["id"] == evidence
    assert not e.detail()["members"][0]["active"]
    restore(e, operation)
    restored = e.client.get(f"/api/editorial/events/{created}").json()
    assert restored["event"]["lifecycle"] == "retired"
    assert restored["event"]["redirected_to"] == e.id
    assert restored["claims"] == []
    assert e.detail()["claims"][0]["id"] == cid


def test_split_retains_shared_original_for_claims_remaining_in_source(database):
    e = Editor()
    e.link()
    moved = e.claim()
    remaining = e.claim()
    e.evidence(moved)
    e.evidence(remaining)
    fields = {k: e.detail()["event"][k] for k in ("title", "subject", "action", "object", "scope")}
    operation = e.post(
        "/split",
        {"member_ids": [e.detail()["members"][0]["id"]], "claim_ids": [moved], "target": fields},
    )
    assert e.detail()["members"][0]["active"]
    assert [c["id"] for c in e.detail()["claims"]] == [remaining]
    with Session() as db:
        assert db.get(EventClaim, moved).event_id == operation["created_event_ids"][0]
        assert len(db.scalars(select(EventMember).where(EventMember.active.is_(True))).all()) == 2


def test_claim_correction_invalidates_old_evidence_checks_and_retains_previous_text(database):
    e = Editor()
    e.link()
    cid = e.claim()
    eid = e.evidence(cid)
    e.verify(eid)
    before = e.detail()
    response = e.client.patch(
        e.base + f"/claims/{cid}",
        json={
            "actor": "test-editor",
            "revision": before["event"]["revision"],
            "reason": "Narrow claim to publisher attribution",
            "text": "Publisher describes a task queue",
            "kind": "reported_claim",
            "critical": True,
        },
    )
    assert response.status_code == 200
    detail = e.detail()
    assert detail["evidence"][0]["status"] == "needs_review"
    change = next(h for h in detail["history"] if h["action"] == "claim-edit")
    assert change["detail"]["previous"]["text"] == before["claims"][0]["text"]
    assert change["detail"]["previous_evidence_checks"][0]["status"] == "verified"


def test_suggestions_do_not_mutate_events_or_approve_gates(database):
    e = Editor()
    e.link()
    another(e)
    result = TestClient(app).get("/api/editorial/cluster-suggestions")
    assert result.status_code == 200, result.text
    assert result.json()["method"] == "event-skeleton-rules-v1"
    assert len(result.json()["pairs"]) == 1
    assert e.detail()["event"]["value_status"] == "pending"
    assert e.detail()["cluster_operations"] == []


def test_new_migration_matches_models_in_isolated_database(database):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from less.db import Base

    with database.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_split_requires_every_original_referenced_by_moved_claim(database):
    from less.collector import save_material
    from less.models import EditorialEvent
    from test_pipeline import material

    e = Editor()
    e.link()
    cid = e.claim()
    with Session() as db:
        version, _ = save_material(
            db, "test-source", {**material(), "url": "https://example.com/second"}
        )
        db.commit()
        second_id = version.id
    e.post("/members", {"version_id": second_id, "paragraph_ids": ["p0001"]}, 200)
    e.post(
        "/evidence",
        {
            "claim_id": cid,
            "version_id": second_id,
            "paragraph_ids": ["p0001"],
            "quote": "The release adds a task queue.",
            "direction": "supporting",
            "rationale": "Second original",
            "source_root": "publisher",
            "limitations": "Fixture",
        },
    )
    first = next(m for m in e.detail()["members"] if m["version_id"] == e.version_id)
    target = {k: e.detail()["event"][k] for k in ("title", "subject", "action", "object", "scope")}
    e.post("/split", {"member_ids": [first["id"]], "claim_ids": [cid], "target": target}, 422)
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(EditorialEvent)) == 1
        assert db.scalar(select(func.count()).select_from(ClusterOperation)) == 0


def test_overlapping_merges_cannot_both_consume_the_same_revision(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    e = Editor()
    middle, right = another(e), another(e)
    left = e.detail()["event"]
    barrier = Barrier(2)

    def apply(pair):
        barrier.wait(timeout=5)
        with TestClient(app) as client:
            return client.post(
                "/api/editorial/clusters/merge",
                json={
                    "actor": "test-editor",
                    "reason": "Concurrent fixture",
                    "target_id": pair[0]["id"],
                    "events": [
                        {"id": event["id"], "revision": event["revision"]} for event in pair
                    ],
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(apply, [(left, middle), (middle, right)]))
    assert sorted(statuses) == [201, 422]
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(ClusterOperation)) == 1
