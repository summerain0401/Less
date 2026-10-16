"""Start, stop and inspect the three local Less services together on macOS."""

import argparse
import fcntl
import json
import os
import plistlib
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from less.agents import agent_environment, get_agent
from less.config import ROOT
from less.runtime import scheduler_is_running

COMPONENTS = ("api", "frontend", "scheduler")
DOMAIN = f"gui/{os.getuid()}"
AGENTS_DIR = Path.home() / "Library/LaunchAgents"
LOG_DIR = Path.home() / "Library/Logs/Less"
STATE_FILE = ROOT / "data/less-services.json"


def label(component: str) -> str:
    return f"local.less.{component}"


def launchctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *arguments], capture_output=True, text=True, check=check)


def service_state(component: str) -> dict:
    result = launchctl("print", f"{DOMAIN}/{label(component)}", check=False)
    state = {"loaded": result.returncode == 0, "state": "stopped", "pid": None}
    for line in result.stdout.splitlines():
        # Nested coalition state fields do not describe the service itself.
        if not line.startswith("\t") or line.startswith("\t\t"):
            continue
        key, separator, value = line.strip().partition(" = ")
        if separator and key in ("state", "pid", "last exit code"):
            state[key] = int(value) if key == "pid" else value
    return state


@contextmanager
def control_lock():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with (STATE_FILE.parent / "less-service-control.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another Less start/stop command is in progress") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def saved_settings() -> dict:
    if not STATE_FILE.exists():
        return {"frontend_port": 5173}
    return json.loads(STATE_FILE.read_text())


def agent_config(component: str, provider: str, port: int = 5173) -> dict:
    environment = agent_environment(provider)
    environment["LESS_AGENT_PROVIDER"] = provider
    python = str(ROOT / ".venv/bin/python")
    if component == "scheduler":
        command = [python, "-u", "-m", "less.cli", "scheduler"]
    elif component == "api":
        command = [python, "-u", "-m", "uvicorn", "less.api:app",
                   "--host", "127.0.0.1", "--port", "8000"]
    elif component == "frontend":
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Node.js is required to start Less")
        command = [node, str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                   str(ROOT / "frontend"), "--config", str(ROOT / "frontend/vite.config.ts"),
                   "--host", "127.0.0.1", "--port", str(port), "--strictPort"]
    else:
        raise ValueError(f"Unknown Less component: {component}")
    return {
        "Label": label(component), "ProgramArguments": command,
        # launchd cannot reliably open a cwd or log on a removable volume before exec.
        "WorkingDirectory": str(Path.home()), "EnvironmentVariables": environment,
        "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 30,
        "ExitTimeOut": 15, "ProcessType": "Background",
        "StandardOutPath": "/dev/null" if component == "scheduler" else str(LOG_DIR / f"{component}.log"),
        "StandardErrorPath": str(LOG_DIR / f"{component}-service.log"),
    }


def port_available(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(preferred: int, *, explicit: bool = False) -> int:
    if not 1024 <= preferred <= 65535:
        raise RuntimeError("Frontend port must be between 1024 and 65535")
    candidates = [preferred] if explicit else dict.fromkeys([preferred, *range(5173, 5184)])
    for port in candidates:
        if port_available(port):
            return port
    raise RuntimeError("Frontend port is occupied; specify a free port with --port")


def healthy(component: str, port: int) -> bool:
    state = service_state(component)
    if state["state"] != "running" or not state["pid"]:
        return False
    if component == "scheduler":
        return scheduler_is_running()
    url = "http://127.0.0.1:8000/openapi.json" if component == "api" else f"http://127.0.0.1:{port}/"
    try:
        with urlopen(url, timeout=2) as response:
            if component == "api":
                return json.load(response).get("info", {}).get("title") == "Less"
            return response.status == 200 and b"<title>Less" in response.read()
    except (OSError, URLError, ValueError):
        return False


def _unload(component: str) -> None:
    target = f"{DOMAIN}/{label(component)}"
    # Disabled state persists across login; bootout alone would restart next login.
    launchctl("disable", target)
    if service_state(component)["loaded"]:
        launchctl("bootout", target)


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def start(port: int | None = None) -> None:
    with control_lock():
        states = {name: service_state(name) for name in COMPONENTS}
        saved = saved_settings()
        preferred = port if port is not None else saved["frontend_port"]
        if all(healthy(name, preferred) for name in COMPONENTS):
            print(f"Less is already running: http://127.0.0.1:{preferred}")
            return
        provider = get_agent().provider
        if states["frontend"]["loaded"]:
            if port is not None and port != saved["frontend_port"]:
                raise RuntimeError("Stop Less before changing its frontend port")
            selected = saved["frontend_port"]
        else:
            selected = choose_port(preferred, explicit=port is not None)
        if not states["api"]["loaded"] and not port_available(8000):
            raise RuntimeError("Port 8000 is occupied by an unmanaged process; stop it before starting Less")
        if not states["scheduler"]["loaded"] and scheduler_is_running():
            raise RuntimeError("A foreground/manual scheduler is active; stop it before starting Less")
        # Validate dependencies and prepare every config before enabling any jobs.
        configs = {name: agent_config(name, provider, selected) for name in COMPONENTS}
        for name, state in states.items():
            if state["loaded"]:
                path = AGENTS_DIR / f"{label(name)}.plist"
                old = plistlib.loads(path.read_bytes())
                if old.get("EnvironmentVariables", {}).get("LESS_AGENT_PROVIDER") != provider:
                    raise RuntimeError("Stop Less before switching its content agent provider")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        new = []
        try:
            for name in COMPONENTS:
                if states[name]["loaded"]:
                    continue
                path = AGENTS_DIR / f"{label(name)}.plist"
                write_file(path, plistlib.dumps(configs[name]))
                new.append(name)
                launchctl("enable", f"{DOMAIN}/{label(name)}")
                launchctl("bootstrap", DOMAIN, str(path))
            write_file(STATE_FILE, json.dumps({"frontend_port": selected, "provider": provider}).encode())
            deadline = time.monotonic() + 20
            ready_checks = 0
            while time.monotonic() < deadline:
                if all(healthy(name, selected) for name in COMPONENTS):
                    ready_checks += 1
                    if ready_checks >= 2:
                        print(f"Less started (API, frontend, scheduler): http://127.0.0.1:{selected}")
                        return
                else:
                    ready_checks = 0
                time.sleep(0.25)
            raise RuntimeError(f"Less did not become ready; check {LOG_DIR}")
        except BaseException:
            for name in reversed(new):
                try:
                    _unload(name)
                except (OSError, subprocess.CalledProcessError):
                    pass
            raise


def stop() -> None:
    with control_lock():
        failures = []
        pids = [state["pid"] for name in COMPONENTS
                if (state := service_state(name))["pid"]]
        for name in ("scheduler", "frontend", "api"):
            try:
                _unload(name)
            except (OSError, subprocess.CalledProcessError) as exc:
                failures.append(f"{name}: {exc}")
        deadline = time.monotonic() + 20
        while (scheduler_is_running() or any(pid_exists(pid) for pid in pids)) and time.monotonic() < deadline:
            time.sleep(0.25)
        if scheduler_is_running():
            failures.append("A scheduler/manual task is still running")
        if any(pid_exists(pid) for pid in pids):
            failures.append("A managed process has not exited yet")
        if failures:
            raise RuntimeError("Could not stop all Less services: " + "; ".join(failures))
        print("Less stopped (API, frontend, scheduler); will remain stopped after login")


def status() -> None:
    port = saved_settings()["frontend_port"]
    for name in COMPONENTS:
        state = service_state(name)
        condition = "running" if healthy(name, port) else ("starting/unhealthy" if state["loaded"] else "stopped")
        print(f"{name}: {condition}" + (f" (PID {state['pid']})" if state["pid"] else ""))
    if healthy("frontend", port):
        print(f"URL: http://127.0.0.1:{port}")


def dev() -> None:
    stopping = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, lambda *_: stopping.set())
    start()
    try:
        print("Ctrl+C stops all Less services; use `make start` to leave them running.")
        stopping.wait()
    finally:
        stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "dev"))
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("Unified service management currently requires macOS")
    try:
        if args.action == "start":
            start(args.port)
        elif args.action == "stop":
            stop()
        elif args.action == "dev":
            dev()
        else:
            status()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            raise SystemExit(exc.stderr.strip()) from exc
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
