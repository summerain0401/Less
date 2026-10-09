"""Twice-daily, local-only content discovery and email delivery."""

import json
import re
import shutil
import signal
import smtplib
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from datetime import time as day_time
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from less.agents import initialize_agent, run_content_task
from less.api import BriefCreate, brief_view, get_brief, replace_content, utc_now
from less.config import ROOT, settings
from less.db import Session, init_db
from less.dedup import exact_ids, related_briefs
from less.models import Brief, DigestRun

SLOTS = {"morning": day_time(6), "evening": day_time(18)}
SLOT_NAMES = {"morning": "早间", "evening": "晚间"}
CHECKER = ROOT / ".agents/skills/less-content/scripts/check_batch.py"
SCHEMA = Path(__file__).with_name("digest.schema.json")
DEDUP_SCHEMA = Path(__file__).with_name("dedup.schema.json")
MAX_START_LATENESS = timedelta(minutes=1)


def next_slot_after(now: datetime) -> tuple[str, datetime]:
    """Find the next future wall-clock slot; never backfill a missed slot."""
    zone = ZoneInfo(settings().timezone)
    local = now.astimezone(zone)
    for offset in (0, 1):
        day = local.date() + timedelta(days=offset)
        for slot, at in SLOTS.items():
            due = datetime.combine(day, at, zone)
            if due > local:
                return slot, due
    raise RuntimeError("No next digest slot")


def slot_is_due(due: datetime, now: datetime) -> bool:
    """A sleeping machine must not run a long-expired slot after waking."""
    return due <= now < due + MAX_START_LATENESS


def _guidance_workspace(target: Path) -> None:
    skill_source = ROOT / ".agents/skills/less-content"
    skill_target = target / ".agents/skills/less-content"
    (skill_target / "references").mkdir(parents=True)
    for name in ("SKILL.md",):
        shutil.copy2(skill_source / name, skill_target / name)
    for name in ("preferred-sources.md", "output-contract.md"):
        shutil.copy2(skill_source / "references" / name, skill_target / "references" / name)
    docs_target = target / "docs/current"
    docs_target.mkdir(parents=True)
    for name in ("00-less-principles.md", "01-less-lite-architecture.md", "02-content-skill.md",
                 "03-brief-deduplication.md"):
        shutil.copy2(ROOT / "docs/current" / name, docs_target / name)


def review_duplicates(batch: dict, workspace: Path) -> dict:
    items = batch["retention_ready"]
    if not items:
        batch["task_note"]["deduplication_basis"] = "No retention-ready Briefs to compare."
        return batch
    for item in items:
        BriefCreate.model_validate(item)
    with Session() as db:
        comparison = [{
            "id": item["id"],
            "exact_ids": sorted(exact_ids(db, item["id"],
                                    [source["url"] for source in item["sources"]])),
            "related": related_briefs(db, item),
        } for item in items]
    if len(items) == 1 and not comparison[0]["related"]:
        batch["task_note"]["deduplication_basis"] = (
            "No retained Brief matched the candidate in the full-library index."
        )
        return batch
    (workspace / "related-briefs.json").write_text(
        json.dumps(comparison, ensure_ascii=False), encoding="utf-8"
    )
    output = workspace / "dedup-decisions.json"
    prompt = (
        "仅执行 Less Brief 去重判断。阅读 batch.json 中的 retention_ready 与 "
        "related-briefs.json 中按全库索引召回的相关旧 Brief。"
        "也比较本批候选之间的重复。对每条候选返回 retain、skip 或 review："
        "同一实质变化的重复报道选 skip；"
        "确有独立新进展选 retain；需要更新旧 Brief 或难以区分时选 review。"
        "共享背景来源链接不自动等于重复，须比较具体新增事实。"
        "每条给出简短、具体的理由与相关旧 Brief ID。"
        "不得搜索、写文件或修改候选内容；只输出符合 JSON Schema 的 decisions。"
    )
    decisions = run_content_task(workspace, output, DEDUP_SCHEMA, prompt)
    entries = decisions.get("decisions") if isinstance(decisions, dict) else None
    if not isinstance(entries, list) or len(entries) != len(items):
        raise RuntimeError("Dedup decisions do not cover every candidate")
    by_id = {entry.get("id"): entry for entry in entries if isinstance(entry, dict)}
    if len(by_id) != len(items) or set(by_id) != {item["id"] for item in items}:
        raise RuntimeError("Dedup decisions have missing or repeated Brief IDs")
    kept = []
    comparison_by_id = {entry["id"]: entry for entry in comparison}
    for item in items:
        entry = by_id[item["id"]]
        if entry.get("action") not in {"retain", "skip", "review"} or not entry.get("reason"):
            raise RuntimeError("Invalid dedup decision")
        if item["id"] in comparison_by_id[item["id"]]["exact_ids"]:
            entry["action"] = "review"
            entry["reason"] = "ID 已存在，需检查并更新原 Brief。"
        elif entry["action"] == "retain" and not set(
            comparison_by_id[item["id"]]["exact_ids"]
        ).issubset(set(entry["related_ids"])):
            entry["action"] = "review"
            entry["reason"] = "共享来源的历史 Brief 尚未逐项比较。"
        if entry["action"] == "retain":
            kept.append(item)
        elif entry["action"] == "review":
            batch["needs_verification"].append(
                f"{item['title']}（{item['id']}）：去重待复核：{entry['reason']}"
            )
    batch["retention_ready"] = kept
    batch["task_note"]["no_item_qualified"] = not kept
    batch["task_note"]["deduplication_basis"] = (
        "Compared each proposed Brief with indexed retained Briefs by ID, normalized source URL, "
        "title and facts; ambiguous updates require review."
    )
    return batch


def discover_content(slot: str, end: datetime) -> dict:
    """Run the content skill in an isolated, read-only temporary workspace."""
    start = end - timedelta(hours=24)
    focus = end - timedelta(hours=12)
    with tempfile.TemporaryDirectory(prefix="less-digest-") as directory:
        workspace = Path(directory)
        _guidance_workspace(workspace)
        output = workspace / "batch.json"
        prompt = (
            "按本目录的 less-content Skill 执行一次中英文区 AI 内容发现任务，用中文写 Brief。"
            "先阅读 .agents/skills/less-content/SKILL.md、其 references 和 docs/current 中的规范。"
            "面向广义知识工作者，分别检索应用实践、观点访谈和重要能力变化。"
            "主动使用中文与英文查询，检查两个语言社区的相关来源；"
            "中文区须观察中国团队、本土产品与中文原创经验，不能仅用海外新闻的中文转载代替。"
            "关注写作、研究、办公、学习、创作和团队工作流；技术进展解释对使用者的具体影响。"
            "应用稿说明问题、做法、观察结果与条件；观点稿说明作者主张、依据和边界，"
            "明确归属，不把作者预测写成事实或 Less 自己的判断。"
            "访谈须有完整相关原始记录或可靠文字稿；厂商案例的效果明确归属于厂商或具名客户。"
            "先生成本轮候选；宿主稍后从全库索引召回相关旧 Brief 并单独进行去重判断。"
            "Brief 正文和 uncertainty 只写内容本身的限制，不写尚待宿主处理的临时流程状态。"
            f"本轮为{SLOT_NAMES[slot]}，时区 {settings().timezone}。"
            f"重点观察 {focus.isoformat()} 至 {end.isoformat()}，"
            f"同时回看 {start.isoformat()} 至 {end.isoformat()} 以发现迟到内容。"
            "只有发布日期而没有具体时刻的原文，如果日期与回看窗口相交，可作为候选；"
            "不可声称它发表于某个确定的 12 小时时段。"
            "优先原始来源，实际打开具体页面，核对日期、范围和关键主张。"
            "只将 high 或 medium 且符合 Important OR Useful 的内容放入 retention_ready；"
            "medium 必须明确写出 uncertainty；低把握线索写入 needs_verification。"
            "允许零条。不要调用 Less 写接口、发送邮件或修改任何文件。"
            "宿主调度程序将在收到结构化输出后运行批次检查器，你无需写文件执行检查。"
            "输出严格符合给定 JSON Schema。task_note 的 window_start、window_end "
            f"必须分别是 {start.isoformat()} 和 {end.isoformat()}；"
            f"timezone 为 {settings().timezone}，time_basis 为 first_primary_publication，"
            "scan_scope 为 broad，在现有 task_note 来源列表中真实记录两种语言社区检查过的来源，"
            "在 access_limitations 中说明打不开原文、缺少文字稿或某类内容覆盖不足。"
            "不设语言或内容类型条数配额，不因缺少某类内容而降低价值、时间或核验标准。"
        )
        batch = run_content_task(workspace, output, SCHEMA, prompt, search=True)
        if not isinstance(batch, dict) or not isinstance(batch.get("task_note"), dict):
            raise RuntimeError("Content agent returned an invalid content batch")
        note = batch["task_note"]
        expected = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "timezone": settings().timezone,
            "time_basis": "first_primary_publication",
            "scan_scope": "broad",
        }
        if any(note.get(key) != value for key, value in expected.items()):
            raise RuntimeError("Content agent returned a batch for the wrong search window")
        review_duplicates(batch, workspace)
        batch_file = workspace / "checked-batch.json"
        batch_file.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        checked = subprocess.run(
            [sys.executable, str(CHECKER), str(batch_file), "--host-checked",
             "--allow-date-only-overlap"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if checked.returncode != 0:
            raise RuntimeError(f"Content batch validation failed: {checked.stderr.strip()[:1200]}")
        return batch


def claim_run(slot: str, due: datetime) -> bool:
    with Session() as db:
        db.add(DigestRun(day=due.date().isoformat(), slot=slot, status="running", started_at=utc_now()))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return False
    return True


def save_batch(slot: str, due: datetime, batch: dict) -> list[dict]:
    """Save all surviving Briefs and the run's Brief IDs in one transaction."""
    with Session.begin() as db:
        run = db.get(DigestRun, (due.date().isoformat(), slot))
        if run is None or run.status != "running":
            raise RuntimeError("Digest run was not claimed")
        saved_ids = []
        for raw in batch["retention_ready"]:
            body = BriefCreate.model_validate(raw)
            matches = exact_ids(db, body.id, [source.url for source in body.sources])
            if body.id in matches:
                continue
            brief = Brief(id=body.id, created_at=utc_now())
            db.add(brief)
            replace_content(db, brief, body)
            saved_ids.append(body.id)
        run.brief_ids_json = json.dumps(saved_ids)
        run.status = "saved"
        views = [brief_view(get_brief(db, brief_id)) for brief_id in saved_ids]
    return views


def mark_run(slot: str, due: datetime, status: str, error: str | None = None,
             email_sent: bool = False) -> None:
    with Session.begin() as db:
        run = db.get(DigestRun, (due.date().isoformat(), slot))
        if run is None:
            raise RuntimeError("Digest run was not claimed")
        run.status = status
        run.error = error
        run.finished_at = utc_now()
        if email_sent:
            run.email_sent_at = utc_now()


def mail_settings() -> None:
    config = settings()
    if not all((config.smtp_host, config.mail_from, config.mail_to)):
        raise RuntimeError("SMTP host, sender and recipient must be configured")
    if config.smtp_username and not config.smtp_password:
        raise RuntimeError("SMTP password must be configured for the SMTP user")


MAIL_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif"
MAIL_TITLE_FONT = "Georgia,'Songti SC',SimSun,serif"
MAIL_WRAP = "overflow-wrap:anywhere;word-break:break-word;"
FAILURE_NOTICE = "本轮内容任务未完成。请查看 Less 本地日志；这不是‘没有新内容’。"


def _mail_paragraphs(value: str) -> str:
    # Paragraph breaks remain paragraphs; single line breaks preserve the author's layout.
    return "".join(
        '<p style="margin:0 0 14px;line-height:1.8;">'
        + escape(paragraph).replace("\n", "<br>") + "</p>"
        for paragraph in re.split(r"\n\s*\n", value.replace("\r\n", "\n"))
        if paragraph.strip()
    )


def _mail_block(label: str, value: str, tone: str = "") -> str:
    decoration = {
        "why": "border-left:2px solid #9caf91;padding:0 0 0 16px;",
        "take": "background-color:#edf2e8;padding:16px 18px 2px;",
        "limit": "color:#6d5e41;",
    }.get(tone, "")
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%;margin:20px 0;table-layout:fixed;"><tr>'
        f'<td style="font-family:{MAIL_FONT};font-size:17px;{MAIL_WRAP}{decoration}">'
        '<h3 style="margin:0 0 8px;font-size:13px;font-weight:600;line-height:1.6;'
        f'color:#657760;">{escape(label)}</h3>{_mail_paragraphs(value)}</td></tr></table>'
    )


def _mail_frame(slot: str, end: datetime, intro: str, content: str,
                failure: bool = False) -> str:
    label = "任务失败" if failure else "简报"
    issue = f"{SLOT_NAMES[slot]}{label} · {end.date().isoformat()}"
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Less {escape(issue)}</title>'
        '<style>@media screen and (max-width:480px){'
        '.mail-padding{padding:24px 20px!important;}'
        '.mail-title{font-size:24px!important;}}</style></head>'
        '<body style="margin:0;padding:0;background-color:#f7f7f2;color:#222820;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'bgcolor="#f7f7f2" style="width:100%;background-color:#f7f7f2;">'
        '<tr><td align="center" style="padding:24px 0;">'
        '<!--[if mso]><table role="presentation" width="640" align="center"><tr><td><![endif]-->'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'bgcolor="#fdfdf9" style="width:100%;max-width:640px;background-color:#fdfdf9;'
        'table-layout:fixed;border-top:4px solid #55714f;">'
        f'<tr><td class="mail-padding" style="padding:32px;font-family:{MAIL_FONT};'
        f'font-size:17px;line-height:1.8;mso-line-height-rule:at-least;{MAIL_WRAP}">'
        f'<h1 style="margin:0;font-family:{MAIL_TITLE_FONT};font-size:36px;'
        'font-weight:400;line-height:1.2;">Less</h1>'
        '<p style="margin:8px 0 26px;font-size:13px;line-height:1.6;color:#657760;">'
        'Read less. Know more.</p>'
        f'<p style="margin:0 0 8px;font-size:13px;color:#657760;">{escape(issue)}</p>'
        f'<p style="margin:0 0 28px;">{escape(intro)}</p>{content}'
        '<p style="margin:28px 0 0;padding-top:20px;border-top:1px solid #dde1d6;'
        'font-size:13px;color:#70786c;line-height:1.8;">'
        '每条内容保留原始来源与必要限制。</p></td></tr></table>'
        '<!--[if mso]></td></tr></table><![endif]--></td></tr></table></body></html>'
    )


def render_digest(slot: str, end: datetime, briefs: list[dict],
                  review_notes: list[str] | None = None) -> tuple[str, str]:
    heading = f"Less {SLOT_NAMES[slot]}简报 · {end.date().isoformat()}"
    intro = "本轮没有值得保留的新内容。" if not briefs else f"本轮保留 {len(briefs)} 条 Brief。"
    lines = [heading, intro]
    parts = []
    for index, brief in enumerate(briefs, 1):
        lines.extend(["", f"{index}. {brief['title']}", f"来源日期：{brief['published_at'] or '未知'}"])
        parts.append(
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="width:100%;table-layout:fixed;border-top:1px solid #dde1d6;"><tr>'
            f'<td style="padding:24px 0 8px;font-family:{MAIL_FONT};font-size:17px;'
            f'line-height:1.8;color:#222820;{MAIL_WRAP}">'
            '<p style="margin:0 0 10px;font-size:13px;color:#657760;">'
            f'{index:02d} / BRIEF</p>'
            f'<h2 class="mail-title" style="margin:0 0 12px;font-family:{MAIL_TITLE_FONT};'
            f'font-size:24px;font-weight:600;line-height:1.5;{MAIL_WRAP}">'
            f'{escape(brief["title"])}</h2>'
            '<p style="margin:0 0 24px;font-size:13px;color:#70786c;">来源日期：'
            f'{escape(brief["published_at"] or "未知")}</p>'
        )
        for label, key, tone in (("发生了什么", "what_happened", ""),
                                 ("为什么值得关注", "why_it_matters", "why"),
                                 ("Less 怎么看", "our_take", "take"),
                                 ("限制与不确定性", "uncertainty", "limit")):
            if brief.get(key):
                lines.extend([f"{label}：{brief[key]}"])
                parts.append(_mail_block(label, brief[key], tone))
        lines.append("来源：")
        parts.append(
            '<h3 style="margin:24px 0 8px;font-size:13px;color:#657760;line-height:1.6;">'
            '来源</h3><ul style="margin:0 0 16px;padding-left:20px;font-size:13px;line-height:1.8;">'
        )
        for source in brief["sources"]:
            source_label = f"{source['name']}（{source['published_at'] or '日期未知'}）"
            lines.append(f"- {source_label} {source['url']}")
            parts.append(
                '<li style="margin:0 0 8px;">'
                f'<a href="{escape(source["url"], quote=True)}" '
                f'style="color:#55714f;text-decoration:underline;{MAIL_WRAP}">'
                f"{escape(source_label)}</a></li>"
            )
        parts.append("</ul></td></tr></table>")
    if review_notes:
        lines.extend(["", "去重待复核：", *[f"- {note}" for note in review_notes]])
        parts.append(_mail_block("去重待复核", "\n\n".join(review_notes), "limit"))
    return "\n".join(lines) + "\n", _mail_frame(slot, end, intro, "".join(parts))


def build_email(slot: str, due: datetime, briefs: list[dict], failure: bool = False,
                review_notes: list[str] | None = None) -> EmailMessage:
    config = settings()
    message = EmailMessage()
    message["From"] = formataddr(("Less", config.mail_from))
    message["To"] = config.mail_to
    label = "任务失败" if failure else "简报"
    message["Subject"] = f"Less {SLOT_NAMES[slot]}{label} · {due.date().isoformat()}"
    domain = config.mail_from.partition("@")[2] or "localhost"
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message["Message-ID"] = make_msgid(domain=domain)
    if failure:
        plain = FAILURE_NOTICE + "\n"
        html = _mail_frame(slot, due, "本轮内容任务未完成。",
                           _mail_block("任务失败", FAILURE_NOTICE, "limit"), failure=True)
    else:
        plain, html = render_digest(slot, due, briefs, review_notes)
    message.set_content(plain)
    message.add_alternative(html, subtype="html")
    return message


def send_email(message: EmailMessage, retries: int = 3) -> None:
    mail_settings()
    config = settings()
    for attempt in range(retries):
        try:
            if config.smtp_port == 465:
                smtp = smtplib.SMTP_SSL(
                    config.smtp_host, config.smtp_port, timeout=30, context=ssl.create_default_context()
                )
            else:
                smtp = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30)
            try:
                if config.smtp_port != 465:
                    smtp.starttls(context=ssl.create_default_context())
                if config.smtp_username:
                    smtp.login(config.smtp_username, config.smtp_password)
                smtp.send_message(message)
            finally:
                try:
                    smtp.quit()
                except (OSError, smtplib.SMTPException):
                    smtp.close()
            return
        except (OSError, smtplib.SMTPException):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def run_slot(slot: str, due: datetime, stopping: threading.Event | None = None) -> bool:
    """Return false when this slot was already claimed by another process."""
    init_db()
    if not claim_run(slot, due):
        return False
    saved = False
    try:
        mail_settings()  # Avoid an expensive content task if delivery cannot work.
        batch = discover_content(slot, due)
        briefs = save_batch(slot, due, batch)
        saved = True
        review_notes = [note for note in batch.get("needs_verification", [])
                        if "去重待复核：" in note]
        send_email(build_email(slot, due, briefs, review_notes=review_notes))
        mark_run(slot, due, "sent", email_sent=True)
        print(f"Less {slot} {due.date()}: saved {len(briefs)}, email sent", flush=True)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[:1500]
        print(f"Less {slot} {due.date()} failed: {detail}", file=sys.stderr, flush=True)
        if stopping is not None and stopping.is_set():
            mark_run(slot, due, "interrupted", error=detail)
            return True
        notified = False
        if not saved:
            try:
                send_email(build_email(slot, due, [], failure=True))
                notified = True
            except Exception as mail_exc:
                print(f"Failure notification could not be sent: {mail_exc}", file=sys.stderr)
        mark_run(slot, due, "failed", error=detail, email_sent=notified)
    return True


def preview_digest(slot: str) -> None:
    initialize_agent()
    init_db()
    now = datetime.now(ZoneInfo(settings().timezone))
    batch = discover_content(slot, now)
    review_notes = [note for note in batch.get("needs_verification", [])
                    if "去重待复核：" in note]
    plain, _ = render_digest(slot, now, batch["retention_ready"], review_notes)
    print(plain)
    print("预览完成：未入库，未发送邮件。", file=sys.stderr)


def run_scheduler() -> None:
    initialize_agent()
    init_db()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    print(f"Less scheduler: 06:00 and 18:00 ({settings().timezone})", flush=True)
    while not stop.is_set():
        slot, due = next_slot_after(datetime.now(timezone.utc))
        seconds = max(0, (due - datetime.now(timezone.utc)).total_seconds())
        if stop.wait(seconds):
            break
        if not slot_is_due(due, datetime.now(timezone.utc)):
            print(f"Less {slot} {due.date()}: skipped missed slot", flush=True)
            continue
        run_slot(slot, due, stop)
