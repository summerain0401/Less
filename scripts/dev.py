"""Run all local application processes; infrastructure is managed by Compose."""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from less.config import settings

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / ".venv/bin"
DATA = ROOT / "data"


def main():
    # Refuse duplicate stacks before starting a second worker or touching Beat state.
    for port in (8000, 5173):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise SystemExit(
                    f"Port {port} is unavailable; inspect the existing Less service before restarting."
                ) from exc
    DATA.mkdir(exist_ok=True)
    subprocess.run(["docker", "compose", "up", "-d", "--wait"], cwd=ROOT, check=True)
    subprocess.run([str(BIN / "alembic"), "upgrade", "head"], cwd=ROOT, check=True)
    subprocess.run([str(BIN / "less"), "seed"], cwd=ROOT, check=True)
    commands = [
        ([str(BIN / "uvicorn"), "less.api:app", "--host", "127.0.0.1", "--port", "8000"], ROOT),
        (
            [
                str(BIN / "celery"),
                "-A",
                "less.tasks:app",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--loglevel=INFO",
            ],
            ROOT,
        ),
        (
            [
                str(BIN / "celery"),
                "-A",
                "less.tasks:app",
                "beat",
                "--schedule",
                str(DATA / "celerybeat-schedule"),
                "--pidfile",
                str(DATA / "beat.pid"),
                "--loglevel=INFO",
            ],
            ROOT,
        ),
        (["npm", "run", "dev"], ROOT / "frontend"),
    ]
    children = []
    failed = False
    shutdown_timeout = max(settings().codex_timeout, (settings().max_items_per_check + 1) * 35) + 60

    def shutdown(signum=None, frame=None):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    try:
        for command, cwd in commands:
            children.append(subprocess.Popen(command, cwd=cwd, start_new_session=True))
        print(
            "Less: http://127.0.0.1:5173 — Ctrl+C stops app processes; database volumes remain.",
            flush=True,
        )
        while all(child.poll() is None for child in children):
            time.sleep(1)
        print("An application process exited; stopping the remaining processes.", file=sys.stderr)
        failed = True
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                # Let an in-flight Codex invocation or bounded collection finish cleanly.
                child.wait(timeout=shutdown_timeout)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
