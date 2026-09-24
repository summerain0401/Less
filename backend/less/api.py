from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone
from typing import Literal
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import selectinload

from less.config import settings
from less.db import Session, init_db
from less.models import Brief, BriefSource, BriefTopic, Source, Topic


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_time(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    try:
        if len(value) == 10:
            return date.fromisoformat(value).isoformat()
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("时间必须是 YYYY-MM-DD 或带时区的 ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("包含时刻时必须提供时区")
    return parsed.isoformat()


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceInput(InputModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    type: Literal["official_docs", "release", "paper", "blog", "media", "other"]
    primary: bool = False
    published_at: str | None = None

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("来源必须是可访问的 http(s) 具体页面")
        return value

    @field_validator("published_at")
    @classmethod
    def valid_published_at(cls, value: str | None) -> str | None:
        return normalize_time(value)


class BriefFields(InputModel):
    title: str = Field(min_length=1, max_length=500)
    published_at: str | None = None
    topics: list[str] = Field(min_length=1, max_length=12)
    important: bool
    useful: bool
    confidence: Literal["high", "medium"]
    sources: list[SourceInput] = Field(min_length=1, max_length=20)
    what_happened: str = Field(min_length=1, max_length=10000)
    why_it_matters: str = Field(min_length=1, max_length=10000)
    our_take: str | None = Field(default=None, max_length=10000)
    uncertainty: str | None = Field(default=None, max_length=10000)

    @field_validator("published_at")
    @classmethod
    def valid_published_at(cls, value: str | None) -> str | None:
        return normalize_time(value)

    @field_validator("topics")
    @classmethod
    def valid_topics(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            value = value.strip()
            if not value or len(value) > 80:
                raise ValueError("主题名称需为 1–80 个字符")
            key = value.casefold()
            if key in seen:
                raise ValueError("主题不能重复")
            seen.add(key)
            result.append(value)
        return result

    @model_validator(mode="after")
    def editorial_rules(self):
        if not self.important and not self.useful:
            raise ValueError("important 和 useful 至少一项为 true")
        if not any(source.primary for source in self.sources):
            raise ValueError("至少需要一个主要来源")
        urls = [source.url for source in self.sources]
        if len(urls) != len(set(urls)):
            raise ValueError("同一 Brief 的来源链接不能重复")
        if self.confidence == "medium" and not self.uncertainty:
            raise ValueError("medium confidence 必须说明 uncertainty")
        return self


class BriefCreate(BriefFields):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class BriefView(BriefCreate):
    created_at: datetime
    updated_at: datetime | None


class TodayView(BaseModel):
    day: date
    entries: list[BriefView]


class TopicView(BaseModel):
    id: str
    name: str
    brief_count: int


def load_options():
    return (
        selectinload(Brief.source_links).selectinload(BriefSource.source),
        selectinload(Brief.topic_links).selectinload(BriefTopic.topic),
    )


def brief_view(brief: Brief) -> dict:
    return {
        "id": brief.id,
        "title": brief.title,
        "published_at": brief.published_at,
        "topics": [link.topic.name for link in brief.topic_links],
        "important": brief.important,
        "useful": brief.useful,
        "confidence": brief.confidence,
        "sources": [
            {
                "name": source.name,
                "url": source.url,
                "type": source.type,
                "primary": link.primary,
                "published_at": source.published_at,
            }
            for link in brief.source_links
            for source in [link.source]
        ],
        "what_happened": brief.what_happened,
        "why_it_matters": brief.why_it_matters,
        "our_take": brief.our_take,
        "uncertainty": brief.uncertainty,
        "created_at": brief.created_at,
        "updated_at": brief.updated_at,
    }


def get_brief(db, brief_id: str) -> Brief | None:
    return db.scalar(select(Brief).where(Brief.id == brief_id).options(*load_options()))


def replace_content(db, brief: Brief, body: BriefFields) -> None:
    previous_source_ids = [link.source_id for link in brief.source_links]
    previous_topic_ids = [link.topic_id for link in brief.topic_links]
    for field in (
        "title",
        "published_at",
        "what_happened",
        "why_it_matters",
        "our_take",
        "important",
        "useful",
        "confidence",
        "uncertainty",
    ):
        setattr(brief, field, getattr(body, field))
    brief.source_links.clear()
    brief.topic_links.clear()
    db.flush()
    for position, source in enumerate(body.sources):
        stored = db.scalar(select(Source).where(Source.url == source.url))
        if stored is None:
            stored = Source(
                id=str(uuid5(NAMESPACE_URL, f"less:source:{source.url}")),
                name=source.name,
                url=source.url,
                type=source.type,
                published_at=source.published_at,
            )
            db.add(stored)
        else:
            stored.name = source.name
            stored.type = source.type
            stored.published_at = source.published_at
        brief.source_links.append(
            BriefSource(position=position, primary=source.primary, source=stored)
        )
    for position, name in enumerate(body.topics):
        topic = db.scalar(select(Topic).where(func.lower(Topic.name) == name.lower()))
        if topic is None:
            topic = Topic(id=str(uuid5(NAMESPACE_URL, f"less:topic:{name.casefold()}")), name=name)
            db.add(topic)
        brief.topic_links.append(BriefTopic(position=position, topic=topic))
    db.flush()
    for source_id in previous_source_ids:
        linked = db.scalar(select(BriefSource).where(BriefSource.source_id == source_id).limit(1))
        if linked is None:
            db.execute(delete(Source).where(Source.id == source_id))
    for topic_id in previous_topic_ids:
        linked = db.scalar(select(BriefTopic).where(BriefTopic.topic_id == topic_id).limit(1))
        if linked is None:
            db.execute(delete(Topic).where(Topic.id == topic_id))


def day_bounds(day: date) -> tuple[str, str]:
    local = ZoneInfo(settings().timezone)
    start = datetime.combine(day, time.min, local).astimezone(timezone.utc)
    end = datetime.combine(day, time.max, local).astimezone(timezone.utc)
    return start.isoformat(), end.isoformat()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Less", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}:
        return JSONResponse({"detail": "Local access only"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    }:
        return JSONResponse({"detail": "Untrusted origin"}, status_code=403)
    if request.method in {"POST", "PUT"}:
        if "application/json" not in request.headers.get("content-type", ""):
            return JSONResponse({"detail": "JSON request required"}, status_code=415)
    return await call_next(request)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/briefs", response_model=list[BriefView])
def list_briefs(
    day: date | None = None,
    topic: str | None = Query(default=None, max_length=80),
    q: str | None = Query(default=None, max_length=200),
):
    statement = select(Brief).options(*load_options()).order_by(Brief.created_at.desc(), Brief.id)
    if day:
        start, end = day_bounds(day)
        statement = statement.where(Brief.created_at.between(start, end))
    if topic:
        statement = statement.join(Brief.topic_links).join(BriefTopic.topic).where(
            func.lower(Topic.name) == topic.lower()
        )
    if q:
        pattern = f"%{q}%"
        statement = statement.where(
            or_(
                Brief.title.ilike(pattern),
                Brief.what_happened.ilike(pattern),
                Brief.why_it_matters.ilike(pattern),
            )
        )
    with Session() as db:
        return [brief_view(brief) for brief in db.scalars(statement).unique().all()]


@app.get("/api/briefs/{brief_id}", response_model=BriefView)
def brief_detail(brief_id: str):
    with Session() as db:
        brief = get_brief(db, brief_id)
        if brief is None:
            raise HTTPException(404, "Brief 不存在")
        return brief_view(brief)


@app.post("/api/briefs", response_model=BriefView, status_code=201)
def create_brief(body: BriefCreate):
    with Session() as db:
        if db.get(Brief, body.id):
            raise HTTPException(409, "Brief ID 已存在")
        brief = Brief(id=body.id, created_at=utc_now())
        db.add(brief)
        replace_content(db, brief, body)
        db.commit()
        return brief_view(get_brief(db, brief.id))


@app.put("/api/briefs/{brief_id}", response_model=BriefView)
def update_brief(brief_id: str, body: BriefFields):
    with Session() as db:
        brief = get_brief(db, brief_id)
        if brief is None:
            raise HTTPException(404, "Brief 不存在")
        replace_content(db, brief, body)
        brief.updated_at = utc_now()
        db.commit()
        return brief_view(get_brief(db, brief.id))


@app.delete("/api/briefs/{brief_id}", status_code=204)
def delete_brief(brief_id: str):
    with Session() as db:
        brief = db.get(Brief, brief_id)
        if brief is None:
            raise HTTPException(404, "Brief 不存在")
        topic_ids = db.scalars(
            select(BriefTopic.topic_id).where(BriefTopic.brief_id == brief_id)
        ).all()
        source_ids = db.scalars(
            select(BriefSource.source_id).where(BriefSource.brief_id == brief_id)
        ).all()
        db.delete(brief)
        db.flush()
        for topic_id in topic_ids:
            linked = db.scalar(select(BriefTopic).where(BriefTopic.topic_id == topic_id).limit(1))
            if linked is None:
                db.execute(delete(Topic).where(Topic.id == topic_id))
        for source_id in source_ids:
            linked = db.scalar(
                select(BriefSource).where(BriefSource.source_id == source_id).limit(1)
            )
            if linked is None:
                db.execute(delete(Source).where(Source.id == source_id))
        db.commit()
    return Response(status_code=204)


@app.get("/api/today", response_model=TodayView)
def today(day: date | None = None):
    selected_day = day or datetime.now(ZoneInfo(settings().timezone)).date()
    start, end = day_bounds(selected_day)
    with Session() as db:
        briefs = db.scalars(
            select(Brief)
            .where(Brief.created_at.between(start, end))
            .options(*load_options())
            .order_by(Brief.created_at.desc(), Brief.id)
        ).unique().all()
        return {"day": selected_day, "entries": [brief_view(brief) for brief in briefs]}


@app.get("/api/topics", response_model=list[TopicView])
def topics():
    with Session() as db:
        rows = db.execute(
            select(Topic.id, Topic.name, func.count(BriefTopic.brief_id).label("brief_count"))
            .outerjoin(BriefTopic)
            .group_by(Topic.id)
            .order_by(Topic.name)
        ).all()
        return [
            {"id": row.id, "name": row.name, "brief_count": row.brief_count}
            for row in rows
        ]
