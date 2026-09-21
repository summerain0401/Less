from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from less.cluster_suggestions import compare


def event(**changes):
    values = dict(
        id="left",
        revision=1,
        title="Agent v2 release",
        subject="Acme",
        action="release",
        object="Agent",
        event_version="v2",
        happened_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
    )
    return SimpleNamespace(**{**values, **changes})


def test_rule_retrieval_reports_matching_skeleton_without_approving_merge():
    result = compare(event(), event(id="right", action="发布"), {"version-a"}, {"version-b"})
    assert result["suggestion"] == "same_candidate"
    assert result["conflicts"] == []
    assert result["left"]["revision"] == 1
    assert "主体文字相近" in result["reasons"]


def test_version_time_and_action_conflicts_are_not_overruled_by_similar_titles():
    left = event()
    right = event(
        id="right",
        action="evaluate",
        event_version="v3",
        happened_at=left.happened_at + timedelta(days=5),
    )
    result = compare(left, right, {"same-article"}, {"same-article"})
    assert result["suggestion"] == "different"
    assert len(result["conflicts"]) == 3
    assert result["shared_version_ids"] == ["same-article"]


def test_no_shared_dimensions_produces_no_pair():
    right = event(
        id="right",
        title="Ocean observations",
        subject="XYZ",
        object="Marine life",
        action="measure",
    )
    assert compare(event(), right, set(), set()) is None
