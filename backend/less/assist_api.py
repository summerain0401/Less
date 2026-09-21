from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import select

from less import assist
from less.db import Session
from less.editorial_api import EventView, Input, ORMView
from less.models import AssistRun, AuditLog, EditorialEvent, now

router = APIRouter(prefix="/api/assist", tags=["Machine editorial assistance"])


class AssistInput(Input):
    stage: Literal["event", "value", "pair", "brief"]
    version_id: str | None = None
    event_ids: list[str] = Field(default_factory=list, max_length=2)


class AssistView(ORMView):
    id: str
    stage: str
    prompt_version: str
    model: str
    input: dict
    status: str
    attempts: int
    created_at: datetime
    finished_at: datetime | None
    output: dict | None
    error: str | None
    applied_event_id: str | None


@router.post("", response_model=AssistView, status_code=201)
def queue(body: AssistInput):
    if body.stage == "event" and (not body.version_id or body.event_ids):
        raise ValueError("事件草稿需要一个原文版本，不接收事件 ID")
    if body.stage != "event" and body.version_id:
        raise ValueError("此任务需要事件 ID，不接收原文版本 ID")
    result = assist.queue(body.stage, body.version_id, body.event_ids)
    with Session() as db:
        db.add(
            AuditLog(
                action="assist-queue",
                object_id=result.id,
                actor=body.actor,
                detail={"stage": body.stage},
            )
        )
        db.commit()
    return result


@router.get("", response_model=list[AssistView])
def runs(offset: int = 0, limit: int = 50):
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("分页参数无效")
    with Session() as db:
        return db.scalars(
            select(AssistRun)
            .order_by(AssistRun.created_at.desc(), AssistRun.id)
            .offset(offset)
            .limit(limit)
        ).all()


@router.post("/{run_id}/retry", response_model=AssistView)
def retry(run_id: str, body: Input):
    with Session() as db:
        run = db.scalar(select(AssistRun).where(AssistRun.id == run_id).with_for_update())
        if not run:
            raise HTTPException(404, "任务不存在")
        if run.status not in {"failed", "blocked"}:
            raise ValueError("仅失败或暂停任务可以人工重试")
        run.status = "pending"
        run.attempts = 0
        run.next_attempt_at = now()
        db.add(AuditLog(action="assist-retry", object_id=run.id, actor=body.actor))
        db.commit()
        return run


@router.post("/{run_id}/event", response_model=EventView)
def apply_event(run_id: str, body: Input):
    with Session() as db:
        event = assist.apply_event(db, run_id, body.actor)
        db.commit()
        return event


@router.get("/candidates")
def candidates():
    with Session() as db:
        # No LIMIT on historical runs: stale retries must not hide valid current recommendations.
        events = {
            e.id: e
            for e in db.scalars(select(EditorialEvent).where(EditorialEvent.lifecycle == "active"))
        }
        found = {}
        for run in db.scalars(
            select(AssistRun)
            .where(AssistRun.stage == "value", AssistRun.status == "succeeded")
            .order_by(AssistRun.created_at.desc(), AssistRun.id)
        ):
            snapshot = run.input["events"][0]
            event = events.get(snapshot["id"])
            if not event or event.id in found or event.revision != snapshot["revision"]:
                continue
            proposal = run.output
            status = (
                "pending"
                if proposal["uncertain"]
                else "candidate"
                if max(proposal["important"], proposal["useful"]) >= 2
                else "excluded"
            )
            found[event.id] = {
                "event": EventView.model_validate(event).model_dump(mode="json"),
                "run_id": run.id,
                "proposal": proposal,
                "selection": status,
            }
        ranked = sorted(
            found.values(),
            key=lambda row: (
                -max(row["proposal"]["important"], row["proposal"]["useful"]),
                -sum(row["proposal"][k] for k in ("important", "useful")),
                row["event"]["id"],
            ),
        )
        return {
            "rows": ranked,
            "unassessed_events": len(events) - len(found),
            "method": "Important OR Useful: 任一达到 2/3 为机器候选；不确定单列，质量门独立。按较强路径再按双维总分排序。",
            "limitations": "只显示与当前事件修订一致的机器结果；不覆盖人工价值、质量或发布判断。排除项保留可审计。",
        }


class ValueAuditInput(Input):
    seed: str = Field(min_length=1, max_length=100)
    target_count: int = Field(default=20, ge=1, le=100)
    pool: Literal["excluded", "candidate"] = "excluded"


class ValueAuditReview(Input):
    run_id: str
    expected_revision: int = Field(ge=0)
    verdict: Literal["value", "no_value", "uncertain"]
    important_reason: str = Field(min_length=1, max_length=5000)
    useful_reason: str = Field(min_length=1, max_length=5000)
    original_checked: bool


@router.post("/audits", status_code=201)
def sample_value(body: ValueAuditInput):
    import hashlib

    rows = candidates()["rows"]
    chosen = [r for r in rows if r["selection"] == body.pool]
    chosen.sort(key=lambda r: hashlib.sha256(f"{body.seed}:{r['run_id']}".encode()).hexdigest())
    if not chosen:
        raise ValueError("当前没有对应的机器评估结果可抽样")
    with Session() as db:
        samples = []
        for row in chosen[: body.target_count]:
            run = db.get(AssistRun, row["run_id"])
            samples.append(
                {
                    "run_id": run.id,
                    "input": run.input,
                    "proposal": run.output,
                    "method": run.prompt_version,
                }
            )
        batch = AuditLog(
            action="value-audit-sample",
            object_id="value-audit",
            actor=body.actor,
            detail={
                "seed": body.seed,
                "target_count": body.target_count,
                "pool": body.pool,
                "population": len(chosen),
                "samples": samples,
            },
        )
        db.add(batch)
        db.commit()
        return {"id": batch.id, "sample_count": len(samples), "population": len(chosen)}


@router.get("/audits")
def value_audits():
    with Session() as db:
        return [
            {
                "id": r.id,
                "actor": r.actor,
                "created_at": r.created_at,
                "seed": r.detail["seed"],
                "pool": r.detail["pool"],
                "sample_count": len(r.detail["samples"]),
                "population": r.detail["population"],
            }
            for r in db.scalars(
                select(AuditLog)
                .where(AuditLog.action == "value-audit-sample")
                .order_by(AuditLog.id.desc())
                .limit(100)
            )
        ]


@router.get("/audits/{batch_id}")
def value_audit(batch_id: int):
    with Session() as db:
        batch = db.get(AuditLog, batch_id)
        if not batch or batch.action != "value-audit-sample":
            raise HTTPException(404, "价值抽样不存在")
        reviews = db.scalars(
            select(AuditLog)
            .where(AuditLog.action == "value-audit-review", AuditLog.object_id == str(batch_id))
            .order_by(AuditLog.id)
        ).all()
        samples = []
        counts = {"reviewed": 0, "value": 0, "no_value": 0, "uncertain": 0}
        blind = {"reviewed": 0, "value": 0, "no_value": 0, "uncertain": 0}
        for sample in batch.detail["samples"]:
            history = [
                {"actor": r.actor, "created_at": r.created_at, **r.detail}
                for r in reviews
                if r.detail["run_id"] == sample["run_id"]
            ]
            if history:
                counts["reviewed"] += 1
                counts[history[-1]["verdict"]] += 1
                blind["reviewed"] += 1
                blind[history[0]["verdict"]] += 1
            samples.append(
                {**sample, "proposal": sample["proposal"] if history else None, "reviews": history}
            )
        return {
            "id": batch.id,
            "pool": batch.detail["pool"],
            "target_count": batch.detail["target_count"],
            "population": batch.detail["population"],
            "samples": samples,
            "latest_counts": counts,
            "blind_counts": blind,
            "limitations": "固定机器结果和原文快照；首次判断前隐藏机器理由。更正保留历史。只能评估已采集与已评估的事件，不能估计全网召回率。",
        }


@router.post("/audits/{batch_id}/reviews", status_code=201)
def value_audit_review(batch_id: int, body: ValueAuditReview):
    with Session() as db:
        batch = db.scalar(
            select(AuditLog)
            .where(AuditLog.id == batch_id, AuditLog.action == "value-audit-sample")
            .with_for_update()
        )
        if not batch or body.run_id not in {s["run_id"] for s in batch.detail["samples"]}:
            raise ValueError("被评估任务不属于此固定批次")
        rows = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "value-audit-review", AuditLog.object_id == str(batch_id)
            )
        ).all()
        revision = sum(r.detail["run_id"] == body.run_id for r in rows)
        if revision != body.expected_revision:
            raise ValueError("此项判断已更新，请刷新")
        if body.verdict != "uncertain" and not body.original_checked:
            raise ValueError("明确价值判断前需核对原文")
        record = AuditLog(
            action="value-audit-review",
            object_id=str(batch_id),
            actor=body.actor,
            detail={
                **body.model_dump(exclude={"actor", "expected_revision"}),
                "revision": revision + 1,
            },
        )
        db.add(record)
        db.commit()
        return {"id": record.id, "revision": revision + 1}
