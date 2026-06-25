from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

import memory_taxonomy


MEMORY_DIR = Path("logs/memory")
REVIEW_QUEUE_PATH = MEMORY_DIR / "review_queue.jsonl"
REVIEW_DECISIONS_PATH = MEMORY_DIR / "review_decisions.jsonl"

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


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def ensure_review_store():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not REVIEW_QUEUE_PATH.exists():
        REVIEW_QUEUE_PATH.write_text("", encoding="utf-8")
    if not REVIEW_DECISIONS_PATH.exists():
        REVIEW_DECISIONS_PATH.write_text("", encoding="utf-8")


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
    REVIEW_QUEUE_PATH.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in items) + ("\n" if items else ""),
        encoding="utf-8",
    )


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
    item = get_review_item(review_id)

    if not item:
        return None

    if item.get("review_status") not in {"pending", "edited", "deferred"}:
        raise ValueError(f"Review item is already closed with status {item.get('review_status')}")

    candidate = item.get("candidate_record", {})
    created_record = None

    # If this is a candidate memory record, approval writes it into real memory.
    if candidate and not candidate.get("record_id"):
        created_record = memory_taxonomy.create_memory_record(
            record_type=candidate.get("record_type"),
            layer=candidate.get("layer"),
            scope=candidate.get("scope"),
            title=candidate.get("title"),
            summary=candidate.get("summary"),
            body=candidate.get("body"),
            tags=candidate.get("tags", []),
            source_type=candidate.get("source_type", "review_queue"),
            source_ref=candidate.get("source_ref", review_id),
            source_title=candidate.get("source_title", "Memory Review Queue"),
            created_by=reviewed_by,
            provenance=candidate.get("provenance", f"Approved through review queue item {review_id}."),
            confidence=candidate.get("confidence", "medium"),
            status="active",
            review_state="oracle_approved",
            expires_at=candidate.get("expires_at"),
            risk_level=candidate.get("risk_level", "low"),
            supersedes=candidate.get("supersedes", []),
            attach_to_context=candidate.get("attach_to_context", False),
            retrieval_priority=candidate.get("retrieval_priority", 50),
            recency_weight=candidate.get("recency_weight", 0.5),
            importance_weight=candidate.get("importance_weight", 0.5),
        )

        item["record_id"] = created_record.get("record_id")

    item["review_status"] = "approved"
    item["reviewed_at"] = utc_now()
    item["reviewed_by"] = reviewed_by
    item["notes"] = notes

    update_review_item(review_id, item)

    decision = write_decision(
        review_id=review_id,
        decision="approved",
        reviewed_by=reviewed_by,
        notes=notes,
        record_id=item.get("record_id"),
    )

    return {
        "review": item,
        "decision": decision,
        "created_record": created_record,
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
