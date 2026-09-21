from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text

from less.ai import Normalized
from less.db import Session
from less.models import AuditLog, HumanReview, Item, ItemVersion, NormalizeRun, Source, SourceCheck
from less.pipeline import ai_state, queue_normalize, resume_ai
from less.storage import read_blob

app = FastAPI(title="Less Content Engine", version="0.1.0")


@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}:
        return JSONResponse({"detail": "Local access only"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    }:
        return JSONResponse({"detail": "Untrusted origin"}, status_code=403)
    if request.method in {
        "POST",
        "PATCH",
        "DELETE",
    } and "application/json" not in request.headers.get("content-type", ""):
        return JSONResponse({"detail": "JSON request required"}, status_code=415)
    return await call_next(request)


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Actor(RequestBody):
    actor: str = Field(min_length=1, max_length=80)


class SourceEdit(Actor):
    status: Literal["active", "paused", "needs_review"]


class NormalizeRequest(RequestBody):
    force: bool = False


class ReviewRequest(RequestBody):
    run_id: str
    reviewer: str = Field(min_length=1, max_length=80)
    decision: Literal["accepted", "needs_correction"]
    note: str = Field(min_length=1, max_length=5000)


class SourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    node_url: str
    feed_url: str
    role: str
    topics: list[str]
    coverage: list[str]
    authority: str
    bias: str
    status: str
    interval_hours: int
    next_due_at: datetime
    last_success_at: datetime | None


class ParagraphView(BaseModel):
    id: str
    text: str
    start: int
    end: int


class VersionView(BaseModel):
    id: str
    item_id: str
    content_hash: str
    title: str
    author: str | None
    published_at: datetime | None
    captured_at: datetime
    text: str
    paragraphs: list[ParagraphView]
    snapshot_path: str
    acquisition: str
    limitations: list[str]


class ItemIdentityView(BaseModel):
    id: str
    source_id: str
    url: str
    created_at: datetime


class ItemView(BaseModel):
    id: str
    source_id: str
    url: str
    version: VersionView


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    cli_version: str | None = None
    duration_seconds: float | None = None
    usage: dict | None = None
    cost: float | None = None


class RunView(BaseModel):
    id: str
    version_id: str
    execution_key: str
    prompt_version: str
    model: str
    status: str
    attempts: int
    attempts_log: list[dict]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    next_attempt_at: datetime
    output: Normalized | None
    raw_output: str | None
    metadata: RunMetadata
    error: str | None


class ReviewView(BaseModel):
    id: str
    version_id: str
    run_id: str
    reviewer: str
    decision: str
    note: str
    created_at: datetime


class DetailView(BaseModel):
    version: VersionView
    item: ItemIdentityView
    runs: list[RunView]
    reviews: list[ReviewView]


class CheckView(BaseModel):
    id: str
    source_id: str
    slot: str
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    status: str
    attempts: int
    attempts_log: list[dict]
    next_attempt_at: datetime
    item_count: int
    feed_item_count: int
    deferred_count: int
    new_versions: int
    error: str | None
    snapshot_path: str | None


class CountsView(BaseModel):
    sources: int
    connected_sources: int
    items: int
    versions: int
    runs: int


class AIStateView(BaseModel):
    paused: bool
    reason: str | None
    code: str | None = None


class OverviewView(BaseModel):
    counts: CountsView
    ai: AIStateView
    stage: str


def serialize(obj):
    return {
        col.key: getattr(obj, "metadata_" if col.key == "metadata" else col.key)
        for col in obj.__table__.columns
    }


@app.get("/api/health")
def health():
    with Session() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "stage": "week-1"}


@app.get("/api/overview", response_model=OverviewView)
def overview():
    with Session() as db:
        counts = {
            name: db.scalar(select(func.count()).select_from(model))
            for name, model in (
                ("sources", Source),
                ("items", Item),
                ("versions", ItemVersion),
                ("runs", NormalizeRun),
            )
        }
        counts["connected_sources"] = db.scalar(
            select(func.count()).select_from(Source).where(Source.last_success_at.is_not(None))
        )
        return {"counts": counts, "ai": ai_state(db), "stage": "Week 1 · Sources & Normalize"}


@app.get("/api/sources", response_model=list[SourceView])
def sources():
    with Session() as db:
        return db.scalars(select(Source).order_by(Source.name)).all()


@app.patch("/api/sources/{source_id}", response_model=SourceView)
def edit_source(source_id: str, body: SourceEdit):
    with Session() as db:
        source = db.get(Source, source_id)
        if not source:
            raise HTTPException(404, "Source not found")
        source.status = body.status
        db.add(
            AuditLog(
                action="source-status",
                object_id=source_id,
                actor=body.actor,
                detail={"status": body.status},
            )
        )
        db.commit()
        return source


@app.post("/api/sources/{source_id}/collect", status_code=202)
def collect_source(source_id: str, body: Actor):
    from less.models import uid

    with Session() as db:
        source = db.get(Source, source_id)
        if not source or source.status != "active":
            raise HTTPException(409, "Source must exist and be active")
        check = SourceCheck(source_id=source_id, slot=f"manual:{uid()}")
        db.add(check)
        db.flush()
        db.add(AuditLog(action="collect", object_id=check.id, actor=body.actor))
        db.commit()
        return {"id": check.id, "status": "pending"}


@app.get("/api/checks", response_model=list[CheckView])
def checks():
    with Session() as db:
        return [
            serialize(c)
            for c in db.scalars(
                select(SourceCheck).order_by(SourceCheck.scheduled_at.desc()).limit(100)
            )
        ]


@app.get("/api/items", response_model=list[ItemView])
def items():
    with Session() as db:
        rows = db.execute(
            select(Item, ItemVersion)
            .join(ItemVersion)
            .order_by(ItemVersion.captured_at.desc())
            .limit(100)
        ).all()
        return [
            {
                "id": item.id,
                "source_id": item.source_id,
                "url": item.url,
                "version": serialize(version),
            }
            for item, version in rows
        ]


@app.get("/api/versions/{version_id}", response_model=DetailView)
def version_detail(version_id: str):
    with Session() as db:
        version = db.get(ItemVersion, version_id)
        if not version:
            raise HTTPException(404, "Item version not found")
        return {
            "version": serialize(version),
            "item": serialize(db.get(Item, version.item_id)),
            "runs": [
                serialize(r)
                for r in db.scalars(
                    select(NormalizeRun)
                    .where(NormalizeRun.version_id == version_id)
                    .order_by(NormalizeRun.created_at.desc())
                )
            ],
            "reviews": [
                serialize(r)
                for r in db.scalars(
                    select(HumanReview)
                    .where(HumanReview.version_id == version_id)
                    .order_by(HumanReview.created_at.desc())
                )
            ],
        }


@app.get("/api/versions/{version_id}/snapshot", response_class=PlainTextResponse)
def snapshot(version_id: str):
    with Session() as db:
        version = db.get(ItemVersion, version_id)
        if not version:
            raise HTTPException(404, "Item version not found")
        return PlainTextResponse(
            read_blob(version.snapshot_path).decode("utf-8", errors="replace"),
            headers={
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'",
            },
        )


@app.post("/api/versions/{version_id}/normalize", status_code=202)
def normalize(version_id: str, body: NormalizeRequest):
    try:
        return {"id": queue_normalize(version_id, body.force)}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/versions/{version_id}/reviews", status_code=201, response_model=ReviewView)
def review(version_id: str, body: ReviewRequest):
    with Session() as db:
        run = db.get(NormalizeRun, body.run_id)
        if not run or run.version_id != version_id or run.status != "succeeded":
            raise HTTPException(409, "A successful run for this exact version is required")
        record = HumanReview(version_id=version_id, **body.model_dump())
        db.add(record)
        db.commit()
        return serialize(record)


@app.get("/api/runs", response_model=list[RunView])
def runs():
    with Session() as db:
        return [
            serialize(r)
            for r in db.scalars(
                select(NormalizeRun).order_by(NormalizeRun.created_at.desc()).limit(100)
            )
        ]


@app.post("/api/ai/resume")
def resume(body: Actor):
    resume_ai(body.actor)
    return {"paused": False}


@app.exception_handler(ValueError)
def invalid_value(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


from less.validation_api import router as validation_router  # noqa: E402

app.include_router(validation_router)

from less.editorial_api import router as editorial_router  # noqa: E402

app.include_router(editorial_router)

from less.cluster_audit import router as cluster_audit_router  # noqa: E402

app.include_router(cluster_audit_router)

from less.briefs import router as briefs_router  # noqa: E402

app.include_router(briefs_router)
