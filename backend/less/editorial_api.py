from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from less import clustering, editorial
from less.cluster_suggestions import suggestions
from less.db import Session
from less.models import (
    AuditLog,
    ClusterOperation,
    EditorialEvent,
    EditorialReview,
    EventClaim,
    EventMember,
    Evidence,
    Item,
    ItemVersion,
    Source,
)

router = APIRouter(prefix="/api/editorial", tags=["Editorial Inbox"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    actor: str = Field(min_length=1, max_length=80)


class Mutation(Input):
    revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=5000)


class EventFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=500)
    object: str = Field(min_length=1, max_length=2000)
    happened_at: AwareDatetime | None = None
    event_version: str | None = Field(default=None, max_length=200)
    scope: str = Field(min_length=1, max_length=5000)


class EventInput(EventFields, Input):
    pass


class EventUpdate(EventInput, Mutation):
    pass


class MemberInput(Mutation):
    version_id: str
    paragraph_ids: list[str] = Field(min_length=1)


class ClaimInput(Mutation):
    text: str = Field(min_length=1, max_length=5000)
    kind: Literal["fact_candidate", "reported_claim", "interpretation"]
    critical: bool = True


class EvidenceInput(Mutation):
    claim_id: str
    version_id: str
    paragraph_ids: list[str] = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=10000)
    direction: Literal["supporting", "counter", "context"]
    rationale: str = Field(min_length=1, max_length=5000)
    source_root: str = Field(min_length=1, max_length=2000)
    limitations: str = Field(min_length=1, max_length=5000)


class EvidenceReview(Mutation):
    status: Literal["verified", "rejected", "needs_review"]
    original_checked: bool


class ValueReview(Mutation):
    status: Literal["passed", "pending", "rejected"]
    important: bool
    useful: bool
    important_reason: str = Field(default="", max_length=5000)
    useful_reason: str = Field(default="", max_length=5000)


class QualityReview(Mutation):
    status: Literal["passed", "pending", "rejected"]
    gaps: list[str]
    conflict_resolutions: dict[str, str] = Field(default_factory=dict)


class DecisionInput(Mutation):
    status: Literal["selected", "deferred", "rejected", "evidence_only", "observe"]


class EventRef(BaseModel):
    id: str
    revision: int = Field(ge=1)


class MergeInput(Input):
    events: list[EventRef] = Field(min_length=2, max_length=20)
    target_id: str
    reason: str = Field(min_length=1, max_length=5000)


class SplitInput(Mutation):
    target: EventFields
    member_ids: list[str] = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)


class RestoreInput(Input):
    reason: str = Field(min_length=1, max_length=5000)


class ORMView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EventView(ORMView):
    id: str
    title: str
    subject: str
    action: str
    object: str
    happened_at: datetime | None
    event_version: str | None
    scope: str
    lifecycle: str
    redirected_to: str | None
    revision: int
    value_status: str
    quality_status: str
    decision: str
    created_at: datetime
    updated_at: datetime


class MemberView(ORMView):
    id: str
    version_id: str
    paragraph_ids: list[str]
    active: bool
    title: str
    source_name: str
    url: str
    published_at: datetime | None
    paragraphs: list[dict]


class ClaimView(ORMView):
    id: str
    text: str
    kind: str
    critical: bool


class EvidenceView(ORMView):
    id: str
    claim_id: str
    version_id: str
    paragraph_ids: list[str]
    quote: str
    direction: str
    rationale: str
    source_root: str
    limitations: str
    status: str
    checked_by: str | None
    checked_at: datetime | None
    created_at: datetime


class ReviewView(ORMView):
    id: str
    revision: int
    gate: str
    status: str
    actor: str
    detail: dict
    created_at: datetime


class HistoryView(ORMView):
    id: int
    action: str
    actor: str
    detail: dict
    created_at: datetime


class ClusterOperationView(ORMView):
    id: str
    kind: str
    actor: str
    reason: str
    after_revisions: dict[str, int]
    created_event_ids: list[str]
    status: str
    created_at: datetime
    restored_at: datetime | None
    restored_by: str | None
    restore_reason: str | None


class EventDetail(BaseModel):
    event: EventView
    members: list[MemberView]
    claims: list[ClaimView]
    evidence: list[EvidenceView]
    reviews: list[ReviewView]
    history: list[HistoryView]
    verified_source_roots: int
    cluster_operations: list[ClusterOperationView]


class InboxView(BaseModel):
    events: list[EventView]
    total: int
    offset: int
    limit: int


class SuggestedEvent(EventRef):
    title: str


class ClusterPair(BaseModel):
    left: SuggestedEvent
    right: SuggestedEvent
    score: float
    suggestion: str
    reasons: list[str]
    conflicts: list[str]
    shared_version_ids: list[str]


class ClusterSuggestionsView(BaseModel):
    method: str
    considered_events: int
    total_events: int
    total_pairs: int
    pairs: list[ClusterPair]
    limitations: list[str]


@router.get("/cluster-suggestions", response_model=ClusterSuggestionsView)
def cluster_suggestions():
    with Session() as db:
        return suggestions(db)


@router.get("/events", response_model=InboxView)
def events(
    decision: Literal["pending", "selected", "deferred", "rejected", "evidence_only", "observe"]
    | None = None,
    offset: int = 0,
    limit: int = 50,
    include_archived: bool = False,
):
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "分页参数无效")
    with Session() as db:
        query = select(EditorialEvent)
        if not include_archived:
            query = query.where(EditorialEvent.lifecycle == "active")
        if decision:
            query = query.where(EditorialEvent.decision == decision)
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(
            query.order_by(EditorialEvent.updated_at.desc(), EditorialEvent.id)
            .offset(offset)
            .limit(limit)
        ).all()
        return {"events": rows, "total": count, "offset": offset, "limit": limit}


@router.post("/events", response_model=EventView, status_code=201)
def create_event(body: EventInput):
    with Session() as db:
        event = EditorialEvent(**body.model_dump(exclude={"actor"}))
        db.add(event)
        db.flush()
        editorial.audit(
            db, event, body.actor, "event-create", body.model_dump(mode="json", exclude={"actor"})
        )
        db.commit()
        return event


@router.get("/events/{event_id}", response_model=EventDetail)
def event_detail(event_id: str):
    with Session() as db:
        event = db.get(EditorialEvent, event_id)
        if not event:
            raise HTTPException(404, "事件不存在")
        rows = db.execute(
            select(EventMember, ItemVersion, Item, Source)
            .join(ItemVersion, ItemVersion.id == EventMember.version_id)
            .join(Item, Item.id == ItemVersion.item_id)
            .join(Source, Source.id == Item.source_id)
            .where(EventMember.event_id == event_id)
            .order_by(EventMember.id)
        ).all()
        members = [
            {
                "id": m.id,
                "version_id": v.id,
                "paragraph_ids": m.paragraph_ids,
                "active": m.active,
                "title": v.title,
                "source_name": s.name,
                "url": i.url,
                "published_at": v.published_at,
                "paragraphs": v.paragraphs,
            }
            for m, v, i, s in rows
        ]
        evidence = db.scalars(
            select(Evidence)
            .join(EventClaim)
            .where(EventClaim.event_id == event_id)
            .order_by(Evidence.created_at)
        ).all()
        return {
            "event": event,
            "members": members,
            "claims": db.scalars(
                select(EventClaim).where(EventClaim.event_id == event_id).order_by(EventClaim.id)
            ).all(),
            "evidence": evidence,
            "reviews": db.scalars(
                select(EditorialReview)
                .where(EditorialReview.event_id == event_id)
                .order_by(EditorialReview.created_at.desc())
            ).all(),
            "history": db.scalars(
                select(AuditLog)
                .where(AuditLog.object_id == event_id)
                .order_by(AuditLog.created_at.desc())
            ).all(),
            "verified_source_roots": len(
                {e.source_root for e in evidence if e.status == "verified"}
            ),
            "cluster_operations": db.scalars(
                select(ClusterOperation)
                .where(ClusterOperation.after_revisions.has_key(event_id))
                .order_by(ClusterOperation.created_at.desc())
            ).all(),
        }


@router.patch("/events/{event_id}", response_model=EventView)
def edit_event(event_id: str, body: EventUpdate):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        changes = body.model_dump(exclude={"actor", "revision", "reason"})
        previous = EventView.model_validate(event).model_dump(mode="json")
        for key, value in changes.items():
            setattr(event, key, value)
        editorial.invalidate(
            db, event, body.actor, "event-edit", {"previous": previous, "reason": body.reason}
        )
        db.commit()
        return event


@router.post("/events/{event_id}/members", response_model=EventView)
def add_member(event_id: str, body: MemberInput):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        editorial.link_member(db, event, body)
        db.commit()
        return event


@router.post("/events/{event_id}/members/{member_id}/unlink", response_model=EventView)
def remove_member(event_id: str, member_id: str, body: Mutation):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        editorial.unlink_member(db, event, member_id, body.actor, body.reason)
        db.commit()
        return event


@router.post("/events/{event_id}/claims", response_model=ClaimView, status_code=201)
def add_claim(event_id: str, body: ClaimInput):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        claim = EventClaim(
            event_id=event_id, text=body.text, kind=body.kind, critical=body.critical
        )
        db.add(claim)
        db.flush()
        editorial.invalidate(
            db, event, body.actor, "claim-add", {"claim_id": claim.id, "reason": body.reason}
        )
        db.commit()
        return claim


@router.post("/events/{event_id}/evidence", response_model=EvidenceView, status_code=201)
def add_evidence(event_id: str, body: EvidenceInput):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        result = editorial.create_evidence(db, event, body)
        db.commit()
        return result


@router.post("/events/{event_id}/evidence/{evidence_id}/review", response_model=EvidenceView)
def check_evidence(event_id: str, evidence_id: str, body: EvidenceReview):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        result = editorial.review_evidence(db, event, evidence_id, body)
        db.commit()
        return result


@router.post("/events/{event_id}/value", response_model=ReviewView, status_code=201)
def check_value(event_id: str, body: ValueReview):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        result = editorial.value_review(db, event, body)
        db.commit()
        return result


@router.post("/events/{event_id}/quality", response_model=ReviewView, status_code=201)
def check_quality(event_id: str, body: QualityReview):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        result = editorial.quality_review(db, event, body)
        db.commit()
        return result


@router.post("/events/{event_id}/decision", response_model=ReviewView, status_code=201)
def make_decision(event_id: str, body: DecisionInput):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        result = editorial.decide(db, event, body)
        db.commit()
        return result


@router.patch("/events/{event_id}/claims/{claim_id}", response_model=ClaimView)
def edit_claim(event_id: str, claim_id: str, body: ClaimInput):
    with Session() as db:
        event = editorial.event_for_update(db, event_id, body.revision)
        result = clustering.edit_claim(db, event, claim_id, body)
        db.commit()
        return result


@router.post("/clusters/merge", response_model=ClusterOperationView, status_code=201)
def merge_events(body: MergeInput):
    with Session() as db:
        result = clustering.merge(db, body)
        db.commit()
        return result


@router.post("/events/{event_id}/split", response_model=ClusterOperationView, status_code=201)
def split_event(event_id: str, body: SplitInput):
    with Session() as db:
        result = clustering.split(db, event_id, body)
        db.commit()
        return result


@router.post("/clusters/{operation_id}/restore", response_model=ClusterOperationView)
def restore_cluster(operation_id: str, body: RestoreInput):
    with Session() as db:
        result = clustering.restore(db, operation_id, body)
        db.commit()
        return result
