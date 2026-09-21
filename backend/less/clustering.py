"""Reversible clustering with stable claim/evidence IDs and optimistic revisions."""

from sqlalchemy import select

from less.editorial import invalidate
from less.models import ClusterOperation, EditorialEvent, EventClaim, EventMember, Evidence, now


def locked_events(db, expected, active=True):
    rows = db.scalars(
        select(EditorialEvent)
        .where(EditorialEvent.id.in_(expected))
        .order_by(EditorialEvent.id)
        .with_for_update()
    ).all()
    events = {e.id: e for e in rows}
    if set(events) != set(expected):
        raise ValueError("有事件不存在")
    if any(e.revision != expected[e.id] for e in rows):
        raise ValueError("事件已修改，请刷新聚类方案后再操作")
    if active and any(e.lifecycle != "active" for e in rows):
        raise ValueError("只能对未合并、未归档的事件操作")
    return events


def snapshot(db, event_ids):
    result = {}
    for eid in sorted(event_ids):
        event = db.get(EditorialEvent, eid)
        members = db.scalars(select(EventMember).where(EventMember.event_id == eid)).all()
        claims = db.scalars(select(EventClaim).where(EventClaim.event_id == eid)).all()
        evidence = db.scalars(
            select(Evidence).where(Evidence.claim_id.in_([c.id for c in claims]))
        ).all()
        result[eid] = {
            "lifecycle": event.lifecycle,
            "redirected_to": event.redirected_to,
            "members": [
                {
                    "id": m.id,
                    "version_id": m.version_id,
                    "paragraph_ids": m.paragraph_ids,
                    "active": m.active,
                }
                for m in members
            ],
            "claim_ids": [c.id for c in claims],
            "evidence": [
                {
                    "id": e.id,
                    "status": e.status,
                    "checked_by": e.checked_by,
                    "checked_at": e.checked_at.isoformat() if e.checked_at else None,
                }
                for e in evidence
            ],
        }
    return result


def clear_evidence(db, claim_ids):
    for evidence in db.scalars(select(Evidence).where(Evidence.claim_id.in_(claim_ids))):
        # A changed context also invalidates former rejections, not just approvals.
        evidence.status = "needs_review"
        evidence.checked_by = evidence.checked_at = None


def copy_member(db, source, target_id):
    target = db.scalar(
        select(EventMember).where(
            EventMember.event_id == target_id, EventMember.version_id == source.version_id
        )
    )
    if target:
        target.paragraph_ids = sorted(set(target.paragraph_ids) | set(source.paragraph_ids))
        target.active = True
    else:
        db.add(
            EventMember(
                event_id=target_id,
                version_id=source.version_id,
                paragraph_ids=list(source.paragraph_ids),
                active=True,
            )
        )
    db.flush()


def finish(db, kind, actor, reason, events, before, created=None):
    operation = ClusterOperation(
        kind=kind,
        actor=actor,
        reason=reason,
        before=before,
        after_revisions={},
        created_event_ids=created or [],
    )
    db.add(operation)
    db.flush()
    for event in events.values():
        invalidate(
            db,
            event,
            actor,
            f"cluster-{kind}",
            {"operation_id": operation.id, "event_ids": sorted(events), "reason": reason},
        )
    operation.after_revisions = {e.id: e.revision for e in events.values()}
    db.flush()
    return operation


def merge(db, body):
    expected = {e.id: e.revision for e in body.events}
    if len(expected) != len(body.events) or body.target_id not in expected or len(expected) < 2:
        raise ValueError("合并需包含目标与至少一个其他事件，且不可重复")
    events = locked_events(db, expected)
    before = snapshot(db, events)
    for source_id, source in events.items():
        if source_id == body.target_id:
            continue
        for member in db.scalars(
            select(EventMember).where(
                EventMember.event_id == source_id, EventMember.active.is_(True)
            )
        ):
            copy_member(db, member, body.target_id)
            member.active = False
        for claim in db.scalars(select(EventClaim).where(EventClaim.event_id == source_id)):
            claim.event_id = body.target_id
        source.lifecycle, source.redirected_to = "merged", body.target_id
    clear_evidence(db, [cid for s in before.values() for cid in s["claim_ids"]])
    return finish(db, "merge", body.actor, body.reason, events, before)


def split(db, source_id, body):
    events = locked_events(db, {source_id: body.revision})
    if len(set(body.member_ids)) != len(body.member_ids) or len(set(body.claim_ids)) != len(
        body.claim_ids
    ):
        raise ValueError("材料或陈述选择不可重复")
    members = db.scalars(
        select(EventMember).where(
            EventMember.id.in_(body.member_ids),
            EventMember.event_id == source_id,
            EventMember.active.is_(True),
        )
    ).all()
    claims = db.scalars(
        select(EventClaim).where(
            EventClaim.id.in_(body.claim_ids), EventClaim.event_id == source_id
        )
    ).all()
    if len(members) != len(body.member_ids) or len(claims) != len(body.claim_ids):
        raise ValueError("选择的材料或陈述不属于当前有效事件")
    version_ids = {m.version_id for m in members}
    evidence = db.scalars(select(Evidence).where(Evidence.claim_id.in_(body.claim_ids))).all()
    if any(e.version_id not in version_ids for e in evidence):
        raise ValueError("移动陈述时须同时选择它引用的全部原文版本")
    target = EditorialEvent(**body.target.model_dump())
    db.add(target)
    db.flush()
    events[target.id] = target
    before = snapshot(db, events)
    for member in members:
        copy_member(db, member, target.id)
        needed = db.scalar(
            select(Evidence.id)
            .join(EventClaim)
            .where(
                EventClaim.event_id == source_id,
                ~EventClaim.id.in_(body.claim_ids),
                Evidence.version_id == member.version_id,
            )
        )
        # An Item may discuss several events; keep the original link when still cited there.
        if not needed:
            member.active = False
    for claim in claims:
        claim.event_id = target.id
    clear_evidence(db, [cid for s in before.values() for cid in s["claim_ids"]])
    return finish(db, "split", body.actor, body.reason, events, before, [target.id])


def restore(db, operation_id, body):
    operation = db.scalar(
        select(ClusterOperation).where(ClusterOperation.id == operation_id).with_for_update()
    )
    if not operation or operation.status != "applied":
        raise ValueError("聚类操作不存在或已恢复")
    events = locked_events(db, operation.after_revisions, active=False)
    for eid, previous in operation.before.items():
        event = events[eid]
        event.lifecycle, event.redirected_to = previous["lifecycle"], previous["redirected_to"]
        original = {m["id"]: m for m in previous["members"]}
        for member in db.scalars(select(EventMember).where(EventMember.event_id == eid)):
            if member.id in original:
                member.paragraph_ids = original[member.id]["paragraph_ids"]
                member.active = original[member.id]["active"]
            else:
                member.active = False
        for claim_id in previous["claim_ids"]:
            db.get(EventClaim, claim_id).event_id = eid
        clear_evidence(db, previous["claim_ids"])
    for eid in operation.created_event_ids:
        events[eid].lifecycle = "retired"
        events[eid].redirected_to = next(i for i in events if i not in operation.created_event_ids)
    operation.status, operation.restored_at, operation.restored_by = "restored", now(), body.actor
    operation.restore_reason = body.reason
    for event in events.values():
        invalidate(
            db,
            event,
            body.actor,
            "cluster-restore",
            {"operation_id": operation.id, "reason": body.reason},
        )
    return operation


def edit_claim(db, event, claim_id, body):
    claim = db.get(EventClaim, claim_id)
    if not claim or claim.event_id != event.id:
        raise ValueError("陈述不属于当前事件")
    previous = {"text": claim.text, "kind": claim.kind, "critical": claim.critical}
    evidence = db.scalars(select(Evidence).where(Evidence.claim_id == claim.id)).all()
    checks = [
        {
            "id": e.id,
            "status": e.status,
            "checked_by": e.checked_by,
            "checked_at": e.checked_at.isoformat() if e.checked_at else None,
        }
        for e in evidence
    ]
    claim.text, claim.kind, claim.critical = body.text, body.kind, body.critical
    clear_evidence(db, [claim.id])
    invalidate(
        db,
        event,
        body.actor,
        "claim-edit",
        {
            "claim_id": claim.id,
            "previous": previous,
            "previous_evidence_checks": checks,
            "reason": body.reason,
        },
    )
    return claim
