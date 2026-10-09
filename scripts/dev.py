"""Run the local API and Vite UI without external infrastructure."""

import os
import signal
import socket
import subprocess
import time
from pathlib import Path

from less.agents import initialize_agent

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / ".venv/bin"


def main():
    try:
        agent = initialize_agent()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    child_env = dict(os.environ, LESS_AGENT_PROVIDER=agent.provider)
    for port in (8000, 5173):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise SystemExit(f"Port {port} is unavailable; stop the existing process first.") from exc

    commands = [
        ([str(BIN / "uvicorn"), "less.api:app", "--host", "127.0.0.1", "--port", "8000"], ROOT),
        (["npm", "run", "dev"], ROOT / "frontend"),
        ([str(BIN / "less"), "scheduler"], ROOT),
    ]
    children: list[subprocess.Popen] = []
    failed = False

    def shutdown(_signum=None, _frame=None):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    try:
        for command, cwd in commands:
            children.append(subprocess.Popen(
                command, cwd=cwd, env=child_env, start_new_session=True
            ))
        print("Less: http://127.0.0.1:5173 — Ctrl+C stops all three processes.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(1)
        failed = True
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
    if failed:
        raise SystemExit("An application process exited unexpectedly.")


if __name__ == "__main__":
    main()
