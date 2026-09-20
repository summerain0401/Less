"""Human validation and truthful operational metrics; no automatic approvals."""

import random
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select

from less.budget import daily_usage, day_bounds
from less.config import settings
from less.db import Session, lock
from less.models import (
    AuditLog,
    FieldReview,
    Item,
    ItemVersion,
    NormalizeRun,
    Source,
    SourceCheck,
    ValidationBatch,
    ValidationSample,
    WorkSession,
    now,
    uid,
)
from less.pipeline import queue_normalize


def create_batch(target: int, actor: str):
    with Session() as db:
        # Freeze one latest version per distinct Item before any result-based filtering.
        versions = db.execute(
            select(ItemVersion, Item.source_id)
            .join(Item)
            .order_by(ItemVersion.captured_at.desc(), ItemVersion.id)
        ).all()
        seen, groups = set(), defaultdict(list)
        for version, source_id in versions:
            if version.item_id not in seen:
                groups[source_id].append(version)
                seen.add(version.item_id)
        if not seen:
            raise ValueError("尚无材料，请先采集")
        seed = uid()
        rng = random.Random(seed)
        sources = sorted(groups)
        rng.shuffle(sources)
        for rows in groups.values():
            rng.shuffle(rows)
        chosen = []
        while len(chosen) < min(target, len(seen)):
            for source_id in sources:
                if groups[source_id] and len(chosen) < target:
                    chosen.append(groups[source_id].pop())
        batch = ValidationBatch(
            actor=actor, seed=seed, target_count=target, population_count=len(seen)
        )
        db.add(batch)
        db.flush()
        for index, version in enumerate(chosen):
            run = db.scalar(
                select(NormalizeRun)
                .where(NormalizeRun.version_id == version.id, NormalizeRun.status == "succeeded")
                .order_by(NormalizeRun.created_at.desc())
            )
            db.add(
                ValidationSample(
                    batch_id=batch.id,
                    version_id=version.id,
                    run_id=run.id if run else None,
                    position=index,
                )
            )
        db.add(
            AuditLog(
                action="create-validation-batch",
                object_id=batch.id,
                actor=actor,
                detail={
                    "seed": seed,
                    "target": target,
                    "population": len(seen),
                    "sampled": len(chosen),
                },
            )
        )
        db.commit()
        return batch.id


def prepare_batch(batch_id: str, actor: str, limit: int):
    with lock(f"validation-batch:{batch_id}") as acquired:
        if not acquired:
            raise ValueError("该批次正在准备，请稍后重试")
        with Session() as db:
            if not db.get(ValidationBatch, batch_id):
                raise ValueError("抽查批次不存在")
            samples = db.scalars(
                select(ValidationSample)
                .where(ValidationSample.batch_id == batch_id, ValidationSample.run_id.is_(None))
                .order_by(ValidationSample.position)
                .limit(limit)
            ).all()
            for sample in samples:
                sample.run_id = queue_normalize(sample.version_id)
            db.add(
                AuditLog(
                    action="prepare-validation-batch",
                    object_id=batch_id,
                    actor=actor,
                    detail={"assigned_runs": len(samples)},
                )
            )
            db.commit()
            return len(samples)


def sample_fields(version, run):
    def field(key, label, value):
        return {
            "key": key,
            "label": label,
            "value": value,
            "allows_unknown": value is None or value == [] or value == "",
        }

    fields = [
        field("title", "标题", version.title),
        field("author", "作者", version.author),
        field(
            "published_at",
            "发布时间",
            version.published_at.isoformat() if version.published_at else None,
        ),
        field("body", "正文完整性与导航噪声", "对照保存快照及原始页面"),
    ]
    if not run or run.status != "succeeded":
        return fields
    output = run.output
    fields.extend(
        [
            field("summary", "摘要是否符合原文", output["summary"]),
            field("language", "原文语言", output["language"]),
        ]
    )
    for i, claim in enumerate(output["claims"]):
        fields.extend(
            [
                field(f"claim:{i}", f"陈述 {i + 1} 的归属、条件与含义", claim["text"]),
                field(f"quote:{i}", f"陈述 {i + 1} 的引用与定位", claim["quote"]),
            ]
        )
    for i, entity in enumerate(output["entities"]):
        fields.append(
            field(
                f"entity:{i}", f"实体 {i + 1} 的身份与分类", f"{entity['name']} · {entity['kind']}"
            )
        )
    fields.append(field("topics", "主题归类", output["topics"]))
    fields.append(field("uncertainties", "缺失信息与不确定性", output["uncertainties"]))
    return fields


def save_field_review(sample_id, run_id, reviewer, fields, note, original_checked):
    with Session() as db:
        sample = db.scalar(
            select(ValidationSample).where(ValidationSample.id == sample_id).with_for_update()
        )
        if not sample or not sample.run_id:
            raise ValueError("样本尚未绑定提取结果")
        if sample.run_id != run_id:
            raise ValueError("样本已重新提取，请刷新后核对当前结果")
        run = db.get(NormalizeRun, sample.run_id)
        if run.status != "succeeded":
            raise ValueError("提取尚未成功，不能记录字段准确率")
        if not original_checked:
            raise ValueError("需要先对照原始材料")
        expected = {f["key"]: f for f in sample_fields(db.get(ItemVersion, sample.version_id), run)}
        keys = [f["key"] for f in fields]
        if len(keys) != len(set(keys)) or set(keys) != set(expected):
            raise ValueError("请完整提交本次样本的字段清单，不得重复或遗漏字段")
        if not any(f["verdict"] != "not_checked" for f in fields):
            raise ValueError("至少需要核查一个字段")
        for field in fields:
            if (
                field["verdict"] == "unknown_correct"
                and not expected[field["key"]]["allows_unknown"]
            ):
                raise ValueError("只有缺失值才能标记为正确保留未知")
            if field["verdict"] == "incorrect" and not field["note"].strip():
                raise ValueError("错误字段需要注明问题及修正依据")
        record = FieldReview(
            sample_id=sample_id, run_id=run.id, reviewer=reviewer, fields=fields, note=note
        )
        db.add(record)
        db.commit()
        return record


def quality_totals(db):
    # One latest human assessment per distinct Item, even across versions/batches.
    records = db.execute(
        select(FieldReview, ItemVersion.item_id)
        .join(NormalizeRun, NormalizeRun.id == FieldReview.run_id)
        .join(ItemVersion, ItemVersion.id == NormalizeRun.version_id)
        .order_by(FieldReview.created_at.desc(), FieldReview.id)
    ).all()
    seen, correct, checked, fully_reviewed, critical_errors = set(), 0, 0, 0, 0
    for review, item_id in records:
        if item_id in seen:
            continue
        seen.add(item_id)
        checked += sum(f["verdict"] != "not_checked" for f in review.fields)
        correct += sum(f["verdict"] in ("correct", "unknown_correct") for f in review.fields)
        fully_reviewed += all(f["verdict"] != "not_checked" for f in review.fields)
        critical_errors += sum(f["verdict"] == "incorrect" for f in review.fields)
    return {
        "reviewed_samples": len(seen),
        "fully_reviewed_samples": fully_reviewed,
        "checked_fields": checked,
        "correct_fields": correct,
        "incorrect_fields": critical_errors,
        "accuracy": correct / checked if checked else None,
    }


def report(day: date, at=None):
    at = at or now()
    start, end = day_bounds(day)
    cutoff = min(at, end)
    with Session() as db:
        checks = db.scalars(
            select(SourceCheck).where(
                SourceCheck.scheduled_at >= start, SourceCheck.scheduled_at < cutoff
            )
        ).all()
        planned = [c for c in checks if not c.slot.startswith("manual:")]
        manual = [c for c in checks if c.slot.startswith("manual:")]

        def succeeded(c):
            return c.status == "succeeded" and c.finished_at is not None and c.finished_at <= cutoff

        success = sum(succeeded(c) for c in planned)
        # An offline scheduler must not make the denominator look healthier.
        missing_by_source = Counter()
        for source in db.scalars(select(Source).where(Source.status == "active")):
            due = source.next_due_at
            if due < start:
                steps = (start - due).total_seconds() // (source.interval_hours * 3600)
                due += timedelta(hours=steps * source.interval_hours)
                if due < start:
                    due += timedelta(hours=source.interval_hours)
            while due < cutoff:
                missing_by_source[source.id] += 1
                due += timedelta(hours=source.interval_hours)
        unrecorded = sum(missing_by_source.values())
        total = len(planned) + unrecorded
        completed_runs = db.scalars(
            select(NormalizeRun).where(
                NormalizeRun.finished_at >= start,
                NormalizeRun.finished_at < cutoff,
                NormalizeRun.status == "succeeded",
            )
        ).all()
        tokens = sum(
            (r.metadata_.get("usage") or {}).get("input_tokens", 0)
            + (r.metadata_.get("usage") or {}).get("output_tokens", 0)
            for r in completed_runs
        )
        sessions = db.scalars(
            select(WorkSession).where(
                WorkSession.started_at < cutoff,
                (WorkSession.ended_at.is_(None)) | (WorkSession.ended_at >= start),
            )
        ).all()
        durations = Counter()
        for session in sessions:
            if session.ended_at:
                durations[session.mode] += max(
                    0,
                    (
                        min(session.ended_at, cutoff) - max(session.started_at, start)
                    ).total_seconds(),
                )
        source_rows = []
        for source in db.scalars(select(Source).order_by(Source.name)):
            owned = [c for c in planned if c.source_id == source.id]
            source_rows.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "status": source.status,
                    "planned": len(owned) + missing_by_source[source.id],
                    "succeeded": sum(succeeded(c) for c in owned),
                    "last_success_at": source.last_success_at,
                }
            )
        raw_count = db.scalar(
            select(func.count())
            .select_from(Item)
            .where(Item.created_at >= start, Item.created_at < cutoff)
        )
        version_count = db.scalar(
            select(func.count())
            .select_from(ItemVersion)
            .where(ItemVersion.captured_at >= start, ItemVersion.captured_at < cutoff)
        )
        first_check = db.scalar(
            select(func.min(SourceCheck.scheduled_at)).where(
                ~SourceCheck.slot.startswith("manual:")
            )
        )
        baseline_count = db.scalar(
            select(func.count())
            .select_from(WorkSession)
            .where(
                WorkSession.mode == "baseline",
                WorkSession.category == "screening",
                WorkSession.read_count > 0,
                WorkSession.ended_at.is_not(None),
            )
        )
        return {
            "date": day,
            "timezone": settings().timezone,
            "window_start": start,
            "window_end": end,
            "as_of": cutoff,
            "closed": at >= end,
            "planned": total,
            "succeeded": success,
            "success_rate": success / total if total else None,
            "unrecorded_due": unrecorded,
            "manual_checks": len(manual),
            "status_counts": dict(
                Counter(
                    "unfinished_at_cutoff" if c.finished_at and c.finished_at > cutoff else c.status
                    for c in planned
                )
            ),
            "raw_items": raw_count,
            "versions": version_count,
            "normalized": len(completed_runs),
            "observed_tokens": tokens,
            "cost": None,
            "cost_note": "仅统计成功任务返回的 token；实际费用及失败任务用量可能未知",
            "budget": daily_usage(db, day),
            "quality": quality_totals(db),
            "baseline_sessions": baseline_count,
            "work_seconds": dict(durations),
            "active_sessions": sum(s.ended_at is None for s in sessions),
            "observation_hours": max(0, (cutoff - first_check).total_seconds() / 3600)
            if first_check
            else 0,
            "sources": source_rows,
            "later_stages": {"events": None, "candidates": None, "published_briefs": None},
        }


def start_session(reviewer, mode, category, source_ids, criteria):
    with lock(f"work-session:{reviewer}") as acquired:
        if not acquired:
            raise ValueError("计时操作正在进行，请稍后重试")
        with Session() as db:
            if db.scalar(
                select(WorkSession.id).where(
                    WorkSession.reviewer == reviewer, WorkSession.ended_at.is_(None)
                )
            ):
                raise ValueError("请先结束已有计时，避免重叠计算")
            known = set(db.scalars(select(Source.id).where(Source.id.in_(source_ids))))
            if known != set(source_ids) or len(source_ids) != len(set(source_ids)):
                raise ValueError("来源范围无效或重复")
            record = WorkSession(
                reviewer=reviewer,
                mode=mode,
                category=category,
                source_ids=source_ids,
                criteria=criteria,
            )
            db.add(record)
            db.commit()
            return record


def stop_session(session_id, read_count, candidate_count, selected_count, note):
    if not 0 <= selected_count <= candidate_count <= read_count:
        raise ValueError("入选数不能大于候选数，候选数不能大于阅读量")
    with Session() as db:
        record = db.scalar(
            select(WorkSession).where(WorkSession.id == session_id).with_for_update()
        )
        if not record:
            raise ValueError("计时记录不存在")
        if record.ended_at:
            raise ValueError("计时已结束，原记录不可覆盖")
        record.ended_at = now()
        record.read_count, record.candidate_count, record.selected_count = (
            read_count,
            candidate_count,
            selected_count,
        )
        record.note = note
        db.commit()
        return record
