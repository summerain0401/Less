import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from less import digest
from less.db import Session
from less.models import Brief, DigestRun
from sqlalchemy import select

DUE = datetime(2026, 9, 28, 6, tzinfo=digest.ZoneInfo("Asia/Shanghai"))


def draft(identifier="morning-one"):
    return {
        "id": identifier,
        "title": "新的 AI 工程方法",
        "published_at": "2026-09-28",
        "topics": ["AI Coding"],
        "important": False,
        "useful": True,
        "confidence": "medium",
        "sources": [{
            "name": "Example Engineering",
            "url": f"https://example.com/posts/{identifier}",
            "type": "blog",
            "primary": True,
            "published_at": "2026-09-28",
        }],
        "what_happened": "作者介绍了方法、此前问题、实际步骤与适用范围。",
        "why_it_matters": "开发者可以减少重复试错。",
        "our_take": None,
        "uncertainty": "只在作者自己的项目中验证。",
    }


def test_next_slot_skips_missed_time():
    zone = digest.ZoneInfo("Asia/Shanghai")
    assert digest.next_slot_after(datetime(2026, 9, 28, 5, 59, tzinfo=zone)) == (
        "morning", datetime(2026, 9, 28, 6, tzinfo=zone)
    )
    assert digest.next_slot_after(datetime(2026, 9, 28, 6, 1, tzinfo=zone)) == (
        "evening", datetime(2026, 9, 28, 18, tzinfo=zone)
    )
    assert digest.next_slot_after(datetime(2026, 9, 28, 18, 1, tzinfo=zone)) == (
        "morning", datetime(2026, 9, 29, 6, tzinfo=zone)
    )
    due = datetime(2026, 9, 28, 6, tzinfo=zone)
    assert digest.slot_is_due(due, due + timedelta(seconds=30))
    assert not digest.slot_is_due(due, due + timedelta(minutes=5))


def test_duplicate_filter_uses_full_id_and_source_links():
    one = draft("one")
    two = draft("two")
    two["sources"][0]["url"] = one["sources"][0]["url"] + "/"
    batch = {"retention_ready": [one, two, draft("three")], "task_note": {}}
    result = digest.remove_exact_duplicates(batch, [])
    assert [item["id"] for item in result["retention_ready"]] == ["one", "three"]
    assert result["task_note"]["no_item_qualified"] is False


def test_run_saves_once_then_sends_full_brief(client, monkeypatch):
    sent = []
    monkeypatch.setattr(digest, "mail_settings", lambda: None)
    monkeypatch.setattr(digest, "discover_content", lambda *_: {"retention_ready": [draft()]})
    monkeypatch.setattr(digest, "send_email", sent.append)

    assert digest.run_slot("morning", DUE)
    assert not digest.run_slot("morning", DUE)
    with Session() as db:
        assert db.get(Brief, "morning-one") is not None
        run = db.get(DigestRun, ("2026-09-28", "morning"))
        assert run.status == "sent"
        assert json.loads(run.brief_ids_json) == ["morning-one"]
        assert run.email_sent_at
    assert len(sent) == 1
    assert sent[0]["Date"]
    assert sent[0]["Message-ID"]
    assert "Less" in str(sent[0]["From"])
    body = sent[0].get_body(preferencelist=("plain",)).get_content()
    assert "作者介绍了方法" in body
    assert "只在作者自己的项目中验证" in body
    assert "https://example.com/posts/morning-one" in body
    assert "来源日期：2026-09-28" in body
    assert "<a href=" in sent[0].get_body(preferencelist=("html",)).get_content()


def test_empty_run_still_sends_an_email(client, monkeypatch):
    sent = []
    monkeypatch.setattr(digest, "mail_settings", lambda: None)
    monkeypatch.setattr(digest, "discover_content", lambda *_: {"retention_ready": []})
    monkeypatch.setattr(digest, "send_email", sent.append)
    assert digest.run_slot("evening", DUE.replace(hour=18))
    assert "没有值得保留的新内容" in sent[0].get_body(preferencelist=("plain",)).get_content()


def test_generation_failure_is_recorded_and_not_reported_as_empty(client, monkeypatch):
    sent = []
    monkeypatch.setattr(digest, "mail_settings", lambda: None)
    monkeypatch.setattr(digest, "discover_content", lambda *_: (_ for _ in ()).throw(RuntimeError("bad output")))
    monkeypatch.setattr(digest, "send_email", sent.append)
    assert digest.run_slot("morning", DUE)
    with Session() as db:
        run = db.get(DigestRun, ("2026-09-28", "morning"))
        assert run.status == "failed"
        assert run.email_sent_at
        assert db.scalars(select(Brief)).all() == []
    assert "任务失败" in str(sent[0]["Subject"])
    assert "没有新内容" in sent[0].get_body(preferencelist=("plain",)).get_content()


def test_missing_mail_configuration_does_not_start_content_search(client, monkeypatch):
    called = []
    monkeypatch.setattr(
        digest, "mail_settings", lambda: (_ for _ in ()).throw(RuntimeError("not configured"))
    )
    monkeypatch.setattr(digest, "discover_content", lambda *_: called.append(True))
    assert digest.run_slot("morning", DUE)
    assert called == []
    with Session() as db:
        assert db.get(DigestRun, ("2026-09-28", "morning")).status == "failed"


def test_invalid_brief_rolls_back_and_sends_failure(client, monkeypatch):
    invalid = draft()
    invalid["confidence"] = "low"
    sent = []
    monkeypatch.setattr(digest, "mail_settings", lambda: None)
    monkeypatch.setattr(digest, "discover_content", lambda *_: {"retention_ready": [invalid]})
    monkeypatch.setattr(digest, "send_email", sent.append)
    assert digest.run_slot("morning", DUE)
    with Session() as db:
        assert db.scalars(select(Brief)).all() == []
        assert db.get(DigestRun, ("2026-09-28", "morning")).status == "failed"
    assert "任务失败" in str(sent[0]["Subject"])


def test_smtp_failure_keeps_saved_brief_and_records_failure(client, monkeypatch):
    monkeypatch.setattr(digest, "mail_settings", lambda: None)
    monkeypatch.setattr(digest, "discover_content", lambda *_: {"retention_ready": [draft()]})
    monkeypatch.setattr(
        digest, "send_email", lambda _: (_ for _ in ()).throw(digest.smtplib.SMTPException("down"))
    )
    assert digest.run_slot("morning", DUE)
    with Session() as db:
        run = db.get(DigestRun, ("2026-09-28", "morning"))
        assert run.status == "failed"
        assert run.email_sent_at is None
        assert json.loads(run.brief_ids_json) == ["morning-one"]
        assert db.get(Brief, "morning-one") is not None


def test_codex_subprocess_does_not_inherit_smtp_secrets(monkeypatch):
    monkeypatch.setenv("LESS_SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    child = digest._codex_environment()
    assert child["PATH"] == "/usr/bin"
    assert "LESS_SMTP_PASSWORD" not in child
    assert "SMTP_PASSWORD" not in child


def test_smtp_retries_transient_failure(monkeypatch):
    monkeypatch.setattr(digest, "settings", lambda: SimpleNamespace(
        smtp_host="smtp.example.com", smtp_port=587, smtp_username="u", smtp_password="p",
        mail_from="a@example.com", mail_to="b@example.com"
    ))
    monkeypatch.setattr(digest.time, "sleep", lambda _: None)
    attempts = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            attempts.append(1)

        def starttls(self, **_kwargs):
            pass

        def login(self, *_args):
            pass

        def send_message(self, _message):
            if len(attempts) < 3:
                raise digest.smtplib.SMTPServerDisconnected("retry")

        def quit(self):
            pass

    monkeypatch.setattr(digest.smtplib, "SMTP", FakeSMTP)
    digest.send_email(digest.build_email("morning", DUE, []))
    assert len(attempts) == 3
