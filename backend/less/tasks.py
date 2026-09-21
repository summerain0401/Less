from datetime import timedelta

from celery import Celery
from sqlalchemy import select

from less.attempts import finish_attempt
from less.collector import collect
from less.config import settings
from less.db import Session, lock
from less.models import AssistRun, ItemVersion, NormalizeRun, Source, SourceCheck, now
from less.pipeline import ai_state, execute_normalize, queue_normalize, recover_interrupted

app = Celery("less", broker=settings().redis_url)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    beat_schedule={"dispatch-durable-work": {"task": "less.dispatch", "schedule": 60.0}},
)


@app.task(name="less.collect")
def collect_task(check_id):
    collect(check_id)


@app.task(name="less.normalize")
def normalize_task(run_id):
    execute_normalize(run_id)


def schedule_due(at=None):
    at = at or now()
    with lock("scheduler") as acquired:
        if not acquired:
            return
        with Session() as db:
            for source in db.scalars(select(Source).where(Source.status == "active")):
                # Previous missed slots remain failures; only the current slot is eligible to run.
                while source.next_due_at <= at:
                    scheduled = source.next_due_at
                    source.next_due_at += timedelta(hours=source.interval_hours)
                    slot = scheduled.isoformat()
                    if not db.scalar(
                        select(SourceCheck.id).where(
                            SourceCheck.source_id == source.id, SourceCheck.slot == slot
                        )
                    ):
                        missed = source.next_due_at <= at
                        db.add(
                            SourceCheck(
                                source_id=source.id,
                                slot=slot,
                                scheduled_at=scheduled,
                                status="missed" if missed else "pending",
                                error="Scheduled collection was not executed" if missed else None,
                            )
                        )
            db.commit()


@app.task(name="less.dispatch")
def dispatch():
    schedule_due()
    recover_interrupted()
    with Session() as db:
        # Recover collectors interrupted for longer than their maximum bounded HTTP work.
        cutoff = now() - timedelta(seconds=(settings().max_items_per_check + 1) * 35 + 60)
        for check in db.scalars(
            select(SourceCheck).where(
                SourceCheck.status == "running", SourceCheck.started_at < cutoff
            )
        ):
            with lock(f"collect:{check.source_id}") as acquired:
                if acquired:
                    check.status = (
                        "retryable" if check.attempts < settings().max_attempts else "failed"
                    )
                    check.error = "Collector interrupted; recovered from durable state"
                    check.next_attempt_at = now()
                    finish_attempt(check)
        db.commit()
        for check in db.scalars(
            select(SourceCheck)
            .join(Source)
            .where(
                Source.status == "active",
                SourceCheck.status.in_(["pending", "retryable"]),
                SourceCheck.next_attempt_at <= now(),
            )
            .order_by(SourceCheck.scheduled_at)
            .limit(30)
        ):
            collect_task.delay(check.id)
        if settings().auto_normalize:
            # Also picks up saved items from partially successful collection attempts.
            versions = db.scalars(
                select(ItemVersion.id)
                .where(
                    ~select(NormalizeRun.id)
                    .where(NormalizeRun.version_id == ItemVersion.id)
                    .exists()
                )
                .limit(10)
            ).all()
            for version_id in versions:
                queue_normalize(version_id)
        if not ai_state(db).get("paused"):
            for pending in db.scalars(
                select(AssistRun)
                .where(
                    AssistRun.status.in_(["pending", "retryable", "budget_wait"]),
                    AssistRun.next_attempt_at <= now(),
                )
                .order_by(AssistRun.created_at)
                .limit(5)
            ):
                assist_task.delay(pending.id)
            for run in db.scalars(
                select(NormalizeRun)
                .where(
                    NormalizeRun.status.in_(["pending", "retryable", "budget_wait"]),
                    NormalizeRun.next_attempt_at <= now(),
                )
                .order_by(NormalizeRun.created_at)
                .limit(5)
            ):
                normalize_task.delay(run.id)


@app.task(name="less.assist")
def assist_task(run_id):
    from less.assist import execute

    execute(run_id)
