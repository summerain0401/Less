from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from less.ai import Normalized
from less.budget import local_today
from less.db import Session, lock
from less.models import (
    AuditLog,
    FieldReview,
    Item,
    ItemVersion,
    NormalizeRun,
    Source,
    ValidationBatch,
    ValidationSample,
    WorkSession,
)
from less.pipeline import queue_normalize
from less.validation import (
    create_batch,
    prepare_batch,
    report,
    sample_fields,
    save_field_review,
    start_session,
    stop_session,
)

router = APIRouter(prefix="/api/validation", tags=["Week 1 validation"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ActorInput(Input):
    actor: str = Field(min_length=1, max_length=80)


class BatchInput(ActorInput):
    target_count: int = Field(default=30, ge=1, le=100)


class PrepareInput(ActorInput):
    limit: int = Field(default=30, ge=1, le=100)


class BudgetView(BaseModel):
    limit: int
    used: int
    remaining: int
    legacy_estimated: int
    resets_at: datetime


class QualityView(BaseModel):
    reviewed_samples: int
    fully_reviewed_samples: int
    checked_fields: int
    correct_fields: int
    incorrect_fields: int
    accuracy: float | None


class SourceMetric(BaseModel):
    id: str
    name: str
    status: str
    planned: int
    succeeded: int
    last_success_at: datetime | None


class DailyReportView(BaseModel):
    date: date
    timezone: str
    window_start: datetime
    window_end: datetime
    as_of: datetime
    closed: bool
    planned: int
    succeeded: int
    success_rate: float | None
    unrecorded_due: int
    manual_checks: int
    status_counts: dict[str, int]
    raw_items: int
    versions: int
    normalized: int
    observed_tokens: int
    cost: float | None
    cost_note: str
    budget: BudgetView
    quality: QualityView
    baseline_sessions: int
    work_seconds: dict[str, float]
    active_sessions: int
    observation_hours: float
    sources: list[SourceMetric]
    later_stages: dict[str, int | None]
    editorial_activity: dict[str, int]
    editorial_activity_note: str


class BatchView(BaseModel):
    id: str
    actor: str
    seed: str
    target_count: int
    population_count: int
    created_at: datetime
    sample_count: int
    source_count: int


class SampleView(BaseModel):
    id: str
    version_id: str
    run_id: str | None
    position: int
    source_name: str
    title: str
    status: str
    reviewed: bool


class BatchDetail(BaseModel):
    batch: BatchView
    samples: list[SampleView]


class FieldSpec(BaseModel):
    key: str
    label: str
    value: str | list[str] | None
    allows_unknown: bool


class FieldInput(Input):
    key: str
    verdict: Literal["correct", "incorrect", "unknown_correct", "not_checked"]
    note: str = Field(default="", max_length=2000)


class FieldReviewInput(Input):
    run_id: str
    reviewer: str = Field(min_length=1, max_length=80)
    fields: list[FieldInput] = Field(min_length=1)
    note: str = Field(default="", max_length=5000)
    original_checked: bool


class FieldReviewView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sample_id: str
    run_id: str
    reviewer: str
    fields: list[FieldInput]
    note: str
    created_at: datetime


class ParagraphView(BaseModel):
    id: str
    text: str


class OriginalView(BaseModel):
    id: str
    title: str
    url: str
    author: str | None
    published_at: datetime | None
    paragraphs: list[ParagraphView]


class SampleDetail(BaseModel):
    sample: SampleView
    original: OriginalView
    output: Normalized | None
    fields: list[FieldSpec]
    reviews: list[FieldReviewView]


class SessionInput(Input):
    reviewer: str = Field(min_length=1, max_length=80)
    mode: Literal["baseline", "system", "setup"]
    category: Literal["screening", "review", "sources", "recovery", "other"]
    source_ids: list[str] = Field(min_length=1)
    criteria: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def baseline_is_screening(self):
        if self.mode == "baseline" and self.category != "screening":
            raise ValueError("手工筛选基线必须使用筛选类别")
        return self


class StopInput(Input):
    read_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    note: str = Field(min_length=1, max_length=5000)


class SessionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    reviewer: str
    mode: str
    category: str
    source_ids: list[str]
    criteria: str
    started_at: datetime
    ended_at: datetime | None
    read_count: int | None
    candidate_count: int | None
    selected_count: int | None
    note: str | None


def batch_view(db, batch):
    rows = db.execute(
        select(ValidationSample.id, Item.source_id)
        .join(ItemVersion, ItemVersion.id == ValidationSample.version_id)
        .join(Item)
        .where(ValidationSample.batch_id == batch.id)
    ).all()
    return {
        "id": batch.id,
        "actor": batch.actor,
        "seed": batch.seed,
        "target_count": batch.target_count,
        "population_count": batch.population_count,
        "created_at": batch.created_at,
        "sample_count": len(rows),
        "source_count": len(set(source for _, source in rows)),
    }


def sample_view(db, sample):
    version = db.get(ItemVersion, sample.version_id)
    item = db.get(Item, version.item_id)
    source = db.get(Source, item.source_id)
    run = db.get(NormalizeRun, sample.run_id) if sample.run_id else None
    reviewed = bool(
        db.scalar(
            select(FieldReview.id).where(
                FieldReview.sample_id == sample.id, FieldReview.run_id == sample.run_id
            )
        )
    )
    return {
        "id": sample.id,
        "version_id": version.id,
        "run_id": sample.run_id,
        "position": sample.position,
        "title": version.title,
        "source_name": source.name,
        "status": run.status if run else "not_prepared",
        "reviewed": reviewed,
    }


@router.get("/report", response_model=DailyReportView)
def daily_report(day: date | None = None):
    day = day or local_today()
    if day > local_today():
        raise HTTPException(422, "不能生成未来日报")
    return report(day)


@router.get("/report.md", response_class=PlainTextResponse)
def daily_markdown(day: date | None = None):
    r = daily_report(day)
    ratio = f"{r['success_rate']:.1%}" if r["success_rate"] is not None else "暂无计划任务"
    q = r["quality"]
    accuracy = f"{q['accuracy']:.1%}" if q["accuracy"] is not None else "尚未人工核查"
    modes = {"baseline": "手工筛选基线", "system": "使用 Less", "setup": "配置与维护"}
    duration = (
        "；".join(
            f"{modes.get(mode, mode)} {seconds / 60:.1f} 分钟"
            for mode, seconds in r["work_seconds"].items()
        )
        or "暂无已结束的工作记录"
    )
    statuses = {"active": "启用", "paused": "暂停", "needs_review": "待复核"}
    lines = [
        f"# Less 运行日报 · {r['date']}",
        "",
        f"时区：{r['timezone']}；统计截至 {r['as_of'].isoformat()}。",
        "当前为完整日窗口；不自动代表连续运行验收完成。"
        if r["closed"]
        else "当前为进行中的部分日记录，不代表连续运行验收完成。",
        "",
        "| 指标 | 结果 |",
        "|---|---|",
        f"| 计划采集成功 / 应执行 | {r['succeeded']} / {r['planned']} |",
        f"| 计划采集成功率 | {ratio} |",
        f"| 调度尚未登记的应执行次数 | {r['unrecorded_due']} |",
        f"| 手动采集（不混入计划分母） | {r['manual_checks']} |",
        f"| 新保存 Items / 版本 | {r['raw_items']} / {r['versions']} |",
        f"| 成功 Normalize | {r['normalized']} |",
        f"| AI 调用预算已用 / 上限 | {r['budget']['used']} / {r['budget']['limit']} |",
        f"| 已观测 token | {r['observed_tokens']} |",
        "| 实际费用 | 未知 |",
        "",
        f"{r['cost_note']}。历史缺少逐次日志的调用按 {r['budget']['legacy_estimated']} 次保守估算，已计入预算。",
        "计划成功率只计算在统计日截止前完成的任务；人工进度与来源状态为导出时的累计记录。",
        "",
        "## 累计人工验收进度",
        "",
        f"- 完整核查的不同 Items：{q['fully_reviewed_samples']} / 30。",
        f"- 已核查字段：{q['checked_fields']}；准确率：{accuracy}；错误字段：{q['incorrect_fields']}。",
        f"- 已完成且有阅读记录的手工筛选基线：{r['baseline_sessions']} / 2。",
        "- 样本量不足时不得宣称准确率目标已通过。机器结果不计为人工复核。",
        "",
        "## 当日人工耗时",
        "",
        f"- {duration}。",
        f"- 尚未结束计时：{r['active_sessions']}。未结束的计时不混入完成耗时。",
        "",
        "## 来源",
        "",
        "| 来源 | 当前状态 | 应执行计划 / 截止前成功 |",
        "|---|---|",
        *[
            f"| {s['name']} | {statuses.get(s['status'], s['status'])} | {s['planned']} / {s['succeeded']} |"
            for s in r["sources"]
        ],
        "",
        "## 当日编辑阶段活动",
        "",
        r["editorial_activity_note"],
        "",
        *[f"- {key}: {value}" for key, value in r["editorial_activity"].items()],
        "",
        "机器候选记录当日完成的最后一次初筛，不代表人工通过或当前有效库存。",
        "此文件是数据库的只读导出；需要更正时应在工作台追加记录后重新导出。",
        "",
    ]
    return "\n".join(lines)


@router.get("/batches", response_model=list[BatchView])
def batches():
    with Session() as db:
        return [
            batch_view(db, b)
            for b in db.scalars(
                select(ValidationBatch).order_by(ValidationBatch.created_at.desc()).limit(50)
            )
        ]


@router.post("/batches", response_model=BatchDetail, status_code=201)
def new_batch(body: BatchInput):
    return batch_detail(create_batch(body.target_count, body.actor))


@router.get("/batches/{batch_id}", response_model=BatchDetail)
def batch_detail(batch_id: str):
    with Session() as db:
        batch = db.get(ValidationBatch, batch_id)
        if not batch:
            raise HTTPException(404, "抽查批次不存在")
        samples = db.scalars(
            select(ValidationSample)
            .where(ValidationSample.batch_id == batch_id)
            .order_by(ValidationSample.position)
        ).all()
        return {"batch": batch_view(db, batch), "samples": [sample_view(db, s) for s in samples]}


@router.post("/batches/{batch_id}/prepare")
def prepare(batch_id: str, body: PrepareInput):
    return {"assigned": prepare_batch(batch_id, body.actor, body.limit)}


@router.get("/samples/{sample_id}", response_model=SampleDetail)
def sample_detail(sample_id: str):
    with Session() as db:
        sample = db.get(ValidationSample, sample_id)
        if not sample:
            raise HTTPException(404, "抽查样本不存在")
        version = db.get(ItemVersion, sample.version_id)
        item = db.get(Item, version.item_id)
        run = db.get(NormalizeRun, sample.run_id) if sample.run_id else None
        return {
            "sample": sample_view(db, sample),
            "original": {
                "id": version.id,
                "title": version.title,
                "url": item.url,
                "author": version.author,
                "published_at": version.published_at,
                "paragraphs": version.paragraphs,
            },
            "output": run.output if run else None,
            "fields": sample_fields(version, run),
            "reviews": db.scalars(
                select(FieldReview)
                .where(FieldReview.sample_id == sample_id)
                .order_by(FieldReview.created_at.desc())
            ).all(),
        }


@router.post("/samples/{sample_id}/reviews", response_model=FieldReviewView, status_code=201)
def field_review(sample_id: str, body: FieldReviewInput):
    return save_field_review(
        sample_id,
        body.run_id,
        body.reviewer,
        [f.model_dump() for f in body.fields],
        body.note,
        body.original_checked,
    )


@router.post("/samples/{sample_id}/rerun")
def rerun(sample_id: str, body: ActorInput):
    with lock(f"validation-sample:{sample_id}") as acquired:
        if not acquired:
            raise HTTPException(409, "正在重新提取")
        with Session() as db:
            sample = db.scalar(
                select(ValidationSample).where(ValidationSample.id == sample_id).with_for_update()
            )
            if not sample:
                raise HTTPException(404, "抽查样本不存在")
            old = db.get(NormalizeRun, sample.run_id) if sample.run_id else None
            if old and old.status in ("pending", "running", "retryable", "budget_wait"):
                raise HTTPException(409, "已有提取正在等待或处理中")
            sample.run_id = queue_normalize(sample.version_id, force=True)
            db.add(
                AuditLog(
                    action="validation-rerun",
                    object_id=sample_id,
                    actor=body.actor,
                    detail={"run_id": sample.run_id},
                )
            )
            db.commit()
            return {"id": sample.run_id}


@router.get("/sessions", response_model=list[SessionView])
def sessions():
    with Session() as db:
        return db.scalars(
            select(WorkSession).order_by(WorkSession.started_at.desc()).limit(100)
        ).all()


@router.post("/sessions", response_model=SessionView, status_code=201)
def new_session(body: SessionInput):
    return start_session(**body.model_dump())


@router.post("/sessions/{session_id}/stop", response_model=SessionView)
def finish_session(session_id: str, body: StopInput):
    return stop_session(session_id, **body.model_dump())
