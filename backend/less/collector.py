import calendar
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
import trafilatura
from lxml import html
from sqlalchemy import select

from less.attempts import finish_attempt, start_attempt
from less.config import settings
from less.db import Session, lock
from less.models import Item, ItemVersion, Source, SourceCheck, now
from less.storage import save_blob


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
        raise ValueError("Expected a public HTTP(S) article URL")
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            urlencode(sorted(query)),
            "",
        )
    )


def paragraphs(text: str) -> list[dict]:
    result = []
    for match in re.finditer(r"[^\n]+", text):
        content = match.group().strip()
        if content:
            result.append(
                {
                    "id": f"p{len(result) + 1:04d}",
                    "text": content,
                    "start": match.start() + len(match.group()) - len(match.group().lstrip()),
                    "end": match.end() - len(match.group()) + len(match.group().rstrip()),
                }
            )
    return result


def fetch(client: httpx.Client, url: str) -> bytes:
    canonical_url(url)
    with client.stream("GET", url) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > 8_000_000:
                raise ValueError("Source response exceeds 8 MB")
            chunks.append(chunk)
    return b"".join(chunks)


def entry_material(entry, client: httpx.Client) -> dict:
    url = canonical_url(entry.get("link", ""))
    limitations = []
    full_content = entry.get("content", [])
    if full_content and full_content[0].get("value"):
        raw = full_content[0]["value"].encode()
        text = trafilatura.extract(raw, include_tables=True, include_links=True) or ""
        if len(text.strip()) < 80:
            # Explicit feed content can be a perfectly valid short release note.
            document = html.fromstring(raw)
            for element in document.xpath("//script|//style"):
                element.drop_tree()
            text = document.text_content().strip()
        acquisition = "feed-content"
    else:
        raw = fetch(client, url)
        text = trafilatura.extract(raw, include_tables=True, include_links=True) or ""
        acquisition = "article-html"
    if not text.strip() or (acquisition == "article-html" and len(text.strip()) < 80):
        raise ValueError("Article body missing or too short; summary-only data is not normalized")
    if len(text) > 60_000:
        text = text[:60_000]
        limitations.append(
            "Body limited to first 60000 characters; complete source snapshot retained"
        )
    date = entry.get("published_parsed")
    published_at = datetime.fromtimestamp(calendar.timegm(date), timezone.utc) if date else None
    return {
        "url": url,
        "title": entry.get("title", "Untitled"),
        "author": entry.get("author"),
        "published_at": published_at,
        "text": text,
        "raw": raw,
        "acquisition": acquisition,
        "limitations": limitations,
    }


def save_material(session, source_id: str, material: dict):
    url = canonical_url(material["url"])
    item = session.scalar(select(Item).where(Item.source_id == source_id, Item.url == url))
    if item is None:
        item = Item(source_id=source_id, url=url)
        session.add(item)
        session.flush()
    stable = {k: material[k] for k in ("title", "author", "published_at", "text")}
    digest = hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()
    existing = session.scalar(
        select(ItemVersion).where(
            ItemVersion.item_id == item.id, ItemVersion.content_hash == digest
        )
    )
    if existing:
        return existing, False
    version = ItemVersion(
        item_id=item.id,
        content_hash=digest,
        **stable,
        paragraphs=paragraphs(material["text"]),
        snapshot_path=save_blob(material["raw"]),
        acquisition=material["acquisition"],
        limitations=material["limitations"],
    )
    session.add(version)
    session.flush()
    return version, True


def select_entries(db, source_id, entries):
    known = set(db.scalars(select(Item.url).where(Item.source_id == source_id)))

    def previously_seen(entry):
        try:
            return canonical_url(entry.get("link", "")) in known
        except ValueError:
            return False

    # New entries take priority so a full feed can be drained over several checks.
    # Known entries then get refreshed in feed order to detect article corrections.
    return sorted(entries, key=previously_seen)[: settings().max_items_per_check]


def collect(check_id: str):
    with Session() as db:
        check = db.get(SourceCheck, check_id)
        if check is None:
            return
        source_id = check.source_id
    with lock(f"collect:{source_id}") as acquired:
        if not acquired:
            return
        with Session() as db:
            check = db.get(SourceCheck, check_id)
            source = db.get(Source, source_id)
            if check.status not in ("pending", "retryable") or source.status != "active":
                return
            if check.next_attempt_at > now():
                return
            check.status, check.started_at = "running", now()
            check.attempts += 1
            start_attempt(check)
            db.commit()
            try:
                errors, versions = [], []
                with httpx.Client(
                    timeout=30,
                    follow_redirects=True,
                    headers={"User-Agent": "Less/0.1 (personal feed reader)"},
                ) as client:
                    if check.entry_batch is None:
                        raw_feed = fetch(client, source.feed_url)
                        check.snapshot_path = save_blob(raw_feed)
                        db.commit()
                        feed = feedparser.parse(raw_feed)
                        if feed.bozo or not feed.version:
                            raise ValueError(
                                "Feed parsing failed; this is not a successful empty check"
                            )
                        entries = select_entries(db, source.id, feed.entries)
                        check.feed_item_count = len(feed.entries)
                        check.deferred_count = len(feed.entries) - len(entries)
                        # Retries use the exact same entry batch, even if the live feed changes.
                        check.entry_batch = json.loads(json.dumps(entries))
                        db.commit()
                    entries = check.entry_batch
                    for entry in entries:
                        try:
                            material = entry_material(entry, client)
                            version, created = save_material(db, source.id, material)
                            db.commit()
                            if created:
                                versions.append(version.id)
                        except (httpx.HTTPError, ValueError) as exc:
                            db.rollback()
                            errors.append(
                                f"{entry.get('link', 'unknown')}: {type(exc).__name__}: {str(exc)[:250]}"
                            )
                check = db.get(SourceCheck, check_id)
                check.item_count = len(entries)
                check.new_versions += len(versions)
                check.finished_at = now()
                db.commit()
                if errors:
                    raise ValueError("; ".join(errors))
                check.status, check.error = "succeeded", None
                source.last_success_at = now()
                finish_attempt(check)
                db.commit()
                if settings().auto_normalize:
                    from less.pipeline import queue_normalize

                    for version_id in versions:
                        queue_normalize(version_id)
            except (httpx.HTTPError, ValueError) as exc:
                db.rollback()
                check = db.get(SourceCheck, check_id)
                check.status = "retryable" if check.attempts < settings().max_attempts else "failed"
                check.finished_at, check.error = now(), str(exc)[:3000]
                check.next_attempt_at = now() + timedelta(minutes=check.attempts * 2)
                finish_attempt(check)
                db.commit()
