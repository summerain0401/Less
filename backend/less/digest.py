"""Twice-daily, local-only content discovery and email delivery."""

import json
import os
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
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from less.api import BriefCreate, brief_view, get_brief, load_options, replace_content, utc_now
from less.config import ROOT, settings
from less.db import Session, init_db
from less.models import Brief, DigestRun

SLOTS = {"morning": day_time(6), "evening": day_time(18)}
SLOT_NAMES = {"morning": "早间", "evening": "晚间"}
CHECKER = ROOT / ".agents/skills/less-content/scripts/check_batch.py"
SCHEMA = Path(__file__).with_name("digest.schema.json")
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


def all_briefs() -> list[dict]:
    with Session() as db:
        rows = db.scalars(select(Brief).options(*load_options()).order_by(Brief.created_at)).unique()
        return [brief_view(row) for row in rows]


def url_key(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def remove_exact_duplicates(batch: dict, existing: list[dict]) -> dict:
    """Drop repeat IDs or source URLs before the strict batch checker runs."""
    seen_ids = {item["id"] for item in existing}
    seen_urls = {url_key(source["url"]) for item in existing for source in item["sources"]}
    retained = []
    for item in batch["retention_ready"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            retained.append(item)
            continue
        sources = item.get("sources")
        if not isinstance(sources, list) or any(
            not isinstance(source, dict) or not isinstance(source.get("url"), str)
            for source in sources
        ):
            retained.append(item)
            continue
        keys = [url_key(source["url"]) for source in sources]
        if item["id"] in seen_ids or any(key in seen_urls for key in keys):
            continue
        retained.append(item)
        seen_ids.add(item["id"])
        seen_urls.update(keys)
    batch["retention_ready"] = retained
    batch["task_note"]["no_item_qualified"] = not retained
    return batch


def _guidance_workspace(target: Path, existing: list[dict]) -> None:
    skill_source = ROOT / ".agents/skills/less-content"
    skill_target = target / ".agents/skills/less-content"
    (skill_target / "references").mkdir(parents=True)
    for name in ("SKILL.md",):
        shutil.copy2(skill_source / name, skill_target / name)
    for name in ("preferred-sources.md", "output-contract.md"):
        shutil.copy2(skill_source / "references" / name, skill_target / "references" / name)
    docs_target = target / "docs/current"
    docs_target.mkdir(parents=True)
    for name in ("00-less-principles.md", "01-less-lite-architecture.md", "02-content-skill.md"):
        shutil.copy2(ROOT / "docs/current" / name, docs_target / name)
    (target / "existing-briefs.json").write_text(
        json.dumps(existing, ensure_ascii=False, default=str), encoding="utf-8"
    )


def _codex_environment() -> dict[str, str]:
    # Do not pass any LESS_ or SMTP credentials to the content-writing process.
    names = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "USER", "CODEX_HOME")
    return {name: os.environ[name] for name in names if name in os.environ}


def discover_content(slot: str, end: datetime, existing: list[dict]) -> dict:
    """Run the content skill in an isolated, read-only temporary workspace."""
    start = end - timedelta(hours=24)
    focus = end - timedelta(hours=12)
    with tempfile.TemporaryDirectory(prefix="less-digest-") as directory:
        workspace = Path(directory)
        _guidance_workspace(workspace, existing)
        output = workspace / "batch.json"
        prompt = (
            "使用本目录的 $less-content Skill 执行一次中文 AI 内容发现任务。"
            "先阅读 .agents/skills/less-content/SKILL.md、其 references 和 docs/current 中的规范。"
            "从 existing-briefs.json 读取完整已保留 Brief，按语义、ID 和来源链接去重。"
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
            "scan_scope 为 broad，并真实记录所检查的来源。"
        )
        command = [
            "codex", "--search", "--ask-for-approval", "never", "exec",
            "--ignore-user-config", "--sandbox", "read-only", "--ephemeral",
            "--skip-git-repo-check", "--cd", str(workspace),
            "--output-schema", str(SCHEMA), "--output-last-message", str(output), prompt,
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=3600,
                env=_codex_environment(), stdin=subprocess.DEVNULL, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"Codex content task could not complete: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip()[-1600:]
            raise RuntimeError(f"Codex content task failed (exit {result.returncode}): {detail}")
        try:
            batch = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Codex did not return a valid content batch") from exc
        if not isinstance(batch, dict) or not isinstance(batch.get("task_note"), dict):
            raise RuntimeError("Codex returned an invalid content batch")
        note = batch["task_note"]
        expected = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "timezone": settings().timezone,
            "time_basis": "first_primary_publication",
            "scan_scope": "broad",
        }
        if any(note.get(key) != value for key, value in expected.items()):
            raise RuntimeError("Codex returned a batch for the wrong search window")
        remove_exact_duplicates(batch, existing)
        batch_file = workspace / "checked-batch.json"
        batch_file.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        checked = subprocess.run(
            [sys.executable, str(CHECKER), str(batch_file), "--existing-briefs",
             str(workspace / "existing-briefs.json"), "--allow-date-only-overlap"],
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
        current = db.scalars(select(Brief).options(*load_options())).unique().all()
        ids = {brief.id for brief in current}
        urls = {url_key(link.source.url) for brief in current for link in brief.source_links}
        saved_ids = []
        for raw in batch["retention_ready"]:
            body = BriefCreate.model_validate(raw)
            keys = [url_key(source.url) for source in body.sources]
            if body.id in ids or any(key in urls for key in keys):
                continue
            brief = Brief(id=body.id, created_at=utc_now())
            db.add(brief)
            replace_content(db, brief, body)
            saved_ids.append(body.id)
            ids.add(body.id)
            urls.update(keys)
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


def render_digest(slot: str, end: datetime, briefs: list[dict]) -> tuple[str, str]:
    heading = f"Less {SLOT_NAMES[slot]}简报 · {end.date().isoformat()}"
    intro = "本轮没有值得保留的新内容。" if not briefs else f"本轮保留 {len(briefs)} 条 Brief。"
    lines = [heading, intro]
    parts = [f"<h1>{escape(heading)}</h1>", f"<p>{escape(intro)}</p>"]
    for index, brief in enumerate(briefs, 1):
        lines.extend(["", f"{index}. {brief['title']}", f"来源日期：{brief['published_at'] or '未知'}"])
        parts.append(f"<section><h2>{index}. {escape(brief['title'])}</h2>")
        parts.append(f"<p>来源日期：{escape(brief['published_at'] or '未知')}</p>")
        for label, key in (("发生了什么", "what_happened"), ("为什么值得关注", "why_it_matters"),
                           ("Less 怎么看", "our_take"), ("限制与不确定性", "uncertainty")):
            if brief.get(key):
                lines.extend([f"{label}：{brief[key]}"])
                parts.append(f"<h3>{label}</h3><p>{escape(brief[key]).replace(chr(10), '<br>')}</p>")
        lines.append("来源：")
        parts.append("<h3>来源</h3><ul>")
        for source in brief["sources"]:
            source_label = f"{source['name']}（{source['published_at'] or '日期未知'}）"
            lines.append(f"- {source_label} {source['url']}")
            parts.append(
                f'<li><a href="{escape(source["url"], quote=True)}">'
                f"{escape(source_label)}</a></li>"
            )
        parts.append("</ul></section>")
    return "\n".join(lines) + "\n", "<!doctype html><html><meta charset='utf-8'><body>" + "".join(parts) + "</body></html>"


def build_email(slot: str, due: datetime, briefs: list[dict], failure: bool = False) -> EmailMessage:
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
        plain = "本轮内容任务未完成。请查看 Less 本地日志；这不是‘没有新内容’。\n"
        html = f"<html><body><h1>{escape(message['Subject'])}</h1><p>{escape(plain)}</p></body></html>"
    else:
        plain, html = render_digest(slot, due, briefs)
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
        mail_settings()  # Avoid an expensive Codex run if delivery cannot work.
        existing = all_briefs()
        batch = discover_content(slot, due, existing)
        briefs = save_batch(slot, due, batch)
        saved = True
        send_email(build_email(slot, due, briefs))
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
    init_db()
    now = datetime.now(ZoneInfo(settings().timezone))
    batch = discover_content(slot, now, all_briefs())
    plain, _ = render_digest(slot, now, batch["retention_ready"])
    print(plain)
    print("预览完成：未入库，未发送邮件。", file=sys.stderr)


def run_scheduler() -> None:
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
