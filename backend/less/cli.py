import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from less.config import ROOT
from less.db import Session
from less.models import Source, SourceCheck, uid


def seed(path: Path, update: bool = False):
    records = json.loads(path.read_text())
    with Session() as db:
        added = 0
        for record in records:
            if record["interval_hours"] < 1:
                raise ValueError("Source interval must be at least one hour")
            existing = db.get(Source, record["id"])
            if not existing:
                db.add(Source(**record))
                added += 1
            elif update:
                from less.models import AuditLog

                allowed = {
                    "name",
                    "node_url",
                    "feed_url",
                    "role",
                    "topics",
                    "coverage",
                    "authority",
                    "bias",
                    "interval_hours",
                    "status",
                }
                changed = {
                    k: v for k, v in record.items() if k in allowed and getattr(existing, k) != v
                }
                for key, value in changed.items():
                    setattr(existing, key, value)
                if changed:
                    db.add(
                        AuditLog(
                            action="source-import-update",
                            object_id=existing.id,
                            actor="local-cli",
                            detail=changed,
                        )
                    )
        db.commit()
    print(json.dumps({"registered": added, "note": "Registration does not prove connectivity"}))


def manual_collect(source_id):
    from less.collector import collect

    with Session() as db:
        sources = db.scalars(select(Source).where(Source.status == "active")).all()
        if source_id != "all":
            sources = [s for s in sources if s.id == source_id]
        if not sources:
            raise ValueError("No active source matched")
        for source in sources:
            check = SourceCheck(source_id=source.id, slot=f"manual:{uid()}")
            db.add(check)
            db.commit()
            collect(check.id)
            db.refresh(check)
            print(
                json.dumps(
                    {
                        "id": check.id,
                        "source": source.id,
                        "status": check.status,
                        "items": check.item_count,
                        "new_versions": check.new_versions,
                        "error": check.error,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description="Less local content engine")
    sub = parser.add_subparsers(dest="command", required=True)
    seed_parser = sub.add_parser("seed")
    seed_parser.add_argument(
        "--update",
        action="store_true",
        help="Explicitly apply registry edits; preserve runtime health",
    )
    seed_parser.add_argument("--file", type=Path, default=ROOT / "operations/source-registry.json")
    sub.add_parser("collect").add_argument("source", help="Source ID or all")
    normalize = sub.add_parser("normalize")
    normalize.add_argument("version_id")
    normalize.add_argument("--force", action="store_true")
    sub.add_parser("dispatch")
    sub.add_parser("resume-ai")
    sub.add_parser("backup")
    sub.add_parser("openapi")
    report_parser = sub.add_parser("report")
    report_parser.add_argument("--date", type=date.fromisoformat)
    report_parser.add_argument("--output", type=Path)
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("folder", type=Path)
    restore_parser.add_argument("--database-name", required=True)
    args = parser.parse_args()
    if args.command == "seed":
        seed(args.file, args.update)
    elif args.command == "collect":
        manual_collect(args.source)
    elif args.command == "normalize":
        from less.pipeline import execute_normalize, queue_normalize

        run_id = queue_normalize(args.version_id, args.force)
        execute_normalize(run_id)
        from less.models import NormalizeRun

        with Session() as db:
            run = db.get(NormalizeRun, run_id)
            print(
                json.dumps(
                    {"id": run.id, "status": run.status, "error": run.error}, ensure_ascii=False
                )
            )
    elif args.command == "dispatch":
        from less.tasks import dispatch

        dispatch()
    elif args.command == "resume-ai":
        from less.pipeline import resume_ai

        resume_ai("local-cli")
    elif args.command == "backup":
        from less.maintenance import backup

        print(backup())
    elif args.command == "restore":
        from less.maintenance import restore

        print(json.dumps(restore(args.folder, args.database_name), indent=2))
    elif args.command == "report":
        from less.validation_api import daily_markdown

        content = daily_markdown(args.date)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(args.output)
        else:
            print(content)
    elif args.command == "openapi":
        from less.api import app

        print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
