"""Human-reviewed hypotheses with counter-search logs and immutable history."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from less.db import Session
from less.editorial_api import Input, Mutation, ORMView
from less.models import (
    EditorialEvent,
    EventClaim,
    EventMember,
    Evidence,
    Item,
    ItemVersion,
    Signal,
    SignalEvidence,
    SignalRecord,
    now,
)

router = APIRouter(prefix="/api/signals", tags=["Signal"])


class Thesis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=500)
    statement: str = Field(min_length=1, max_length=5000)
    scope: str = Field(min_length=1, max_length=5000)
    starts_on: date
    ends_on: date
    falsification: str = Field(min_length=1, max_length=5000)
    counter_plan: str = Field(min_length=1, max_length=5000)
    owner: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def window(self):
        if self.ends_on < self.starts_on:
            raise ValueError("观察期结束不能早于开始")
        return self


class SignalCreate(Input):
    thesis: Thesis


class ThesisEdit(Mutation):
    thesis: Thesis


class SignalLink(Mutation):
    evidence_id: str
    direction: Literal["supporting", "counter", "context"]
    rationale: str = Field(min_length=1, max_length=5000)
    original_checked: bool


class SearchRecord(Mutation):
    query: str = Field(min_length=1, max_length=2000)
    source_types: str = Field(min_length=1, max_length=3000)
    results: str = Field(min_length=1, max_length=5000)
    gaps: str = Field(min_length=1, max_length=5000)


class SignalReviewInput(Mutation):
    status: Literal["candidate", "emerging", "strong", "established", "weakening", "rejected"]
    our_view: str = Field(min_length=1, max_length=5000)
    independence: str = Field(min_length=1, max_length=5000)
    alternatives: str = Field(min_length=1, max_length=5000)
    maturity_evidence: str = Field(default="", max_length=5000)
    counter_resolutions: dict[str, str] = Field(default_factory=dict)
    original_checked: bool


class SignalView(ORMView):
    id: str
    revision: int
    thesis: dict
    status: str
    needs_review: bool
    last_reviewed_at: datetime | None
    created_at: datetime


class SignalLinkView(ORMView):
    id: str
    evidence_id: str
    event_id: str
    event_revision: int
    direction: str
    rationale: str
    snapshot: dict
    active: bool
    added_at: datetime


class SignalRecordView(ORMView):
    id: str
    revision: int
    kind: str
    actor: str
    reason: str
    detail: dict
    created_at: datetime


class SignalDetail(BaseModel):
    signal: SignalView
    evidence: list[SignalLinkView]
    records: list[SignalRecordView]
    stale_link_ids: list[str]


def locked(db, signal_id, revision):
    result = db.scalar(select(Signal).where(Signal.id == signal_id).with_for_update())
    if not result:
        raise HTTPException(404, "Signal 不存在")
    if result.revision != revision:
        raise ValueError("Signal 已更新，请刷新后操作")
    return result


def record(db, signal, body, kind, detail):
    signal.revision += 1
    signal.needs_review = True
    db.add(
        SignalRecord(
            signal_id=signal.id,
            revision=signal.revision,
            kind=kind,
            actor=body.actor,
            reason=body.reason,
            detail=detail,
        )
    )


def link_valid(db, link):
    evidence = db.get(Evidence, link.evidence_id)
    claim = db.get(EventClaim, evidence.claim_id) if evidence else None
    event = db.get(EditorialEvent, link.event_id)
    member = (
        db.scalar(
            select(EventMember).where(
                EventMember.event_id == link.event_id,
                EventMember.version_id == evidence.version_id,
                EventMember.active.is_(True),
            )
        )
        if evidence
        else None
    )
    return bool(
        evidence
        and evidence.status == "verified"
        and claim
        and claim.event_id == link.event_id
        and event
        and event.lifecycle == "active"
        and event.revision == link.event_revision
        and member
        and set(evidence.paragraph_ids) <= set(member.paragraph_ids)
    )


@router.get("", response_model=list[SignalView])
def signals():
    with Session() as db:
        return db.scalars(
            select(Signal).order_by(Signal.created_at.desc(), Signal.id).limit(100)
        ).all()


@router.post("", response_model=SignalView, status_code=201)
def create(body: SignalCreate):
    with Session() as db:
        s = Signal(thesis=body.thesis.model_dump(mode="json"))
        db.add(s)
        db.flush()
        db.add(
            SignalRecord(
                signal_id=s.id,
                revision=1,
                kind="thesis",
                actor=body.actor,
                reason="建立待核验假设草稿",
                detail={"thesis": s.thesis},
            )
        )
        db.commit()
        return s


@router.get("/{signal_id}", response_model=SignalDetail)
def detail(signal_id: str):
    with Session() as db:
        s = db.get(Signal, signal_id)
        if not s:
            raise HTTPException(404, "Signal 不存在")
        links = db.scalars(
            select(SignalEvidence)
            .where(SignalEvidence.signal_id == signal_id)
            .order_by(SignalEvidence.added_at, SignalEvidence.id)
        ).all()
        return {
            "signal": s,
            "evidence": links,
            "records": db.scalars(
                select(SignalRecord)
                .where(SignalRecord.signal_id == signal_id)
                .order_by(SignalRecord.created_at, SignalRecord.id)
            ).all(),
            "stale_link_ids": [
                linked.id for linked in links if linked.active and not link_valid(db, linked)
            ],
        }


@router.patch("/{signal_id}", response_model=SignalView)
def edit(signal_id: str, body: ThesisEdit):
    with Session() as db:
        s = locked(db, signal_id, body.revision)
        previous = s.thesis
        s.thesis = body.thesis.model_dump(mode="json")
        record(db, s, body, "thesis", {"previous": previous, "thesis": s.thesis})
        db.commit()
        return s


@router.post("/{signal_id}/evidence", response_model=SignalLinkView)
def link(signal_id: str, body: SignalLink):
    with Session() as db:
        e = db.get(Evidence, body.evidence_id)
        c = db.get(EventClaim, e.claim_id) if e else None
        if not c:
            raise ValueError("证据不存在")
        event = db.scalar(
            select(EditorialEvent).where(EditorialEvent.id == c.event_id).with_for_update()
        )
        # Refresh after acquiring event lock to catch concurrent evidence/claim changes.
        db.refresh(e)
        db.refresh(c)
        if (
            c.event_id != event.id
            or event.lifecycle != "active"
            or e.status != "verified"
            or not body.original_checked
        ):
            raise ValueError("需核对活跃事件的已验证原文证据")
        s = locked(db, signal_id, body.revision)
        member = db.scalar(
            select(EventMember).where(
                EventMember.event_id == event.id,
                EventMember.version_id == e.version_id,
                EventMember.active.is_(True),
            )
        )
        if not member or not set(e.paragraph_ids) <= set(member.paragraph_ids):
            raise ValueError("原文关联已失效")
        version = db.get(ItemVersion, e.version_id)
        item = db.get(Item, version.item_id)
        linked = db.scalar(
            select(SignalEvidence).where(
                SignalEvidence.signal_id == s.id, SignalEvidence.evidence_id == e.id
            )
        )
        previous = SignalLinkView.model_validate(linked).model_dump(mode="json") if linked else None
        snapshot = {
            "claim": c.text,
            "quote": e.quote,
            "version_id": version.id,
            "paragraph_ids": e.paragraph_ids,
            "source_root": e.source_root,
            "limitations": e.limitations,
            "url": item.url,
            "happened_at": event.happened_at.isoformat() if event.happened_at else None,
            "published_at": version.published_at.isoformat() if version.published_at else None,
        }
        if not linked:
            linked = SignalEvidence(
                signal_id=s.id,
                evidence_id=e.id,
                event_id=event.id,
                event_revision=event.revision,
                direction=body.direction,
                rationale=body.rationale,
                snapshot=snapshot,
            )
            db.add(linked)
        else:
            linked.event_id, linked.event_revision = event.id, event.revision
            linked.direction, linked.rationale, linked.snapshot, linked.active = (
                body.direction,
                body.rationale,
                snapshot,
                True,
            )
        db.flush()
        record(
            db,
            s,
            body,
            "evidence",
            {
                "previous": previous,
                "link": SignalLinkView.model_validate(linked).model_dump(mode="json"),
            },
        )
        db.commit()
        return linked


@router.post("/{signal_id}/evidence/{link_id}/unlink", response_model=SignalView)
def unlink(signal_id: str, link_id: str, body: Mutation):
    with Session() as db:
        s = locked(db, signal_id, body.revision)
        linked = db.get(SignalEvidence, link_id)
        if not linked or linked.signal_id != s.id or not linked.active:
            raise ValueError("有效关联不存在")
        linked.active = False
        record(db, s, body, "unlink", {"link_id": linked.id})
        db.commit()
        return s


@router.post("/{signal_id}/searches", response_model=SignalView)
def search(signal_id: str, body: SearchRecord):
    with Session() as db:
        s = locked(db, signal_id, body.revision)
        record(
            db, s, body, "counter_search", body.model_dump(exclude={"actor", "revision", "reason"})
        )
        db.commit()
        return s


@router.post("/{signal_id}/reviews", response_model=SignalView)
def review(signal_id: str, body: SignalReviewInput):
    with Session() as db:
        event_ids = select(SignalEvidence.event_id).where(
            SignalEvidence.signal_id == signal_id, SignalEvidence.active.is_(True)
        )
        db.scalars(
            select(EditorialEvent)
            .where(EditorialEvent.id.in_(event_ids))
            .order_by(EditorialEvent.id)
            .with_for_update(read=True)
        ).all()
        s = locked(db, signal_id, body.revision)
        links = db.scalars(
            select(SignalEvidence).where(
                SignalEvidence.signal_id == s.id, SignalEvidence.active.is_(True)
            )
        ).all()
        if not body.original_checked or not links:
            raise ValueError("复评需要可定位起始证据并明确核对原文")
        if any(not link_valid(db, linked) for linked in links):
            raise ValueError("有关联证据已变化，请先重新核验并更新或移除关联")
        searches = db.scalars(
            select(SignalRecord).where(
                SignalRecord.signal_id == s.id,
                SignalRecord.kind == "counter_search",
                SignalRecord.created_at > s.last_reviewed_at if s.last_reviewed_at else True,
            )
        ).all()
        if not searches:
            raise ValueError("每轮复评前需记录新的反证检索及缺口")
        counters = {linked.id for linked in links if linked.direction == "counter"}
        if set(body.counter_resolutions) - counters or any(
            not body.counter_resolutions.get(i, "").strip() for i in counters
        ):
            raise ValueError("需要逐项说明反面证据如何影响判断")
        support = [linked for linked in links if linked.direction == "supporting"]
        if body.status in {"emerging", "strong", "established"} and (
            len({linked.event_id for linked in support}) < 2
            or len({linked.snapshot["source_root"] for linked in support}) < 2
        ):
            raise ValueError("升级需要至少两个不同事件与来源根的支持，且人工说明独立性")
        if body.status in {"strong", "established"} and not body.maturity_evidence.strip():
            raise ValueError(
                "需具体说明跨时间、主体、证据类型及持续验证；采用或效果主张需对应行为或结果证据"
            )
        previous = s.status
        record(
            db,
            s,
            body,
            "review",
            {
                "previous_status": previous,
                **body.model_dump(exclude={"actor", "revision", "reason"}),
                "search_ids": [r.id for r in searches],
                "evidence_ids": [linked.id for linked in links],
            },
        )
        s.status = body.status
        s.needs_review = False
        s.last_reviewed_at = now()
        db.commit()
        return s
