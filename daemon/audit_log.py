import fcntl
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_PATH = LOG_DIR / "audit_log.jsonl"
_WRITE_LOCK = threading.Lock()


def lock_path() -> Path:
    return LOG_PATH.with_name(f"{LOG_PATH.name}.lock")


def append_jsonl_line(line: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with _WRITE_LOCK:
        with open(lock_path(), "a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

            try:
                with open(LOG_PATH, "a+", encoding="utf-8") as f:
                    position = f.tell()

                    try:
                        f.write(line)
                    except OSError:
                        try:
                            f.truncate(position)
                        except OSError:
                            pass

                        raise
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def report_audit_write_failure(exc: OSError) -> None:
    try:
        print(
            "Technemachina audit log write failed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
    except Exception:
        pass

def write_event(event_type: str, status: str, provider: str = "unknown", detail: str = "") -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "status": status,
        "provider": provider,
        "detail": detail
    }

    line = json.dumps(event) + "\n"

    try:
        append_jsonl_line(line)
    except OSError as exc:
        report_audit_write_failure(exc)
