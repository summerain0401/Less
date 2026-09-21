from types import SimpleNamespace

from less.cluster_audit import statistics
from less.db import Session
from less.models import ClusterAuditPair
from sqlalchemy import select
from test_clustering import another
from test_editorial import Editor


def batch(e, **values):
    response = e.client.post(
        "/api/editorial/cluster-audits",
        json={
            "actor": "fixture-editor",
            "seed": "fixed-fixture",
            "purpose": "development",
            "target_count": 30,
            **values,
        },
    )
    assert response.status_code == 201, response.text
    return "/api/editorial/cluster-audits/" + response.json()["id"]


def linked_pair(e):
    e.link()
    other = another(e)
    response = e.client.post(
        f"/api/editorial/events/{other['id']}/members",
        json={
            "actor": "fixture-editor",
            "revision": 1,
            "reason": "fixture",
            "version_id": e.version_id,
            "paragraph_ids": ["p0001"],
        },
    )
    assert response.status_code == 200
    return other


def annotate(e, path, pair, **values):
    return e.client.post(
        f"{path}/pairs/{pair['id']}/labels",
        json={
            "actor": "fixture-editor",
            "expected_revision": 0,
            "verdict": "different",
            "original_checked": True,
            "reason": "Fixture judgment; not real content review",
            **values,
        },
    )


def test_blind_snapshot_survives_event_edit_and_corrections_preserve_first_judgment(database):
    e = Editor()
    linked_pair(e)
    path = batch(e)
    initial = e.client.get(path).json()
    pair = initial["pairs"][0]
    assert pair["prediction"] is None
    assert pair["labels"] == []
    assert initial["metrics"]["error_rate"] is None
    e.post("/claims", {"text": "Later claim", "kind": "reported_claim"})
    assert e.client.get(path).json()["pairs"][0]["snapshot"] == pair["snapshot"]
    assert annotate(e, path, pair, original_checked=False).status_code == 422
    assert annotate(e, path, pair).status_code == 201
    checked = e.client.get(path).json()
    assert checked["pairs"][0]["prediction"]["suggestion"] == "same_candidate"
    assert checked["metrics"]["wrong_merge"] == 1
    assert annotate(e, path, pair).status_code == 422
    assert annotate(e, path, pair, expected_revision=1, verdict="same").status_code == 201
    revised = e.client.get(path).json()
    assert revised["metrics"]["wrong_merge"] == 0
    assert revised["blind_metrics"]["wrong_merge"] == 1
    assert len(revised["pairs"][0]["labels"]) == 2
    assert e.detail()["event"]["value_status"] == "pending"


def test_sampling_includes_non_retrieved_pairs_and_is_repeatable(database):
    e = Editor()
    another(e, title="XYZ", subject="ZZZZZ", object="QQQQQ", action="other")
    another(e)
    first = e.client.get(batch(e)).json()
    second = e.client.get(batch(e)).json()
    assert len(first["pairs"]) == 3
    assert first["batch"]["population_pairs"] == 3
    assert [p["snapshot"] for p in first["pairs"]] == [p["snapshot"] for p in second["pairs"]]
    with Session() as db:
        predictions = db.scalars(select(ClusterAuditPair)).all()
        assert any(p.prediction["suggestion"] == "not_retrieved" for p in predictions)
    pair = first["pairs"][0]
    path = "/api/editorial/cluster-audits/" + first["batch"]["id"]
    assert annotate(e, path, pair).status_code == 422  # no linked originals
    assert annotate(e, path, pair, verdict="uncertain", original_checked=False).status_code == 201
    assert e.client.get(path).json()["metrics"]["evaluated"] == 0
    wrong_batch = "/api/editorial/cluster-audits/" + second["batch"]["id"]
    assert annotate(e, wrong_batch, pair).status_code == 404


def test_statistics_separate_missed_retrieval_and_abstentions():
    predictions = ["same_candidate", "different", "not_retrieved", "uncertain", "different"]
    verdicts = ["different", "same", "same", "different", "uncertain"]
    pairs = [
        SimpleNamespace(id=str(i), prediction={"suggestion": p}) for i, p in enumerate(predictions)
    ]
    labels = {str(i): [SimpleNamespace(verdict=v)] for i, v in enumerate(verdicts)}
    values = statistics(pairs, labels)
    assert values == {
        "sampled": 5,
        "reviewed": 5,
        "human_definite": 4,
        "evaluated": 2,
        "wrong_merge": 1,
        "wrong_split": 1,
        "machine_abstained": 2,
        "same_without_positive_suggestion": 2,
        "error_rate": 1.0,
        "decision_coverage": 0.5,
    }


def test_empty_sample_rejected(database):
    e = Editor()
    response = e.client.post(
        "/api/editorial/cluster-audits",
        json={"actor": "fixture-editor", "seed": "fixed", "purpose": "acceptance"},
    )
    assert response.status_code == 422
