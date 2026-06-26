from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import uuid

MEMORY_DIR = Path("logs/memory")
MEMORY_RECORDS_PATH = MEMORY_DIR / "memory_records.jsonl"
MEMORY_INDEX_PATH = MEMORY_DIR / "memory_index.json"

CONTINUUM_LAYERS = {
    "gamma": {
        "name": "Gamma",
        "meaning": "Current message / immediate prompt context",
        "persistence": "ephemeral",
        "rule": "Short-lived. Keep small. Do not treat as long-term memory.",
    },
    "beta": {
        "name": "Beta",
        "meaning": "Current thread context",
        "persistence": "thread-scoped",
        "rule": "Thread memory. Promote only if it helps current thread coherence.",
    },
    "alpha": {
        "name": "Alpha",
        "meaning": "Recent episodes, project events, active risks, recent decisions",
        "persistence": "recent",
        "rule": "Store recent build events, decisions, and operational notes.",
    },
    "theta": {
        "name": "Theta",
        "meaning": "Stable project knowledge, architecture facts, conventions, validated preferences",
        "persistence": "long-term",
        "rule": "Stable knowledge. Requires provenance and confidence.",
    },
    "delta": {
        "name": "Delta",
        "meaning": "Doctrine, genome, procedures, rules, safety commitments",
        "persistence": "governance",
        "rule": "Hardest layer to change. Requires explicit Oracle approval.",
    },
}

MEMORY_TYPES = {
    "thread_memory": "A promoted thread detail that may matter beyond one exchange.",
    "project_fact": "A stable fact about the project.",
    "decision": "A choice made by the Oracle or build process.",
    "procedure": "A repeatable operational step or command sequence.",
    "research_note": "A research finding, repo pattern, or architecture note.",
    "external_reference": "A reference to an external tool, repo, document, or source.",
    "risk_note": "A security, safety, reliability, or failure-mode observation.",
    "doctrine_note": "A rule or principle that affects future behavior.",
}

SCOPES = {
    "thread": "Attached to one thread.",
    "project": "Attached to the Technemachina project.",
    "global_doctrine": "Affects doctrine or global daemon behavior.",
}

STATUS_ENUM = {
    "active": "Usable memory.",
    "draft": "Captured but not fully trusted.",
    "superseded": "Replaced by a newer record.",
    "revoked": "Hidden from normal retrieval but preserved for auditability.",
    "expired": "No longer current due to time or scope.",
}

REVIEW_STATES = {
    "unreviewed": "Not yet reviewed.",
    "oracle_approved": "Approved by the Oracle.",
    "needs_review": "Should not be promoted further until reviewed.",
}

RISK_LEVELS = {"low", "medium", "high"}

CONFIDENCE_LEVELS = {"low", "medium", "high"}

ALLOWED_TRANSITIONS = {
    "gamma": ["beta", "alpha"],
    "beta": ["alpha", "theta"],
    "alpha": ["theta", "delta"],
    "theta": ["delta"],
    "delta": [],
}

WRITE_RULES = {
    "gamma": "May be captured automatically later, but not persisted as long-term memory by default.",
    "beta": "May be created from thread context. Should stay thread-scoped unless promoted.",
    "alpha": "May store recent project events and decisions with provenance.",
    "theta": "Requires stable source and clear reason for promotion.",
    "delta": "Requires explicit Oracle approval and should be versioned carefully.",
}

SENSITIVE_TYPES = {"doctrine_note", "risk_note"}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def ensure_memory_store():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_RECORDS_PATH.exists():
        MEMORY_RECORDS_PATH.write_text("", encoding="utf-8")
    if not MEMORY_INDEX_PATH.exists():
        MEMORY_INDEX_PATH.write_text(json.dumps(empty_index(), indent=2), encoding="utf-8")

def empty_index():
    return {
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "record_count": 0,
        "revoked_count": 0,
        "types": {},
        "layers": {},
        "scopes": {},
        "statuses": {},
        "tags": {},
    }

def make_hash(payload: dict) -> str:
    stable = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()

@dataclass
class MemoryRecord:
    # Identity
    record_id: str
    record_type: str
    layer: str
    scope: str
    title: str

    # Content
    summary: str
    body: str
    tags: list[str] = field(default_factory=list)

    # Provenance
    source_type: str = "manual"
    source_ref: str = ""
    source_title: str = ""
    created_by: str = "Oracle"
    provenance: str = ""

    # Trust and safety
    confidence: str = "medium"
    status: str = "active"
    review_state: str = "oracle_approved"
    expires_at: str | None = None
    risk_level: str = "low"

    # Change control
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    supersedes: list[str] = field(default_factory=list)
    superseded_by: list[str] = field(default_factory=list)
    revocation_reason: str = ""

    # Routing
    attach_to_context: bool = False
    retrieval_priority: int = 50
    recency_weight: float = 0.5
    importance_weight: float = 0.5

    # Immutable content hash
    hash: str = ""

def validate_memory(record: dict):
    if record["record_type"] not in MEMORY_TYPES:
        raise ValueError(f"Unknown record_type: {record['record_type']}")
    if record["layer"] not in CONTINUUM_LAYERS:
        raise ValueError(f"Unknown layer: {record['layer']}")
    if record["scope"] not in SCOPES:
        raise ValueError(f"Unknown scope: {record['scope']}")
    if record["confidence"] not in CONFIDENCE_LEVELS:
        raise ValueError("confidence must be low, medium, or high")
    if record["status"] not in STATUS_ENUM:
        raise ValueError(f"Unknown status: {record['status']}")
    if record["review_state"] not in REVIEW_STATES:
        raise ValueError(f"Unknown review_state: {record['review_state']}")
    if record["risk_level"] not in RISK_LEVELS:
        raise ValueError("risk_level must be low, medium, or high")

    # Non-Gamma records need provenance. Gamma is ephemeral and may be looser later.
    if record["layer"] != "gamma" and not record.get("source_ref"):
        raise ValueError("source_ref is required for non-Gamma memory records.")

    if record["layer"] == "delta" and record["review_state"] != "oracle_approved":
        raise ValueError("Delta memory requires oracle_approved review_state.")

    if record["record_type"] in SENSITIVE_TYPES and record["review_state"] != "oracle_approved":
        raise ValueError("Sensitive memory types require oracle_approved review_state.")

def load_records(include_revoked: bool = False):
    ensure_memory_store()
    records = []

    for line in MEMORY_RECORDS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not include_revoked and record.get("status") != "active":
            continue
        records.append(record)

    return records

def rebuild_index():
    ensure_memory_store()
    all_records = load_records(include_revoked=True)
    index = empty_index()

    active_records = [r for r in all_records if r.get("status") == "active"]
    revoked_records = [r for r in all_records if r.get("status") == "revoked"]

    index["record_count"] = len(active_records)
    index["revoked_count"] = len(revoked_records)

    for record in active_records:
        for key, bucket_name in [
            ("record_type", "types"),
            ("layer", "layers"),
            ("scope", "scopes"),
            ("status", "statuses"),
        ]:
            value = record.get(key, "unknown")
            index[bucket_name][value] = index[bucket_name].get(value, 0) + 1

        for tag in record.get("tags", []):
            index["tags"][tag] = index["tags"].get(tag, 0) + 1

    MEMORY_INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index

def create_memory_record(
    record_type: str,
    layer: str,
    scope: str,
    title: str,
    summary: str,
    body: str,
    tags: list[str] | None = None,
    source_type: str = "manual",
    source_ref: str = "",
    source_title: str = "",
    created_by: str = "Oracle",
    provenance: str = "",
    confidence: str = "medium",
    status: str = "active",
    review_state: str = "oracle_approved",
    expires_at: str | None = None,
    risk_level: str = "low",
    supersedes: list[str] | None = None,
    attach_to_context: bool = False,
    retrieval_priority: int = 50,
    recency_weight: float = 0.5,
    importance_weight: float = 0.5,
):
    ensure_memory_store()

    record = MemoryRecord(
        record_id=f"mem_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
        record_type=record_type,
        layer=layer,
        scope=scope,
        title=title.strip(),
        summary=summary.strip(),
        body=body.strip(),
        tags=tags or [],
        source_type=source_type.strip() or "manual",
        source_ref=source_ref.strip(),
        source_title=source_title.strip(),
        created_by=created_by.strip() or "Oracle",
        provenance=provenance.strip(),
        confidence=confidence,
        status=status,
        review_state=review_state,
        expires_at=expires_at,
        risk_level=risk_level,
        supersedes=supersedes or [],
        attach_to_context=attach_to_context,
        retrieval_priority=int(retrieval_priority),
        recency_weight=float(recency_weight),
        importance_weight=float(importance_weight),
    )

    payload = asdict(record)
    validate_memory(payload)

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
    payload["hash"] = make_hash(hash_payload)

    with MEMORY_RECORDS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    rebuild_index()
    return payload

def revoke_memory(record_id: str, reason: str = ""):
    ensure_memory_store()
    records = load_records(include_revoked=True)
    updated = None

    for record in records:
        if record.get("record_id") == record_id:
            record["status"] = "revoked"
            record["updated_at"] = utc_now()
            record["revocation_reason"] = reason
            updated = record
            break

    if not updated:
        return None

    MEMORY_RECORDS_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8"
    )

    rebuild_index()
    return updated

def taxonomy_summary():
    ensure_memory_store()
    index = rebuild_index()
    return {
        "continuum_layers": CONTINUUM_LAYERS,
        "record_types": MEMORY_TYPES,
        "scopes": SCOPES,
        "statuses": STATUS_ENUM,
        "review_states": REVIEW_STATES,
        "risk_levels": sorted(RISK_LEVELS),
        "confidence_levels": sorted(CONFIDENCE_LEVELS),
        "allowed_transitions": ALLOWED_TRANSITIONS,
        "write_rules": WRITE_RULES,
        "sensitive_types": sorted(SENSITIVE_TYPES),
        "storage": {
            "memory_records": str(MEMORY_RECORDS_PATH),
            "memory_index": str(MEMORY_INDEX_PATH),
        },
        "index": index,
        "doctrine": [
            "Threads are not memory.",
            "Memory is promoted from threads or entered manually.",
            "Every memory record must have provenance.",
            "Non-Gamma memory requires source_ref.",
            "Delta/doctrine memory requires Oracle approval.",
            "Revocation hides memory without destroying auditability.",
            "Future retrieval must explain why a memory was selected.",
            "Memory is a ledger, not a generic notes database.",
        ],
    }
