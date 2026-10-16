"""Local scheduler ownership and logging independent of terminal lifetimes."""

import fcntl
import logging
import os
import sys
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler

from less.config import ROOT

RUNTIME_DIR = ROOT / "data"
LOGGER = logging.getLogger("less.scheduler")
LOGGER.addHandler(logging.NullHandler())
LOGGER.propagate = False


class SchedulerAlreadyRunning(RuntimeError):
    pass


@contextmanager
def scheduler_lock(*, record_pid: bool = True):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    # Never unlink this file: all processes must lock the same inode.
    with (RUNTIME_DIR / "less-scheduler.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SchedulerAlreadyRunning("Less scheduler is already running") from exc
        if record_pid:
            lock.seek(0)
            lock.truncate()
            lock.write(str(os.getpid()))
            lock.flush()
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def scheduler_is_running() -> bool:
    try:
        with scheduler_lock(record_pid=False):
            return False
    except SchedulerAlreadyRunning:
        return True


def configure_scheduler_logging() -> None:
    if any(isinstance(handler, RotatingFileHandler) for handler in LOGGER.handlers):
        return
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        RUNTIME_DIR / "less-scheduler.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


def log_event(message: str, *, error: bool = False, stderr: bool = False) -> None:
    # Neither a full disk nor a closed terminal may interrupt task state updates.
    try:
        LOGGER.log(logging.ERROR if error else logging.INFO, message)
    except (OSError, ValueError):
        pass
    try:
        print(message, file=sys.stderr if error or stderr else sys.stdout, flush=True)
    except (OSError, ValueError):
        pass
