from datetime import datetime, timezone

from less.db import Session
from less.models import Brief, Source, Topic
from sqlalchemy import func, select


def payload(identifier="brief-one", **changes):
    value = {
        "id": identifier,
        "title": "Agent 工具新增可恢复任务",
        "published_at": "2026-09-20",
        "topics": ["Agents", "AI Coding"],
        "important": True,
        "useful": True,
        "confidence": "high",
        "sources": [
            {
                "name": "Example release",
                "url": f"https://example.com/releases/{identifier}",
                "type": "release",
                "primary": True,
                "published_at": "2026-09-20T09:00:00+08:00",
            }
        ],
        "what_happened": "项目发布了可恢复的后台任务。",
        "why_it_matters": "长任务失败后无需从头运行，适合代理工作流。",
        "our_take": None,
        "uncertainty": None,
    }
    value.update(changes)
    return value


def test_create_read_update_delete_and_topic_cleanup(client):
    created = client.post("/api/briefs", json=payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["id"] == "brief-one"
    assert body["created_at"]
    assert body["updated_at"] is None
    assert body["sources"][0]["published_at"] == "2026-09-20T09:00:00+08:00"

    duplicate = client.post("/api/briefs", json=payload())
    assert duplicate.status_code == 409

    update = payload()
    update.pop("id")
    update["title"] = "更正后的标题"
    update["topics"] = ["agents", "Reasoning"]
    changed = client.put("/api/briefs/brief-one", json=update)
    assert changed.status_code == 200, changed.text
    assert changed.json()["title"] == "更正后的标题"
    assert changed.json()["created_at"] == body["created_at"]
    assert changed.json()["updated_at"]

    topics = client.get("/api/topics").json()
    assert {topic["name"] for topic in topics} == {"Agents", "Reasoning"}
    assert all(topic["brief_count"] == 1 for topic in topics)

    assert client.delete("/api/briefs/brief-one").status_code == 204
    assert client.get("/api/briefs/brief-one").status_code == 404
    assert client.get("/api/topics").json() == []
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Source)) == 0


def test_editorial_validation(client):
    cases = [
        ({"important": False, "useful": False}, "至少一项"),
        ({"confidence": "low"}, "high"),
        ({"confidence": "medium", "uncertainty": None}, "uncertainty"),
        ({"sources": [{**payload()["sources"][0], "primary": False}]}, "主要来源"),
        ({"sources": [payload()["sources"][0], payload()["sources"][0]]}, "不能重复"),
        ({"topics": ["Agents", "agents"]}, "不能重复"),
    ]
    for index, (changes, message) in enumerate(cases):
        response = client.post("/api/briefs", json=payload(f"invalid-{index}", **changes))
        assert response.status_code == 422
        assert message in response.text

    invalid_url = payload("bad-url")
    invalid_url["sources"][0]["url"] = "example.com/post"
    assert client.post("/api/briefs", json=invalid_url).status_code == 422

    medium = payload("medium", confidence="medium", uncertainty="仅有厂商数据。")
    assert client.post("/api/briefs", json=medium).status_code == 201


def test_today_dates_filters_and_empty_day(client):
    for identifier, title, topic in (
        ("one", "Queue release", "Agents"),
        ("two", "Reasoning guide", "Reasoning"),
    ):
        assert client.post(
            "/api/briefs", json=payload(identifier, title=title, topics=[topic])
        ).status_code == 201

    with Session() as db:
        first = db.get(Brief, "one")
        first.created_at = datetime(2026, 9, 21, 15, 59, tzinfo=timezone.utc).isoformat()
        second = db.get(Brief, "two")
        second.created_at = datetime(2026, 9, 21, 16, 0, tzinfo=timezone.utc).isoformat()
        db.commit()

    day_one = client.get("/api/today?day=2026-09-21").json()
    day_two = client.get("/api/today?day=2026-09-22").json()
    assert [entry["id"] for entry in day_one["entries"]] == ["one"]
    assert [entry["id"] for entry in day_two["entries"]] == ["two"]
    assert client.get("/api/today?day=2026-09-23").json()["entries"] == []

    assert [item["id"] for item in client.get("/api/briefs?topic=agents").json()] == ["one"]
    assert [item["id"] for item in client.get("/api/briefs?q=guide").json()] == ["two"]
    assert [item["id"] for item in client.get("/api/briefs?day=2026-09-21").json()] == ["one"]

    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Topic)) == 2


def test_local_access_and_json_only(client):
    assert client.get("/api/health", headers={"host": "example.com"}).status_code == 403
    assert client.post(
        "/api/briefs", content="not json", headers={"content-type": "text/plain"}
    ).status_code == 415
