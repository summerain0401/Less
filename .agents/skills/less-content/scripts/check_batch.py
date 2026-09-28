"""Check a time-bounded Less Content delivery before presenting it."""

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))
from less.api import BriefCreate  # noqa: E402


def timestamp(value: object, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"{label}: expected a timezone-qualified timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label}: invalid timestamp")
        return None
    if parsed.tzinfo is None or len(value) <= 10:
        errors.append(f"{label}: timestamp must include a timezone")
        return None
    return parsed


def publication_interval(value: str, zone: ZoneInfo) -> tuple[datetime, datetime] | None:
    if len(value) == 10:
        day = date.fromisoformat(value)
        start = datetime.combine(day, time.min, zone)
        end = datetime.combine(day + timedelta(days=1), time.min, zone)
        return start, end
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment, moment


def inside_window(
    interval: tuple[datetime, datetime], start: datetime, end: datetime
) -> bool:
    first, last = interval
    if first == last:
        return start <= first < end
    return start <= first and last <= end


def compatible(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> bool:
    a_start, a_end = a
    b_start, b_end = b
    if a_start == a_end and b_start == b_end:
        return a_start == b_start
    if a_start == a_end:
        return b_start <= a_start < b_end
    if b_start == b_end:
        return a_start <= b_start < a_end
    return max(a_start, b_start) < min(a_end, b_end)


def url_key(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def string_list(value: object, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{label}: expected a list of non-empty strings")
        return []
    return value


def check(
    batch: object,
    existing: object | None,
    dedup_unavailable: bool,
    allow_date_only_overlap: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(batch, dict):
        return ["batch: expected an object"]
    ready = batch.get("retention_ready")
    verify = batch.get("needs_verification")
    note = batch.get("task_note")
    if not isinstance(ready, list):
        errors.append("retention_ready: expected a list")
        ready = []
    string_list(verify, "needs_verification", errors)
    if not isinstance(note, dict):
        return errors + ["task_note: expected an object"]

    start = timestamp(note.get("window_start"), "window_start", errors)
    end = timestamp(note.get("window_end"), "window_end", errors)
    if start and end and start >= end:
        errors.append("task_note: window_start must precede window_end")
    try:
        zone = ZoneInfo(note["timezone"])
    except (KeyError, TypeError, ZoneInfoNotFoundError):
        errors.append("timezone: expected a valid IANA timezone")
        zone = ZoneInfo("UTC")
    if note.get("time_basis") != "first_primary_publication":
        errors.append("time_basis: strict checker requires first_primary_publication")
    if note.get("scan_scope") not in {"broad", "focused"}:
        errors.append("scan_scope: expected broad or focused")
    coverage = string_list(note.get("coverage_considered"), "coverage_considered", errors)
    preferred = string_list(note.get("preferred_sources_checked"), "preferred_sources_checked", errors)
    string_list(note.get("expanded_sources_used"), "expanded_sources_used", errors)
    string_list(note.get("access_limitations"), "access_limitations", errors)
    if not coverage:
        errors.append("coverage_considered: expected at least one area")
    if note.get("scan_scope") == "broad" and not preferred:
        errors.append("preferred_sources_checked: required for a broad scan")
    if not isinstance(note.get("deduplication_basis"), str) or not note["deduplication_basis"].strip():
        errors.append("deduplication_basis: expected a non-empty explanation")
    if not isinstance(note.get("no_item_qualified"), bool) or note["no_item_qualified"] != (len(ready) == 0):
        errors.append("no_item_qualified: must match whether retention_ready is empty")

    known_ids: set[str] = set()
    known_urls: set[str] = set()
    if not dedup_unavailable:
        if not isinstance(existing, list):
            errors.append("existing briefs: expected the complete JSON list from GET /api/briefs")
        else:
            for index, item in enumerate(existing):
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("sources"), list):
                    errors.append(f"existing briefs[{index}]: expected id and sources")
                    continue
                known_ids.add(item["id"])
                for source_index, source in enumerate(item["sources"]):
                    if not isinstance(source, dict) or not isinstance(source.get("url"), str) or not source["url"].strip():
                        errors.append(f"existing briefs[{index}].sources[{source_index}]: expected a URL")
                    else:
                        known_urls.add(url_key(source["url"]))

    for index, item in enumerate(ready):
        label = f"retention_ready[{index}]"
        try:
            brief = BriefCreate.model_validate(item)
        except ValidationError as exc:
            errors.append(f"{label}: invalid Brief: {exc.errors(include_url=False)}")
            continue
        if brief.id in known_ids:
            errors.append(f"{label}: duplicate Brief ID {brief.id}")
        known_ids.add(brief.id)
        for source in brief.sources:
            key = url_key(source.url)
            if key in known_urls:
                errors.append(f"{label}: duplicate source link {source.url}")
            known_urls.add(key)

        primary = next(source for source in brief.sources if source.primary)
        if not primary.published_at:
            errors.append(f"{label}: first primary source needs a publication date")
            continue
        primary_interval = publication_interval(primary.published_at, zone)
        if start and end and start < end:
            date_only_overlap = (
                allow_date_only_overlap
                and len(primary.published_at) == 10
                and primary_interval[0] < end
                and primary_interval[1] > start
            )
            if not inside_window(primary_interval, start, end) and not date_only_overlap:
                errors.append(
                    f"{label}: first primary publication is outside or ambiguous at the window boundary"
                )
        if not brief.published_at:
            errors.append(f"{label}: top-level published_at is required for a time-bounded scan")
        elif not compatible(publication_interval(brief.published_at, zone), primary_interval):
            errors.append(f"{label}: top-level published_at conflicts with first primary source")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    dedup = parser.add_mutually_exclusive_group(required=True)
    dedup.add_argument("--existing-briefs", type=Path)
    dedup.add_argument("--dedup-unavailable", action="store_true")
    parser.add_argument(
        "--allow-date-only-overlap",
        action="store_true",
        help="Allow a date-only primary source whose local calendar day overlaps the window",
    )
    args = parser.parse_args()
    try:
        batch = json.loads(args.batch.read_text(encoding="utf-8"))
        existing = json.loads(args.existing_briefs.read_text(encoding="utf-8")) if args.existing_briefs else None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    errors = check(batch, existing, args.dedup_unavailable, args.allow_date_only_overlap)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(batch['retention_ready'])} retention-ready Brief(s); dedup {'unavailable' if args.dedup_unavailable else 'checked'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
