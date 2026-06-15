import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


THREAD_DIR = Path(__file__).resolve().parent.parent / "logs" / "threads"
DEFAULT_THREAD_ID = "default"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def thread_path(thread_id: str = DEFAULT_THREAD_ID) -> Path:
    safe_id = "".join(c for c in str(thread_id) if c.isalnum() or c in ("_", "-", "."))
    if not safe_id:
        safe_id = DEFAULT_THREAD_ID

    THREAD_DIR.mkdir(parents=True, exist_ok=True)
    return THREAD_DIR / f"{safe_id}.jsonl"


def new_thread_id() -> str:
    return f"thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def append_message(role: str, content: str, thread_id: str = DEFAULT_THREAD_ID) -> dict:
    record = {
        "timestamp": utc_now(),
        "thread_id": thread_id,
        "role": role,
        "content": str(content),
    }

    path = thread_path(thread_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def load_messages(thread_id: str = DEFAULT_THREAD_ID, limit: int = 16) -> list[dict]:
    path = thread_path(thread_id)

    if not path.exists():
        return []

    records = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return records[-limit:]


def build_context_prompt(
    latest_user_message: str,
    thread_id: str = DEFAULT_THREAD_ID,
    history_limit: int = 16,
    max_chars: int = 12000,
) -> str:
    messages = load_messages(thread_id=thread_id, limit=history_limit)

    if not messages:
        return latest_user_message

    lines = [
        "You are Technemachina Daemon, the local engineering Apprentice.",
        "Use the following current thread context to answer follow-up questions coherently.",
        "Do not treat the latest user message as a brand-new topic if the context shows an active topic.",
        "",
        "Authoritative Thread Storage Doctrine:",
        "- Thread messages are stored in logs/threads/<thread_id>.jsonl.",
        "- The default thread is logs/threads/default.jsonl.",
        "- Thread metadata is stored in logs/threads/thread_registry.json.",
        "- audit_log.jsonl stores audit events, not thread conversations.",
        "- decision_ledger.jsonl stores routing and decision traces, not thread conversations.",
        "- If asked where threads are, answer from this doctrine and do not guess.",
        "",
        "Current Thread Context:",
    ]

    for msg in messages:
        role = str(msg.get("role", "unknown")).upper()
        content = str(msg.get("content", "")).strip()

        if not content:
            continue

        # Do not inject transient provider/API failure messages as memory.
        # These are operational errors, not meaningful thread context.
        lowered = content.lower()
        skip_phrases = [
            "gemini_api_key is not set",
            "openrouter_api_key is not set",
            "external gemini brain is temporarily unavailable",
            "external openrouter brain is temporarily unavailable",
            "provider/api issue",
            "all configured external brains failed",
        ]

        if any(phrase in lowered for phrase in skip_phrases):
            continue

        if len(content) > 1200:
            content = content[:1200] + "..."

        lines.append(f"{role}: {content}")

    lines.extend([
        "",
        "Latest User Message:",
        str(latest_user_message).strip(),
    ])

    prompt = "\n".join(lines)

    if len(prompt) > max_chars:
        prompt = prompt[-max_chars:]

    return prompt


def get_thread_summary(thread_id: str = DEFAULT_THREAD_ID) -> str:
    messages = load_messages(thread_id=thread_id, limit=8)

    if not messages:
        return f"Thread {thread_id}: no messages yet."

    return f"Thread {thread_id}: {len(messages)} recent messages loaded."
