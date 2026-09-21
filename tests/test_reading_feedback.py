from datetime import timedelta

from less.budget import local_today
from less.db import Session
from less.models import BriefReview, now
from less.validation import report
from sqlalchemy import select
from test_briefs import prepared, publish, save


def test_feedback_requires_later_real_reading_and_preserves_version_history(database):
    e, content = prepared()
    brief = save(e, content)
    publish(e, brief)
    detail = e.client.get(f"/api/briefs/{brief['id']}").json()
    version = detail["versions"][0]["id"]
    path = f"/api/briefs/{brief['id']}/reading-feedback"
    body = {
        "actor": "Fixture reader",
        "version_id": version,
        "would_read_again": True,
        "reason": "Still useful",
        "read_original": True,
    }
    assert e.client.post(path, json=body).status_code == 422
    with Session() as db:
        record = db.scalar(select(BriefReview).where(BriefReview.action == "publish"))
        record.created_at = now() - timedelta(days=1)
        db.commit()
    assert e.client.post(path, json={**body, "read_original": False}).status_code == 422
    assert e.client.post(path, json={**body, "version_id": "invented"}).status_code == 422
    first = e.client.post(path, json=body)
    assert first.status_code == 201 and first.json()["next_day"]
    assert (
        e.client.post(
            path, json={**body, "would_read_again": False, "reason": "Correction after reread"}
        ).status_code
        == 201
    )
    assert len(e.client.get(path).json()) == 2
    metrics = report(local_today())["editorial_activity"]
    assert metrics["next_day_reviews"] == 1 and metrics["next_day_would_read"] == 0
    assert metrics["events_created"] == 1 and metrics["decision_selected"] == 1
    with Session() as db:
        record = db.scalar(select(BriefReview).where(BriefReview.action == "publish"))
        record.created_at = now() - timedelta(days=3)
        db.commit()
    later = e.client.post(path, json=body)
    assert later.status_code == 201 and not later.json()["next_day"]
