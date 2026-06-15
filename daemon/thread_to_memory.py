from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import memory_review_queue
import thread_context
import thread_registry


MEMORY_DIR = Path(__file__).resolve().parent.parent / "logs" / "memory"
CANDIDATES_PATH = MEMORY_DIR / "candidates.jsonl"

CANDIDATE_VERSION = "v0.2.7e"
POLICY_VERSION = "thread_to_memory_candidate_policy_v1"

IGNORE_PATTERNS = [
    "hello",
    "hi",
    "hey",
    "thanks",
    "thank you",
    "greeting loop",
    "what is the objective",
    "i am ready for instructions",
    "do we move toward",
    "provider unavailable",
    "traceback",
    "internal server error",
    "command not found",
    "zsh:",
    "curl -s",
    "grep -n",
    "sed -n",
]

STRONG_SIGNAL_PATTERNS = [
    "remember",
    "lock",
    "locked",
    "milestone",
    "status",
    "current objective",
    "doctrine",
    "rule",
    "should",
    "must",
    "never",
    "always",
    "confirmed",
    "working",
    "online",
    "architecture",
    "endpoint",
    "backup",
    "version",
    "v0.",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_store() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.touch(exist_ok=True)


def safe_text(text: str, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit]


def make_candidate_id() -> str:
    return f"cand_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def load_candidates(include_enqueued: bool = True) -> list[dict[str, Any]]:
    ensure_store()
    candidates = []

    for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not include_enqueued and item.get("review_status") != "candidate":
            continue

        candidates.append(item)

    return candidates


def write_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    ensure_store()
    with CANDIDATES_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    return candidate


def update_candidate(candidate_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    ensure_store()
    candidates = load_candidates(include_enqueued=True)
    updated = None

    for item in candidates:
        if item.get("candidate_id") == candidate_id:
            item.update(patch)
            item["updated_at"] = utc_now()
            updated = item
            break

    if not updated:
        raise ValueError(f"Candidate not found: {candidate_id}")

    CANDIDATES_PATH.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in candidates) + "\n",
        encoding="utf-8",
    )

    return updated


def is_candidate_worthy(text: str) -> bool:
    cleaned = safe_text(text, limit=1200).lower()

    if len(cleaned) < 45:
        return False

    # Hard ignore obvious conversational boilerplate, greetings, provider noise, and terminal clutter.
    if any(pattern in cleaned for pattern in IGNORE_PATTERNS):
        return False

    # Require at least one durable-memory signal.
    if not any(pattern in cleaned for pattern in STRONG_SIGNAL_PATTERNS):
        return False

    # Require the text to look like a decision, state change, rule, procedure, or confirmed result.
    durable_phrases = [
        "confirmed",
        "verified",
        "working",
        "online",
        "locked",
        "backup",
        "milestone",
        "current objective",
        "status",
        "doctrine",
        "rule",
        "must",
        "never",
        "always",
        "endpoint",
        "module",
        "procedure",
        "workflow",
    ]

    return any(phrase in cleaned for phrase in durable_phrases)


def infer_record_type(text: str) -> str:
    lowered = text.lower()

    if any(word in lowered for word in ["doctrine", "rule", "must", "never", "always", "governance"]):
        return "doctrine_note"

    if any(word in lowered for word in ["endpoint", "function", "module", "patch", "command", "workflow", "procedure"]):
        return "procedure"

    if any(word in lowered for word in ["risk", "unsafe", "guardrail", "safety", "blocked"]):
        return "risk_note"

    if any(word in lowered for word in ["version", "milestone", "status", "online", "backup", "locked"]):
        return "project_fact"

    return "project_fact"


def infer_layer(record_type: str, text: str) -> str:
    lowered = text.lower()

    if record_type in {"doctrine_note", "risk_note"}:
        return "theta"

    if any(word in lowered for word in ["locked", "milestone", "online", "current objective", "status"]):
        return "alpha"

    return "alpha"


def infer_tags(text: str, record_type: str) -> list[str]:
    lowered = text.lower()
    tags = ["thread-candidate", record_type]

    for tag, words in {
        "memory": ["memory", "candidate", "review", "queue"],
        "thread": ["thread", "chat", "conversation"],
        "frontend": ["frontend", "browser", "button", "ui", "control center"],
        "backend": ["endpoint", "api", "module", "python", "fastapi"],
        "governance": ["approve", "reject", "defer", "oracle", "review", "governance"],
        "version": ["v0.", "version", "milestone", "locked"],
        "safety": ["risk", "unsafe", "guardrail", "blocked"],
    }.items():
        if any(word in lowered for word in words):
            tags.append(tag)

    return sorted(set(tags))


def candidate_title(text: str, record_type: str) -> str:
    text = safe_text(text, 120)

    if not text:
        return f"Thread candidate · {record_type}"

    text = text.strip("`-*# ")
    if len(text) > 72:
        text = text[:69].rstrip() + "..."

    return text


def build_candidate_from_message(message: dict[str, Any], thread_id: str) -> dict[str, Any] | None:
    role = message.get("role", "unknown")
    content = safe_text(message.get("content", ""), limit=1500)

    if not is_candidate_worthy(content):
        return None

    record_type = infer_record_type(content)
    layer = infer_layer(record_type, content)
    tags = infer_tags(content, record_type)

    message_id = message.get("message_id") or message.get("id") or message.get("timestamp") or ""

    candidate = {
        "candidate_id": make_candidate_id(),
        "candidate_version": CANDIDATE_VERSION,
        "policy_version": POLICY_VERSION,
        "source_thread_id": thread_id,
        "source_message_ids": [message_id] if message_id else [],
        "source_excerpt": content[:500],
        "record_type": record_type,
        "layer_suggested": layer,
        "layer": layer,
        "scope": "project",
        "title": candidate_title(content, record_type),
        "summary": content[:220],
        "body": content,
        "why_candidate": "Thread message matched conservative candidate extraction signals.",
        "matched_tags": tags,
        "tags": tags,
        "source_type": "thread",
        "source_ref": f"thread:{thread_id}",
        "source_title": f"Thread {thread_id}",
        "created_by": "Technemachina Candidate Factory",
        "provenance": f"Extracted from {role} message in thread {thread_id}; requires Oracle review before durable memory.",
        "confidence": "medium",
        "importance": 0.5,
        "importance_weight": 0.5,
        "recency_weight": 0.5,
        "retrieval_priority": 50,
        "risk_level": "low",
        "attach_recommendation": "no",
        "attach_to_context": False,
        "review_status": "candidate",
        "created_at": utc_now(),
        "expires_at": None,
    }

    return candidate


def generate_candidates_from_thread(thread_id: str = "", limit: int = 40, persist: bool = True) -> dict[str, Any]:
    thread_id = thread_registry.safe_thread_id(thread_id or thread_registry.get_active_thread_id())
    messages = thread_context.load_messages(thread_id=thread_id, limit=limit)

    generated = []
    seen_bodies = {item.get("body", "") for item in load_candidates(include_enqueued=True)}

    for message in messages:
        candidate = build_candidate_from_message(message, thread_id)
        if not candidate:
            continue

        if candidate["body"] in seen_bodies:
            continue

        if persist:
            write_candidate(candidate)

        generated.append(candidate)
        seen_bodies.add(candidate["body"])

    return {
        "status": "success",
        "thread_id": thread_id,
        "message_count": len(messages),
        "candidate_count": len(generated),
        "candidates": generated,
        "candidate_path": str(CANDIDATES_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "policy": POLICY_VERSION,
    }


def enqueue_candidate(candidate_id: str, reviewed_by: str = "Oracle", notes: str = "") -> dict[str, Any]:
    candidates = load_candidates(include_enqueued=True)
    candidate = next((item for item in candidates if item.get("candidate_id") == candidate_id), None)

    if not candidate:
        raise ValueError(f"Candidate not found: {candidate_id}")

    if candidate.get("review_status") not in {"candidate", "deferred"}:
        raise ValueError(f"Candidate is already {candidate.get('review_status')}")

    candidate_record = {
        "record_type": candidate.get("record_type", "project_fact"),
        "layer": candidate.get("layer_suggested") or candidate.get("layer", "alpha"),
        "scope": candidate.get("scope", "project"),
        "title": candidate.get("title", "Untitled candidate"),
        "summary": candidate.get("summary", ""),
        "body": candidate.get("body", ""),
        "tags": candidate.get("tags") or candidate.get("matched_tags") or ["thread-candidate"],
        "source_type": candidate.get("source_type", "thread"),
        "source_ref": candidate.get("source_ref", ""),
        "source_title": candidate.get("source_title", ""),
        "created_by": candidate.get("created_by", "Technemachina Candidate Factory"),
        "provenance": candidate.get("provenance", ""),
        "confidence": candidate.get("confidence", "medium"),
        "risk_level": candidate.get("risk_level", "low"),
        "attach_to_context": candidate.get("attach_to_context", False),
        "retrieval_priority": candidate.get("retrieval_priority", 50),
        "recency_weight": candidate.get("recency_weight", 0.5),
        "importance_weight": candidate.get("importance_weight", candidate.get("importance", 0.5)),
    }

    review = memory_review_queue.create_review_item(
        candidate_record=candidate_record,
        suggested_action="approve",
        created_by=reviewed_by,
        reason=candidate.get("why_candidate", "Thread-to-memory candidate requires Oracle review."),
        source_refs=[candidate.get("source_ref", "")],
    )

    updated = update_candidate(candidate_id, {
        "review_status": "enqueued",
        "review_id": review.get("review_id"),
        "enqueued_at": utc_now(),
        "enqueued_by": reviewed_by,
        "enqueue_notes": notes,
    })

    return {
        "status": "success",
        "candidate": updated,
        "review": review,
    }


def candidate_status() -> dict[str, Any]:
    candidates = load_candidates(include_enqueued=True)
    counts = {}

    for item in candidates:
        status = item.get("review_status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    return {
        "candidate_version": CANDIDATE_VERSION,
        "policy_version": POLICY_VERSION,
        "candidate_path": str(CANDIDATES_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "total_candidates": len(candidates),
        "counts": counts,
        "doctrine": [
            "Thread extraction creates candidates only.",
            "Candidates are not durable memory.",
            "Candidates must enter the review queue before promotion.",
            "Durable memory is created only after Oracle approval.",
        ],
    }
