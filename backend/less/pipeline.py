import hashlib
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select

from less.ai import PROMPT_VERSION, AIError, CodexCliExecutor, validate_output
from less.attempts import finish_attempt, start_attempt
from less.budget import daily_usage, local_today
from less.config import settings
from less.db import Session, lock
from less.models import AuditLog, Item, ItemVersion, NormalizeRun, RuntimeState, now


def queue_normalize(version_id: str, force: bool = False) -> str:
    from less.models import uid

    key = hashlib.sha256(f"{PROMPT_VERSION}:{settings().codex_model}".encode()).hexdigest()
    if force:
        key = uid()
    with lock(f"normalize-queue:{version_id}") as acquired:
        if not acquired:
            raise ValueError("Normalization is already being queued; try again")
        with Session() as db:
            if not db.get(ItemVersion, version_id):
                raise ValueError("Unknown Item version")
            run = db.scalar(
                select(NormalizeRun).where(
                    NormalizeRun.version_id == version_id, NormalizeRun.execution_key == key
                )
            )
            if not run:
                run = NormalizeRun(
                    version_id=version_id,
                    execution_key=key,
                    prompt_version=PROMPT_VERSION,
                    model=settings().codex_model or "cli-default",
                )
                db.add(run)
                db.commit()
            return run.id


def ai_state(db) -> dict:
    state = db.get(RuntimeState, "ai")
    return state.value if state else {"paused": False, "reason": None}


def resume_ai(actor: str):
    with Session() as db:
        state = db.get(RuntimeState, "ai")
        if state:
            state.value = {"paused": False, "reason": None}
        for run in db.scalars(select(NormalizeRun).where(NormalizeRun.status == "blocked")):
            run.status, run.next_attempt_at = "pending", now()
            run.attempts = 0
        db.add(AuditLog(action="resume-ai", object_id="ai", actor=actor))
        db.commit()


def execute_normalize(run_id: str, executor=None):
    # Also enforces one AI invocation when several workers are accidentally started.
    with lock("ai-executor") as acquired:
        if not acquired:
            return
        with Session() as db:
            if ai_state(db).get("paused"):
                return
            run = db.get(NormalizeRun, run_id)
            if run is None or run.status not in ("pending", "retryable", "budget_wait"):
                return
            if run.next_attempt_at > now():
                return
            budget = daily_usage(db, local_today())
            if budget["remaining"] == 0:
                run.status = "budget_wait"
                run.next_attempt_at = budget["resets_at"]
                run.error = "Daily AI attempt limit reached; waiting for the next local day"
                db.commit()
                return
            version = db.get(ItemVersion, run.version_id)
            item = db.get(Item, version.item_id)
            material = {
                "item_id": item.id,
                "version_id": version.id,
                "url": item.url,
                "title": version.title,
                "author": version.author,
                "published_at": str(version.published_at) if version.published_at else None,
                "paragraphs": version.paragraphs,
                "limitations": version.limitations,
            }
            run.status, run.started_at, run.error = "running", now(), None
            run.attempts += 1
            start_attempt(run)
            db.commit()
            try:
                config = settings().model_copy(
                    update={"codex_model": "" if run.model == "cli-default" else run.model}
                )
                result = (executor or CodexCliExecutor(config)).execute(material)
                run.raw_output, run.metadata_ = result.raw, result.metadata
                db.commit()  # Preserve invalid model output for inspection, not as approved data.
                normalized = validate_output(result.raw, version.paragraphs)
                run.output, run.status = normalized.model_dump(), "succeeded"
            except (ValueError, ValidationError) as exc:
                run.status = "failed"
                run.error = f"Invalid structured output: {str(exc)[:1500]}"
            except AIError as exc:
                run.error, run.metadata_ = str(exc), exc.metadata
                if exc.code in ("auth", "quota", "unavailable"):
                    run.status = "blocked"
                    state = db.get(RuntimeState, "ai")
                    if not state:
                        state = RuntimeState(id="ai")
                        db.add(state)
                    state.value = {"paused": True, "reason": str(exc), "code": exc.code}
                else:
                    run.status = "retryable" if run.attempts < settings().max_attempts else "failed"
                    run.next_attempt_at = now() + timedelta(minutes=run.attempts * 2)
            run.finished_at = now()
            finish_attempt(run)
            db.commit()


def recover_interrupted():
    """Recover abandoned runs only when no executor currently holds the advisory lock."""
    with lock("ai-executor") as acquired:
        if not acquired:
            return
        with Session() as db:
            cutoff = now() - timedelta(seconds=settings().codex_timeout + 60)
            runs = db.scalars(
                select(NormalizeRun).where(
                    NormalizeRun.status == "running", NormalizeRun.started_at < cutoff
                )
            )
            for run in runs:
                run.status = "retryable" if run.attempts < settings().max_attempts else "failed"
                run.error, run.finished_at = (
                    "Executor interrupted; recovered from durable state",
                    now(),
                )
                run.next_attempt_at = now()
                finish_attempt(run)
            db.commit()
