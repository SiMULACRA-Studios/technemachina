import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


THREAD_DIR = Path(__file__).resolve().parent.parent / "logs" / "threads"
REGISTRY_PATH = THREAD_DIR / "thread_registry.json"
DEFAULT_THREAD_ID = "default"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_thread_id(thread_id: str) -> str:
    cleaned = "".join(c for c in str(thread_id) if c.isalnum() or c in ("_", "-", "."))
    return cleaned or DEFAULT_THREAD_ID


def title_from_text(text: str, fallback: str = "New Thread", limit: int = 48) -> str:
    value = " ".join(str(text).strip().split())

    if not value:
        return fallback

    if len(value) <= limit:
        return value

    return value[:limit].rstrip() + "..."


def preview_from_text(text: str, limit: int = 120) -> str:
    value = " ".join(str(text).strip().split())

    if len(value) <= limit:
        return value

    return value[:limit].rstrip() + "..."


def load_registry() -> dict[str, Any]:
    THREAD_DIR.mkdir(parents=True, exist_ok=True)

    if not REGISTRY_PATH.exists():
        registry = {
            "active_thread_id": DEFAULT_THREAD_ID,
            "threads": {},
        }
        save_registry(registry)
        return registry

    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        broken_path = REGISTRY_PATH.with_suffix(".broken.json")
        REGISTRY_PATH.rename(broken_path)
        registry = {
            "active_thread_id": DEFAULT_THREAD_ID,
            "threads": {},
            "recovered_from_broken_registry": str(broken_path),
        }
        save_registry(registry)
        return registry


def save_registry(registry: dict[str, Any]) -> None:
    THREAD_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def ensure_thread(
    thread_id: str = DEFAULT_THREAD_ID,
    title: str | None = None,
    preview: str = "",
) -> dict[str, Any]:
    thread_id = safe_thread_id(thread_id)
    registry = load_registry()
    threads = registry.setdefault("threads", {})

    now = utc_now()

    if thread_id not in threads:
        threads[thread_id] = {
            "thread_id": thread_id,
            "title": title or ("Default Thread" if thread_id == DEFAULT_THREAD_ID else "New Thread"),
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "preview": preview,
            "archived": False,
        }
    else:
        if title and threads[thread_id].get("title") in {"New Thread", "Default Thread", ""}:
            threads[thread_id]["title"] = title

    registry["active_thread_id"] = thread_id
    save_registry(registry)
    return threads[thread_id]


def create_thread(title: str | None = None, first_message: str = "") -> dict[str, Any]:
    thread_id = f"thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    if not title:
        title = title_from_text(first_message, fallback="New Thread")

    registry = load_registry()
    registry.setdefault("threads", {})

    now = utc_now()

    registry["threads"][thread_id] = {
        "thread_id": thread_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
        "preview": preview_from_text(first_message),
        "archived": False,
    }

    registry["active_thread_id"] = thread_id
    save_registry(registry)

    return registry["threads"][thread_id]


def set_active_thread(thread_id: str) -> dict[str, Any]:
    thread_id = safe_thread_id(thread_id)
    thread = ensure_thread(thread_id=thread_id)

    registry = load_registry()
    registry["active_thread_id"] = thread_id
    save_registry(registry)

    return thread


def get_active_thread_id() -> str:
    registry = load_registry()
    return safe_thread_id(registry.get("active_thread_id", DEFAULT_THREAD_ID))


def get_thread(thread_id: str) -> dict[str, Any] | None:
    thread_id = safe_thread_id(thread_id)
    registry = load_registry()
    return registry.get("threads", {}).get(thread_id)


def list_threads(include_archived: bool = False) -> list[dict[str, Any]]:
    registry = load_registry()
    threads = list(registry.get("threads", {}).values())

    if not include_archived:
        threads = [thread for thread in threads if not thread.get("archived", False)]

    threads.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return threads


def touch_thread(thread_id: str, role: str, content: str) -> dict[str, Any]:
    thread_id = safe_thread_id(thread_id)
    registry = load_registry()
    threads = registry.setdefault("threads", {})

    if thread_id not in threads:
        title = title_from_text(content) if role == "user" else "New Thread"
        ensure_thread(thread_id=thread_id, title=title, preview=preview_from_text(content))
        registry = load_registry()
        threads = registry.setdefault("threads", {})

    thread = threads[thread_id]

    thread["updated_at"] = utc_now()
    thread["message_count"] = int(thread.get("message_count", 0)) + 1

    if role == "user":
        if thread.get("title") in {"New Thread", "Default Thread", ""}:
            thread["title"] = title_from_text(content)
        thread["preview"] = preview_from_text(content)

    registry["active_thread_id"] = thread_id
    save_registry(registry)

    return thread


def registry_summary() -> str:
    threads = list_threads()
    active = get_active_thread_id()
    return f"{len(threads)} thread(s), active_thread_id={active}"


def rename_thread(thread_id: str, title: str):
    """Rename a thread in the registry without changing its message file."""
    thread_id = safe_thread_id(thread_id)
    clean_title = title_from_text(title or "Untitled Thread", fallback="Untitled Thread", limit=64)

    registry = load_registry()
    ensure_thread(thread_id=thread_id)

    registry = load_registry()
    thread = registry.get("threads", {}).get(thread_id)
    if not thread:
        return None

    thread["title"] = clean_title
    thread["updated_at"] = utc_now()
    save_registry(registry)
    return thread


def archive_thread(thread_id: str):
    """Archive a thread so it is hidden from normal sidebar lists but preserved on disk."""
    thread_id = safe_thread_id(thread_id)

    registry = load_registry()
    thread = registry.get("threads", {}).get(thread_id)
    if not thread:
        return None

    thread["archived"] = True
    thread["updated_at"] = utc_now()

    # If the archived thread was active, switch to the most recently updated non-archived thread.
    if registry.get("active_thread_id") == thread_id:
        remaining = [
            item for item in registry.get("threads", {}).values()
            if not item.get("archived", False) and item.get("thread_id") != thread_id
        ]

        if remaining:
            remaining.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            registry["active_thread_id"] = remaining[0]["thread_id"]
        else:
            default = registry.get("threads", {}).get(DEFAULT_THREAD_ID)
            if not default:
                default = {
                    "thread_id": DEFAULT_THREAD_ID,
                    "title": "Default Thread",
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "message_count": 0,
                    "preview": "",
                    "archived": False,
                }
                registry.setdefault("threads", {})[DEFAULT_THREAD_ID] = default
            default["archived"] = False
            registry["active_thread_id"] = DEFAULT_THREAD_ID

    save_registry(registry)
    return thread


def restore_thread(thread_id: str):
    """Restore an archived thread to the normal sidebar list."""
    thread_id = safe_thread_id(thread_id)

    registry = load_registry()
    thread = registry.get("threads", {}).get(thread_id)
    if not thread:
        return None

    thread["archived"] = False
    thread["updated_at"] = utc_now()
    registry["active_thread_id"] = thread_id

    save_registry(registry)
    return thread
