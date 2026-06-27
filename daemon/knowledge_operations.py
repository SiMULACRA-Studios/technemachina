from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OPERATIONS_PATH = (
    Path(__file__).resolve().parent.parent
    / "logs"
    / "knowledge"
    / "knowledge_operations.json"
)

OPERATION_LOCK = threading.RLock()
PENDING_STATES = {"prepared", "in_progress"}
VALID_STATES = {"prepared", "in_progress", "complete", "conflict"}


class KnowledgeOperationConflict(Exception):
    """A durable recovery operation conflicts with existing ledger state."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_request_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _empty_journal() -> dict[str, Any]:
    return {
        "journal_version": "knowledge_operations_v1",
        "operations": [],
    }


def _write_operations_atomically(journal: dict[str, Any]) -> None:
    OPERATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(journal, indent=2, sort_keys=True, ensure_ascii=False)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{OPERATIONS_PATH.name}.",
        suffix=".tmp",
        dir=str(OPERATIONS_PATH.parent),
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, OPERATIONS_PATH)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def load_journal() -> dict[str, Any]:
    if not OPERATIONS_PATH.exists():
        return _empty_journal()

    journal = json.loads(OPERATIONS_PATH.read_text(encoding="utf-8"))
    journal.setdefault("operations", [])
    return journal


def load_operations() -> list[dict[str, Any]]:
    return list(load_journal().get("operations", []))


def _save_operation(operation: dict[str, Any]) -> dict[str, Any]:
    journal = load_journal()
    operations = journal.setdefault("operations", [])

    for index, existing in enumerate(operations):
        if existing.get("operation_id") == operation.get("operation_id"):
            operations[index] = operation
            break
    else:
        operations.append(operation)

    _write_operations_atomically(journal)
    return operation


def _operation_by_id(operation_id: str) -> dict[str, Any]:
    for operation in load_operations():
        if operation.get("operation_id") == operation_id:
            return operation
    raise KnowledgeOperationConflict("knowledge_operation_conflict")


def pending_operations(operation_kind: str, request_fingerprint: str) -> list[dict[str, Any]]:
    return [
        operation
        for operation in load_operations()
        if operation.get("operation_kind") == operation_kind
        and operation.get("request_fingerprint") == request_fingerprint
        and operation.get("state") in PENDING_STATES
    ]


def get_single_pending_operation(
    operation_kind: str,
    request_fingerprint: str,
) -> dict[str, Any] | None:
    matches = pending_operations(operation_kind, request_fingerprint)
    if len(matches) > 1:
        raise KnowledgeOperationConflict("knowledge_operation_conflict")
    return matches[0] if matches else None


def prepare_operation(
    *,
    operation_kind: str,
    request_fingerprint: str,
    canonical_request_inputs: dict[str, Any],
    intended_identities: dict[str, Any],
    intended_effect_payloads: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    operation = {
        "operation_id": f"kop_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "operation_kind": operation_kind,
        "request_fingerprint": request_fingerprint,
        "state": "prepared",
        "created_at": now,
        "updated_at": now,
        "canonical_request_inputs": canonical_request_inputs,
        "intended_identities": intended_identities,
        "intended_effect_payloads": intended_effect_payloads,
        "effect_progress": {},
        "result_identity": {},
        "last_safe_error_code": "",
        "transition_history": [
            {
                "state": "prepared",
                "at": now,
                "detail": "operation_prepared",
            }
        ],
    }
    return _save_operation(operation)


def update_operation_intent(
    operation_id: str,
    *,
    canonical_request_inputs: dict[str, Any] | None = None,
    intended_identities: dict[str, Any] | None = None,
    intended_effect_payloads: dict[str, Any] | None = None,
) -> dict[str, Any]:
    operation = _operation_by_id(operation_id)
    if operation.get("state") not in PENDING_STATES:
        raise KnowledgeOperationConflict("knowledge_operation_conflict")

    if canonical_request_inputs is not None:
        operation["canonical_request_inputs"] = canonical_request_inputs
    if intended_identities is not None:
        operation["intended_identities"] = intended_identities
    if intended_effect_payloads is not None:
        operation["intended_effect_payloads"] = intended_effect_payloads

    now = utc_now()
    operation["state"] = "in_progress"
    operation["updated_at"] = now
    operation.setdefault("transition_history", []).append(
        {
            "state": "in_progress",
            "at": now,
            "detail": "intent_refreshed",
        }
    )
    return _save_operation(operation)


def record_operation_progress(
    operation_id: str,
    effect_name: str,
    *,
    result_identity: dict[str, Any] | None = None,
    safe_error_code: str = "",
) -> dict[str, Any]:
    operation = _operation_by_id(operation_id)
    if operation.get("state") not in PENDING_STATES:
        raise KnowledgeOperationConflict("knowledge_operation_conflict")

    now = utc_now()
    operation["state"] = "in_progress"
    operation["updated_at"] = now
    operation.setdefault("effect_progress", {})[effect_name] = {
        "state": "durable",
        "at": now,
    }
    if result_identity:
        operation.setdefault("result_identity", {}).update(result_identity)
    if safe_error_code:
        operation["last_safe_error_code"] = safe_error_code
    operation.setdefault("transition_history", []).append(
        {
            "state": "in_progress",
            "at": now,
            "detail": f"{effect_name}_durable",
        }
    )
    return _save_operation(operation)


def complete_operation(
    operation_id: str,
    *,
    result_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    operation = _operation_by_id(operation_id)
    if operation.get("state") == "conflict":
        raise KnowledgeOperationConflict("knowledge_operation_conflict")

    now = utc_now()
    operation["state"] = "complete"
    operation["updated_at"] = now
    if result_identity:
        operation.setdefault("result_identity", {}).update(result_identity)
    operation.setdefault("transition_history", []).append(
        {
            "state": "complete",
            "at": now,
            "detail": "operation_complete",
        }
    )
    return _save_operation(operation)


def mark_operation_conflict(
    operation_id: str,
    *,
    safe_error_code: str = "knowledge_operation_conflict",
) -> dict[str, Any]:
    operation = _operation_by_id(operation_id)
    now = utc_now()
    operation["state"] = "conflict"
    operation["updated_at"] = now
    operation["last_safe_error_code"] = safe_error_code
    operation.setdefault("transition_history", []).append(
        {
            "state": "conflict",
            "at": now,
            "detail": safe_error_code,
        }
    )
    return _save_operation(operation)


def operation_inventory() -> dict[str, Any]:
    operations = load_operations()
    counts = {"pending": 0, "complete": 0, "conflict": 0}
    items = []

    for operation in operations:
        state = operation.get("state", "")
        if state in PENDING_STATES:
            counts["pending"] += 1
        elif state == "complete":
            counts["complete"] += 1
        elif state == "conflict":
            counts["conflict"] += 1

        identities = operation.get("intended_identities", {})
        result = operation.get("result_identity", {})
        items.append(
            {
                "operation_id": operation.get("operation_id", ""),
                "operation_kind": operation.get("operation_kind", ""),
                "state": state,
                "intended_source_id": identities.get("source_id", ""),
                "intended_record_id": identities.get("record_id", ""),
                "candidate_id": identities.get("candidate_id", ""),
                "review_id": result.get("review_id", identities.get("review_id", "")),
                "effect_progress": operation.get("effect_progress", {}),
            }
        )

    return {
        "path": str(OPERATIONS_PATH),
        "counts": counts,
        "operations": items,
    }
