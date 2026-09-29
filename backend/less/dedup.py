"""Bounded lookup of retained Briefs for scheduled digest deduplication."""

import re
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select, text

from less.models import Brief, BriefSource, SourceKey

MAX_RELATED = 12


def url_key(value: str) -> str:
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
        host = parts.netloc.lower()
    if port and not ((parts.scheme.lower() == "https" and port == 443) or
                     (parts.scheme.lower() == "http" and port == 80)):
        host = f"{host}:{port}"
    if parts.username or parts.password:
        # A URL containing credentials is not a valid Brief source; keep its identity distinct.
        host = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


def exact_ids(db, identifier: str, urls: list[str]) -> set[str]:
    found = set()
    if db.get(Brief, identifier) is not None:
        found.add(identifier)
    keys = {url_key(url) for url in urls}
    if keys:
        found.update(db.scalars(
            select(BriefSource.brief_id)
            .join(SourceKey, SourceKey.source_id == BriefSource.source_id)
            .where(SourceKey.key.in_(keys))
        ))
    return found


def _search_terms(value: str) -> list[str]:
    terms = []
    for part in re.findall(r"[\u3400-\u9fff]{3,}|[A-Za-z0-9][A-Za-z0-9.+-]{2,}", value):
        if "\u3400" <= part[0] <= "\u9fff":
            terms.extend(part[index:index + 3] for index in range(len(part) - 2))
        else:
            terms.append(part)
    return list(dict.fromkeys(terms))[:16]


def related_ids(db, title: str, what_happened: str, exact: set[str]) -> list[str]:
    result = list(sorted(exact))[:MAX_RELATED]
    terms = _search_terms(title) or _search_terms(what_happened[:200])
    if terms:
        query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        rows = db.execute(text(
            "SELECT brief_id FROM brief_fts WHERE brief_fts MATCH :query "
            "ORDER BY bm25(brief_fts) LIMIT :limit"
        ), {"query": query, "limit": MAX_RELATED}).scalars()
        for identifier in rows:
            if identifier not in result:
                result.append(identifier)
            if len(result) == MAX_RELATED:
                return result
    for identifier in db.scalars(
        select(Brief.id).order_by(Brief.created_at.desc()).limit(5)
    ):
        if identifier not in result:
            result.append(identifier)
        if len(result) == MAX_RELATED:
            break
    return result


def related_briefs(db, item: dict) -> list[dict]:
    """Return only the history needed to judge one proposed Brief."""
    from less.api import brief_view, get_brief

    urls = [source["url"] for source in item.get("sources", []) if isinstance(source, dict)
            and isinstance(source.get("url"), str)]
    exact = exact_ids(db, item.get("id", ""), urls)
    ids = related_ids(db, item.get("title", ""), item.get("what_happened", ""), exact)
    related = []
    for identifier in ids:
        view = brief_view(get_brief(db, identifier))
        related.append({
            "id": view["id"],
            "title": view["title"],
            "published_at": view["published_at"],
            "topics": view["topics"],
            "what_happened": view["what_happened"][:2000],
            "why_it_matters": view["why_it_matters"][:600],
            "sources": [{"url": source["url"], "primary": source["primary"]}
                        for source in view["sources"]],
        })
    return related
