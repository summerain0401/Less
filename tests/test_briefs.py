from less.db import Session
from less.models import BriefReview, BriefVersion
from sqlalchemy import func, select
from test_clustering import another, merge
from test_editorial import Editor


def prepared():
    e = Editor()
    e.link()
    claim = e.claim()
    evidence = e.evidence(claim)
    e.verify(evidence)
    e.value()
    e.post("/quality", {"status": "passed", "gaps": []})
    e.post("/decision", {"status": "selected"})
    content = {
        "title": "Fixture brief",
        "why_it_matters": "Bounded task queue use",
        "what_changed": "Queue added",
        "our_take": "Interpretation; test first",
        "try_it": "",
        "facts": [{"claim_id": claim, "evidence_ids": [evidence]}],
    }
    return e, content


def save(e, content, revision=0, status=201):
    response = e.client.post(
        "/api/briefs",
        json={
            "actor": "fixture-editor",
            "event_id": e.id,
            "event_revision": e.detail()["event"]["revision"],
            "expected_revision": revision,
            "reason": "Fixture draft or correction",
            "content": content,
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def act(e, brief, action, status=200, **changes):
    response = e.client.post(
        f"/api/briefs/{brief['id']}/actions",
        json={
            "actor": "fixture-editor",
            "revision": brief["revision"],
            "action": action,
            "reason": "Fixture review, not real publication",
            "original_checked": True,
            **changes,
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def publish(e, brief):
    act(e, brief, "submit")
    act(e, brief, "approve")
    act(e, brief, "publish")


def test_approval_required_current_version_and_correction_hides_old_content(database):
    e, content = prepared()
    brief = save(e, content)
    act(e, brief, "publish", 422)
    act(e, brief, "approve", 422)
    act(e, brief, "submit")
    act(e, brief, "approve", 422, original_checked=False)
    act(e, brief, "approve")
    act(e, brief, "publish")
    today = e.client.get("/api/today").json()
    assert today["readable_count"] == 1
    assert today["entries"][0]["sources"][0]["quote"] == "The release adds a task queue."
    corrected = save(e, {**content, "title": "Corrected fixture"}, revision=1)
    assert corrected["revision"] == 2
    assert e.client.get("/api/today").json()["entries"][0]["content"] is None
    act(e, brief, "publish", 422)
    act(e, corrected, "publish", 422)
    publish(e, corrected)
    today = e.client.get("/api/today").json()
    assert len(today["entries"]) == 1 and today["entries"][0]["revision"] == 2
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(BriefVersion)) == 2
        assert (
            db.scalar(
                select(func.count()).select_from(BriefReview).where(BriefReview.action == "approve")
            )
            == 2
        )
    act(e, corrected, "withdraw")
    assert e.client.get("/api/today").json()["entries"][0]["status"] == "withdrawn"


def test_evidence_change_or_merge_invalidates_published_brief(database):
    e, content = prepared()
    brief = save(e, content)
    publish(e, brief)
    evidence = content["facts"][0]["evidence_ids"][0]
    e.post(
        f"/evidence/{evidence}/review", {"status": "needs_review", "original_checked": False}, 200
    )
    detail = e.client.get(f"/api/briefs/{brief['id']}").json()
    assert detail["brief"]["status"] == "needs_review"
    assert not detail["current_eligible"]
    assert detail["reviews"][-1]["action"] == "source_changed"
    assert e.client.get("/api/today").json()["readable_count"] == 0
    save(e, content, revision=1, status=422)
    target = another(e)
    merge(e, target)
    assert e.client.get("/api/today").json()["entries"][0]["sources"] == []


def test_draft_cannot_skip_critical_claims_or_reuse_unrelated_evidence(database):
    e, content = prepared()
    missing = {**content, "facts": [{"claim_id": "other", "evidence_ids": ["other"]}]}
    save(e, missing, status=422)
    duplicate = {**content, "facts": content["facts"] * 2}
    save(e, duplicate, status=422)
    brief = save(e, content)
    save(e, content, status=422)
    assert e.client.get("/api/today").json()["recorded"] is False
    act(e, brief, "submit")
    act(e, brief, "return_to_draft")
    act(e, brief, "publish", 422)


def test_zero_content_day_is_explicit_and_no_backdating(database):
    e = Editor()
    result = e.client.post(
        "/api/today/note",
        json={"actor": "fixture-editor", "note": "No qualified content in fixture"},
    )
    assert result.status_code == 200
    today = e.client.get("/api/today").json()
    assert today["recorded"] and today["entries"] == []
    assert today["note"] == "No qualified content in fixture"
    assert not e.client.get("/api/today?day=2020-01-01").json()["recorded"]


def test_today_cap_cannot_be_bypassed_by_sixth_publication(database):
    e, content = prepared()
    publish(e, save(e, content))
    for i in range(5):
        other = another(e, title=f"Fixture event {i}")
        e.id = other["id"]
        e.base = f"/api/editorial/events/{e.id}"
        e.link()
        claim = e.claim()
        evidence = e.evidence(claim)
        e.verify(evidence)
        e.value()
        e.post("/quality", {"status": "passed", "gaps": []})
        e.post("/decision", {"status": "selected"})
        brief = save(e, {**content, "facts": [{"claim_id": claim, "evidence_ids": [evidence]}]})
        act(e, brief, "submit")
        act(e, brief, "approve")
        act(e, brief, "publish", 422 if i == 4 else 200)
    assert e.client.get("/api/today").json()["readable_count"] == 5
