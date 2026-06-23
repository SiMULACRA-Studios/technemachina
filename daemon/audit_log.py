import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_PATH = LOG_DIR / "audit_log.jsonl"

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
        LOG_DIR.mkdir(parents=True, exist_ok=True)

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
    except OSError as exc:
        print(
            "Technemachina audit log write failed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
