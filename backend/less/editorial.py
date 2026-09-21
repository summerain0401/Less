"""Versioned event editing and independent value/evidence gates."""

from sqlalchemy import select

from less.models import (
    AuditLog,
    Brief,
    BriefReview,
    EditorialEvent,
    EditorialReview,
    EventClaim,
    EventMember,
    Evidence,
    ItemVersion,
    Signal,
    SignalEvidence,
    SignalRecord,
    now,
)


def event_for_update(db, event_id, revision):
    event = db.scalar(select(EditorialEvent).where(EditorialEvent.id == event_id).with_for_update())
    if not event:
        raise ValueError("事件不存在")
    if event.lifecycle != "active":
        raise ValueError("事件已合并或归档，请查看映射到的事件或恢复聚类操作")
    if event.revision != revision:
        raise ValueError("事件内容已更新，请刷新后再操作")
    return event


def audit(db, event, actor, action, detail):
    db.add(
        AuditLog(
            action=action,
            object_id=event.id,
            actor=actor,
            detail={"revision": event.revision, **detail},
        )
    )


def invalidate(db, event, actor, action, detail):
    event.revision += 1
    event.value_status = event.quality_status = event.decision = "pending"
    event.updated_at = now()
    for brief in db.scalars(select(Brief).where(Brief.event_id == event.id).with_for_update()):
        if brief.status != "withdrawn":
            brief.status = "needs_review"
            db.add(
                BriefReview(
                    brief_id=brief.id,
                    revision=brief.revision,
                    action="source_changed",
                    actor=actor,
                    reason=f"事件修订 {event.revision}: {action}；{detail.get('reason', '')}",
                )
            )
    linked_signals = select(SignalEvidence.signal_id).where(
        SignalEvidence.event_id == event.id, SignalEvidence.active.is_(True)
    )
    for signal in db.scalars(
        select(Signal).where(Signal.id.in_(linked_signals)).order_by(Signal.id).with_for_update()
    ):
        signal.revision += 1
        signal.needs_review = True
        db.add(
            SignalRecord(
                signal_id=signal.id,
                revision=signal.revision,
                kind="source_changed",
                actor=actor,
                reason=f"关联事件修订 {event.revision}: {action}",
                detail={"event_id": event.id, "event_revision": event.revision},
            )
        )
    audit(db, event, actor, action, detail)


def check_location(db, version_id, paragraph_ids, quote=None):
    version = db.get(ItemVersion, version_id)
    if not version:
        raise ValueError("原文版本不存在")
    paragraphs = {p["id"]: p["text"] for p in version.paragraphs}
    if (
        not paragraph_ids
        or len(set(paragraph_ids)) != len(paragraph_ids)
        or any(p not in paragraphs for p in paragraph_ids)
    ):
        raise ValueError("原文段落定位无效或重复")
    if quote is not None and not any(quote in paragraphs[p] for p in paragraph_ids):
        raise ValueError("摘录必须逐字存在于指定的原文段落中")
    return version


def link_member(db, event, body):
    check_location(db, body.version_id, body.paragraph_ids)
    member = db.scalar(
        select(EventMember).where(
            EventMember.event_id == event.id, EventMember.version_id == body.version_id
        )
    )
    if member and member.active and member.paragraph_ids == body.paragraph_ids:
        return member
    # Existing evidence must stay locatable after changing membership paragraphs.
    claims = select(EventClaim.id).where(EventClaim.event_id == event.id)
    evidence = db.scalars(
        select(Evidence).where(
            Evidence.claim_id.in_(claims), Evidence.version_id == body.version_id
        )
    ).all()
    if any(not set(e.paragraph_ids) <= set(body.paragraph_ids) for e in evidence):
        raise ValueError("新的关联范围必须包含已有证据的段落")
    previous = {"active": member.active, "paragraph_ids": member.paragraph_ids} if member else None
    if not member:
        member = EventMember(
            event_id=event.id, version_id=body.version_id, paragraph_ids=body.paragraph_ids
        )
        db.add(member)
    else:
        member.active, member.paragraph_ids = True, body.paragraph_ids
    invalidate(
        db,
        event,
        body.actor,
        "event-link",
        {
            "version_id": body.version_id,
            "previous": previous,
            "paragraph_ids": body.paragraph_ids,
            "reason": body.reason,
        },
    )
    return member


def unlink_member(db, event, member_id, actor, reason):
    member = db.get(EventMember, member_id)
    if not member or member.event_id != event.id or not member.active:
        raise ValueError("有效材料关联不存在")
    affected = db.scalars(
        select(Evidence)
        .join(EventClaim)
        .where(EventClaim.event_id == event.id, Evidence.version_id == member.version_id)
    ).all()
    # Preserve the evidence and decision history; detached evidence cannot pass the gate.
    for evidence in affected:
        evidence.status = "needs_review"
        evidence.checked_by = evidence.checked_at = None
    member.active = False
    invalidate(
        db,
        event,
        actor,
        "event-unlink",
        {
            "member_id": member_id,
            "version_id": member.version_id,
            "reason": reason,
            "affected_evidence": [e.id for e in affected],
        },
    )


def create_evidence(db, event, body):
    claim = db.get(EventClaim, body.claim_id)
    if not claim or claim.event_id != event.id:
        raise ValueError("陈述不属于当前事件")
    check_location(db, body.version_id, body.paragraph_ids, body.quote)
    member = db.scalar(
        select(EventMember).where(
            EventMember.event_id == event.id,
            EventMember.version_id == body.version_id,
            EventMember.active.is_(True),
        )
    )
    if not member or not set(body.paragraph_ids) <= set(member.paragraph_ids):
        raise ValueError("请先将对应原文段落关联到事件")
    evidence = Evidence(**body.model_dump(exclude={"actor", "revision", "reason"}))
    db.add(evidence)
    db.flush()
    invalidate(
        db, event, body.actor, "evidence-add", {"evidence_id": evidence.id, "reason": body.reason}
    )
    return evidence


def review_evidence(db, event, evidence_id, body):
    evidence = db.get(Evidence, evidence_id)
    claim = db.get(EventClaim, evidence.claim_id) if evidence else None
    if not claim or claim.event_id != event.id:
        raise ValueError("证据不属于当前事件")
    if body.status == "verified":
        member = db.scalar(
            select(EventMember).where(
                EventMember.event_id == event.id,
                EventMember.version_id == evidence.version_id,
                EventMember.active.is_(True),
            )
        )
        if not member or not set(evidence.paragraph_ids) <= set(member.paragraph_ids):
            raise ValueError("证据原文已取消关联，需要先恢复关联")
        if not body.original_checked:
            raise ValueError("核验证据前必须对照原文")
    previous = {
        "status": evidence.status,
        "checked_by": evidence.checked_by,
        "checked_at": evidence.checked_at.isoformat() if evidence.checked_at else None,
    }
    evidence.status, evidence.checked_by, evidence.checked_at = body.status, body.actor, now()
    invalidate(
        db,
        event,
        body.actor,
        "evidence-review",
        {"evidence_id": evidence.id, "previous": previous, **body.model_dump(exclude={"revision"})},
    )
    return evidence


def value_review(db, event, body):
    # Important OR Useful. Neither is an evidence-quality score.
    if body.status == "passed" and not (body.important or body.useful):
        raise ValueError("至少一条 Important 或 Useful 路径必须成立")
    if body.important and not body.important_reason.strip():
        raise ValueError("需要具体的重要性理由")
    if body.useful and not body.useful_reason.strip():
        raise ValueError("需要具体的实用性理由")
    if body.status == "rejected" and (body.important or body.useful):
        raise ValueError("存在已认可的价值路径时不能以价值不足淘汰")
    event.value_status, event.decision = body.status, "pending"
    record = EditorialReview(
        event_id=event.id,
        revision=event.revision,
        gate="value",
        status=body.status,
        actor=body.actor,
        detail=body.model_dump(exclude={"actor", "revision"}),
    )
    db.add(record)
    return record


def quality_review(db, event, body):
    claims = db.scalars(
        select(EventClaim).where(EventClaim.event_id == event.id, EventClaim.critical.is_(True))
    ).all()
    evidence = db.scalars(
        select(Evidence).join(EventClaim).where(EventClaim.event_id == event.id)
    ).all()
    if body.status == "passed":
        if body.gaps:
            raise ValueError("关键证据缺口未解决，不能通过质量门")
        if not claims:
            raise ValueError("请先列出决定标题和结论的关键陈述")
        for claim in claims:
            related = [e for e in evidence if e.claim_id == claim.id]
            if not any(e.status == "verified" and e.direction == "supporting" for e in related):
                raise ValueError("每条关键陈述都需要已核验的支持证据；背景不能代替支持")
            for e in related:
                if (
                    e.direction == "counter"
                    and e.status != "rejected"
                    and not body.conflict_resolutions.get(e.id, "").strip()
                ):
                    raise ValueError("反面或限制证据必须逐项说明处理结果，不能忽略冲突")
        known = {e.id for e in evidence if e.direction == "counter"}
        if set(body.conflict_resolutions) - known:
            raise ValueError("冲突处理引用了不属于本事件的反面证据")
    elif not body.gaps:
        raise ValueError("待核实或不通过时必须列出证据缺口")
    event.quality_status, event.decision = body.status, "pending"
    record = EditorialReview(
        event_id=event.id,
        revision=event.revision,
        gate="quality",
        status=body.status,
        actor=body.actor,
        detail=body.model_dump(exclude={"actor", "revision"}),
    )
    db.add(record)
    return record


def decide(db, event, body):
    if body.status == "selected" and (
        event.value_status != "passed" or event.quality_status != "passed"
    ):
        raise ValueError("通过 Value Gate 和 Quality Gate 后才能入选")
    event.decision = body.status
    record = EditorialReview(
        event_id=event.id,
        revision=event.revision,
        gate="decision",
        status=body.status,
        actor=body.actor,
        detail={"reason": body.reason},
    )
    db.add(record)
    return record
