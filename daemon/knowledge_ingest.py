from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "logs" / "knowledge"
RECORDS_PATH = KNOWLEDGE_DIR / "knowledge_records.jsonl"
SOURCES_PATH = KNOWLEDGE_DIR / "knowledge_sources.json"

KNOWLEDGE_VERSION = "v0.2.8"
POLICY_VERSION = "knowledge_ingest_policy_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_store() -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    RECORDS_PATH.touch(exist_ok=True)

    if not SOURCES_PATH.exists():
        SOURCES_PATH.write_text(
            json.dumps(
                {
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "sources": {}
                },
                indent=2
            ),
            encoding="utf-8",
        )


def normalize_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compact_text(text: str, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit]


def content_hash(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def make_source_id(hash_value: str) -> str:
    return f"ksrc_{hash_value[:12]}"


def make_record_id() -> str:
    return f"krec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def load_sources() -> dict[str, Any]:
    ensure_store()

    try:
        return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "sources": {}
        }


def save_sources(registry: dict[str, Any]) -> dict[str, Any]:
    ensure_store()
    registry["updated_at"] = utc_now()
    SOURCES_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    return registry


def load_records(limit: int = 100, include_inactive: bool = False) -> list[dict[str, Any]]:
    ensure_store()
    records = []

    for line in RECORDS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not include_inactive and item.get("status", "active") != "active":
            continue

        records.append(item)

    return records[-limit:]


def write_record(record: dict[str, Any]) -> dict[str, Any]:
    ensure_store()
    with RECORDS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def find_duplicate_source(hash_value: str, source_path: str = "", source_title: str = "") -> dict[str, Any] | None:
    registry = load_sources()
    sources = registry.get("sources", {})

    for source in sources.values():
        if source.get("content_hash") == hash_value:
            return source

        if source_path and source.get("source_path") == source_path and source.get("source_title") == source_title:
            return source

    return None


def register_source(
    *,
    source_title: str,
    source_type: str,
    source_path: str,
    origin: str,
    tags: list[str],
    hash_value: str,
    duplicate_of: str | None = None,
) -> dict[str, Any]:
    registry = load_sources()
    sources = registry.setdefault("sources", {})

    source_id = make_source_id(hash_value)

    source = sources.get(source_id, {
        "source_id": source_id,
        "created_at": utc_now(),
    })

    source.update({
        "source_path": source_path,
        "source_title": source_title,
        "source_type": source_type,
        "content_hash": hash_value,
        "origin": origin,
        "tags": tags,
        "last_ingested_at": utc_now(),
        "duplicate_of": duplicate_of,
        "status": "active" if not duplicate_of else "duplicate",
    })

    sources[source_id] = source
    save_sources(registry)

    return source


def ingest_text(
    *,
    title: str,
    body: str,
    source_type: str = "text",
    source_path: str = "",
    origin: str = "manual",
    tags: list[str] | None = None,
    created_by: str = "Oracle",
    provenance: str = "",
) -> dict[str, Any]:
    ensure_store()

    tags = tags or []
    normalized_body = normalize_text(body)

    if not normalized_body:
        raise ValueError("Knowledge body is empty.")

    hash_value = content_hash(normalized_body)
    duplicate = find_duplicate_source(hash_value, source_path=source_path, source_title=title)
    duplicate_of = duplicate.get("source_id") if duplicate else None

    source = register_source(
        source_title=title,
        source_type=source_type,
        source_path=source_path,
        origin=origin,
        tags=tags,
        hash_value=hash_value,
        duplicate_of=duplicate_of,
    )

    record = {
        "record_id": make_record_id(),
        "source_id": source.get("source_id"),
        "source_title": title,
        "source_type": source_type,
        "source_path": source_path,
        "origin": origin,
        "content_hash": hash_value,
        "title": title,
        "summary": compact_text(normalized_body, 280),
        "body": normalized_body,
        "tags": tags,
        "created_by": created_by,
        "created_at": utc_now(),
        "ingested_at": utc_now(),
        "provenance": provenance or f"Ingested from {origin} as source-backed knowledge.",
        "status": "duplicate" if duplicate_of else "active",
        "duplicate_of": duplicate_of,
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "doctrine": "Knowledge is ingested, indexed, and searched. Memory is extracted, reviewed, and approved.",
    }

    write_record(record)

    return {
        "status": "duplicate" if duplicate_of else "success",
        "duplicate": bool(duplicate_of),
        "duplicate_of": duplicate_of,
        "source": source,
        "record": record,
    }


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9_.#-]+", text or "")
        if len(token) > 2
    ]


def search_knowledge(query: str, limit: int = 10) -> dict[str, Any]:
    records = load_records(limit=500, include_inactive=True)
    query_tokens = set(tokenize(query))

    if not query_tokens:
        return {
            "query": query,
            "matches": [],
            "explanation": "No searchable query tokens.",
        }

    matches = []

    for record in records:
        haystack = " ".join([
            record.get("title", ""),
            record.get("summary", ""),
            record.get("body", ""),
            " ".join(record.get("tags", [])),
            record.get("source_title", ""),
            record.get("source_path", ""),
            record.get("provenance", ""),
        ])

        tokens = set(tokenize(haystack))
        overlap = sorted(query_tokens & tokens)

        if not overlap:
            continue

        score = len(overlap) / max(len(query_tokens), 1)

        matches.append({
            "record": record,
            "score": round(score, 4),
            "matched_terms": overlap,
            "why_matched": f"Matched {len(overlap)} query term(s): {', '.join(overlap)}",
        })

    matches.sort(key=lambda item: item["score"], reverse=True)

    return {
        "query": query,
        "matches": matches[:limit],
        "match_count": len(matches),
        "explanation": "Knowledge search is local keyword search over source-backed knowledge records.",
        "doctrine": "Search does not mutate memory or create durable memory records.",
    }


def knowledge_status() -> dict[str, Any]:
    ensure_store()
    registry = load_sources()
    records = load_records(limit=100000, include_inactive=True)

    counts: dict[str, int] = {}
    for record in records:
        status = record.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "records_path": str(RECORDS_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "sources_path": str(SOURCES_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "record_count": len(records),
        "source_count": len(registry.get("sources", {})),
        "counts": counts,
        "doctrine": [
            "Knowledge is ingested, indexed, and searched.",
            "Memory is extracted, reviewed, and approved.",
            "Knowledge ingest never writes durable memory.",
            "Knowledge sources require provenance and hashes.",
        ],
    }


# --- Technemachina Knowledge Source Registry Refinement v0.2.8a ---

KNOWLEDGE_VERSION = "v0.2.8a"
POLICY_VERSION = "knowledge_source_registry_policy_v1"

PROVENANCE_LABELS = {
    "manual",
    "imported",
    "generated",
    "external",
    "transcribed",
    "unknown",
}


def infer_provenance_label(origin: str = "", source_type: str = "") -> str:
    value = f"{origin} {source_type}".lower()

    if "manual" in value:
        return "manual"
    if "import" in value or "file" in value or "upload" in value:
        return "imported"
    if "generated" in value or "ai" in value:
        return "generated"
    if "external" in value or "web" in value or "url" in value:
        return "external"
    if "transcribed" in value or "audio" in value or "video" in value:
        return "transcribed"

    return "unknown"


def make_duplicate_source_id(hash_value: str) -> str:
    return f"ksrc_dup_{hash_value[:8]}_{uuid.uuid4().hex[:8]}"


def load_sources() -> dict[str, Any]:
    ensure_store()

    try:
        registry = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        registry = {
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "sources": {},
            "duplicate_events": [],
        }

    registry.setdefault("sources", {})
    registry.setdefault("duplicate_events", [])

    changed = False

    for source in registry["sources"].values():
        if "source_kind" not in source:
            source["source_kind"] = "knowledge"
            changed = True

        if "provenance_label" not in source:
            source["provenance_label"] = infer_provenance_label(
                source.get("origin", ""),
                source.get("source_type", ""),
            )
            changed = True

        if "duplicate_reason" not in source:
            source["duplicate_reason"] = ""
            changed = True

        if "memory_write_allowed" not in source:
            source["memory_write_allowed"] = False
            changed = True

        if "candidate_path_allowed" not in source:
            source["candidate_path_allowed"] = False
            changed = True

        if "lane" not in source:
            source["lane"] = "knowledge"
            changed = True

    if changed:
        save_sources(registry)

    return registry


def find_duplicate_source(hash_value: str, source_path: str = "", source_title: str = "") -> dict[str, Any] | None:
    registry = load_sources()
    sources = registry.get("sources", {})

    for source in sources.values():
        if source.get("status", "active") != "active":
            continue

        if source.get("content_hash") == hash_value:
            return source

        if source_path and source.get("source_path") == source_path and source.get("source_title") == source_title:
            return source

    return None


def register_source(
    *,
    source_title: str,
    source_type: str,
    source_path: str,
    origin: str,
    tags: list[str],
    hash_value: str,
    duplicate_of: str | None = None,
    duplicate_reason: str = "",
) -> dict[str, Any]:
    registry = load_sources()
    sources = registry.setdefault("sources", {})

    if duplicate_of:
        source_id = make_duplicate_source_id(hash_value)
    else:
        source_id = make_source_id(hash_value)

    source = sources.get(source_id, {
        "source_id": source_id,
        "created_at": utc_now(),
    })

    provenance_label = infer_provenance_label(origin, source_type)

    source.update({
        "source_id": source_id,
        "source_title": source_title,
        "source_path": source_path,
        "source_type": source_type,
        "origin": origin,
        "provenance_label": provenance_label,
        "content_hash": hash_value,
        "tags": tags,
        "created_at": source.get("created_at", utc_now()),
        "last_ingested_at": utc_now(),
        "duplicate_of": duplicate_of,
        "duplicate_reason": duplicate_reason,
        "status": "duplicate" if duplicate_of else "active",
        "lane": "knowledge",
        "source_kind": "knowledge",
        "memory_write_allowed": False,
        "candidate_path_allowed": False,
        "registry_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
    })

    sources[source_id] = source

    if duplicate_of:
        registry.setdefault("duplicate_events", []).append({
            "event_id": f"kdup_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            "source_id": source_id,
            "duplicate_of": duplicate_of,
            "content_hash": hash_value,
            "duplicate_reason": duplicate_reason,
            "created_at": utc_now(),
        })

    save_sources(registry)

    return source


def ingest_text(
    *,
    title: str,
    body: str,
    source_type: str = "text",
    source_path: str = "",
    origin: str = "manual",
    tags: list[str] | None = None,
    created_by: str = "Oracle",
    provenance: str = "",
) -> dict[str, Any]:
    ensure_store()

    tags = tags or []
    normalized_body = normalize_text(body)

    if not normalized_body:
        raise ValueError("Knowledge body is empty.")

    hash_value = content_hash(normalized_body)
    duplicate = find_duplicate_source(hash_value, source_path=source_path, source_title=title)

    duplicate_of = duplicate.get("source_id") if duplicate else None
    duplicate_reason = ""

    if duplicate_of:
        if duplicate.get("content_hash") == hash_value:
            duplicate_reason = "exact_content_hash_match"
        elif source_path and duplicate.get("source_path") == source_path:
            duplicate_reason = "source_path_title_match"
        else:
            duplicate_reason = "registry_match"

    source = register_source(
        source_title=title,
        source_type=source_type,
        source_path=source_path,
        origin=origin,
        tags=tags,
        hash_value=hash_value,
        duplicate_of=duplicate_of,
        duplicate_reason=duplicate_reason,
    )

    record = {
        "record_id": make_record_id(),
        "source_id": source.get("source_id"),
        "source_title": title,
        "source_type": source_type,
        "source_path": source_path,
        "origin": origin,
        "provenance_label": source.get("provenance_label", "unknown"),
        "content_hash": hash_value,
        "title": title,
        "summary": compact_text(normalized_body, 280),
        "body": normalized_body,
        "tags": tags,
        "created_by": created_by,
        "created_at": utc_now(),
        "ingested_at": utc_now(),
        "provenance": provenance or f"Ingested from {origin} as source-backed knowledge.",
        "status": "duplicate" if duplicate_of else "active",
        "duplicate_of": duplicate_of,
        "duplicate_reason": duplicate_reason,
        "lane": "knowledge",
        "memory_write_allowed": False,
        "candidate_path_allowed": False,
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "doctrine": "Knowledge is ingested, indexed, and searched. Memory is extracted, reviewed, and approved.",
    }

    write_record(record)

    return {
        "status": "duplicate" if duplicate_of else "success",
        "duplicate": bool(duplicate_of),
        "duplicate_of": duplicate_of,
        "duplicate_reason": duplicate_reason,
        "source": source,
        "record": record,
        "doctrine": "Knowledge ingest does not write durable memory.",
    }


def source_summary(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source.get("source_id", ""),
        "source_title": source.get("source_title", ""),
        "source_path": source.get("source_path", ""),
        "source_type": source.get("source_type", ""),
        "origin": source.get("origin", ""),
        "provenance_label": source.get("provenance_label", "unknown"),
        "content_hash": source.get("content_hash", ""),
        "status": source.get("status", "unknown"),
        "duplicate_of": source.get("duplicate_of"),
        "duplicate_reason": source.get("duplicate_reason", ""),
        "lane": source.get("lane", "knowledge"),
        "memory_write_allowed": source.get("memory_write_allowed", False),
        "candidate_path_allowed": source.get("candidate_path_allowed", False),
        "created_at": source.get("created_at", ""),
        "last_ingested_at": source.get("last_ingested_at", ""),
    }


def search_knowledge(query: str, limit: int = 10) -> dict[str, Any]:
    records = load_records(limit=500, include_inactive=True)
    registry = load_sources()
    sources = registry.get("sources", {})
    query_tokens = set(tokenize(query))

    if not query_tokens:
        return {
            "query": query,
            "matches": [],
            "explanation": "No searchable query tokens.",
        }

    matches = []

    for record in records:
        source = sources.get(record.get("source_id", ""), {})

        haystack = " ".join([
            record.get("title", ""),
            record.get("summary", ""),
            record.get("body", ""),
            " ".join(record.get("tags", [])),
            record.get("source_title", ""),
            record.get("source_path", ""),
            record.get("provenance", ""),
            source.get("source_title", ""),
            source.get("source_path", ""),
            source.get("provenance_label", ""),
        ])

        tokens = set(tokenize(haystack))
        overlap = sorted(query_tokens & tokens)

        if not overlap:
            continue

        score = len(overlap) / max(len(query_tokens), 1)

        matches.append({
            "record": record,
            "source": source_summary(source),
            "score": round(score, 4),
            "matched_terms": overlap,
            "why_matched": f"Matched {len(overlap)} query term(s): {', '.join(overlap)}",
        })

    matches.sort(key=lambda item: item["score"], reverse=True)

    return {
        "query": query,
        "matches": matches[:limit],
        "match_count": len(matches),
        "explanation": "Knowledge search is local keyword search over source-backed knowledge records and source metadata.",
        "doctrine": "Search does not mutate memory or create durable memory records.",
    }


def knowledge_status() -> dict[str, Any]:
    ensure_store()
    registry = load_sources()
    sources = list(registry.get("sources", {}).values())
    records = load_records(limit=100000, include_inactive=True)

    record_counts: dict[str, int] = {}
    for record in records:
        status = record.get("status", "unknown")
        record_counts[status] = record_counts.get(status, 0) + 1

    source_counts: dict[str, int] = {}
    provenance_counts: dict[str, int] = {}

    for source in sources:
        status = source.get("status", "unknown")
        source_counts[status] = source_counts.get(status, 0) + 1

        label = source.get("provenance_label", "unknown")
        provenance_counts[label] = provenance_counts.get(label, 0) + 1

    recent_sources = sorted(
        [source_summary(source) for source in sources],
        key=lambda item: item.get("last_ingested_at", ""),
        reverse=True,
    )[:5]

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "records_path": str(RECORDS_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "sources_path": str(SOURCES_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "record_count": len(records),
        "source_count": len(sources),
        "record_counts": record_counts,
        "source_counts": source_counts,
        "provenance_counts": provenance_counts,
        "duplicate_event_count": len(registry.get("duplicate_events", [])),
        "recent_sources": recent_sources,
        "updated_at": registry.get("updated_at", ""),
        "doctrine": [
            "Knowledge is ingested, indexed, and searched.",
            "Memory is extracted, reviewed, and approved.",
            "Knowledge ingest never writes durable memory.",
            "Knowledge sources require provenance and hashes.",
            "The source registry is the canonical provenance index for knowledge.",
        ],
    }


# --- End Technemachina Knowledge Source Registry Refinement ---


# --- Technemachina Knowledge Search Refinement v0.2.8b ---

KNOWLEDGE_VERSION = "v0.2.8b"
POLICY_VERSION = "knowledge_search_refinement_policy_v1"


def search_knowledge(
    query: str,
    limit: int = 10,
    include_duplicates: bool = False,
    source_status: str = "",
    provenance_label: str = "",
) -> dict[str, Any]:
    records = load_records(limit=1000, include_inactive=True)
    registry = load_sources()
    sources = registry.get("sources", {})
    query_tokens = set(tokenize(query))

    if not query_tokens:
        return {
            "query": query,
            "matches": [],
            "match_count": 0,
            "explanation": "No searchable query tokens.",
            "filters": {
                "include_duplicates": include_duplicates,
                "source_status": source_status,
                "provenance_label": provenance_label,
            },
            "doctrine": "Search does not mutate memory or create durable memory records.",
        }

    matches = []
    skipped = {
        "duplicates": 0,
        "source_status_filter": 0,
        "provenance_label_filter": 0,
        "missing_source": 0,
    }

    for record in records:
        source = sources.get(record.get("source_id", ""), {})

        if not source:
            skipped["missing_source"] += 1
            continue

        record_status = record.get("status", "active")
        current_source_status = source.get("status", record_status)

        if not include_duplicates:
            if record_status == "duplicate" or current_source_status == "duplicate":
                skipped["duplicates"] += 1
                continue

        if source_status and current_source_status != source_status:
            skipped["source_status_filter"] += 1
            continue

        current_provenance_label = source.get("provenance_label", record.get("provenance_label", "unknown"))

        if provenance_label and current_provenance_label != provenance_label:
            skipped["provenance_label_filter"] += 1
            continue

        haystack = " ".join([
            record.get("title", ""),
            record.get("summary", ""),
            record.get("body", ""),
            " ".join(record.get("tags", [])),
            record.get("source_title", ""),
            record.get("source_path", ""),
            record.get("provenance", ""),
            source.get("source_title", ""),
            source.get("source_path", ""),
            source.get("provenance_label", ""),
            source.get("origin", ""),
        ])

        tokens = set(tokenize(haystack))
        overlap = sorted(query_tokens & tokens)

        if not overlap:
            continue

        score = len(overlap) / max(len(query_tokens), 1)

        matches.append({
            "record": record,
            "source": source_summary(source),
            "score": round(score, 4),
            "matched_terms": overlap,
            "why_matched": f"Matched {len(overlap)} query term(s): {', '.join(overlap)}",
            "search_policy": {
                "duplicates_visible": include_duplicates,
                "memory_mutation": False,
                "embedding_used": False,
            },
        })

    matches.sort(key=lambda item: item["score"], reverse=True)

    return {
        "query": query,
        "matches": matches[:limit],
        "match_count": len(matches),
        "returned_count": len(matches[:limit]),
        "skipped": skipped,
        "filters": {
            "include_duplicates": include_duplicates,
            "source_status": source_status,
            "provenance_label": provenance_label,
        },
        "explanation": "Knowledge search is local keyword search over canonical source-backed knowledge. Duplicate records are hidden by default unless include_duplicates=true.",
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "doctrine": "Search does not mutate memory or create durable memory records.",
    }


# --- End Technemachina Knowledge Search Refinement ---


# --- Technemachina Knowledge-to-Candidate Bridge v0.2.8c ---

KNOWLEDGE_VERSION = "v0.2.8c"
POLICY_VERSION = "knowledge_to_candidate_bridge_policy_v1"
KNOWLEDGE_CANDIDATES_PATH = KNOWLEDGE_DIR / "knowledge_candidates.jsonl"


def ensure_candidate_store() -> None:
    ensure_store()
    KNOWLEDGE_CANDIDATES_PATH.touch(exist_ok=True)


def load_knowledge_candidates(limit: int = 100, include_closed: bool = True) -> list[dict[str, Any]]:
    ensure_candidate_store()
    candidates = []

    for line in KNOWLEDGE_CANDIDATES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not include_closed and item.get("review_status") in {"enqueued", "approved", "rejected"}:
            continue

        candidates.append(item)

    return candidates[-limit:]


def write_knowledge_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    ensure_candidate_store()
    with KNOWLEDGE_CANDIDATES_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    return candidate


def make_knowledge_candidate_id() -> str:
    return f"kcand_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def get_knowledge_record(record_id: str) -> dict[str, Any] | None:
    for record in load_records(limit=100000, include_inactive=True):
        if record.get("record_id") == record_id:
            return record
    return None


def get_source_for_record(record: dict[str, Any]) -> dict[str, Any]:
    registry = load_sources()
    return registry.get("sources", {}).get(record.get("source_id", ""), {})


def knowledge_candidate_score(record: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    text = " ".join([
        record.get("title", ""),
        record.get("summary", ""),
        record.get("body", ""),
        " ".join(record.get("tags", [])),
        record.get("provenance", ""),
        source.get("source_title", ""),
        source.get("source_path", ""),
    ]).lower()

    signals = []

    signal_rules = {
        "doctrine": ["doctrine", "rule", "must", "must not", "never", "boundary"],
        "project_architecture": ["architecture", "module", "endpoint", "foundation", "bridge", "registry", "daemon"],
        "stable_procedure": ["workflow", "procedure", "process", "pipeline", "step", "sequence"],
        "governance": ["review", "approval", "oracle", "candidate", "governance", "memory"],
        "explicit_importance": ["important", "critical", "foundation", "locked", "confirmed", "verified"],
        "direct_instruction": ["should", "must", "do not", "avoid", "keep", "preserve"],
    }

    for label, terms in signal_rules.items():
        if any(term in text for term in terms):
            signals.append(label)

    base_score = min(1.0, len(signals) / 4)

    if record.get("status") == "duplicate" or source.get("status") == "duplicate":
        base_score = min(base_score, 0.35)
        signals.append("duplicate_penalty")

    if "doctrine" in signals or "governance" in signals:
        suggested_layer = "delta"
        suggested_type = "doctrine_note"
    elif "project_architecture" in signals or "stable_procedure" in signals:
        suggested_layer = "theta"
        suggested_type = "project_fact"
    else:
        suggested_layer = "alpha"
        suggested_type = "research_note"

    if base_score >= 0.75:
        confidence = "high"
        importance = "high"
    elif base_score >= 0.45:
        confidence = "medium"
        importance = "medium"
    else:
        confidence = "low"
        importance = "low"

    return {
        "score": round(base_score, 4),
        "signals": signals,
        "confidence": confidence,
        "importance": importance,
        "suggested_layer": suggested_layer,
        "suggested_record_type": suggested_type,
        "why_candidate": (
            "Knowledge item contains stable or governance-relevant signals: "
            + ", ".join(signals)
            if signals else
            "Knowledge item has weak candidate signals."
        ),
    }


def build_candidate_from_knowledge(
    *,
    knowledge_record_id: str,
    created_by: str = "Oracle",
    reason: str = "",
    force: bool = False,
) -> dict[str, Any]:
    record = get_knowledge_record(knowledge_record_id)

    if not record:
        raise ValueError("knowledge_record_not_found")

    source = get_source_for_record(record)
    score = knowledge_candidate_score(record, source)

    if not force and score["score"] < 0.25:
        return {
            "status": "not_created",
            "reason": "candidate_score_too_low",
            "score": score,
            "knowledge_record_id": knowledge_record_id,
            "doctrine": "Knowledge-to-candidate bridge proposes candidates only; it does not write memory.",
        }

    body = record.get("body", "")
    excerpt = compact_text(body, 900)

    candidate = {
        "candidate_id": make_knowledge_candidate_id(),
        "source_kind": "knowledge",
        "knowledge_record_id": knowledge_record_id,
        "source_id": record.get("source_id", ""),
        "source_title": record.get("source_title", ""),
        "source_path": record.get("source_path", ""),
        "title": record.get("title", "Untitled knowledge candidate"),
        "summary": record.get("summary", ""),
        "body_excerpt": excerpt,
        "body": body,
        "tags": record.get("tags", []),
        "why_candidate": reason or score["why_candidate"],
        "candidate_score": score["score"],
        "signals": score["signals"],
        "confidence": score["confidence"],
        "importance": score["importance"],
        "suggested_layer": score["suggested_layer"],
        "suggested_record_type": score["suggested_record_type"],
        "provenance": (
            f"Knowledge-to-candidate bridge from knowledge record {knowledge_record_id}; "
            f"source {record.get('source_id', '')}; "
            f"original provenance: {record.get('provenance', '')}"
        ),
        "review_status": "candidate_created",
        "created_by": created_by,
        "created_at": utc_now(),
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "memory_write_allowed": False,
        "candidate_path_allowed": True,
        "doctrine": "Knowledge candidates must go through Review Queue before durable memory.",
    }

    write_knowledge_candidate(candidate)

    return {
        "status": "success",
        "candidate": candidate,
        "source": source_summary(source),
        "score": score,
        "doctrine": "No durable memory was written.",
    }


def enqueue_knowledge_candidate(candidate_id: str, reviewed_by: str = "Oracle", notes: str = "") -> dict[str, Any]:
    import memory_review_queue

    candidates = load_knowledge_candidates(limit=100000, include_closed=True)
    candidate = None

    for item in candidates:
        if item.get("candidate_id") == candidate_id:
            candidate = item
            break

    if not candidate:
        raise ValueError("knowledge_candidate_not_found")

    candidate_record = {
        "record_type": candidate.get("suggested_record_type", "research_note"),
        "layer": candidate.get("suggested_layer", "alpha"),
        "scope": "technemachina_daemon",
        "title": candidate.get("title", "Knowledge candidate"),
        "summary": candidate.get("summary", ""),
        "body": candidate.get("body", candidate.get("body_excerpt", "")),
        "tags": candidate.get("tags", []) + ["knowledge_candidate"],
        "source_type": "knowledge",
        "source_ref": candidate.get("knowledge_record_id", ""),
        "source_title": candidate.get("source_title", ""),
        "created_by": reviewed_by,
        "provenance": candidate.get("provenance", ""),
        "confidence": candidate.get("confidence", "medium"),
        "status": "active",
        "review_state": "pending_oracle_review",
        "risk_level": "low",
        "attach_to_context": False,
        "retrieval_priority": 50,
        "importance_weight": 0.7 if candidate.get("importance") == "high" else 0.5,
    }

    review = memory_review_queue.create_review_item(
        candidate_record=candidate_record,
        suggested_action="approve",
        reason=notes or candidate.get("why_candidate", "Knowledge candidate proposed for review."),
        source_refs=[
            candidate.get("knowledge_record_id", ""),
            candidate.get("source_id", ""),
            candidate.get("candidate_id", ""),
        ],
        related_record_ids=[],
        conflicting_record_ids=[],
        original_record=candidate,
        created_by=reviewed_by,
    )

    event = {
        **candidate,
        "review_status": "candidate_queued",
        "review_id": review.get("review_id"),
        "queued_at": utc_now(),
        "queued_by": reviewed_by,
    }
    write_knowledge_candidate(event)

    return {
        "status": "success",
        "review": review,
        "candidate": event,
        "doctrine": "Candidate was enqueued for Oracle review; durable memory was not written.",
    }


def knowledge_candidate_status() -> dict[str, Any]:
    candidates = load_knowledge_candidates(limit=100000, include_closed=True)

    counts: dict[str, int] = {}
    for candidate in candidates:
        status = candidate.get("review_status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "candidate_count": len(candidates),
        "counts": counts,
        "candidates_path": str(KNOWLEDGE_CANDIDATES_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "doctrine": [
            "Knowledge-to-candidate bridge creates proposals only.",
            "Knowledge records are preserved unchanged.",
            "Durable memory requires Review Queue approval.",
            "No direct knowledge-to-memory writes are allowed.",
        ],
    }


# --- End Technemachina Knowledge-to-Candidate Bridge ---


# --- Technemachina Knowledge Candidate Cleanup v0.2.8c-1 ---

KNOWLEDGE_VERSION = "v0.2.8c-1"
POLICY_VERSION = "knowledge_candidate_cleanup_policy_v1"


def knowledge_candidate_current_states() -> dict[str, dict[str, Any]]:
    """
    Collapse append-only knowledge candidate events into one current state per candidate_id.
    The JSONL remains append-only; this function provides the clean operational view.
    """
    candidates = load_knowledge_candidates(limit=100000, include_closed=True)
    current: dict[str, dict[str, Any]] = {}

    for item in candidates:
        candidate_id = item.get("candidate_id")
        if not candidate_id:
            continue

        current[candidate_id] = item

    return current


def knowledge_candidate_by_record() -> dict[str, dict[str, Any]]:
    """
    Return latest candidate state by knowledge_record_id.
    This prevents creating duplicate candidates from the same knowledge record.
    """
    current = knowledge_candidate_current_states()
    by_record: dict[str, dict[str, Any]] = {}

    for candidate in current.values():
        record_id = candidate.get("knowledge_record_id")
        if not record_id:
            continue

        by_record[record_id] = candidate

    return by_record


def bridge_state_for_knowledge_record(record_id: str) -> str:
    candidate = knowledge_candidate_by_record().get(record_id)

    if not candidate:
        return "knowledge_only"

    status = candidate.get("review_status", "")

    if status == "candidate_created":
        return "candidate_created"

    if status == "candidate_queued":
        return "candidate_queued"

    if status in {"approved", "rejected", "deferred"}:
        return "candidate_reviewed"

    return status or "candidate_created"


def knowledge_bridge_status() -> dict[str, Any]:
    records = load_records(limit=100000, include_inactive=True)
    current_candidates = knowledge_candidate_current_states()
    by_record = knowledge_candidate_by_record()

    counts = {
        "knowledge_only": 0,
        "candidate_created": 0,
        "candidate_queued": 0,
        "candidate_reviewed": 0,
        "duplicate_records": 0,
    }

    record_states = []

    for record in records:
        record_id = record.get("record_id", "")

        if record.get("status") == "duplicate":
            counts["duplicate_records"] += 1
            state = "duplicate_record"
        else:
            state = bridge_state_for_knowledge_record(record_id)
            if state in counts:
                counts[state] += 1
            else:
                counts["knowledge_only"] += 1

        candidate = by_record.get(record_id, {})

        record_states.append({
            "knowledge_record_id": record_id,
            "title": record.get("title", ""),
            "source_id": record.get("source_id", ""),
            "record_status": record.get("status", "active"),
            "bridge_state": state,
            "candidate_id": candidate.get("candidate_id", ""),
            "candidate_review_status": candidate.get("review_status", ""),
            "review_id": candidate.get("review_id", ""),
        })

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "raw_candidate_event_count": len(load_knowledge_candidates(limit=100000, include_closed=True)),
        "current_candidate_count": len(current_candidates),
        "knowledge_record_count": len(records),
        "counts": counts,
        "record_states": record_states,
        "doctrine": [
            "Knowledge candidate cleanup is a view and suppression layer.",
            "The candidate ledger remains append-only.",
            "A knowledge record should not create duplicate candidates.",
            "Durable memory still requires Review Queue approval.",
            "No direct knowledge-to-memory writes are allowed.",
        ],
    }


# Preserve previous implementation for fallback/debug.
_previous_build_candidate_from_knowledge_v028c = build_candidate_from_knowledge


def build_candidate_from_knowledge(
    *,
    knowledge_record_id: str,
    created_by: str = "Oracle",
    reason: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """
    Idempotent wrapper:
    - same knowledge_record_id returns the existing current candidate state
    - force still allows low-score records, but does not duplicate existing candidates
    """
    existing = knowledge_candidate_by_record().get(knowledge_record_id)

    if existing:
        return {
            "status": "existing_candidate",
            "candidate": existing,
            "bridge_state": bridge_state_for_knowledge_record(knowledge_record_id),
            "doctrine": "Existing knowledge candidate returned; no duplicate candidate was written.",
        }

    return _previous_build_candidate_from_knowledge_v028c(
        knowledge_record_id=knowledge_record_id,
        created_by=created_by,
        reason=reason,
        force=force,
    )


# Preserve previous loader for raw access.
_previous_load_knowledge_candidates_v028c = load_knowledge_candidates


def load_knowledge_candidates(
    limit: int = 100,
    include_closed: bool = True,
    current_only: bool = True,
) -> list[dict[str, Any]]:
    """
    Default view now returns current candidate states only.
    Raw append-only events remain available with current_only=False.
    """
    raw = _previous_load_knowledge_candidates_v028c(
        limit=100000,
        include_closed=include_closed,
    )

    if not current_only:
        return raw[-limit:]

    current = knowledge_candidate_current_states()
    items = list(current.values())

    if not include_closed:
        items = [
            item for item in items
            if item.get("review_status") not in {"approved", "rejected"}
        ]

    return items[-limit:]


def knowledge_candidate_status() -> dict[str, Any]:
    current = load_knowledge_candidates(limit=100000, include_closed=True, current_only=True)
    raw = load_knowledge_candidates(limit=100000, include_closed=True, current_only=False)

    counts: dict[str, int] = {}
    for candidate in current:
        status = candidate.get("review_status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "candidate_count": len(current),
        "raw_candidate_event_count": len(raw),
        "counts": counts,
        "bridge_status": knowledge_bridge_status(),
        "candidates_path": str(KNOWLEDGE_CANDIDATES_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "doctrine": [
            "Knowledge candidates are shown as current state by default.",
            "Raw candidate events remain append-only.",
            "Duplicate candidate creation is suppressed by knowledge_record_id.",
            "Durable memory requires Review Queue approval.",
            "No direct knowledge-to-memory writes are allowed.",
        ],
    }


# --- End Technemachina Knowledge Candidate Cleanup ---


# --- Technemachina Knowledge Candidate Cleanup Hotfix v0.2.8c-1a ---

KNOWLEDGE_VERSION = "v0.2.8c-1a"
POLICY_VERSION = "knowledge_candidate_cleanup_hotfix_policy_v1"


def knowledge_candidate_current_states() -> dict[str, dict[str, Any]]:
    """
    Hotfix: use raw append-only loader directly to avoid recursive wrapper calls.
    """
    raw_loader = globals().get("_previous_load_knowledge_candidates_v028c")

    if raw_loader:
        candidates = raw_loader(limit=100000, include_closed=True)
    else:
        candidates = []

    current: dict[str, dict[str, Any]] = {}

    for item in candidates:
        candidate_id = item.get("candidate_id")
        if not candidate_id:
            continue

        current[candidate_id] = item

    return current


def knowledge_candidate_by_record() -> dict[str, dict[str, Any]]:
    current = knowledge_candidate_current_states()
    by_record: dict[str, dict[str, Any]] = {}

    for candidate in current.values():
        record_id = candidate.get("knowledge_record_id")
        if not record_id:
            continue

        by_record[record_id] = candidate

    return by_record


def load_knowledge_candidates(
    limit: int = 100,
    include_closed: bool = True,
    current_only: bool = True,
) -> list[dict[str, Any]]:
    raw_loader = globals().get("_previous_load_knowledge_candidates_v028c")

    if not raw_loader:
        return []

    raw = raw_loader(limit=100000, include_closed=include_closed)

    if not current_only:
        return raw[-limit:]

    current = knowledge_candidate_current_states()
    items = list(current.values())

    if not include_closed:
        items = [
            item for item in items
            if item.get("review_status") not in {"approved", "rejected"}
        ]

    return items[-limit:]


def knowledge_bridge_status() -> dict[str, Any]:
    records = load_records(limit=100000, include_inactive=True)
    current_candidates = knowledge_candidate_current_states()
    by_record = knowledge_candidate_by_record()

    counts = {
        "knowledge_only": 0,
        "candidate_created": 0,
        "candidate_queued": 0,
        "candidate_reviewed": 0,
        "duplicate_records": 0,
    }

    record_states = []

    for record in records:
        record_id = record.get("record_id", "")

        if record.get("status") == "duplicate":
            counts["duplicate_records"] += 1
            state = "duplicate_record"
        else:
            candidate = by_record.get(record_id)
            if not candidate:
                state = "knowledge_only"
            else:
                status = candidate.get("review_status", "")
                if status == "candidate_created":
                    state = "candidate_created"
                elif status == "candidate_queued":
                    state = "candidate_queued"
                elif status in {"approved", "rejected", "deferred"}:
                    state = "candidate_reviewed"
                else:
                    state = status or "candidate_created"

            if state in counts:
                counts[state] += 1
            elif state != "duplicate_record":
                counts["knowledge_only"] += 1

        candidate = by_record.get(record_id, {})

        record_states.append({
            "knowledge_record_id": record_id,
            "title": record.get("title", ""),
            "source_id": record.get("source_id", ""),
            "record_status": record.get("status", "active"),
            "bridge_state": state,
            "candidate_id": candidate.get("candidate_id", ""),
            "candidate_review_status": candidate.get("review_status", ""),
            "review_id": candidate.get("review_id", ""),
        })

    raw_loader = globals().get("_previous_load_knowledge_candidates_v028c")
    raw = raw_loader(limit=100000, include_closed=True) if raw_loader else []

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "raw_candidate_event_count": len(raw),
        "current_candidate_count": len(current_candidates),
        "knowledge_record_count": len(records),
        "counts": counts,
        "record_states": record_states,
        "doctrine": [
            "Knowledge candidate cleanup is a view and suppression layer.",
            "The candidate ledger remains append-only.",
            "A knowledge record should not create duplicate candidates.",
            "Durable memory still requires Review Queue approval.",
            "No direct knowledge-to-memory writes are allowed.",
        ],
    }


def knowledge_candidate_status() -> dict[str, Any]:
    current = load_knowledge_candidates(limit=100000, include_closed=True, current_only=True)
    raw = load_knowledge_candidates(limit=100000, include_closed=True, current_only=False)

    counts: dict[str, int] = {}
    for candidate in current:
        status = candidate.get("review_status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "candidate_count": len(current),
        "raw_candidate_event_count": len(raw),
        "counts": counts,
        "bridge_status": knowledge_bridge_status(),
        "candidates_path": str(KNOWLEDGE_CANDIDATES_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "doctrine": [
            "Knowledge candidates are shown as current state by default.",
            "Raw candidate events remain append-only.",
            "Duplicate candidate creation is suppressed by knowledge_record_id.",
            "Durable memory requires Review Queue approval.",
            "No direct knowledge-to-memory writes are allowed.",
        ],
    }


# --- End Technemachina Knowledge Candidate Cleanup Hotfix ---


# --- Technemachina Knowledge Candidate Cleanup Hardfix v0.2.8c-1b ---

KNOWLEDGE_VERSION = "v0.2.8c-1b"
POLICY_VERSION = "knowledge_candidate_cleanup_hardfix_policy_v1"


def load_knowledge_candidate_events_raw(limit: int = 100000, include_closed: bool = True) -> list[dict[str, Any]]:
    """
    Hard raw reader.
    This function reads knowledge_candidates.jsonl directly.
    It must never call load_knowledge_candidates().
    """
    ensure_candidate_store()

    events = []

    for line in KNOWLEDGE_CANDIDATES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not include_closed and item.get("review_status") in {"approved", "rejected"}:
            continue

        events.append(item)

    return events[-limit:]


def knowledge_candidate_current_states() -> dict[str, dict[str, Any]]:
    """
    Collapse append-only raw events into one current state per candidate_id.
    Uses only the hard raw reader.
    """
    events = load_knowledge_candidate_events_raw(limit=100000, include_closed=True)
    current: dict[str, dict[str, Any]] = {}

    for item in events:
        candidate_id = item.get("candidate_id")
        if not candidate_id:
            continue

        current[candidate_id] = item

    return current


def knowledge_candidate_by_record() -> dict[str, dict[str, Any]]:
    current = knowledge_candidate_current_states()
    by_record: dict[str, dict[str, Any]] = {}

    for candidate in current.values():
        record_id = candidate.get("knowledge_record_id")
        if not record_id:
            continue

        by_record[record_id] = candidate

    return by_record


def bridge_state_for_knowledge_record(record_id: str) -> str:
    candidate = knowledge_candidate_by_record().get(record_id)

    if not candidate:
        return "knowledge_only"

    status = candidate.get("review_status", "")

    if status == "candidate_created":
        return "candidate_created"

    if status == "candidate_queued":
        return "candidate_queued"

    if status in {"approved", "rejected", "deferred"}:
        return "candidate_reviewed"

    return status or "candidate_created"


def load_knowledge_candidates(
    limit: int = 100,
    include_closed: bool = True,
    current_only: bool = True,
) -> list[dict[str, Any]]:
    """
    Public loader.
    current_only=True returns one current state per candidate_id.
    current_only=False returns raw append-only events.
    """
    if not current_only:
        return load_knowledge_candidate_events_raw(
            limit=limit,
            include_closed=include_closed,
        )

    current = knowledge_candidate_current_states()
    items = list(current.values())

    if not include_closed:
        items = [
            item for item in items
            if item.get("review_status") not in {"approved", "rejected"}
        ]

    return items[-limit:]


def knowledge_bridge_status() -> dict[str, Any]:
    records = load_records(limit=100000, include_inactive=True)
    current_candidates = knowledge_candidate_current_states()
    by_record = knowledge_candidate_by_record()
    raw_events = load_knowledge_candidate_events_raw(limit=100000, include_closed=True)

    counts = {
        "knowledge_only": 0,
        "candidate_created": 0,
        "candidate_queued": 0,
        "candidate_reviewed": 0,
        "duplicate_records": 0,
    }

    record_states = []

    for record in records:
        record_id = record.get("record_id", "")

        if record.get("status") == "duplicate":
            state = "duplicate_record"
            counts["duplicate_records"] += 1
        else:
            state = bridge_state_for_knowledge_record(record_id)

            if state in counts:
                counts[state] += 1
            else:
                counts["knowledge_only"] += 1

        candidate = by_record.get(record_id, {})

        record_states.append({
            "knowledge_record_id": record_id,
            "title": record.get("title", ""),
            "source_id": record.get("source_id", ""),
            "record_status": record.get("status", "active"),
            "bridge_state": state,
            "candidate_id": candidate.get("candidate_id", ""),
            "candidate_review_status": candidate.get("review_status", ""),
            "review_id": candidate.get("review_id", ""),
        })

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "raw_candidate_event_count": len(raw_events),
        "current_candidate_count": len(current_candidates),
        "knowledge_record_count": len(records),
        "counts": counts,
        "record_states": record_states,
        "doctrine": [
            "Knowledge candidate cleanup is a view and suppression layer.",
            "The candidate ledger remains append-only.",
            "A knowledge record should not create duplicate candidates.",
            "Durable memory still requires Review Queue approval.",
            "No direct knowledge-to-memory writes are allowed.",
        ],
    }


def knowledge_candidate_status() -> dict[str, Any]:
    current = load_knowledge_candidates(limit=100000, include_closed=True, current_only=True)
    raw = load_knowledge_candidate_events_raw(limit=100000, include_closed=True)

    counts: dict[str, int] = {}

    for candidate in current:
        status = candidate.get("review_status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "candidate_count": len(current),
        "raw_candidate_event_count": len(raw),
        "counts": counts,
        "bridge_status": knowledge_bridge_status(),
        "candidates_path": str(KNOWLEDGE_CANDIDATES_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "doctrine": [
            "Knowledge candidates are shown as current state by default.",
            "Raw candidate events remain append-only.",
            "Duplicate candidate creation is suppressed by knowledge_record_id.",
            "Durable memory requires Review Queue approval.",
            "No direct knowledge-to-memory writes are allowed.",
        ],
    }


_previous_build_candidate_from_knowledge_v028c1b = build_candidate_from_knowledge


def build_candidate_from_knowledge(
    *,
    knowledge_record_id: str,
    created_by: str = "Oracle",
    reason: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """
    Idempotent hardfix:
    same knowledge_record_id returns existing current candidate state.
    """
    existing = knowledge_candidate_by_record().get(knowledge_record_id)

    if existing:
        return {
            "status": "existing_candidate",
            "candidate": existing,
            "bridge_state": bridge_state_for_knowledge_record(knowledge_record_id),
            "doctrine": "Existing knowledge candidate returned; no duplicate candidate was written.",
        }

    return _previous_build_candidate_from_knowledge_v028c1b(
        knowledge_record_id=knowledge_record_id,
        created_by=created_by,
        reason=reason,
        force=force,
    )


# --- End Technemachina Knowledge Candidate Cleanup Hardfix ---


# --- Technemachina Knowledge Candidate Cleanup Hardfix v0.2.8c-1b ---

KNOWLEDGE_VERSION = "v0.2.8c-1b"
POLICY_VERSION = "knowledge_candidate_cleanup_hardfix_policy_v1"


def load_knowledge_candidate_events_raw(limit: int = 100000, include_closed: bool = True) -> list[dict[str, Any]]:
    """
    Hard raw reader.
    This function reads knowledge_candidates.jsonl directly.
    It must never call load_knowledge_candidates().
    """
    ensure_candidate_store()

    events = []

    for line in KNOWLEDGE_CANDIDATES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not include_closed and item.get("review_status") in {"approved", "rejected"}:
            continue

        events.append(item)

    return events[-limit:]


def knowledge_candidate_current_states() -> dict[str, dict[str, Any]]:
    """
    Collapse append-only raw events into one current state per candidate_id.
    Uses only the hard raw reader.
    """
    events = load_knowledge_candidate_events_raw(limit=100000, include_closed=True)
    current: dict[str, dict[str, Any]] = {}

    for item in events:
        candidate_id = item.get("candidate_id")
        if not candidate_id:
            continue

        current[candidate_id] = item

    return current


def knowledge_candidate_by_record() -> dict[str, dict[str, Any]]:
    current = knowledge_candidate_current_states()
    by_record: dict[str, dict[str, Any]] = {}

    for candidate in current.values():
        record_id = candidate.get("knowledge_record_id")
        if not record_id:
            continue

        by_record[record_id] = candidate

    return by_record


def bridge_state_for_knowledge_record(record_id: str) -> str:
    candidate = knowledge_candidate_by_record().get(record_id)

    if not candidate:
        return "knowledge_only"

    status = candidate.get("review_status", "")

    if status == "candidate_created":
        return "candidate_created"

    if status == "candidate_queued":
        return "candidate_queued"

    if status in {"approved", "rejected", "deferred"}:
        return "candidate_reviewed"

    return status or "candidate_created"


def load_knowledge_candidates(
    limit: int = 100,
    include_closed: bool = True,
    current_only: bool = True,
) -> list[dict[str, Any]]:
    """
    Public loader.
    current_only=True returns one current state per candidate_id.
    current_only=False returns raw append-only events.
    """
    if not current_only:
        return load_knowledge_candidate_events_raw(
            limit=limit,
            include_closed=include_closed,
        )

    current = knowledge_candidate_current_states()
    items = list(current.values())

    if not include_closed:
        items = [
            item for item in items
            if item.get("review_status") not in {"approved", "rejected"}
        ]

    return items[-limit:]


def knowledge_bridge_status() -> dict[str, Any]:
    records = load_records(limit=100000, include_inactive=True)
    current_candidates = knowledge_candidate_current_states()
    by_record = knowledge_candidate_by_record()
    raw_events = load_knowledge_candidate_events_raw(limit=100000, include_closed=True)

    counts = {
        "knowledge_only": 0,
        "candidate_created": 0,
        "candidate_queued": 0,
        "candidate_reviewed": 0,
        "duplicate_records": 0,
    }

    record_states = []

    for record in records:
        record_id = record.get("record_id", "")

        if record.get("status") == "duplicate":
            state = "duplicate_record"
            counts["duplicate_records"] += 1
        else:
            state = bridge_state_for_knowledge_record(record_id)

            if state in counts:
                counts[state] += 1
            else:
                counts["knowledge_only"] += 1

        candidate = by_record.get(record_id, {})

        record_states.append({
            "knowledge_record_id": record_id,
            "title": record.get("title", ""),
            "source_id": record.get("source_id", ""),
            "record_status": record.get("status", "active"),
            "bridge_state": state,
            "candidate_id": candidate.get("candidate_id", ""),
            "candidate_review_status": candidate.get("review_status", ""),
            "review_id": candidate.get("review_id", ""),
        })

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "raw_candidate_event_count": len(raw_events),
        "current_candidate_count": len(current_candidates),
        "knowledge_record_count": len(records),
        "counts": counts,
        "record_states": record_states,
        "doctrine": [
            "Knowledge candidate cleanup is a view and suppression layer.",
            "The candidate ledger remains append-only.",
            "A knowledge record should not create duplicate candidates.",
            "Durable memory still requires Review Queue approval.",
            "No direct knowledge-to-memory writes are allowed.",
        ],
    }


def knowledge_candidate_status() -> dict[str, Any]:
    current = load_knowledge_candidates(limit=100000, include_closed=True, current_only=True)
    raw = load_knowledge_candidate_events_raw(limit=100000, include_closed=True)

    counts: dict[str, int] = {}

    for candidate in current:
        status = candidate.get("review_status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    return {
        "knowledge_version": KNOWLEDGE_VERSION,
        "policy_version": POLICY_VERSION,
        "candidate_count": len(current),
        "raw_candidate_event_count": len(raw),
        "counts": counts,
        "bridge_status": knowledge_bridge_status(),
        "candidates_path": str(KNOWLEDGE_CANDIDATES_PATH.relative_to(Path(__file__).resolve().parent.parent)),
        "doctrine": [
            "Knowledge candidates are shown as current state by default.",
            "Raw candidate events remain append-only.",
            "Duplicate candidate creation is suppressed by knowledge_record_id.",
            "Durable memory requires Review Queue approval.",
            "No direct knowledge-to-memory writes are allowed.",
        ],
    }


_previous_build_candidate_from_knowledge_v028c1b = build_candidate_from_knowledge


def build_candidate_from_knowledge(
    *,
    knowledge_record_id: str,
    created_by: str = "Oracle",
    reason: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """
    Idempotent hardfix:
    same knowledge_record_id returns existing current candidate state.
    """
    existing = knowledge_candidate_by_record().get(knowledge_record_id)

    if existing:
        return {
            "status": "existing_candidate",
            "candidate": existing,
            "bridge_state": bridge_state_for_knowledge_record(knowledge_record_id),
            "doctrine": "Existing knowledge candidate returned; no duplicate candidate was written.",
        }

    return _previous_build_candidate_from_knowledge_v028c1b(
        knowledge_record_id=knowledge_record_id,
        created_by=created_by,
        reason=reason,
        force=force,
    )


# --- End Technemachina Knowledge Candidate Cleanup Hardfix ---
