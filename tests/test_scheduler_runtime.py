import importlib.util
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from jsonschema import ValidationError, validate
from less import agents, digest, runtime
from less.config import ROOT
from less.db import Session
from less.models import DigestRun

DUE = datetime(2026, 10, 16, 6, tzinfo=ZoneInfo("Asia/Shanghai"))


class ClosedStream:
    def write(self, _value):
        raise BrokenPipeError("terminal reader closed")

    def flush(self):
        pass


def empty_batch():
    return {
        "retention_ready": [], "needs_verification": [],
        "task_note": {
            "window_start": "2026-10-15T06:00:00+08:00",
            "window_end": DUE.isoformat(), "timezone": "Asia/Shanghai",
            "time_basis": "first_primary_publication", "scan_scope": "broad",
            "coverage_considered": ["Builders"],
            "preferred_sources_checked": ["Example Engineering"],
            "expanded_sources_used": [], "access_limitations": [],
            "deduplication_basis": "Pending host comparison", "no_item_qualified": False,
        },
    }


def test_empty_discovery_normalizes_summary_without_inventing_sources(client, monkeypatch):
    batch = empty_batch()
    monkeypatch.setattr(digest, "run_content_task", lambda *_a, **_kw: batch)
    result = digest.discover_content("morning", DUE)
    assert result["task_note"]["no_item_qualified"] is True
    assert result["task_note"]["preferred_sources_checked"] == ["Example Engineering"]


@pytest.mark.parametrize("field", ["preferred_sources_checked", "coverage_considered"])
def test_generation_schema_rejects_missing_scan_evidence(field):
    batch = empty_batch()
    batch["task_note"][field] = []
    with pytest.raises(ValidationError):
        validate(batch, json.loads(digest.SCHEMA.read_text()))


@pytest.mark.parametrize("smtp_fails", [False, True])
def test_closed_error_stream_cannot_prevent_failure_persistence(client, monkeypatch, smtp_fails):
    monkeypatch.setattr(digest, "mail_settings", lambda: None)
    monkeypatch.setattr(digest, "discover_content", Mock(side_effect=RuntimeError("bad batch")))
    delivered = []

    def send(_message):
        with Session() as db:
            run = db.get(DigestRun, ("2026-10-16", "morning"))
            assert run.status == "failed"  # Recorded before any notification I/O.
            assert "bad batch" in run.error
        if smtp_fails:
            raise OSError("SMTP unavailable")
        delivered.append(True)

    monkeypatch.setattr(digest, "send_email", send)
    with monkeypatch.context() as patch:
        patch.setattr(runtime.sys, "stderr", ClosedStream())
        assert digest.run_slot("morning", DUE)
    with Session() as db:
        run = db.get(DigestRun, ("2026-10-16", "morning"))
        assert run.status == "failed"
        assert bool(run.email_sent_at) == bool(delivered)


def test_closed_output_stream_does_not_turn_sent_mail_into_failure(client, monkeypatch):
    monkeypatch.setattr(digest, "mail_settings", lambda: None)
    monkeypatch.setattr(digest, "discover_content", lambda *_: {"retention_ready": []})
    send = Mock()
    monkeypatch.setattr(digest, "send_email", send)
    with monkeypatch.context() as patch:
        patch.setattr(runtime.sys, "stdout", ClosedStream())
        assert digest.run_slot("morning", DUE)
    assert send.call_count == 1
    with Session() as db:
        assert db.get(DigestRun, ("2026-10-16", "morning")).status == "sent"


def test_shutdown_does_not_save_or_send_completed_generation(client, monkeypatch):
    stopping = threading.Event()

    def discover(*_args, **_kwargs):
        stopping.set()
        return {"retention_ready": []}

    monkeypatch.setattr(digest, "mail_settings", lambda: None)
    monkeypatch.setattr(digest, "discover_content", discover)
    send = Mock()
    monkeypatch.setattr(digest, "send_email", send)
    assert digest.run_slot("morning", DUE, stopping)
    send.assert_not_called()
    with Session() as db:
        assert db.get(DigestRun, ("2026-10-16", "morning")).status == "interrupted"


def test_startup_recovers_orphans_without_retrying_or_changing_saved_content(client, monkeypatch,
                                                                          tmp_path):
    monkeypatch.setattr(runtime, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(digest, "configure_scheduler_logging", lambda: None)
    states = ("running", "saved", "sent", "failed")
    with Session.begin() as db:
        for n, state in enumerate(states):
            db.add(DigestRun(day=f"2026-10-{10+n}", slot="morning", status=state,
                             started_at="2026-10-10T00:00:00+00:00",
                             brief_ids_json='["retained"]'))

    def loop():
        assert runtime.scheduler_is_running()
        with Session() as db:
            for n, state in enumerate(states):
                run = db.get(DigestRun, (f"2026-10-{10+n}", "morning"))
                assert run.status == ("interrupted" if n < 2 else state)
                assert run.brief_ids_json == '["retained"]'
                assert run.email_sent_at is None
                if n < 2:
                    assert run.finished_at and "unknown" in run.error

    monkeypatch.setattr(digest, "_scheduler_loop", loop)
    digest.run_scheduler()
    assert not runtime.scheduler_is_running()
    with runtime.scheduler_lock():
        with pytest.raises(runtime.SchedulerAlreadyRunning):
            digest.run_scheduler()


def test_lock_rejects_second_process_and_releases_after_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "RUNTIME_DIR", tmp_path)
    script = (
        "from pathlib import Path; from less import runtime; "
        f"runtime.RUNTIME_DIR=Path({str(tmp_path)!r}); "
        "print(runtime.scheduler_is_running())"
    )
    with runtime.scheduler_lock():
        result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                                text=True, check=True)
        assert result.stdout.strip() == "True"
    assert not runtime.scheduler_is_running()


@pytest.mark.parametrize("cancel", [False, True])
def test_agent_timeout_and_shutdown_terminate_the_process(monkeypatch, tmp_path, cancel):
    pidfile = tmp_path / "pid"
    command = [sys.executable, "-c", (
        "import os,time; from pathlib import Path; "
        f"Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(20)"
    )]
    stopping = threading.Event()
    monkeypatch.setattr(agents, "TIMEOUT", 5 if cancel else 0.5)
    timer = threading.Timer(0.5, stopping.set) if cancel else None
    if timer:
        timer.start()
    try:
        with pytest.raises(InterruptedError if cancel else subprocess.TimeoutExpired):
            agents._run_agent(command, tmp_path, "codex", stopping)
    finally:
        if timer:
            timer.cancel()
            timer.join()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_service_configuration_excludes_credentials_and_uses_absolute_paths(monkeypatch):
    monkeypatch.setenv("LESS_SMTP_PASSWORD", "must-not-be-copied")
    monkeypatch.setenv("CODEX_THREAD_ID", "must-not-be-copied")
    spec = importlib.util.spec_from_file_location("less_service", ROOT / "scripts/scheduler_service.py")
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    config = service.launch_agent("codex")
    assert config["KeepAlive"] and config["RunAtLoad"]
    assert Path(config["ProgramArguments"][0]).is_absolute()
    assert config["WorkingDirectory"] == str(Path.home())
    assert config["EnvironmentVariables"]["LESS_AGENT_PROVIDER"] == "codex"
    assert "must-not-be-copied" not in json.dumps(config)
