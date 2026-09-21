from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from less.db import Base


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str]
    node_url: Mapped[str] = mapped_column(Text)
    feed_url: Mapped[str] = mapped_column(Text)
    role: Mapped[str]
    topics: Mapped[list] = mapped_column(JSONB)
    coverage: Mapped[list] = mapped_column(JSONB)
    authority: Mapped[str] = mapped_column(Text)
    bias: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="active")
    interval_hours: Mapped[int] = mapped_column(default=6)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceCheck(Base):
    __tablename__ = "source_checks"
    __table_args__ = (UniqueConstraint("source_id", "slot"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    slot: Mapped[str]
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    attempts_log: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    item_count: Mapped[int] = mapped_column(default=0)
    feed_item_count: Mapped[int] = mapped_column(default=0, server_default="0")
    deferred_count: Mapped[int] = mapped_column(default=0, server_default="0")
    entry_batch: Mapped[list | None] = mapped_column(JSONB)
    new_versions: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    snapshot_path: Mapped[str | None]


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source_id", "url"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ItemVersion(Base):
    __tablename__ = "item_versions"
    __table_args__ = (UniqueConstraint("item_id", "content_hash"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"))
    content_hash: Mapped[str]
    title: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None]
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    text: Mapped[str] = mapped_column(Text)
    paragraphs: Mapped[list] = mapped_column(JSONB)
    snapshot_path: Mapped[str]
    acquisition: Mapped[str]
    limitations: Mapped[list] = mapped_column(JSONB, default=list)


class NormalizeRun(Base):
    __tablename__ = "normalize_runs"
    __table_args__ = (UniqueConstraint("version_id", "execution_key"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    version_id: Mapped[str] = mapped_column(ForeignKey("item_versions.id"))
    execution_key: Mapped[str]
    prompt_version: Mapped[str]
    model: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    attempts_log: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    output: Mapped[dict | None] = mapped_column(JSONB)
    raw_output: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class HumanReview(Base):
    __tablename__ = "human_reviews"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    version_id: Mapped[str] = mapped_column(ForeignKey("item_versions.id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("normalize_runs.id"))
    reviewer: Mapped[str]
    decision: Mapped[str]
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RuntimeState(Base):
    __tablename__ = "runtime_state"
    id: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str]
    object_id: Mapped[str]
    actor: Mapped[str]
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ValidationBatch(Base):
    __tablename__ = "validation_batches"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    actor: Mapped[str]
    seed: Mapped[str]
    target_count: Mapped[int]
    population_count: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ValidationSample(Base):
    __tablename__ = "validation_samples"
    __table_args__ = (UniqueConstraint("batch_id", "version_id"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("validation_batches.id"))
    version_id: Mapped[str] = mapped_column(ForeignKey("item_versions.id"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("normalize_runs.id"))
    position: Mapped[int]


class FieldReview(Base):
    __tablename__ = "field_reviews"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    sample_id: Mapped[str] = mapped_column(ForeignKey("validation_samples.id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("normalize_runs.id"))
    reviewer: Mapped[str]
    fields: Mapped[list] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkSession(Base):
    __tablename__ = "work_sessions"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    reviewer: Mapped[str]
    mode: Mapped[str]
    category: Mapped[str]
    source_ids: Mapped[list] = mapped_column(JSONB)
    criteria: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_count: Mapped[int | None]
    candidate_count: Mapped[int | None]
    selected_count: Mapped[int | None]
    note: Mapped[str | None] = mapped_column(Text)


class EditorialEvent(Base):
    __tablename__ = "editorial_events"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(Text)
    subject: Mapped[str]
    action: Mapped[str]
    object: Mapped[str] = mapped_column(Text)
    happened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_version: Mapped[str | None]
    scope: Mapped[str] = mapped_column(Text)
    lifecycle: Mapped[str] = mapped_column(default="active", server_default="active")
    redirected_to: Mapped[str | None] = mapped_column(ForeignKey("editorial_events.id"))
    revision: Mapped[int] = mapped_column(default=1)
    value_status: Mapped[str] = mapped_column(default="pending")
    quality_status: Mapped[str] = mapped_column(default="pending")
    decision: Mapped[str] = mapped_column(default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EventMember(Base):
    __tablename__ = "event_members"
    __table_args__ = (UniqueConstraint("event_id", "version_id"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey("editorial_events.id"))
    version_id: Mapped[str] = mapped_column(ForeignKey("item_versions.id"))
    paragraph_ids: Mapped[list] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(default=True)


class EventClaim(Base):
    __tablename__ = "event_claims"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey("editorial_events.id"))
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str]
    critical: Mapped[bool] = mapped_column(default=True)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    claim_id: Mapped[str] = mapped_column(ForeignKey("event_claims.id"))
    version_id: Mapped[str] = mapped_column(ForeignKey("item_versions.id"))
    paragraph_ids: Mapped[list] = mapped_column(JSONB)
    quote: Mapped[str] = mapped_column(Text)
    direction: Mapped[str]
    rationale: Mapped[str] = mapped_column(Text)
    source_root: Mapped[str] = mapped_column(Text)
    limitations: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="unchecked")
    checked_by: Mapped[str | None]
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EditorialReview(Base):
    __tablename__ = "editorial_reviews"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey("editorial_events.id"))
    revision: Mapped[int]
    gate: Mapped[str]
    status: Mapped[str]
    actor: Mapped[str]
    detail: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ClusterOperation(Base):
    __tablename__ = "cluster_operations"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    kind: Mapped[str]
    actor: Mapped[str]
    reason: Mapped[str] = mapped_column(Text)
    before: Mapped[dict] = mapped_column(JSONB)
    after_revisions: Mapped[dict] = mapped_column(JSONB)
    created_event_ids: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(default="applied")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restored_by: Mapped[str | None]
    restore_reason: Mapped[str | None] = mapped_column(Text)


class ClusterAuditBatch(Base):
    __tablename__ = "cluster_audit_batches"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    actor: Mapped[str]
    seed: Mapped[str]
    purpose: Mapped[str]
    method: Mapped[str]
    target_count: Mapped[int]
    population_events: Mapped[int]
    considered_events: Mapped[int]
    population_pairs: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ClusterAuditPair(Base):
    __tablename__ = "cluster_audit_pairs"
    __table_args__ = (UniqueConstraint("batch_id", "position"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("cluster_audit_batches.id"))
    position: Mapped[int]
    snapshot: Mapped[dict] = mapped_column(JSONB)
    prediction: Mapped[dict] = mapped_column(JSONB)


class ClusterAuditLabel(Base):
    __tablename__ = "cluster_audit_labels"
    __table_args__ = (UniqueConstraint("pair_id", "revision"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    pair_id: Mapped[str] = mapped_column(ForeignKey("cluster_audit_pairs.id"))
    revision: Mapped[int]
    actor: Mapped[str]
    verdict: Mapped[str]
    reason: Mapped[str] = mapped_column(Text)
    original_checked: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
