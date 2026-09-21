"""Internal publication with immutable content versions and explicit approval."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from less.budget import local_today
from less.db import Session
from less.editorial import event_for_update
from less.editorial_api import Input, ORMView
from less.models import (
    AuditLog,
    Brief,
    BriefPublication,
    BriefReview,
    BriefVersion,
    EditorialEvent,
    EventClaim,
    EventMember,
    Evidence,
    Item,
    ItemVersion,
    TodayEdition,
    now,
)

router = APIRouter(prefix="/api", tags=["Brief and Today"])


class BriefFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class BriefContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=500)
    why_it_matters: str = Field(min_length=1, max_length=5000)
    what_changed: str = Field(min_length=1, max_length=5000)
    our_take: str = Field(min_length=1, max_length=5000)
    try_it: str = Field(default="", max_length=5000)
    facts: list[BriefFact] = Field(min_length=1, max_length=30)


class BriefDraftInput(Input):
    event_id: str
    event_revision: int = Field(ge=1)
    expected_revision: int = Field(ge=0)
    content: BriefContent
    reason: str = Field(min_length=1, max_length=5000)


class BriefActionInput(Input):
    revision: int = Field(ge=1)
    action: Literal["submit", "approve", "publish", "withdraw", "return_to_draft"]
    reason: str = Field(min_length=1, max_length=5000)
    original_checked: bool = False


class BriefView(ORMView):
    id: str
    event_id: str
    revision: int
    status: str
    created_at: datetime


class BriefVersionView(ORMView):
    id: str
    revision: int
    event_revision: int
    content: dict
    sources: list[dict]
    actor: str
    reason: str
    created_at: datetime


class BriefReviewView(ORMView):
    id: str
    revision: int
    action: str
    actor: str
    reason: str
    created_at: datetime


class BriefDetailView(BaseModel):
    brief: BriefView
    versions: list[BriefVersionView]
    reviews: list[BriefReviewView]
    current_eligible: bool


class EditionNote(Input):
    note: str = Field(min_length=1, max_length=5000)


def eligible(event, version=None):
    return bool(
        event
        and event.lifecycle == "active"
        and event.value_status == "passed"
        and event.quality_status == "passed"
        and event.decision == "selected"
        and (version is None or event.revision == version.event_revision)
    )


def current_version(db, brief):
    return db.scalar(
        select(BriefVersion).where(
            BriefVersion.brief_id == brief.id, BriefVersion.revision == brief.revision
        )
    )


def sources_for(db, event, content):
    ids = [f.claim_id for f in content.facts]
    if len(ids) != len(set(ids)):
        raise ValueError("关键陈述不能重复")
    claims = {
        c.id: c for c in db.scalars(select(EventClaim).where(EventClaim.event_id == event.id))
    }
    if not set(ids) <= claims.keys() or not {c.id for c in claims.values() if c.critical} <= set(
        ids
    ):
        raise ValueError("必须包含事件的全部关键陈述，不得引用其他事件陈述")
    sources = []
    for fact in content.facts:
        if len(fact.evidence_ids) != len(set(fact.evidence_ids)):
            raise ValueError("证据不能重复")
        supporting = False
        for evidence_id in fact.evidence_ids:
            e = db.get(Evidence, evidence_id)
            if not e or e.claim_id != fact.claim_id or e.status != "verified":
                raise ValueError("事实引用必须指向本陈述已核验的证据")
            member = db.scalar(
                select(EventMember).where(
                    EventMember.event_id == event.id,
                    EventMember.version_id == e.version_id,
                    EventMember.active.is_(True),
                )
            )
            if not member or not set(e.paragraph_ids) <= set(member.paragraph_ids):
                raise ValueError("证据原文已脱离事件，请重新核验")
            version = db.get(ItemVersion, e.version_id)
            item = db.get(Item, version.item_id)
            supporting |= e.direction == "supporting"
            sources.append(
                {
                    "claim_id": fact.claim_id,
                    "claim": claims[fact.claim_id].text,
                    "kind": claims[fact.claim_id].kind,
                    "evidence_id": e.id,
                    "version_id": version.id,
                    "paragraph_ids": e.paragraph_ids,
                    "quote": e.quote,
                    "direction": e.direction,
                    "limitations": e.limitations,
                    "source_root": e.source_root,
                    "url": item.url,
                    "checked_by": e.checked_by,
                    "checked_at": e.checked_at.isoformat() if e.checked_at else None,
                }
            )
        if not supporting:
            raise ValueError("每条事实至少需要一条已核验支持证据")
    return sources


@router.get("/briefs", response_model=list[BriefView])
def briefs():
    with Session() as db:
        return db.scalars(
            select(Brief).order_by(Brief.created_at.desc(), Brief.id).limit(200)
        ).all()


@router.get("/briefs/{brief_id}", response_model=BriefDetailView)
def detail(brief_id: str):
    with Session() as db:
        brief = db.get(Brief, brief_id)
        if not brief:
            raise HTTPException(404, "Brief 不存在")
        return {
            "brief": brief,
            "versions": db.scalars(
                select(BriefVersion)
                .where(BriefVersion.brief_id == brief_id)
                .order_by(BriefVersion.revision.desc())
            ).all(),
            "reviews": db.scalars(
                select(BriefReview)
                .where(BriefReview.brief_id == brief_id)
                .order_by(BriefReview.created_at, BriefReview.id)
            ).all(),
            "current_eligible": eligible(
                db.get(EditorialEvent, brief.event_id), current_version(db, brief)
            ),
        }


@router.post("/briefs", response_model=BriefView, status_code=201)
def draft(body: BriefDraftInput):
    with Session() as db:
        event = event_for_update(db, body.event_id, body.event_revision)
        if not eligible(event):
            raise ValueError("事件需先通过两道门并明确入选，才能形成 Brief")
        brief = db.scalar(select(Brief).where(Brief.event_id == event.id).with_for_update())
        if (brief.revision if brief else 0) != body.expected_revision:
            raise ValueError("Brief 已有新版本，请刷新后再修改")
        sources = sources_for(db, event, body.content)
        if brief:
            brief.revision += 1
            brief.status = "draft"
        else:
            brief = Brief(event_id=event.id)
            db.add(brief)
            db.flush()
        db.add(
            BriefVersion(
                brief_id=brief.id,
                revision=brief.revision,
                event_revision=event.revision,
                content=body.content.model_dump(),
                sources=sources,
                actor=body.actor,
                reason=body.reason,
            )
        )
        db.add(
            BriefReview(
                brief_id=brief.id,
                revision=brief.revision,
                action="draft",
                actor=body.actor,
                reason=body.reason,
            )
        )
        db.commit()
        return brief


@router.post("/briefs/{brief_id}/actions", response_model=BriefView)
def action(brief_id: str, body: BriefActionInput):
    with Session() as db:
        initial = db.get(Brief, brief_id)
        if not initial:
            raise HTTPException(404, "Brief 不存在")
        # Event -> brief -> edition lock order also used by all content mutations.
        event = db.scalar(
            select(EditorialEvent).where(EditorialEvent.id == initial.event_id).with_for_update()
        )
        brief = db.scalar(
            select(Brief)
            .where(Brief.id == brief_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if brief.revision != body.revision:
            raise ValueError("Brief 已有新版本，请刷新后再操作")
        version = current_version(db, brief)
        if body.action in ("submit", "approve", "publish"):
            if not eligible(event, version):
                raise ValueError("事件或证据已变化，需重新核验并保存新的 Brief 版本")
            sources_for(db, event, BriefContent.model_validate(version.content))
        allowed = {
            "submit": {"draft"},
            "approve": {"in_review"},
            "publish": {"approved"},
            "withdraw": {"draft", "in_review", "approved", "published", "needs_review"},
            "return_to_draft": {"in_review", "approved", "published", "needs_review"},
        }
        if brief.status not in allowed[body.action]:
            raise ValueError("当前状态不允许此操作")
        if body.action == "approve" and not body.original_checked:
            raise ValueError("批准前必须明确核查原文、事实与解释边界及新增价值")
        if body.action == "publish":
            approval = db.scalar(
                select(BriefReview.id).where(
                    BriefReview.brief_id == brief.id,
                    BriefReview.revision == brief.revision,
                    BriefReview.action == "approve",
                )
            )
            if not approval:
                raise ValueError("当前版本没有人工批准记录")
            day = local_today().isoformat()
            db.execute(
                insert(TodayEdition)
                .values(id=day, note="", actor=body.actor, updated_at=now())
                .on_conflict_do_nothing()
            )
            db.scalar(select(TodayEdition).where(TodayEdition.id == day).with_for_update())
            existing = db.scalar(
                select(BriefPublication).where(
                    BriefPublication.edition_id == day, BriefPublication.brief_id == brief.id
                )
            )
            count = db.scalar(
                select(func.count())
                .select_from(BriefPublication)
                .where(BriefPublication.edition_id == day)
            )
            if not existing and count >= 5:
                raise ValueError("Today 已有 5 条内容，请保持有限阅读量；无需为达到数量而发布")
            if existing:
                db.add(
                    AuditLog(
                        action="brief-publication-correction",
                        object_id=brief.id,
                        actor=body.actor,
                        detail={
                            "day": day,
                            "previous_revision": existing.revision,
                            "revision": brief.revision,
                            "reason": body.reason,
                        },
                    )
                )
                existing.revision, existing.actor = brief.revision, body.actor
            else:
                db.add(
                    BriefPublication(
                        edition_id=day, brief_id=brief.id, revision=brief.revision, actor=body.actor
                    )
                )
        brief.status = {
            "submit": "in_review",
            "approve": "approved",
            "publish": "published",
            "withdraw": "withdrawn",
            "return_to_draft": "draft",
        }[body.action]
        db.add(
            BriefReview(
                brief_id=brief.id,
                revision=brief.revision,
                action=body.action,
                actor=body.actor,
                reason=body.reason,
            )
        )
        db.commit()
        return brief


@router.post("/today/note")
def edition_note(body: EditionNote):
    with Session() as db:
        day = local_today().isoformat()
        db.execute(
            insert(TodayEdition)
            .values(id=day, note=body.note, actor=body.actor, updated_at=now())
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"note": body.note, "actor": body.actor, "updated_at": now()},
            )
        )
        db.add(
            AuditLog(
                action="today-note", object_id=day, actor=body.actor, detail={"note": body.note}
            )
        )
        db.commit()
        return {"day": day, "note": body.note}


@router.get("/today")
def today(day: date | None = None):
    day_id = (day or local_today()).isoformat()
    with Session() as db:
        edition = db.get(TodayEdition, day_id)
        publications = db.scalars(
            select(BriefPublication)
            .where(BriefPublication.edition_id == day_id)
            .order_by(BriefPublication.created_at, BriefPublication.id)
        ).all()
        entries = []
        for p in publications:
            brief = db.get(Brief, p.brief_id)
            version = db.scalar(
                select(BriefVersion).where(
                    BriefVersion.brief_id == p.brief_id, BriefVersion.revision == p.revision
                )
            )
            readable = (
                brief.status == "published"
                and brief.revision == p.revision
                and eligible(db.get(EditorialEvent, brief.event_id), version)
            )
            entries.append(
                {
                    "brief_id": brief.id,
                    "revision": p.revision,
                    "status": "published"
                    if readable
                    else "withdrawn"
                    if brief.status == "withdrawn"
                    else "needs_review",
                    "content": version.content if readable else None,
                    "sources": version.sources if readable else [],
                    "published_at": p.created_at,
                    "actor": p.actor,
                }
            )
        return {
            "day": day_id,
            "recorded": edition is not None,
            "note": edition.note if edition else "",
            "entries": entries,
            "readable_count": sum(e["status"] == "published" for e in entries),
            "limit": 5,
        }
