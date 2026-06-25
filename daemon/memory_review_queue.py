from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import threading
import uuid

import memory_taxonomy


MEMORY_DIR = Path("logs/memory")
REVIEW_QUEUE_PATH = MEMORY_DIR / "review_queue.jsonl"
REVIEW_DECISIONS_PATH = MEMORY_DIR / "review_decisions.jsonl"
APPROVAL_OPERATIONS_PATH = MEMORY_DIR / "approval_operations.jsonl"

REVIEW_QUEUE_VERSION = "v0.2.7c"
POLICY_VERSION = "memory_review_policy_v1"

REVIEW_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "edited",
    "deferred",
}

SUGGESTED_ACTIONS = {
    "approve",
    "edit",
    "reject",
    "merge",
    "defer",
    "promote",
    "decay",
    "refresh",
    "revoke",
}

HIGH_TRUST_LAYERS = {"theta", "delta"}
HIGH_RISK_TYPES = {"doctrine_note", "risk_note", "procedure"}
_APPROVAL_LOCK = threading.RLock()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def ensure_review_store():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not REVIEW_QUEUE_PATH.exists():
        REVIEW_QUEUE_PATH.write_text("", encoding="utf-8")
    if not REVIEW_DECISIONS_PATH.exists():
        REVIEW_DECISIONS_PATH.write_text("", encoding="utf-8")
    if not APPROVAL_OPERATIONS_PATH.exists():
        APPROVAL_OPERATIONS_PATH.write_text("", encoding="utf-8")


def _atomic_write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, path)


def _atomic_write_jsonl(path: Path, rows: list[dict]):
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    _atomic_write_text(path, text + ("\n" if rows else ""))


def load_queue(include_closed: bool = False):
    ensure_review_store()
    items = []

    for line in REVIEW_QUEUE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        item = json.loads(line)

        if not include_closed and item.get("review_status") not in {"pending", "edited", "deferred"}:
            continue

        items.append(item)

    return items


def save_queue(items: list[dict]):
    ensure_review_store()
    _atomic_write_jsonl(REVIEW_QUEUE_PATH, items)


def load_decisions(limit: int = 100):
    ensure_review_store()
    rows = []

    for line in REVIEW_DECISIONS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))

    return rows[-max(1, min(int(limit), 1000)):]


def write_decision(review_id: str, decision: str, reviewed_by: str = "Oracle", notes: str = "", record_id: str | None = None):
    ensure_review_store()

    entry = {
        "decision_id": f"rd_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "review_id": review_id,
        "decision": decision,
        "reviewed_by": reviewed_by,
        "reviewed_at": utc_now(),
        "notes": notes,
        "record_id": record_id,
        "queue_version": REVIEW_QUEUE_VERSION,
        "policy_version": POLICY_VERSION,
    }

    with REVIEW_DECISIONS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def _load_approval_operations() -> list[dict]:
    ensure_review_store()
    rows = []

    for line in APPROVAL_OPERATIONS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))

    return rows


def _save_approval_operations(rows: list[dict]):
    ensure_review_store()
    _atomic_write_jsonl(APPROVAL_OPERATIONS_PATH, rows)


def _candidate_identity(candidate: dict) -> str:
    stable = json.dumps(candidate or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _stable_approval_ids(review_id: str, item: dict) -> dict:
    candidate = item.get("candidate_record", {}) or {}
    intended_record_id = (
        item.get("record_id")
        or candidate.get("record_id")
        or f"mem_{review_id}_approved"
    )
    return {
        "operation_id": f"approval_{review_id}",
        "memory_record_id": intended_record_id,
        "decision_id": f"rd_{review_id}_approved",
        "candidate_identity": _candidate_identity(candidate),
    }


def _find_approval_operation(review_id: str) -> dict | None:
    operation_id = f"approval_{review_id}"
    for operation in _load_approval_operations():
        if operation.get("operation_id") == operation_id:
            return operation
    return None


def _upsert_approval_operation(operation: dict):
    rows = _load_approval_operations()
    for index, row in enumerate(rows):
        if row.get("operation_id") == operation.get("operation_id"):
            rows[index] = operation
            break
    else:
        rows.append(operation)
    _save_approval_operations(rows)
    return operation


def _ensure_approval_operation(review_id: str, item: dict, reviewed_by: str, notes: str) -> dict:
    ids = _stable_approval_ids(review_id, item)
    existing = _find_approval_operation(review_id)
    now = utc_now()

    if existing:
        if existing.get("candidate_identity") != ids["candidate_identity"]:
            raise ValueError("approval_operation_candidate_mismatch")
        return existing

    operation = {
        "operation_id": ids["operation_id"],
        "review_id": review_id,
        "candidate_identity": ids["candidate_identity"],
        "intended_memory_record_id": ids["memory_record_id"],
        "intended_decision_id": ids["decision_id"],
        "stage": "operation_started",
        "status": "incomplete",
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "reviewed_by": reviewed_by,
        "notes": notes,
        "error": "",
    }
    return _upsert_approval_operation(operation)


def _mark_approval_operation(operation: dict, stage: str, status: str = "incomplete", error: str = "") -> dict:
    operation = dict(operation)
    operation["stage"] = stage
    operation["status"] = status
    operation["updated_at"] = utc_now()
    operation["error"] = error
    if status == "complete":
        operation["completed_at"] = operation["updated_at"]
    return _upsert_approval_operation(operation)


def _load_all_memory_records() -> list[dict]:
    memory_taxonomy.ensure_memory_store()
    rows = []
    for line in memory_taxonomy.MEMORY_RECORDS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _save_memory_records(rows: list[dict]):
    memory_taxonomy.ensure_memory_store()
    _atomic_write_jsonl(memory_taxonomy.MEMORY_RECORDS_PATH, rows)


def _find_memory_record(record_id: str) -> dict | None:
    for record in _load_all_memory_records():
        if record.get("record_id") == record_id:
            return record
    return None


def _memory_hash(payload: dict) -> str:
    hash_payload = {
        "record_id": payload["record_id"],
        "record_type": payload["record_type"],
        "layer": payload["layer"],
        "scope": payload["scope"],
        "title": payload["title"],
        "summary": payload["summary"],
        "body": payload["body"],
        "source_type": payload["source_type"],
        "source_ref": payload["source_ref"],
        "created_at": payload["created_at"],
    }
    return memory_taxonomy.make_hash(hash_payload)


def _approval_memory_payload(operation: dict, item: dict, reviewed_by: str) -> dict:
    candidate = item.get("candidate_record", {}) or {}
    now = utc_now()
    payload = {
        "record_id": operation["intended_memory_record_id"],
        "record_type": candidate.get("record_type"),
        "layer": candidate.get("layer"),
        "scope": candidate.get("scope"),
        "title": str(candidate.get("title", "")).strip(),
        "summary": str(candidate.get("summary", "")).strip(),
        "body": str(candidate.get("body", "")).strip(),
        "tags": candidate.get("tags", []),
        "source_type": str(candidate.get("source_type", "review_queue")).strip() or "review_queue",
        "source_ref": str(candidate.get("source_ref", item.get("review_id"))).strip(),
        "source_title": str(candidate.get("source_title", "Memory Review Queue")).strip(),
        "created_by": (reviewed_by or "Oracle").strip() or "Oracle",
        "provenance": str(candidate.get(
            "provenance",
            f"Approved through review queue item {item.get('review_id')}.",
        )).strip(),
        "confidence": candidate.get("confidence", "medium"),
        "status": "active",
        "review_state": "oracle_approved",
        "expires_at": candidate.get("expires_at"),
        "risk_level": candidate.get("risk_level", "low"),
        "created_at": now,
        "updated_at": now,
        "supersedes": candidate.get("supersedes", []),
        "superseded_by": [],
        "revocation_reason": "",
        "attach_to_context": candidate.get("attach_to_context", False),
        "retrieval_priority": int(candidate.get("retrieval_priority", 50)),
        "recency_weight": float(candidate.get("recency_weight", 0.5)),
        "importance_weight": float(candidate.get("importance_weight", 0.5)),
        "hash": "",
    }
    payload["hash"] = _memory_hash(payload)
    memory_taxonomy.validate_memory(payload)
    return payload


def _ensure_approval_memory(operation: dict, item: dict, reviewed_by: str) -> dict | None:
    candidate = item.get("candidate_record", {}) or {}
    record_id = operation.get("intended_memory_record_id")

    if candidate.get("record_id"):
        existing = _find_memory_record(record_id)
        if not existing:
            raise ValueError("approval_target_memory_missing")
        return existing

    records = _load_all_memory_records()
    for record in records:
        if record.get("record_id") == record_id:
            return record

    payload = _approval_memory_payload(operation, item, reviewed_by)
    records.append(payload)
    _save_memory_records(records)
    return payload


def _load_all_decisions() -> list[dict]:
    ensure_review_store()
    rows = []
    for line in REVIEW_DECISIONS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _save_decisions(rows: list[dict]):
    ensure_review_store()
    _atomic_write_jsonl(REVIEW_DECISIONS_PATH, rows)


def _find_approval_decision(decision_id: str) -> dict | None:
    for decision in _load_all_decisions():
        if decision.get("decision_id") == decision_id:
            return decision
    return None


def _ensure_approval_decision(operation: dict, reviewed_by: str, notes: str) -> dict:
    existing = _find_approval_decision(operation["intended_decision_id"])
    if existing:
        return existing

    decision = {
        "decision_id": operation["intended_decision_id"],
        "review_id": operation["review_id"],
        "decision": "approved",
        "reviewed_by": reviewed_by,
        "reviewed_at": utc_now(),
        "notes": notes,
        "record_id": operation["intended_memory_record_id"],
        "queue_version": REVIEW_QUEUE_VERSION,
        "policy_version": POLICY_VERSION,
        "operation_id": operation["operation_id"],
    }
    rows = _load_all_decisions()
    rows.append(decision)
    _save_decisions(rows)
    return decision


def _index_contains_active_record(record_id: str) -> bool:
    if not memory_taxonomy.MEMORY_INDEX_PATH.exists():
        return False
    try:
        index = json.loads(memory_taxonomy.MEMORY_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    records = _load_all_memory_records()
    active_ids = {r.get("record_id") for r in records if r.get("status") == "active"}
    return record_id in active_ids and index.get("record_count", 0) == len(active_ids)


def _approval_effects_complete(item: dict, operation: dict) -> bool:
    record = _find_memory_record(operation["intended_memory_record_id"])
    decision = _find_approval_decision(operation["intended_decision_id"])
    return (
        item.get("review_status") == "approved"
        and bool(decision)
        and bool(record)
        and record.get("status") == "active"
        and _index_contains_active_record(record.get("record_id"))
        and operation.get("status") == "complete"
    )


def _approval_has_incomplete_recoverable_state(item: dict, operation: dict) -> bool:
    if item.get("review_status") != "approved":
        return False
    return not _approval_effects_complete(item, operation)


def reason_for_review(candidate_record: dict, suggested_action: str = "approve"):
    reasons = []

    layer = candidate_record.get("layer", "")
    record_type = candidate_record.get("record_type", "")
    confidence = candidate_record.get("confidence", "medium")
    source_ref = candidate_record.get("source_ref", "")
    provenance = candidate_record.get("provenance", "")
    risk_level = candidate_record.get("risk_level", "low")

    if layer in HIGH_TRUST_LAYERS:
        reasons.append(f"{layer} layer requires review before durable trust")

    if record_type in HIGH_RISK_TYPES:
        reasons.append(f"{record_type} may affect doctrine, risk, or procedure")

    if confidence != "high":
        reasons.append(f"confidence is {confidence}")

    if not source_ref:
        reasons.append("missing source_ref")

    if not provenance:
        reasons.append("missing provenance")

    if risk_level != "low":
        reasons.append(f"risk_level is {risk_level}")

    if suggested_action in {"merge", "promote", "decay", "refresh", "revoke"}:
        reasons.append(f"suggested action {suggested_action} changes memory state")

    if not reasons:
        reasons.append("human approval requested before memory activation")

    return "; ".join(reasons)


def build_diff(original_record: dict | None, proposed_record: dict | None):
    original_record = original_record or {}
    proposed_record = proposed_record or {}

    keys = sorted(set(original_record.keys()).union(set(proposed_record.keys())))
    diff = {}

    for key in keys:
        old = original_record.get(key)
        new = proposed_record.get(key)

        if old != new:
            diff[key] = {
                "old": old,
                "new": new,
            }

    return diff


def create_review_item(
    candidate_record: dict,
    suggested_action: str = "approve",
    reason: str = "",
    source_refs: list[str] | None = None,
    conflicting_record_ids: list[str] | None = None,
    related_record_ids: list[str] | None = None,
    original_record: dict | None = None,
    created_by: str = "consolidation_worker",
):
    ensure_review_store()

    if suggested_action not in SUGGESTED_ACTIONS:
        raise ValueError(f"Unknown suggested_action: {suggested_action}")

    review_id = f"rev_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    item = {
        "review_id": review_id,
        "record_id": candidate_record.get("record_id"),
        "record_type": candidate_record.get("record_type"),
        "layer": candidate_record.get("layer"),
        "scope": candidate_record.get("scope"),
        "title": candidate_record.get("title", ""),
        "summary": candidate_record.get("summary", ""),
        "reason_for_review": reason or reason_for_review(candidate_record, suggested_action),
        "provenance": candidate_record.get("provenance", ""),
        "confidence": candidate_record.get("confidence", "medium"),
        "risk_level": candidate_record.get("risk_level", "low"),
        "suggested_action": suggested_action,
        "review_status": "pending",
        "created_at": utc_now(),
        "reviewed_at": None,
        "reviewed_by": "",
        "notes": "",
        "diff": build_diff(original_record, candidate_record),
        "source_refs": source_refs or ([candidate_record.get("source_ref")] if candidate_record.get("source_ref") else []),
        "conflicting_record_ids": conflicting_record_ids or [],
        "related_record_ids": related_record_ids or [],
        "candidate_record": candidate_record,
        "original_record": original_record or {},
        "created_by": created_by,
        "queue_version": REVIEW_QUEUE_VERSION,
        "policy_version": POLICY_VERSION,
    }

    items = load_queue(include_closed=True)
    items.append(item)
    save_queue(items)

    return item


def get_review_item(review_id: str):
    for item in load_queue(include_closed=True):
        if item.get("review_id") == review_id:
            return item
    return None


def update_review_item(review_id: str, updated_item: dict):
    items = load_queue(include_closed=True)
    found = False

    for index, item in enumerate(items):
        if item.get("review_id") == review_id:
            items[index] = updated_item
            found = True
            break

    if not found:
        return None

    save_queue(items)
    return updated_item


def approve_review(review_id: str, reviewed_by: str = "Oracle", notes: str = ""):
    with _APPROVAL_LOCK:
        item = get_review_item(review_id)

        if not item:
            return None

        operation = _ensure_approval_operation(review_id, item, reviewed_by, notes)

        if item.get("review_status") not in {"pending", "edited", "deferred"}:
            if _approval_effects_complete(item, operation):
                raise ValueError(f"Review item is already closed with status {item.get('review_status')}")
            if not _approval_has_incomplete_recoverable_state(item, operation):
                raise ValueError(f"Review item is already closed with status {item.get('review_status')}")

        decision = _ensure_approval_decision(operation, reviewed_by, notes)
        operation = _mark_approval_operation(operation, "decision_recorded")

        created_record = _ensure_approval_memory(operation, item, reviewed_by)
        operation = _mark_approval_operation(operation, "memory_active")

        item = get_review_item(review_id)
        if not item:
            return None

        item["record_id"] = operation.get("intended_memory_record_id")
        item["review_status"] = "approved"
        item["reviewed_at"] = item.get("reviewed_at") or utc_now()
        item["reviewed_by"] = reviewed_by
        item["notes"] = notes

        update_review_item(review_id, item)
        operation = _mark_approval_operation(operation, "review_approved")

        memory_taxonomy.rebuild_index()
        operation = _mark_approval_operation(operation, "memory_indexed")

        operation = _mark_approval_operation(operation, "complete", status="complete")

        return {
            "review": item,
            "decision": decision,
            "created_record": created_record,
            "approval_operation": operation,
        }


def reject_review(review_id: str, reviewed_by: str = "Oracle", notes: str = ""):
    item = get_review_item(review_id)

    if not item:
        return None

    if item.get("review_status") not in {"pending", "edited", "deferred"}:
        raise ValueError(f"Review item is already closed with status {item.get('review_status')}")

    item["review_status"] = "rejected"
    item["reviewed_at"] = utc_now()
    item["reviewed_by"] = reviewed_by
    item["notes"] = notes

    update_review_item(review_id, item)

    decision = write_decision(
        review_id=review_id,
        decision="rejected",
        reviewed_by=reviewed_by,
        notes=notes,
        record_id=item.get("record_id"),
    )

    return {
        "review": item,
        "decision": decision,
    }


def defer_review(review_id: str, reviewed_by: str = "Oracle", notes: str = ""):
    item = get_review_item(review_id)

    if not item:
        return None

    if item.get("review_status") not in {"pending", "edited", "deferred"}:
        raise ValueError(f"Review item is already closed with status {item.get('review_status')}")

    item["review_status"] = "deferred"
    item["reviewed_at"] = utc_now()
    item["reviewed_by"] = reviewed_by
    item["notes"] = notes

    update_review_item(review_id, item)

    decision = write_decision(
        review_id=review_id,
        decision="deferred",
        reviewed_by=reviewed_by,
        notes=notes,
        record_id=item.get("record_id"),
    )

    return {
        "review": item,
        "decision": decision,
    }


def edit_review(review_id: str, patch: dict, reviewed_by: str = "Oracle", notes: str = ""):
    item = get_review_item(review_id)

    if not item:
        return None

    if item.get("review_status") not in {"pending", "edited", "deferred"}:
        raise ValueError(f"Review item is already closed with status {item.get('review_status')}")

    candidate = item.get("candidate_record", {})
    original_candidate = dict(candidate)

    for key, value in patch.items():
        candidate[key] = value

    item["candidate_record"] = candidate
    item["diff"] = build_diff(item.get("original_record", {}), candidate)
    item["review_status"] = "edited"
    item["reviewed_at"] = utc_now()
    item["reviewed_by"] = reviewed_by
    item["notes"] = notes or "Candidate record edited."

    update_review_item(review_id, item)

    decision = write_decision(
        review_id=review_id,
        decision="edited",
        reviewed_by=reviewed_by,
        notes=notes,
        record_id=item.get("record_id"),
    )

    return {
        "review": item,
        "decision": decision,
        "previous_candidate": original_candidate,
    }


def review_status():
    ensure_review_store()
    all_items = load_queue(include_closed=True)

    counts = {}
    for item in all_items:
        status = item.get("review_status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    return {
        "queue_version": REVIEW_QUEUE_VERSION,
        "policy_version": POLICY_VERSION,
        "queue_path": str(REVIEW_QUEUE_PATH),
        "decisions_path": str(REVIEW_DECISIONS_PATH),
        "total_items": len(all_items),
        "counts": counts,
        "pending_count": counts.get("pending", 0),
        "doctrine": [
            "The review queue is not permanent memory.",
            "Approval writes candidate memory into the durable memory ledger.",
            "Rejection preserves the decision trail without activating the memory.",
            "Theta and Delta changes should pass human review.",
            "Doctrine changes must not auto-promote without Oracle approval.",
        ],
    }
