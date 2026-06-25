from datetime import datetime, timezone
from pathlib import Path
import json
import re
import uuid

import memory_taxonomy


MEMORY_DIR = Path("logs/memory")
CONSOLIDATION_JOURNAL_PATH = MEMORY_DIR / "consolidation_journal.jsonl"
ENTITY_INDEX_PATH = MEMORY_DIR / "entity_index.json"

WORKER_VERSION = "v0.2.7b"
POLICY_VERSION = "memory_consolidation_policy_v1"

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "into", "from", "are", "not",
    "you", "your", "was", "were", "has", "have", "had", "but", "about",
    "memory", "record", "records", "technemachina", "daemon"
}

ACTION_TYPES = {
    "scan": "Worker inspected memory state.",
    "extract_candidate": "Potential atomic fact candidate.",
    "merge_candidate": "Possible duplicate or overlapping memory.",
    "promote_candidate": "Possible upward promotion candidate.",
    "decay_candidate": "Potential confidence/freshness decay candidate.",
    "refresh_candidate": "Potential revalidation or timestamp refresh candidate.",
    "revoke_candidate": "Potential revocation candidate; requires review.",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def ensure_worker_store():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not CONSOLIDATION_JOURNAL_PATH.exists():
        CONSOLIDATION_JOURNAL_PATH.write_text("", encoding="utf-8")
    if not ENTITY_INDEX_PATH.exists():
        ENTITY_INDEX_PATH.write_text(json.dumps({
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "entity_count": 0,
            "entities": {},
        }, indent=2), encoding="utf-8")


def tokenize(text: str) -> list[str]:
    cleaned = []
    for token in re.findall(r"[a-zA-Z0-9_#.-]+", text or ""):
        token = token.lower().strip(".,;:!?()[]{}<>\\\"'")
        if len(token) > 2 and token not in STOPWORDS:
            cleaned.append(token)
    return cleaned


def canonical_entity(value: str) -> str:
    tokens = tokenize(value)
    if not tokens:
        return ""
    return "_".join(tokens[:6])


def extract_entities(record: dict) -> list[str]:
    candidates = []

    for field in ["title", "summary", "source_title", "record_type", "layer", "scope"]:
        value = record.get(field, "")
        entity = canonical_entity(value)
        if entity:
            candidates.append(entity)

    for tag in record.get("tags", []):
        entity = canonical_entity(str(tag))
        if entity:
            candidates.append(entity)

    return sorted(set(candidates))


def record_terms(record: dict) -> set[str]:
    text = " ".join([
        record.get("title", ""),
        record.get("summary", ""),
        record.get("body", ""),
        " ".join(record.get("tags", [])),
        record.get("source_title", ""),
        record.get("provenance", ""),
    ])
    return set(tokenize(text))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a.intersection(b)) / len(a.union(b))


def load_journal(limit: int = 50):
    ensure_worker_store()
    rows = []
    for line in CONSOLIDATION_JOURNAL_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows[-max(1, min(int(limit), 500)):]


def write_journal_entry(
    action_type: str,
    source_record_ids: list[str] | None = None,
    target_record_id: str | None = None,
    reason: str = "",
    confidence_before: str | None = None,
    confidence_after: str | None = None,
    entity_resolution: dict | None = None,
    duplicate_group_id: str | None = None,
    human_review_required: bool = True,
    proposal: dict | None = None,
):
    ensure_worker_store()

    entry = {
        "journal_id": f"cj_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "timestamp": utc_now(),
        "worker_version": WORKER_VERSION,
        "policy_version": POLICY_VERSION,
        "action_type": action_type,
        "source_record_ids": source_record_ids or [],
        "target_record_id": target_record_id,
        "reason": reason,
        "confidence_before": confidence_before,
        "confidence_after": confidence_after,
        "entity_resolution": entity_resolution or {},
        "duplicate_group_id": duplicate_group_id,
        "human_review_required": human_review_required,
        "proposal": proposal or {},
    }

    with CONSOLIDATION_JOURNAL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def load_records_read_only(include_revoked: bool = False) -> list[dict]:
    if not memory_taxonomy.MEMORY_RECORDS_PATH.exists():
        return []

    records = []
    for line in memory_taxonomy.MEMORY_RECORDS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        record = json.loads(line)
        if not include_revoked and record.get("status") == "revoked":
            continue
        records.append(record)

    return records


def build_entity_index(records: list[dict]) -> dict:
    entities = {}

    for record in records:
        record_id = record.get("record_id")
        if not record_id:
            continue

        extracted = extract_entities(record)

        for entity in extracted:
            bucket = entities.setdefault(entity, {
                "entity": entity,
                "record_ids": [],
                "layers": {},
                "types": {},
                "tags": {},
            })

            bucket["record_ids"].append(record_id)

            layer = record.get("layer", "unknown")
            record_type = record.get("record_type", "unknown")

            bucket["layers"][layer] = bucket["layers"].get(layer, 0) + 1
            bucket["types"][record_type] = bucket["types"].get(record_type, 0) + 1

            for tag in record.get("tags", []):
                bucket["tags"][tag] = bucket["tags"].get(tag, 0) + 1

    index = {
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "entity_count": len(entities),
        "entities": entities,
    }

    return index


def rebuild_entity_index(records: list[dict] | None = None):
    ensure_worker_store()

    if records is None:
        records = memory_taxonomy.load_records(include_revoked=False)

    index = build_entity_index(records)
    ENTITY_INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index


def find_merge_candidates(records: list[dict], similarity_threshold: float = 0.55):
    candidates = []

    active = [r for r in records if r.get("status") == "active"]

    for i, left in enumerate(active):
        for right in active[i + 1:]:
            if left.get("record_type") != right.get("record_type"):
                continue
            if left.get("scope") != right.get("scope"):
                continue

            score = jaccard(record_terms(left), record_terms(right))

            if score >= similarity_threshold:
                group_id = f"dup_{uuid.uuid4().hex[:8]}"
                candidates.append({
                    "action_type": "merge_candidate",
                    "source_record_ids": [left.get("record_id"), right.get("record_id")],
                    "target_record_id": left.get("record_id"),
                    "duplicate_group_id": group_id,
                    "similarity_score": round(score, 4),
                    "reason": "Records share high term overlap and same type/scope.",
                    "human_review_required": True,
                })

    return candidates


def find_promotion_candidates(records: list[dict]):
    candidates = []

    for record in records:
        if record.get("status") != "active":
            continue

        layer = record.get("layer")
        confidence = record.get("confidence")
        importance = float(record.get("importance_weight", 0.5) or 0.5)

        if layer == "alpha" and confidence == "high" and importance >= 0.75:
            candidates.append({
                "action_type": "promote_candidate",
                "source_record_ids": [record.get("record_id")],
                "target_layer": "theta",
                "reason": "High-confidence Alpha record with high importance may be stable project knowledge.",
                "human_review_required": True,
            })

        if layer == "theta" and record.get("record_type") in {"doctrine_note", "procedure"}:
            candidates.append({
                "action_type": "promote_candidate",
                "source_record_ids": [record.get("record_id")],
                "target_layer": "delta",
                "reason": "Theta doctrine/procedure may belong in Delta governance after Oracle review.",
                "human_review_required": True,
            })

    return candidates


def find_decay_candidates(records: list[dict]):
    candidates = []

    temporal_types = {"thread_memory", "research_note", "external_reference"}

    for record in records:
        if record.get("status") != "active":
            continue

        if record.get("record_type") not in temporal_types:
            continue

        if record.get("confidence") == "high":
            continue

        candidates.append({
            "action_type": "decay_candidate",
            "source_record_ids": [record.get("record_id")],
            "reason": "Temporal or externally sourced memory may require freshness review over time.",
            "confidence_before": record.get("confidence"),
            "confidence_after": "low" if record.get("confidence") == "medium" else record.get("confidence"),
            "human_review_required": True,
        })

    return candidates


def find_refresh_candidates(records: list[dict]):
    candidates = []

    for record in records:
        if record.get("status") != "active":
            continue

        if record.get("source_type") in {"external_reference", "repo_reference", "web_reference"}:
            candidates.append({
                "action_type": "refresh_candidate",
                "source_record_ids": [record.get("record_id")],
                "reason": "External references should be revalidated before reuse.",
                "human_review_required": True,
            })

    return candidates


def consolidate_memory(dry_run: bool = True, limit: int = 50):
    if dry_run:
        records = load_records_read_only(include_revoked=True)
    else:
        ensure_worker_store()
        records = memory_taxonomy.load_records(include_revoked=True)

    active_records = [r for r in records if r.get("status") != "revoked"]

    if dry_run:
        entity_index = build_entity_index(active_records)
    else:
        entity_index = rebuild_entity_index(active_records)

    proposals = []
    proposals.extend(find_merge_candidates(active_records))
    proposals.extend(find_promotion_candidates(active_records))
    proposals.extend(find_decay_candidates(active_records))
    proposals.extend(find_refresh_candidates(active_records))

    proposals = proposals[:max(1, min(int(limit), 200))]

    scan_entry = None
    journal_entries = []

    if not dry_run:
        scan_entry = write_journal_entry(
            action_type="scan",
            source_record_ids=[r.get("record_id") for r in active_records],
            reason=f"Scanned {len(active_records)} active memory records and generated {len(proposals)} proposals.",
            human_review_required=False,
            proposal={
                "record_count": len(active_records),
                "proposal_count": len(proposals),
                "entity_count": entity_index.get("entity_count", 0),
            },
        )

        for proposal in proposals:
            entry = write_journal_entry(
                action_type=proposal.get("action_type"),
                source_record_ids=proposal.get("source_record_ids", []),
                target_record_id=proposal.get("target_record_id"),
                reason=proposal.get("reason", ""),
                confidence_before=proposal.get("confidence_before"),
                confidence_after=proposal.get("confidence_after"),
                entity_resolution={
                    "entity_index_path": str(ENTITY_INDEX_PATH),
                    "entity_count": entity_index.get("entity_count", 0),
                },
                duplicate_group_id=proposal.get("duplicate_group_id"),
                human_review_required=proposal.get("human_review_required", True),
                proposal=proposal,
            )
            journal_entries.append(entry)

    return {
        "worker_version": WORKER_VERSION,
        "policy_version": POLICY_VERSION,
        "dry_run": dry_run,
        "record_count": len(active_records),
        "entity_count": entity_index.get("entity_count", 0),
        "proposal_count": len(proposals),
        "proposals": proposals,
        "scan_entry": scan_entry,
        "journal_entries": journal_entries,
        "storage": {
            "consolidation_journal": str(CONSOLIDATION_JOURNAL_PATH),
            "entity_index": str(ENTITY_INDEX_PATH),
        },
        "doctrine": [
            "The consolidation worker proposes memory edits; it does not silently rewrite doctrine.",
            "Merge, promote, decay, refresh, and revoke actions require human review in this version.",
            "Stable doctrine should not decay merely because it is old.",
            "Eviction is not deletion; revocation preserves auditability.",
            "Validation before reuse is required for external references.",
        ],
    }


def consolidation_status():
    ensure_worker_store()

    records = memory_taxonomy.load_records(include_revoked=True)
    journal = load_journal(limit=20)

    entity_index = {}
    if ENTITY_INDEX_PATH.exists():
        entity_index = json.loads(ENTITY_INDEX_PATH.read_text(encoding="utf-8"))

    return {
        "worker_version": WORKER_VERSION,
        "policy_version": POLICY_VERSION,
        "record_count": len(records),
        "journal_count": len(load_journal(limit=100000)),
        "entity_count": entity_index.get("entity_count", 0),
        "journal_path": str(CONSOLIDATION_JOURNAL_PATH),
        "entity_index_path": str(ENTITY_INDEX_PATH),
        "recent_journal_entries": journal,
    }
