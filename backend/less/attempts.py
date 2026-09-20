from less.models import now


def start_attempt(record):
    record.attempts_log = [
        *(record.attempts_log or []),
        {
            "attempt": record.attempts,
            "started_at": now().isoformat(),
            "finished_at": None,
            "status": "running",
            "error": None,
        },
    ]


def finish_attempt(record):
    history = list(record.attempts_log or [])
    if history:
        history[-1] = {
            **history[-1],
            "finished_at": now().isoformat(),
            "status": record.status,
            "error": record.error,
        }
        record.attempts_log = history
