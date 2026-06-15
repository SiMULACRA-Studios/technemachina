from datetime import datetime, timezone
import math
import re

import memory_taxonomy


LAYER_PRIORITY = {
    "delta": 1.00,
    "theta": 0.90,
    "alpha": 0.75,
    "beta": 0.60,
    "gamma": 0.40,
}

CONFIDENCE_SCORE = {
    "high": 1.00,
    "medium": 0.65,
    "low": 0.35,
}

STATUS_MULTIPLIER = {
    "active": 1.00,
    "draft": 0.55,
    "superseded": 0.25,
    "expired": 0.20,
    "revoked": 0.00,
}


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9_#.-]+", text or "")
        if len(token.strip()) > 1
    ]


def age_days(iso_timestamp: str | None) -> float:
    if not iso_timestamp:
        return 9999.0

    try:
        created = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max((now - created).total_seconds() / 86400, 0.0)
    except Exception:
        return 9999.0


def freshness_label(days: float) -> str:
    if days <= 1:
        return "fresh"
    if days <= 14:
        return "recent"
    if days <= 90:
        return "aging"
    return "old"


def freshness_score(days: float) -> float:
    # Smooth decay: today ~= 1, two weeks ~= .5, old records still get some score.
    return max(0.10, 1.0 / (1.0 + (days / 14.0)))


def record_search_blob(record: dict) -> dict:
    fields = {
        "title": record.get("title", ""),
        "summary": record.get("summary", ""),
        "body": record.get("body", ""),
        "tags": " ".join(record.get("tags", [])),
        "source_title": record.get("source_title", ""),
        "source_ref": record.get("source_ref", ""),
        "provenance": record.get("provenance", ""),
        "record_type": record.get("record_type", ""),
        "layer": record.get("layer", ""),
        "scope": record.get("scope", ""),
    }
    return fields


def match_record(record: dict, query: str) -> dict:
    query_terms = tokenize(query)
    query_set = set(query_terms)

    fields = record_search_blob(record)

    matched_fields = []
    matched_text = []
    exact_matches = 0

    for field, value in fields.items():
        field_terms = set(tokenize(value))
        overlap = sorted(query_set.intersection(field_terms))

        if overlap:
            matched_fields.append(field)
            matched_text.extend(overlap)
            exact_matches += len(overlap)

    record_tags = set(str(tag).lower() for tag in record.get("tags", []))
    matched_tags = sorted(query_set.intersection(record_tags))

    tag_score = min(len(matched_tags) / max(len(query_set), 1), 1.0)
    keyword_score = min(exact_matches / max(len(query_set), 1), 1.0)

    layer = record.get("layer", "gamma")
    layer_score = LAYER_PRIORITY.get(layer, 0.40)

    confidence = record.get("confidence", "medium")
    confidence_score = CONFIDENCE_SCORE.get(confidence, 0.50)

    days = age_days(record.get("created_at"))
    fresh_score = freshness_score(days)

    status = record.get("status", "active")
    status_multiplier = STATUS_MULTIPLIER.get(status, 0.50)

    importance_weight = float(record.get("importance_weight", 0.5) or 0.5)
    retrieval_priority = float(record.get("retrieval_priority", 50) or 50) / 100.0

    base_score = (
        (tag_score * 0.28)
        + (keyword_score * 0.30)
        + (layer_score * 0.12)
        + (confidence_score * 0.12)
        + (fresh_score * 0.08)
        + (importance_weight * 0.05)
        + (retrieval_priority * 0.05)
    )

    rank_score = round(base_score * status_multiplier, 4)

    attach = should_attach_to_context(record, query, rank_score, matched_fields, matched_tags)

    why_parts = []

    if matched_tags:
        why_parts.append(f"matched tags: {', '.join(matched_tags)}")
    if matched_fields:
        why_parts.append(f"matched fields: {', '.join(sorted(set(matched_fields)))}")
    if confidence:
        why_parts.append(f"{confidence} confidence")
    if layer:
        why_parts.append(f"{layer} layer")

    if not why_parts:
        why_parts.append("weak policy/ranking match")

    confidence_basis = build_confidence_basis(
        tag_score=tag_score,
        keyword_score=keyword_score,
        confidence=confidence,
        status=status,
        layer=layer,
    )

    return {
        "record_id": record.get("record_id"),
        "record_type": record.get("record_type"),
        "layer": layer,
        "layer_origin": memory_taxonomy.CONTINUUM_LAYERS.get(layer, {}).get("name", layer),
        "scope": record.get("scope"),
        "title": record.get("title"),
        "summary": record.get("summary"),
        "status": status,
        "confidence": confidence,
        "confidence_basis": confidence_basis,
        "provenance": record.get("provenance", ""),
        "source_ref": record.get("source_ref", ""),
        "source_type": record.get("source_type", ""),
        "matched_tags": matched_tags,
        "matched_fields": sorted(set(matched_fields)),
        "matched_text": sorted(set(matched_text)),
        "retrieval_method": "local_keyword_policy_ranker",
        "freshness": freshness_label(days),
        "age_days": round(days, 3),
        "attach_to_context": attach["attach_to_context"],
        "attach_recommendation": attach["attach_recommendation"],
        "attach_reason": attach["attach_reason"],
        "attach_priority": attach["attach_priority"],
        "context_slot": attach["context_slot"],
        "rank_score": rank_score,
        "why_selected": "; ".join(why_parts),
        "explainability": {
            "tag_score": round(tag_score, 4),
            "keyword_score": round(keyword_score, 4),
            "layer_score": round(layer_score, 4),
            "confidence_score": round(confidence_score, 4),
            "freshness_score": round(fresh_score, 4),
            "status_multiplier": round(status_multiplier, 4),
            "importance_weight": round(importance_weight, 4),
            "retrieval_priority": round(retrieval_priority, 4),
        },
        "record": record,
    }


def build_confidence_basis(tag_score: float, keyword_score: float, confidence: str, status: str, layer: str) -> str:
    basis = []

    if tag_score > 0:
        basis.append("tag overlap")
    if keyword_score > 0:
        basis.append("exact keyword overlap")

    basis.append(f"record confidence={confidence}")
    basis.append(f"status={status}")
    basis.append(f"layer={layer}")

    return " + ".join(basis)


def should_attach_to_context(
    record: dict,
    query: str,
    rank_score: float,
    matched_fields: list[str],
    matched_tags: list[str],
) -> dict:
    layer = record.get("layer", "gamma")
    status = record.get("status", "active")

    if status != "active":
        return {
            "attach_to_context": False,
            "attach_recommendation": "no",
            "attach_reason": f"status is {status}, not active",
            "attach_priority": "blocked",
            "context_slot": "none",
        }

    if record.get("attach_to_context") is True and rank_score >= 0.25:
        explicit_attach = True
    else:
        explicit_attach = False

    has_match = bool(matched_fields or matched_tags)

    if layer in {"gamma", "beta"} and has_match:
        recommendation = "yes"
        priority = "medium"
        slot = "thread"
        reason = "short-range memory relevant to current query"
    elif layer == "alpha" and rank_score >= 0.35:
        recommendation = "yes"
        priority = "medium"
        slot = "project"
        reason = "recent project memory relevant to current query"
    elif layer == "theta" and (rank_score >= 0.30 or explicit_attach):
        recommendation = "yes"
        priority = "high" if rank_score >= 0.55 else "medium"
        slot = "project"
        reason = "stable project knowledge relevant to query"
    elif layer == "delta" and rank_score >= 0.45:
        recommendation = "yes"
        priority = "high"
        slot = "doctrine"
        reason = "doctrine memory relevant to governance or procedure"
    else:
        recommendation = "maybe" if rank_score >= 0.20 else "no"
        priority = "low" if recommendation == "maybe" else "none"
        slot = "project" if recommendation == "maybe" else "none"
        reason = "weak match; inspect before attaching"

    return {
        "attach_to_context": recommendation == "yes",
        "attach_recommendation": recommendation,
        "attach_reason": reason,
        "attach_priority": priority,
        "context_slot": slot,
    }


def search_memory(
    query: str,
    record_type: str | None = None,
    layer: str | None = None,
    scope: str | None = None,
    include_revoked: bool = False,
    limit: int = 10,
    min_score: float = 0.01,
) -> dict:
    records = memory_taxonomy.load_records(include_revoked=include_revoked)

    filtered = []

    for record in records:
        if record_type and record.get("record_type") != record_type:
            continue
        if layer and record.get("layer") != layer:
            continue
        if scope and record.get("scope") != scope:
            continue

        result = match_record(record, query)

        if result["rank_score"] >= min_score:
            filtered.append(result)

    filtered.sort(key=lambda item: item["rank_score"], reverse=True)
    results = filtered[: max(1, min(int(limit), 50))]

    selected = results[0] if results else None

    return {
        "query": query,
        "retrieval_method": "local_keyword_policy_ranker",
        "result_count": len(results),
        "selected_record": selected,
        "results": results,
        "explanation": build_search_explanation(query, results),
        "filters": {
            "record_type": record_type,
            "layer": layer,
            "scope": scope,
            "include_revoked": include_revoked,
            "limit": limit,
            "min_score": min_score,
        },
    }


def build_search_explanation(query: str, results: list[dict]) -> str:
    if not results:
        return f"No memory records matched query: {query!r}."

    top = results[0]
    return (
        f"Selected {top['record_id']} because it scored {top['rank_score']} "
        f"using {top['retrieval_method']}; {top['why_selected']}."
    )
