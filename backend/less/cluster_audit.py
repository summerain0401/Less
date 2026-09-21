"""Frozen rule evaluations with blind, append-only human annotations."""

import hashlib
from datetime import datetime
from itertools import combinations
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from less.cluster_suggestions import METHOD, compare
from less.db import Session
from less.editorial_api import EventView, Input, ORMView
from less.models import (
    AuditLog,
    ClusterAuditBatch,
    ClusterAuditLabel,
    ClusterAuditPair,
    EditorialEvent,
    EventMember,
    Item,
    ItemVersion,
    Source,
)

router = APIRouter(prefix="/api/editorial/cluster-audits", tags=["Cluster audit"])


class BatchInput(Input):
    seed: str = Field(min_length=1, max_length=100)
    purpose: Literal["development", "acceptance"]
    target_count: int = Field(default=30, ge=1, le=100)


class LabelInput(Input):
    expected_revision: int = Field(ge=0)
    verdict: Literal["same", "different", "uncertain"]
    reason: str = Field(min_length=1, max_length=5000)
    original_checked: bool


class ClusterAuditBatchView(ORMView):
    id: str
    actor: str
    seed: str
    purpose: str
    method: str
    target_count: int
    population_events: int
    considered_events: int
    population_pairs: int
    created_at: datetime


class LabelView(ORMView):
    id: str
    revision: int
    actor: str
    verdict: str
    reason: str
    original_checked: bool
    created_at: datetime


class PairView(BaseModel):
    id: str
    position: int
    snapshot: dict
    prediction: dict | None
    labels: list[LabelView]


class AuditDetail(BaseModel):
    batch: ClusterAuditBatchView
    pairs: list[PairView]
    metrics: dict
    blind_metrics: dict
    limitations: list[str]


def freeze_event(db, event):
    members = db.execute(
        select(EventMember, ItemVersion, Item, Source)
        .join(ItemVersion, EventMember.version_id == ItemVersion.id)
        .join(Item, ItemVersion.item_id == Item.id)
        .join(Source, Item.source_id == Source.id)
        .where(EventMember.event_id == event.id, EventMember.active.is_(True))
        .order_by(EventMember.id)
    ).all()
    return {
        "event": EventView.model_validate(event).model_dump(
            mode="json", exclude={"value_status", "quality_status", "decision"}
        ),
        "materials": [
            {
                "version_id": v.id,
                "title": v.title,
                "url": i.url,
                "source": s.name,
                "paragraphs": [p for p in v.paragraphs if p["id"] in m.paragraph_ids],
            }
            for m, v, i, s in members
        ],
    }


def create_batch(db, body):
    # Lock the selected events so concurrent edits/merge cannot mix revisions in a snapshot.
    recent = (
        select(EditorialEvent.id)
        .where(EditorialEvent.lifecycle == "active")
        .order_by(EditorialEvent.updated_at.desc(), EditorialEvent.id)
        .limit(200)
    )
    events = db.scalars(
        select(EditorialEvent)
        .where(EditorialEvent.id.in_(recent), EditorialEvent.lifecycle == "active")
        .order_by(EditorialEvent.id)
        .with_for_update(read=True)
    ).all()
    population = db.scalar(
        select(func.count()).select_from(EditorialEvent).where(EditorialEvent.lifecycle == "active")
    )
    pairs = list(combinations(sorted(events, key=lambda e: e.id), 2))
    if not pairs:
        raise ValueError("至少需要两个活跃事件才能固定抽样")
    # Include non-retrieved pairs too; sampling only suggestions hides missed matches.
    pairs.sort(
        key=lambda pair: hashlib.sha256(
            f"{body.seed}:{pair[0].id}:{pair[1].id}".encode()
        ).hexdigest()
    )
    batch = ClusterAuditBatch(
        **body.model_dump(),
        method=METHOD,
        population_events=population,
        considered_events=len(events),
        population_pairs=len(pairs),
    )
    db.add(batch)
    db.flush()
    frozen = {}
    for position, (left, right) in enumerate(pairs[: body.target_count], 1):
        for event in (left, right):
            if event.id not in frozen:
                frozen[event.id] = freeze_event(db, event)

        def versions(e):
            return [m["version_id"] for m in frozen[e.id]["materials"]]

        prediction = compare(left, right, versions(left), versions(right))
        if prediction is None:
            prediction = {"suggestion": "not_retrieved", "reasons": [], "conflicts": []}
        db.add(
            ClusterAuditPair(
                batch_id=batch.id,
                position=position,
                snapshot={"left": frozen[left.id], "right": frozen[right.id]},
                prediction=prediction,
            )
        )
    db.add(
        AuditLog(
            action="cluster-audit-create",
            object_id=batch.id,
            actor=body.actor,
            detail={"method": METHOD, "purpose": body.purpose},
        )
    )
    db.flush()
    return batch


def statistics(pairs, labels):
    reviewed = definite = evaluated = wrong_merge = wrong_split = missed = abstained = 0
    for pair in pairs:
        history = labels.get(pair.id, [])
        if not history:
            continue
        reviewed += 1
        verdict = history[-1].verdict
        if verdict == "uncertain":
            continue
        definite += 1
        prediction = pair.prediction["suggestion"]
        if prediction not in {"same_candidate", "different"}:
            abstained += 1
            missed += int(verdict == "same")
            continue
        evaluated += 1
        wrong_merge += int(prediction == "same_candidate" and verdict == "different")
        wrong_split += int(prediction == "different" and verdict == "same")
    return {
        "sampled": len(pairs),
        "reviewed": reviewed,
        "human_definite": definite,
        "evaluated": evaluated,
        "wrong_merge": wrong_merge,
        "wrong_split": wrong_split,
        "machine_abstained": abstained,
        "same_without_positive_suggestion": missed + wrong_split,
        "error_rate": (wrong_merge + wrong_split) / evaluated if evaluated else None,
        "decision_coverage": evaluated / definite if definite else None,
    }


@router.get("", response_model=list[ClusterAuditBatchView])
def batches():
    with Session() as db:
        return db.scalars(
            select(ClusterAuditBatch)
            .order_by(ClusterAuditBatch.created_at.desc(), ClusterAuditBatch.id)
            .limit(100)
        ).all()


@router.post("", response_model=ClusterAuditBatchView, status_code=201)
def sample(body: BatchInput):
    with Session() as db:
        batch = create_batch(db, body)
        db.commit()
        return batch


@router.get("/{batch_id}", response_model=AuditDetail)
def detail(batch_id: str):
    with Session() as db:
        batch = db.get(ClusterAuditBatch, batch_id)
        if not batch:
            raise HTTPException(404, "抽样批次不存在")
        pairs = db.scalars(
            select(ClusterAuditPair)
            .where(ClusterAuditPair.batch_id == batch_id)
            .order_by(ClusterAuditPair.position)
        ).all()
        rows = db.scalars(
            select(ClusterAuditLabel)
            .join(ClusterAuditPair)
            .where(ClusterAuditPair.batch_id == batch_id)
            .order_by(ClusterAuditLabel.revision)
        ).all()
        labels = {p.id: [r for r in rows if r.pair_id == p.id] for p in pairs}
        return {
            "batch": batch,
            "pairs": [
                {
                    "id": p.id,
                    "position": p.position,
                    "snapshot": p.snapshot,
                    "prediction": p.prediction if labels[p.id] else None,
                    "labels": labels[p.id],
                }
                for p in pairs
            ],
            "metrics": statistics(pairs, labels),
            "blind_metrics": statistics(pairs, {k: v[:1] for k, v in labels.items()}),
            "limitations": [
                "按种子从最近 200 个活跃事件的所有配对中抽样，包含未召回项；不是只抽相似建议。",
                "当前评估事件骨架规则，关联原文供核查；不能替代独立的 30 组原始材料配对验收。",
                "错误率仅计算机器和人工都明确判断的配对；未判断比例与漏召回另列，样本不足不能宣称通过。",
                "首次提交前隐藏机器结果；更正保留历史，已看过结果后的更正不再是盲判。开发与验收批次独立列示。",
            ],
        }


@router.post("/{batch_id}/pairs/{pair_id}/labels", response_model=LabelView, status_code=201)
def label(batch_id: str, pair_id: str, body: LabelInput):
    with Session() as db:
        pair = db.scalar(
            select(ClusterAuditPair)
            .where(ClusterAuditPair.id == pair_id, ClusterAuditPair.batch_id == batch_id)
            .with_for_update()
        )
        if not pair:
            raise HTTPException(404, "抽样材料对不存在")
        revision = (
            db.scalar(
                select(func.max(ClusterAuditLabel.revision)).where(
                    ClusterAuditLabel.pair_id == pair_id
                )
            )
            or 0
        )
        if revision != body.expected_revision:
            raise ValueError("标注已更新，请刷新后再提交")
        if body.verdict != "uncertain":
            if not body.original_checked:
                raise ValueError("明确判断前需核对两侧原文")
            if any(not pair.snapshot[side]["materials"] for side in ("left", "right")):
                raise ValueError("抽样时一侧缺少关联原文，只能记录无法判断；补充材料后建立新批次")
        result = ClusterAuditLabel(
            pair_id=pair.id, revision=revision + 1, **body.model_dump(exclude={"expected_revision"})
        )
        db.add(result)
        db.add(
            AuditLog(
                action="cluster-audit-label",
                object_id=pair.id,
                actor=body.actor,
                detail={"revision": revision + 1, "batch_id": batch_id},
            )
        )
        db.commit()
        return result
