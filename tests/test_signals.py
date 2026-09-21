from less.db import Session
from less.models import SignalRecord
from sqlalchemy import select
from test_briefs import prepared


def create(e):
    thesis = {
        "title": "Fixture hypothesis",
        "statement": "Bounded tasks may shift to delegation",
        "scope": "Test fixture only",
        "starts_on": "2026-09-21",
        "ends_on": "2026-09-28",
        "falsification": "Review effort exceeds saved time",
        "counter_plan": "Search failures and costs",
        "owner": "Fixture editor",
    }
    response = e.client.post("/api/signals", json={"actor": "Fixture editor", "thesis": thesis})
    assert response.status_code == 201, response.text
    return "/api/signals/" + response.json()["id"]


def post(e, path, suffix, values, status=200):
    revision = e.client.get(path).json()["signal"]["revision"]
    r = e.client.post(
        path + suffix,
        json={
            "actor": "Fixture editor",
            "revision": revision,
            "reason": "Fixture review",
            **values,
        },
    )
    assert r.status_code == status, r.text
    return r.json()


def search(e, path):
    return post(
        e,
        path,
        "/searches",
        {
            "query": "agent review cost failures",
            "source_types": "Independent engineering reports",
            "results": "Fixture only; no actual search claimed",
            "gaps": "No real counter material in fixture",
        },
    )


def review(e, path, status="candidate", **values):
    return post(
        e,
        path,
        "/reviews",
        {
            "status": status,
            "our_view": "Only a hypothesis",
            "independence": "Publisher only",
            "alternatives": "Tool novelty may explain interest",
            "original_checked": True,
            **values,
        },
    )


def test_signal_does_not_mature_without_evidence_search_and_explicit_review(database):
    e, content = prepared()
    path = create(e)
    post(
        e,
        path,
        "/reviews",
        {
            "status": "candidate",
            "our_view": "fixture",
            "independence": "fixture",
            "alternatives": "fixture",
            "original_checked": True,
        },
        422,
    )
    eid = content["facts"][0]["evidence_ids"][0]
    post(
        e,
        path,
        "/evidence",
        {
            "evidence_id": eid,
            "direction": "supporting",
            "rationale": "Starting observation",
            "original_checked": False,
        },
        422,
    )
    post(
        e,
        path,
        "/evidence",
        {
            "evidence_id": eid,
            "direction": "supporting",
            "rationale": "Starting observation",
            "original_checked": True,
        },
    )
    assert e.client.get(path).json()["signal"]["last_reviewed_at"] is None
    search(e, path)
    result = review(e, path)
    assert result["status"] == "candidate" and not result["needs_review"]
    post(
        e,
        path,
        "/reviews",
        {
            "status": "candidate",
            "our_view": "fixture",
            "independence": "fixture",
            "alternatives": "fixture",
            "original_checked": True,
        },
        422,
    )
    search(e, path)
    post(
        e,
        path,
        "/reviews",
        {
            "status": "emerging",
            "our_view": "fixture",
            "independence": "fixture",
            "alternatives": "fixture",
            "original_checked": True,
        },
        422,
    )
    result = review(e, path, "weakening")
    assert result["status"] == "weakening"
    search(e, path)
    assert review(e, path, "rejected")["status"] == "rejected"
    with Session() as db:
        decisions = db.scalars(
            select(SignalRecord)
            .where(SignalRecord.kind == "review")
            .order_by(SignalRecord.created_at)
        ).all()
        assert [r.detail["status"] for r in decisions] == ["candidate", "weakening", "rejected"]


def test_signal_source_correction_marks_review_without_rewriting_past_judgment(database):
    e, content = prepared()
    path = create(e)
    eid = content["facts"][0]["evidence_ids"][0]
    linked = post(
        e,
        path,
        "/evidence",
        {
            "evidence_id": eid,
            "direction": "supporting",
            "rationale": "Fixture",
            "original_checked": True,
        },
    )
    search(e, path)
    before = review(e, path)
    e.post(f"/evidence/{eid}/review", {"status": "needs_review", "original_checked": False}, 200)
    detail = e.client.get(path).json()
    assert detail["signal"]["needs_review"] and detail["signal"]["status"] == "candidate"
    assert detail["signal"]["last_reviewed_at"] == before["last_reviewed_at"]
    assert detail["stale_link_ids"] == [linked["id"]]
    assert detail["signal"]["revision"] == before["revision"] + 1
    e.verify(eid)
    post(
        e,
        path,
        "/evidence",
        {
            "evidence_id": eid,
            "direction": "counter",
            "rationale": "Reconsidered boundary",
            "original_checked": True,
        },
    )
    search(e, path)
    post(
        e,
        path,
        "/reviews",
        {
            "status": "weakening",
            "our_view": "fixture",
            "independence": "fixture",
            "alternatives": "fixture",
            "original_checked": True,
        },
        422,
    )
    assert (
        review(e, path, "weakening", counter_resolutions={linked["id"]: "Scope now too broad"})[
            "status"
        ]
        == "weakening"
    )
    assert any(r["kind"] == "source_changed" for r in e.client.get(path).json()["records"])


def test_thesis_versions_and_stale_updates_are_retained(database):
    e, _ = prepared()
    path = create(e)
    initial = e.client.get(path).json()["signal"]
    body = {
        "actor": "Fixture editor",
        "revision": initial["revision"],
        "reason": "Narrow scope",
        "thesis": {**initial["thesis"], "scope": "Only deterministic unit-test tasks"},
    }
    assert e.client.patch(path, json=body).status_code == 200
    assert e.client.patch(path, json=body).status_code == 422
    records = e.client.get(path).json()["records"]
    assert records[-1]["detail"]["previous"]["scope"] == "Test fixture only"
    assert e.client.get(path).json()["signal"]["needs_review"]
