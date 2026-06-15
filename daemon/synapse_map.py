from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DAEMON_DIR = Path(__file__).resolve().parent

LOGS_DIR = ROOT_DIR / "logs"
MEMORY_DIR = LOGS_DIR / "memory"
KNOWLEDGE_DIR = LOGS_DIR / "knowledge"
THREAD_DIR = LOGS_DIR / "threads"

SYNAPSE_VERSION = "v0.2.9"
POLICY_VERSION = "synapse_map_read_only_policy_v1"
DEFAULT_SKIN = "constellation"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    items = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(item, dict):
            items.append(item)

    return items


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def compact(value: str, limit: int = 240) -> str:
    value = " ".join(str(value or "").split())
    return value[:limit]


def classify_owner_scope(entity_type: str) -> str:
    scope_by_type = {
        "milestone": "developer",
        "milestone_cluster": "developer",
        "project_context": "developer",
        "doctrine": "system_doctrine",
        "memory_layer": "system",
        "thread": "personal",
        "memory_record": "personal",
        "thread_candidate": "personal_governance",
        "review_item": "personal_governance",
        "review_decision": "personal_governance",
        "knowledge_source": "imported",
        "knowledge_record": "imported",
        "knowledge_candidate": "imported_governance",
    }
    return scope_by_type.get(entity_type, "unclassified")


def entity(
    *,
    entity_id: str,
    entity_type: str,
    label: str,
    status: str = "active",
    weight: float = 0.5,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": entity_id,
        "type": entity_type,
        "owner_scope": classify_owner_scope(entity_type),
        "label": label or entity_id,
        "status": status or "unknown",
        "weight": weight,
        "visibility": "local",
        "skin": {
            "renderer": DEFAULT_SKIN,
            "node_class": entity_type,
            "salience": weight,
        },
        "metadata": metadata or {},
    }


def relation(
    *,
    relation_id: str,
    source: str,
    target: str,
    relation_type: str,
    strength: float = 0.5,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": relation_id,
        "source": source,
        "target": target,
        "type": relation_type,
        "strength": strength,
        "visibility": "local",
        "skin": {
            "renderer": DEFAULT_SKIN,
            "edge_class": relation_type,
            "luminosity": strength,
        },
        "metadata": metadata or {},
    }


def dedupe_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}

    for item in entities:
        item_id = item.get("id")
        if not item_id:
            continue
        seen[item_id] = item

    return list(seen.values())


def dedupe_relations(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}

    for item in relations:
        item_id = item.get("id")
        if not item_id:
            continue
        seen[item_id] = item

    return list(seen.values())


def build_memory_entities() -> list[dict[str, Any]]:
    records = read_jsonl(MEMORY_DIR / "memory_records.jsonl")
    entities = []

    for record in records:
        record_id = record.get("record_id") or record.get("id")
        if not record_id:
            continue

        layer = record.get("layer", "unknown")
        confidence = record.get("confidence", "medium")
        status = record.get("status", "active")

        weight = 0.8 if confidence == "high" else 0.55 if confidence == "medium" else 0.35

        entities.append(entity(
            entity_id=f"memory:{record_id}",
            entity_type="memory_record",
            label=record.get("title") or record.get("summary") or record_id,
            status=status,
            weight=weight,
            metadata={
                "record_id": record_id,
                "layer": layer,
                "record_type": record.get("record_type"),
                "confidence": confidence,
                "summary": record.get("summary", ""),
                "source_ref": record.get("source_ref", ""),
                "tags": record.get("tags", []),
            },
        ))

        if layer:
            entities.append(entity(
                entity_id=f"layer:{layer}",
                entity_type="memory_layer",
                label=f"{layer.upper()} Layer",
                status="active",
                weight=0.65,
                metadata={"layer": layer},
            ))

    return entities


def build_knowledge_entities() -> list[dict[str, Any]]:
    records = load_knowledge_records_for_synapse()
    sources_registry = read_json(KNOWLEDGE_DIR / "knowledge_sources.json", {"sources": {}})
    sources = sources_registry.get("sources", {})
    entities = []

    for source in sources.values():
        source_id = source.get("source_id")
        if not source_id:
            continue

        entities.append(entity(
            entity_id=f"knowledge_source:{source_id}",
            entity_type="knowledge_source",
            label=source.get("source_title") or source_id,
            status=source.get("status", "active"),
            weight=0.5,
            metadata={
                "source_id": source_id,
                "source_path": source.get("source_path", ""),
                "source_type": source.get("source_type", ""),
                "origin": source.get("origin", ""),
                "content_hash": source.get("content_hash", ""),
                "provenance_label": source.get("provenance_label", ""),
                "duplicate_of": source.get("duplicate_of"),
            },
        ))

    for record in records:
        record_id = record.get("record_id")
        if not record_id:
            continue

        status = record.get("status", "active")
        weight = 0.55 if status == "active" else 0.25

        entities.append(entity(
            entity_id=f"knowledge_record:{record_id}",
            entity_type="knowledge_record",
            label=record.get("title") or record_id,
            status=status,
            weight=weight,
            metadata={
                "record_id": record_id,
                "source_id": record.get("source_id", ""),
                "summary": record.get("summary", ""),
                "tags": record.get("tags", []),
                "provenance": record.get("provenance", ""),
                "memory_write_allowed": record.get("memory_write_allowed", False),
                "candidate_path_allowed": record.get("candidate_path_allowed", False),
            },
        ))

    return entities


def build_candidate_entities() -> list[dict[str, Any]]:
    thread_candidates = read_jsonl(MEMORY_DIR / "candidates.jsonl")
    knowledge_candidates = read_jsonl(KNOWLEDGE_DIR / "knowledge_candidates.jsonl")

    entities = []

    # Current state by candidate_id for knowledge candidates.
    current_knowledge_candidates: dict[str, dict[str, Any]] = {}
    for item in knowledge_candidates:
        candidate_id = item.get("candidate_id")
        if candidate_id:
            current_knowledge_candidates[candidate_id] = item

    for candidate in thread_candidates:
        candidate_id = candidate.get("candidate_id")
        if not candidate_id:
            continue

        status = candidate.get("review_status", "candidate")
        weight = 0.65 if status in {"candidate", "queued_for_review", "enqueued"} else 0.45

        entities.append(entity(
            entity_id=f"thread_candidate:{candidate_id}",
            entity_type="thread_candidate",
            label=candidate.get("title") or candidate_id,
            status=status,
            weight=weight,
            metadata={
                "candidate_id": candidate_id,
                "source_thread_id": candidate.get("source_thread_id", ""),
                "record_type": candidate.get("record_type"),
                "layer": candidate.get("layer_suggested") or candidate.get("layer"),
                "confidence": candidate.get("confidence"),
                "summary": candidate.get("summary", ""),
                "why_candidate": candidate.get("why_candidate", ""),
            },
        ))

    for candidate in current_knowledge_candidates.values():
        candidate_id = candidate.get("candidate_id")
        if not candidate_id:
            continue

        status = candidate.get("review_status", "candidate_created")
        weight = 0.85 if candidate.get("confidence") == "high" else 0.65

        entities.append(entity(
            entity_id=f"knowledge_candidate:{candidate_id}",
            entity_type="knowledge_candidate",
            label=candidate.get("title") or candidate_id,
            status=status,
            weight=weight,
            metadata={
                "candidate_id": candidate_id,
                "knowledge_record_id": candidate.get("knowledge_record_id", ""),
                "source_id": candidate.get("source_id", ""),
                "suggested_layer": candidate.get("suggested_layer", ""),
                "suggested_record_type": candidate.get("suggested_record_type", ""),
                "candidate_score": candidate.get("candidate_score"),
                "signals": candidate.get("signals", []),
                "confidence": candidate.get("confidence"),
                "review_id": candidate.get("review_id", ""),
                "why_candidate": candidate.get("why_candidate", ""),
            },
        ))

    return entities


def build_review_entities() -> list[dict[str, Any]]:
    queue = read_jsonl(MEMORY_DIR / "review_queue.jsonl")
    decisions = read_jsonl(MEMORY_DIR / "review_decisions.jsonl")
    entities = []

    for item in queue:
        review_id = item.get("review_id")
        if not review_id:
            continue

        status = item.get("review_status", "pending")
        weight = 0.8 if status == "pending" else 0.55

        entities.append(entity(
            entity_id=f"review:{review_id}",
            entity_type="review_item",
            label=item.get("title") or review_id,
            status=status,
            weight=weight,
            metadata={
                "review_id": review_id,
                "record_id": item.get("record_id"),
                "record_type": item.get("record_type"),
                "layer": item.get("layer"),
                "confidence": item.get("confidence"),
                "suggested_action": item.get("suggested_action"),
                "reason_for_review": item.get("reason_for_review", ""),
                "source_refs": item.get("source_refs", []),
            },
        ))

    for decision in decisions:
        decision_id = decision.get("decision_id")
        if not decision_id:
            continue

        status = decision.get("decision", "decision")
        weight = 0.9 if status == "approved" else 0.55

        entities.append(entity(
            entity_id=f"decision:{decision_id}",
            entity_type="review_decision",
            label=f"{status}: {decision.get('review_id', '')}",
            status=status,
            weight=weight,
            metadata={
                "decision_id": decision_id,
                "review_id": decision.get("review_id"),
                "record_id": decision.get("record_id"),
                "reviewed_by": decision.get("reviewed_by"),
                "reviewed_at": decision.get("reviewed_at"),
                "notes": decision.get("notes", ""),
            },
        ))

    return entities


def build_thread_entities() -> list[dict[str, Any]]:
    registry = read_json(THREAD_DIR / "thread_registry.json", {"threads": {}})
    threads = registry.get("threads", {})
    entities = []

    for thread in threads.values():
        thread_id = thread.get("thread_id")
        if not thread_id:
            continue

        status = "archived" if thread.get("archived") else "active"

        entities.append(entity(
            entity_id=f"thread:{thread_id}",
            entity_type="thread",
            label=thread.get("title") or thread_id,
            status=status,
            weight=0.45,
            metadata={
                "thread_id": thread_id,
                "preview": thread.get("preview", ""),
                "created_at": thread.get("created_at", ""),
                "updated_at": thread.get("updated_at", ""),
                "message_count": thread.get("message_count", 0),
            },
        ))

    return entities


def build_project_entities() -> list[dict[str, Any]]:
    context = read_json(DAEMON_DIR / "project_context.json", {})
    entities = []

    if context:
        entities.append(entity(
            entity_id="project_context:technemachina",
            entity_type="project_context",
            label=context.get("project", "Technemachina Daemon"),
            status=context.get("status", "active"),
            weight=0.95,
            metadata={
                "version": context.get("current_version"),
                "status": context.get("status"),
                "objective": context.get("current_objective"),
                "active_provider": context.get("active_provider"),
            },
        ))

    doctrine_lines = context.get("doctrine", "")
    if doctrine_lines:
        entities.append(entity(
            entity_id="doctrine:daemon_evolution",
            entity_type="doctrine",
            label="Daemon Evolution Doctrine",
            status="active",
            weight=0.9,
            metadata={"doctrine": doctrine_lines},
        ))

    return entities


def build_relations() -> list[dict[str, Any]]:
    relations = []

    memory_records = read_jsonl(MEMORY_DIR / "memory_records.jsonl")
    knowledge_records = load_knowledge_records_for_synapse()
    knowledge_candidates = read_jsonl(KNOWLEDGE_DIR / "knowledge_candidates.jsonl")
    thread_candidates = read_jsonl(MEMORY_DIR / "candidates.jsonl")
    review_queue = read_jsonl(MEMORY_DIR / "review_queue.jsonl")
    decisions = read_jsonl(MEMORY_DIR / "review_decisions.jsonl")

    for record in memory_records:
        record_id = record.get("record_id") or record.get("id")
        layer = record.get("layer")
        if record_id and layer:
            relations.append(relation(
                relation_id=f"rel:memory:{record_id}:layer:{layer}",
                source=f"memory:{record_id}",
                target=f"layer:{layer}",
                relation_type="belongs_to_layer",
                strength=0.75,
            ))

    for record in knowledge_records:
        record_id = record.get("record_id")
        source_id = record.get("source_id")
        if record_id and source_id:
            relations.append(relation(
                relation_id=f"rel:knowledge_record:{record_id}:source:{source_id}",
                source=f"knowledge_record:{record_id}",
                target=f"knowledge_source:{source_id}",
                relation_type="references_source",
                strength=0.7,
            ))

    # Current state by candidate_id.
    current_knowledge_candidates: dict[str, dict[str, Any]] = {}
    for candidate in knowledge_candidates:
        candidate_id = candidate.get("candidate_id")
        if candidate_id:
            current_knowledge_candidates[candidate_id] = candidate

    for candidate in current_knowledge_candidates.values():
        candidate_id = candidate.get("candidate_id")
        record_id = candidate.get("knowledge_record_id")
        source_id = candidate.get("source_id")
        review_id = candidate.get("review_id")

        if candidate_id and record_id:
            relations.append(relation(
                relation_id=f"rel:knowledge_candidate:{candidate_id}:from_record:{record_id}",
                source=f"knowledge_candidate:{candidate_id}",
                target=f"knowledge_record:{record_id}",
                relation_type="candidate_from",
                strength=0.9,
            ))

        if candidate_id and source_id:
            relations.append(relation(
                relation_id=f"rel:knowledge_candidate:{candidate_id}:source:{source_id}",
                source=f"knowledge_candidate:{candidate_id}",
                target=f"knowledge_source:{source_id}",
                relation_type="references_source",
                strength=0.75,
            ))

        if candidate_id and review_id:
            relations.append(relation(
                relation_id=f"rel:knowledge_candidate:{candidate_id}:queued_as:{review_id}",
                source=f"knowledge_candidate:{candidate_id}",
                target=f"review:{review_id}",
                relation_type="queued_as",
                strength=0.95,
            ))

    for candidate in thread_candidates:
        candidate_id = candidate.get("candidate_id")
        thread_id = candidate.get("source_thread_id")

        if candidate_id and thread_id:
            relations.append(relation(
                relation_id=f"rel:thread_candidate:{candidate_id}:thread:{thread_id}",
                source=f"thread_candidate:{candidate_id}",
                target=f"thread:{thread_id}",
                relation_type="linked_to_thread",
                strength=0.75,
            ))

    for item in review_queue:
        review_id = item.get("review_id")
        source_refs = item.get("source_refs", [])

        for ref in source_refs:
            if not ref:
                continue

            if str(ref).startswith("krec_"):
                target = f"knowledge_record:{ref}"
            elif str(ref).startswith("ksrc_"):
                target = f"knowledge_source:{ref}"
            elif str(ref).startswith("kcand_"):
                target = f"knowledge_candidate:{ref}"
            elif str(ref).startswith("cand_"):
                target = f"thread_candidate:{ref}"
            else:
                continue

            relations.append(relation(
                relation_id=f"rel:review:{review_id}:source_ref:{ref}",
                source=f"review:{review_id}",
                target=target,
                relation_type="governed_by",
                strength=0.7,
            ))

    for decision in decisions:
        decision_id = decision.get("decision_id")
        review_id = decision.get("review_id")
        record_id = decision.get("record_id")
        decision_type = decision.get("decision", "reviewed")

        if decision_id and review_id:
            relations.append(relation(
                relation_id=f"rel:decision:{decision_id}:review:{review_id}",
                source=f"decision:{decision_id}",
                target=f"review:{review_id}",
                relation_type="reviewed_by",
                strength=0.8,
            ))

        if decision_id and record_id:
            rel_type = "approved_into" if decision_type == "approved" else f"{decision_type}_as"
            relations.append(relation(
                relation_id=f"rel:decision:{decision_id}:record:{record_id}",
                source=f"decision:{decision_id}",
                target=f"memory:{record_id}",
                relation_type=rel_type,
                strength=0.85,
            ))

    relations.append(relation(
        relation_id="rel:project_context:doctrine",
        source="project_context:technemachina",
        target="doctrine:daemon_evolution",
        relation_type="governed_by",
        strength=0.9,
    ))

    return dedupe_relations(relations)


def build_entities() -> list[dict[str, Any]]:
    entities = []
    entities.extend(build_memory_entities())
    entities.extend(build_knowledge_entities())
    entities.extend(build_candidate_entities())
    entities.extend(build_review_entities())
    entities.extend(build_thread_entities())
    entities.extend(build_project_entities())
    return dedupe_entities(entities)


def synapse_status() -> dict[str, Any]:
    entities = build_entities()
    relations = build_relations()

    entity_counts: dict[str, int] = {}
    for item in entities:
        entity_type = item.get("type", "unknown")
        entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1

    relation_counts: dict[str, int] = {}
    for item in relations:
        relation_type = item.get("type", "unknown")
        relation_counts[relation_type] = relation_counts.get(relation_type, 0) + 1

    return {
        "synapse_version": SYNAPSE_VERSION,
        "policy_version": POLICY_VERSION,
        "skin": DEFAULT_SKIN,
        "ready": True,
        "read_only": True,
        "entity_count": len(entities),
        "relation_count": len(relations),
        "entity_counts": entity_counts,
        "relation_counts": relation_counts,
        "generated_at": utc_now(),
        "doctrine": [
            "Synapse Map is read-only.",
            "Control Center is operational governance.",
            "Synapse Map is relationship discovery.",
            "H.I.V.E. is documented but not operational.",
            "The Constellation Skin is visual-only and swappable.",
        ],
    }


def get_entities(entity_type: str = "") -> dict[str, Any]:
    entities = build_entities()

    if entity_type:
        entities = [item for item in entities if item.get("type") == entity_type]

    return {
        "entities": entities,
        "count": len(entities),
        "filter": {"type": entity_type},
        "synapse_version": SYNAPSE_VERSION,
        "read_only": True,
    }


def get_relations(relation_type: str = "") -> dict[str, Any]:
    relations = build_relations()

    if relation_type:
        relations = [item for item in relations if item.get("type") == relation_type]

    return {
        "relations": relations,
        "count": len(relations),
        "filter": {"type": relation_type},
        "synapse_version": SYNAPSE_VERSION,
        "read_only": True,
    }


def get_map(entity_type: str = "", relation_type: str = "") -> dict[str, Any]:
    entity_payload = get_entities(entity_type=entity_type)
    relation_payload = get_relations(relation_type=relation_type)

    entity_ids = {item["id"] for item in entity_payload["entities"]}

    relations = [
        rel for rel in relation_payload["relations"]
        if rel.get("source") in entity_ids and rel.get("target") in entity_ids
    ]

    return {
        "nodes": entity_payload["entities"],
        "edges": relations,
        "meta": {
            "synapse_version": SYNAPSE_VERSION,
            "policy_version": POLICY_VERSION,
            "skin": DEFAULT_SKIN,
            "generated_at": utc_now(),
            "node_count": len(entity_payload["entities"]),
            "edge_count": len(relations),
            "filters": {
                "entity_type": entity_type,
                "relation_type": relation_type,
            },
            "read_only": True,
        },
        "styleHints": {
            "defaultRenderer": DEFAULT_SKIN,
            "nodeShape": "mini-star",
            "edgeShape": "luminous-constellation-link",
            "zoomBehavior": "constellation-to-technical",
            "mutationAllowed": False,
        },
        "doctrine": "The Synapse Map visualizes relationships without mutating memory, knowledge, candidates, reviews, decisions, or H.I.V.E.",
    }


# --- Technemachina Synapse Map Review Ledger Hardpatch v0.2.9a ---

SYNAPSE_VERSION = "v0.2.9a"
POLICY_VERSION = "synapse_map_review_ledger_hardpatch_policy_v1"


def synapse_candidate_paths(folder: str, filename: str) -> list[Path]:
    cwd = Path.cwd()
    return [
        ROOT_DIR / "logs" / folder / filename,
        DAEMON_DIR / "logs" / folder / filename,
        cwd / "logs" / folder / filename,
        cwd.parent / "logs" / folder / filename,
    ]


def read_jsonl_many(paths: list[Path]) -> list[dict[str, Any]]:
    merged = []
    seen = set()

    for priority, path in enumerate(paths, start=1):
        for item in read_jsonl(path):
            key = (
                item.get("record_id")
                or item.get("review_id")
                or item.get("decision_id")
                or item.get("candidate_id")
                or item.get("source_id")
                or json.dumps(item, sort_keys=True, ensure_ascii=False)
            )

            if key in seen:
                continue

            enriched = dict(item)
            enriched["_source_path"] = str(path.resolve())
            enriched["_source_priority"] = priority

            seen.add(key)
            merged.append(enriched)

    return merged


def load_review_queue_for_synapse() -> list[dict[str, Any]]:
    return read_jsonl_many(synapse_candidate_paths("memory", "review_queue.jsonl"))


def load_review_decisions_for_synapse() -> list[dict[str, Any]]:
    return read_jsonl_many(synapse_candidate_paths("memory", "review_decisions.jsonl"))


def load_thread_candidates_for_synapse() -> list[dict[str, Any]]:
    return read_jsonl_many(synapse_candidate_paths("memory", "candidates.jsonl"))


def load_memory_records_for_synapse() -> list[dict[str, Any]]:
    return read_jsonl_many(
        synapse_candidate_paths("memory", "memory_records.jsonl")
        + synapse_candidate_paths("memory", "records.jsonl")
        + synapse_candidate_paths("memory", "memory_ledger.jsonl")
    )


def load_knowledge_records_for_synapse() -> list[dict[str, Any]]:
    return read_jsonl_many(
        synapse_candidate_paths("knowledge", "knowledge_records.jsonl")
    )


def load_knowledge_candidates_for_synapse() -> list[dict[str, Any]]:
    return read_jsonl_many(synapse_candidate_paths("knowledge", "knowledge_candidates.jsonl"))


def build_review_entities() -> list[dict[str, Any]]:
    queue = load_review_queue_for_synapse()
    decisions = load_review_decisions_for_synapse()
    entities = []

    for item in queue:
        review_id = item.get("review_id")
        if not review_id:
            continue

        status = item.get("review_status", "pending")
        weight = 0.85 if status == "pending" else 0.55

        entities.append(entity(
            entity_id=f"review:{review_id}",
            entity_type="review_item",
            label=item.get("title") or item.get("summary") or review_id,
            status=status,
            weight=weight,
            metadata={
                "review_id": review_id,
                "record_id": item.get("record_id"),
                "record_type": item.get("record_type"),
                "layer": item.get("layer"),
                "confidence": item.get("confidence"),
                "suggested_action": item.get("suggested_action"),
                "reason_for_review": item.get("reason_for_review", ""),
                "source_refs": item.get("source_refs", []),
                "created_at": item.get("created_at", ""),
                "reviewed_at": item.get("reviewed_at", ""),
                "reviewed_by": item.get("reviewed_by", ""),
            },
        ))

    for decision in decisions:
        decision_id = decision.get("decision_id")
        if not decision_id:
            continue

        status = decision.get("decision", "decision")
        weight = 0.9 if status == "approved" else 0.55

        entities.append(entity(
            entity_id=f"decision:{decision_id}",
            entity_type="review_decision",
            label=f"{status}: {decision.get('review_id', '')}",
            status=status,
            weight=weight,
            metadata={
                "decision_id": decision_id,
                "review_id": decision.get("review_id"),
                "record_id": decision.get("record_id"),
                "reviewed_by": decision.get("reviewed_by"),
                "reviewed_at": decision.get("reviewed_at"),
                "notes": decision.get("notes", ""),
            },
        ))

    return entities


def build_relations() -> list[dict[str, Any]]:
    relations = []

    memory_records = load_memory_records_for_synapse()
    knowledge_records = load_knowledge_records_for_synapse()
    knowledge_candidates = load_knowledge_candidates_for_synapse()
    thread_candidates = load_thread_candidates_for_synapse()
    review_queue = load_review_queue_for_synapse()
    decisions = load_review_decisions_for_synapse()

    for record in memory_records:
        record_id = record.get("record_id") or record.get("id")
        layer = record.get("layer")
        if record_id and layer:
            relations.append(relation(
                relation_id=f"rel:memory:{record_id}:layer:{layer}",
                source=f"memory:{record_id}",
                target=f"layer:{layer}",
                relation_type="belongs_to_layer",
                strength=0.75,
            ))

    for record in knowledge_records:
        record_id = record.get("record_id")
        source_id = record.get("source_id")
        if record_id and source_id:
            relations.append(relation(
                relation_id=f"rel:knowledge_record:{record_id}:source:{source_id}",
                source=f"knowledge_record:{record_id}",
                target=f"knowledge_source:{source_id}",
                relation_type="references_source",
                strength=0.7,
            ))

    current_knowledge_candidates = {}
    for candidate in knowledge_candidates:
        candidate_id = candidate.get("candidate_id")
        if candidate_id:
            current_knowledge_candidates[candidate_id] = candidate

    for candidate in current_knowledge_candidates.values():
        candidate_id = candidate.get("candidate_id")
        record_id = candidate.get("knowledge_record_id")
        source_id = candidate.get("source_id")
        review_id = candidate.get("review_id")

        if candidate_id and record_id:
            relations.append(relation(
                relation_id=f"rel:knowledge_candidate:{candidate_id}:from_record:{record_id}",
                source=f"knowledge_candidate:{candidate_id}",
                target=f"knowledge_record:{record_id}",
                relation_type="candidate_from",
                strength=0.9,
            ))

        if candidate_id and source_id:
            relations.append(relation(
                relation_id=f"rel:knowledge_candidate:{candidate_id}:source:{source_id}",
                source=f"knowledge_candidate:{candidate_id}",
                target=f"knowledge_source:{source_id}",
                relation_type="references_source",
                strength=0.75,
            ))

        if candidate_id and review_id:
            relations.append(relation(
                relation_id=f"rel:knowledge_candidate:{candidate_id}:queued_as:{review_id}",
                source=f"knowledge_candidate:{candidate_id}",
                target=f"review:{review_id}",
                relation_type="queued_as",
                strength=0.95,
            ))

    for candidate in thread_candidates:
        candidate_id = candidate.get("candidate_id")
        thread_id = candidate.get("source_thread_id")
        if candidate_id and thread_id:
            relations.append(relation(
                relation_id=f"rel:thread_candidate:{candidate_id}:thread:{thread_id}",
                source=f"thread_candidate:{candidate_id}",
                target=f"thread:{thread_id}",
                relation_type="linked_to_thread",
                strength=0.75,
            ))

    for item in review_queue:
        review_id = item.get("review_id")
        if not review_id:
            continue

        for ref in item.get("source_refs", []):
            ref = str(ref)
            if ref.startswith("krec_"):
                target = f"knowledge_record:{ref}"
            elif ref.startswith("ksrc_"):
                target = f"knowledge_source:{ref}"
            elif ref.startswith("kcand_"):
                target = f"knowledge_candidate:{ref}"
            elif ref.startswith("cand_"):
                target = f"thread_candidate:{ref}"
            else:
                continue

            relations.append(relation(
                relation_id=f"rel:review:{review_id}:source_ref:{ref}",
                source=f"review:{review_id}",
                target=target,
                relation_type="governed_by",
                strength=0.7,
            ))

    for decision in decisions:
        decision_id = decision.get("decision_id")
        review_id = decision.get("review_id")
        record_id = decision.get("record_id")
        decision_type = decision.get("decision", "reviewed")

        if decision_id and review_id:
            relations.append(relation(
                relation_id=f"rel:decision:{decision_id}:review:{review_id}",
                source=f"decision:{decision_id}",
                target=f"review:{review_id}",
                relation_type="reviewed_by",
                strength=0.8,
            ))

        if decision_id and record_id:
            rel_type = "approved_into" if decision_type == "approved" else f"{decision_type}_as"
            relations.append(relation(
                relation_id=f"rel:decision:{decision_id}:record:{record_id}",
                source=f"decision:{decision_id}",
                target=f"memory:{record_id}",
                relation_type=rel_type,
                strength=0.85,
            ))

    relations.append(relation(
        relation_id="rel:project_context:doctrine",
        source="project_context:technemachina",
        target="doctrine:daemon_evolution",
        relation_type="governed_by",
        strength=0.9,
    ))

    return dedupe_relations(relations)


# --- End Technemachina Synapse Map Review Ledger Hardpatch ---


# --- Technemachina Synapse Map Memory Node Hardpatch v0.2.9b ---

SYNAPSE_VERSION = "v0.2.9b"
POLICY_VERSION = "synapse_map_memory_node_hardpatch_policy_v1"


def build_memory_entities() -> list[dict[str, Any]]:
    records = load_memory_records_for_synapse()
    entities = []

    for record in records:
        record_id = record.get("record_id") or record.get("id")
        if not record_id:
            continue

        layer = record.get("layer", "unknown")
        confidence = record.get("confidence", "medium")
        status = record.get("status", "active")
        weight = 0.8 if confidence == "high" else 0.55 if confidence == "medium" else 0.35

        entities.append(entity(
            entity_id=f"memory:{record_id}",
            entity_type="memory_record",
            label=record.get("title") or record.get("summary") or record_id,
            status=status,
            weight=weight,
            metadata={
                "record_id": record_id,
                "layer": layer,
                "record_type": record.get("record_type"),
                "confidence": confidence,
                "summary": record.get("summary", ""),
                "source_ref": record.get("source_ref", ""),
                "source_title": record.get("source_title", ""),
                "source_type": record.get("source_type", ""),
                "tags": record.get("tags", []),
                "review_state": record.get("review_state", ""),
                "created_at": record.get("created_at", ""),
                "updated_at": record.get("updated_at", ""),
            },
        ))

        if layer:
            entities.append(entity(
                entity_id=f"layer:{layer}",
                entity_type="memory_layer",
                label=f"{str(layer).upper()} Layer",
                status="active",
                weight=0.65,
                metadata={"layer": layer},
            ))

    return entities


def build_entities() -> list[dict[str, Any]]:
    entities = []
    entities.extend(build_memory_entities())
    entities.extend(build_knowledge_entities())
    entities.extend(build_candidate_entities())
    entities.extend(build_review_entities())
    entities.extend(build_thread_entities())
    entities.extend(build_project_entities())
    return dedupe_entities(entities)


# --- End Technemachina Synapse Map Memory Node Hardpatch ---


# --- Technemachina Synapse Map Object-Backed Stars + Milestone Layer v0.2.9c-1 ---

SYNAPSE_VERSION = "v0.2.9c-1"
POLICY_VERSION = "synapse_object_backed_stars_milestone_layer_policy_v1"

_previous_build_project_entities_for_milestones = build_project_entities
_previous_build_relations_for_milestones = build_relations


def milestone_slug(text: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(text))
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_")[:90] or "milestone"


def milestone_group(name: str) -> str:
    lower = name.lower()

    if "brain" in lower or "provider" in lower or "router" in lower:
        return "brain_provider"
    if "memory" in lower or "review" in lower:
        return "memory_governance"
    if "thread" in lower or "candidate" in lower:
        return "threads_candidates"
    if "knowledge" in lower:
        return "knowledge"
    if "synapse" in lower:
        return "synapse"
    if "control center" in lower or "ui" in lower or "frontend" in lower:
        return "interface"
    if "h.i.v.e" in lower or "hive" in lower:
        return "hive_documented"
    if "guardrail" in lower or "risk" in lower or "restriction" in lower:
        return "safety"
    return "core"


def load_project_context_for_synapse() -> dict[str, Any]:
    candidates = [
        DAEMON_DIR / "project_context.json",
        ROOT_DIR / "daemon" / "project_context.json",
        ROOT_DIR / "project_context.json",
        Path.cwd() / "project_context.json",
    ]

    for path in candidates:
        data = read_json(path, {})
        if data:
            return data

    return {}


def build_milestone_entities() -> list[dict[str, Any]]:
    context = load_project_context_for_synapse()
    milestones = context.get("locked_milestones", [])
    entities = []

    for index, milestone in enumerate(milestones):
        if not milestone:
            continue

        group = milestone_group(milestone)
        weight = 0.72

        if "Online" in milestone:
            weight = 0.82
        if "Verified" in milestone or "Locked" in milestone:
            weight = 0.78
        if milestone.startswith("v0.2.9"):
            weight = 0.92

        entities.append(entity(
            entity_id=f"milestone:{milestone_slug(milestone)}",
            entity_type="milestone",
            label=milestone,
            status="locked",
            weight=weight,
            metadata={
                "milestone": milestone,
                "sequence": index + 1,
                "group": group,
                "source": "project_context.locked_milestones",
            },
        ))

    return entities


def build_project_entities() -> list[dict[str, Any]]:
    entities = []
    entities.extend(_previous_build_project_entities_for_milestones())
    entities.extend(build_milestone_entities())
    return dedupe_entities(entities)


def build_relations() -> list[dict[str, Any]]:
    relations = []
    relations.extend(_previous_build_relations_for_milestones())

    milestones = build_milestone_entities()
    previous_id = None

    for node in milestones:
        node_id = node.get("id")
        if not node_id:
            continue

        relations.append(relation(
            relation_id=f"rel:project_context:milestone:{node_id}",
            source="project_context:technemachina",
            target=node_id,
            relation_type="has_milestone",
            strength=0.72,
        ))

        group = node.get("metadata", {}).get("group", "core")
        cluster_id = f"milestone_cluster:{group}"

        relations.append(relation(
            relation_id=f"rel:{node_id}:cluster:{group}",
            source=node_id,
            target=cluster_id,
            relation_type="belongs_to_cluster",
            strength=0.58,
        ))

        if previous_id:
            relations.append(relation(
                relation_id=f"rel:{previous_id}:precedes:{node_id}",
                source=previous_id,
                target=node_id,
                relation_type="precedes",
                strength=0.5,
            ))

        previous_id = node_id

    return dedupe_relations(relations)


def build_milestone_cluster_entities() -> list[dict[str, Any]]:
    groups = {
        "brain_provider": "Brain / Provider Cluster",
        "memory_governance": "Memory / Governance Cluster",
        "threads_candidates": "Threads / Candidates Cluster",
        "knowledge": "Knowledge Cluster",
        "synapse": "Synapse Cluster",
        "interface": "Interface Cluster",
        "hive_documented": "H.I.V.E. Documented Cluster",
        "safety": "Safety Cluster",
        "core": "Core Cluster",
    }

    return [
        entity(
            entity_id=f"milestone_cluster:{group}",
            entity_type="milestone_cluster",
            label=label,
            status="active",
            weight=0.7,
            metadata={
                "group": group,
                "source": "derived_from_milestone_groups",
            },
        )
        for group, label in groups.items()
    ]


_previous_build_entities_for_milestone_clusters = build_entities


def build_entities() -> list[dict[str, Any]]:
    entities = []
    entities.extend(_previous_build_entities_for_milestone_clusters())
    entities.extend(build_milestone_cluster_entities())
    return dedupe_entities(entities)


# --- End Technemachina Synapse Map Object-Backed Stars + Milestone Layer ---
