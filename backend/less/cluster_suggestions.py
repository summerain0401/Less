"""Inspectable first-pass retrieval; never treats similar topics as a merge decision."""

import re
from difflib import SequenceMatcher
from itertools import combinations

from sqlalchemy import func, select

from less.models import EditorialEvent, EventMember

METHOD = "event-skeleton-rules-v1"
ACTION_GROUPS = [
    {"release", "released", "launch", "launched", "announce", "announced", "发布", "推出", "公布"},
    {"review", "evaluate", "evaluated", "test", "tested", "评测", "测试", "复现"},
    {"say", "said", "argue", "argued", "提出", "认为", "表示"},
]


def normalized(value):
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def action_group(value):
    text = normalized(value)
    return next((str(i) for i, group in enumerate(ACTION_GROUPS) if text in group), text)


def similarity(left, right):
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, normalized(left), normalized(right)).ratio()


def compare(left, right, left_versions, right_versions):
    subject = similarity(left.subject, right.subject)
    object_score = similarity(left.object, right.object)
    title = similarity(left.title, right.title)
    action_same = action_group(left.action) == action_group(right.action)
    shared = sorted(set(left_versions) & set(right_versions))
    reasons, conflicts = [], []
    if subject >= 0.8:
        reasons.append("主体文字相近")
    if object_score >= 0.65:
        reasons.append("对象文字相近")
    if action_same:
        reasons.append("动作相同或属于同一基础动作组")
    elif subject >= 0.8:
        conflicts.append("动作不同，发布与评测等不能仅因主体相同而合并")
    if shared:
        reasons.append("共享原文版本；一篇原文也可能包含多个事件")
    if (
        left.event_version
        and right.event_version
        and normalized(left.event_version) != normalized(right.event_version)
    ):
        conflicts.append("版本或范围标识不同")
    if (
        left.happened_at
        and right.happened_at
        and abs((left.happened_at - right.happened_at).total_seconds()) > 3 * 86400
    ):
        conflicts.append("发生时间相隔超过三天")
    score = round(
        0.3 * subject + 0.3 * object_score + 0.15 * title + 0.15 * action_same + 0.1 * bool(shared),
        4,
    )
    if max(subject, object_score, title) < 0.55 and not shared:
        return None
    return {
        "left": {"id": left.id, "revision": left.revision, "title": left.title},
        "right": {"id": right.id, "revision": right.revision, "title": right.title},
        "score": score,
        "suggestion": "different"
        if conflicts
        else "same_candidate"
        if score >= 0.72 and action_same
        else "uncertain",
        "reasons": reasons,
        "conflicts": conflicts,
        "shared_version_ids": shared,
    }


def suggestions(db):
    events = db.scalars(
        select(EditorialEvent)
        .where(EditorialEvent.lifecycle == "active")
        .order_by(EditorialEvent.updated_at.desc(), EditorialEvent.id)
        .limit(200)
    ).all()
    total = db.scalar(
        select(func.count()).select_from(EditorialEvent).where(EditorialEvent.lifecycle == "active")
    )
    members = db.scalars(
        select(EventMember).where(
            EventMember.event_id.in_([e.id for e in events]), EventMember.active.is_(True)
        )
    ).all()
    versions = {e.id: {m.version_id for m in members if m.event_id == e.id} for e in events}
    pairs = []
    for left, right in combinations(events, 2):
        pair = compare(left, right, versions[left.id], versions[right.id])
        if pair:
            pairs.append(pair)
    pairs.sort(key=lambda p: (-p["score"], p["left"]["id"], p["right"]["id"]))
    return {
        "method": METHOD,
        "considered_events": len(events),
        "total_events": total,
        "total_pairs": len(pairs),
        "pairs": pairs[:50],
        "limitations": [
            "仅为主体、动作、对象、标题、版本、时间与共享原文的规则召回，不是语义模型判断。",
            "最多考虑最近更新的 200 个事件、展示前 50 个材料对；不估计全量召回率。",
            "不能据相似度自动合并，跨语言别名、引用关系与语义判断仍需进一步处理。",
        ],
    }
