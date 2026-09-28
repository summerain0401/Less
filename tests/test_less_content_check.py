"""Regression cases for time-bounded Less Content deliveries."""

import json
import subprocess
import sys
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / ".agents/skills/less-content/scripts/check_batch.py"


def brief(source_date="2026-09-27T09:00:00+08:00", published_date="2026-09-27"):
    return {
        "id": "example-ai-release",
        "title": "Example AI 发布更新",
        "published_at": published_date,
        "topics": ["AI Coding"],
        "important": True,
        "useful": False,
        "confidence": "high",
        "sources": [{
            "name": "Example AI",
            "url": "https://example.com/releases/update",
            "type": "release",
            "primary": True,
            "published_at": source_date,
        }],
        "what_happened": "Example AI 发布了一项更新，并说明了可用范围。",
        "why_it_matters": "该更新影响使用此产品的开发者。",
        "our_take": None,
        "uncertainty": None,
    }


def batch(items):
    return {
        "retention_ready": items,
        "needs_verification": [],
        "task_note": {
            "window_start": "2026-09-26T10:00:00+08:00",
            "window_end": "2026-09-28T10:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "time_basis": "first_primary_publication",
            "scan_scope": "broad",
            "coverage_considered": ["Frontier", "Builders"],
            "preferred_sources_checked": ["Example AI News"],
            "expanded_sources_used": [],
            "access_limitations": [],
            "deduplication_basis": "Compared with the complete retained Brief list.",
            "no_item_qualified": not items,
        },
    }


def run_check(tmp_path, items, existing=None):
    draft = tmp_path / "draft.json"
    retained = tmp_path / "retained.json"
    draft.write_text(json.dumps(batch(items)), encoding="utf-8")
    retained.write_text(json.dumps(existing or []), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(CHECKER), str(draft), "--existing-briefs", str(retained)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_in_range_and_zero_item_deliveries_pass(tmp_path):
    assert run_check(tmp_path, [brief()]).returncode == 0
    assert run_check(tmp_path, []).returncode == 0


def test_later_report_cannot_move_old_primary_source_into_window(tmp_path):
    old = brief("2026-09-25T18:00:00+08:00", "2026-09-26")
    old["sources"].append({
        "name": "Later report",
        "url": "https://example.org/news/report",
        "type": "media",
        "primary": False,
        "published_at": "2026-09-27T08:00:00+08:00",
    })
    result = run_check(tmp_path, [old])
    assert result.returncode == 1
    assert "outside" in result.stderr
    assert "conflicts" in result.stderr


def test_date_only_boundary_is_ambiguous(tmp_path):
    result = run_check(tmp_path, [brief("2026-09-26", "2026-09-26")])
    assert result.returncode == 1
    assert "ambiguous" in result.stderr


def test_existing_brief_id_or_source_link_is_rejected(tmp_path):
    existing = [{"id": "example-ai-release", "sources": []}]
    assert "duplicate Brief ID" in run_check(tmp_path, [brief()], existing).stderr
    existing = [{"id": "different-id", "sources": [{"url": "https://example.com/releases/update"}]}]
    assert "duplicate source link" in run_check(tmp_path, [brief()], existing).stderr
