from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

import synapse_map


ANALYSIS_VERSION = "v0.3.0a"
POLICY_VERSION = "synapse_perception_read_only_policy_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_nodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = payload.get("nodes")
    if isinstance(nodes, list):
        return nodes

    entities = payload.get("entities")
    if isinstance(entities, list):
        return entities

    return []


def get_edges(payload: dict[str, Any]) -> list[dict[str, Any]]:
    edges = payload.get("edges")
    if isinstance(edges, list):
        return edges

    relations = payload.get("relations")
    if isinstance(relations, list):
        return relations

    return []


def confidence_label(score: float) -> str:
    if score >= 0.75:
        return "strong"
    if score >= 0.45:
        return "moderate"
    return "tentative"


def metadata_richness(node: dict[str, Any]) -> float:
    metadata = node.get("metadata") or {}
    if not isinstance(metadata, dict) or not metadata:
        return 0.0

    meaningful = 0

    for value in metadata.values():
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            meaningful += 1
        elif isinstance(value, (int, float, bool)):
            meaningful += 1
        elif isinstance(value, (list, dict)) and value:
            meaningful += 1

    return min(1.0, meaningful / 6)


def galaxy_for_type(entity_type: str) -> str:
    entity_type = str(entity_type or "unknown")

    if entity_type in {"memory_record", "memory_layer", "review_item", "review_decision"}:
        return "Memory / Governance"

    if entity_type in {"thread", "thread_candidate"}:
        return "Threads / Candidates"

    if entity_type in {"knowledge_source", "knowledge_record", "knowledge_candidate"}:
        return "Knowledge"

    if entity_type in {"project_context", "doctrine"}:
        return "Doctrine / Project Context"

    if entity_type in {"milestone", "milestone_cluster"}:
        return "Milestones"

    return "Unclassified"


def node_summary(node: dict[str, Any], degree: int = 0, weighted_degree: float = 0.0) -> dict[str, Any]:
    node_id = node.get("id", "")
    node_type = node.get("type", "unknown")
    metadata = node.get("metadata") or {}

    confidence_score = min(
        1.0,
        (0.35 if degree > 0 else 0.05)
        + min(0.35, weighted_degree / 3)
        + (0.30 * metadata_richness(node)),
    )

    description = (
        metadata.get("summary")
        or metadata.get("doctrine")
        or metadata.get("objective")
        or metadata.get("preview")
        or metadata.get("reason_for_review")
        or metadata.get("why_candidate")
        or metadata.get("milestone")
        or "No long description stored for this node yet."
    )

    return {
        "id": node_id,
        "label": node.get("label") or node_id,
        "type": node_type,
        "status": node.get("status", "unknown"),
        "galaxy": galaxy_for_type(node_type),
        "degree": degree,
        "weighted_degree": round(weighted_degree, 3),
        "confidence": confidence_label(confidence_score),
        "description": description,
    }


def analyze_synapse_map() -> dict[str, Any]:
    payload = synapse_map.get_map()
    nodes = get_nodes(payload)
    edges = get_edges(payload)

    node_by_id = {
        node.get("id"): node
        for node in nodes
        if node.get("id")
    }

    degree: Counter[str] = Counter()
    weighted_degree: Counter[str] = Counter()
    connected_types: dict[str, set[str]] = defaultdict(set)

    relation_type_counts: Counter[str] = Counter()
    entity_type_counts: Counter[str] = Counter()
    galaxy_counts: Counter[str] = Counter()

    for node in nodes:
        node_type = node.get("type", "unknown")
        entity_type_counts[node_type] += 1
        galaxy_counts[galaxy_for_type(node_type)] += 1

    bridge_edges = []

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        relation_type = edge.get("type", "unknown")
        strength = float(edge.get("strength", 0.5) or 0.5)

        relation_type_counts[relation_type] += 1

        if source:
            degree[source] += 1
            weighted_degree[source] += strength

        if target:
            degree[target] += 1
            weighted_degree[target] += strength

        source_node = node_by_id.get(source, {})
        target_node = node_by_id.get(target, {})

        source_type = source_node.get("type", "unknown")
        target_type = target_node.get("type", "unknown")

        if source:
            connected_types[source].add(target_type)
        if target:
            connected_types[target].add(source_type)

        source_galaxy = galaxy_for_type(source_type)
        target_galaxy = galaxy_for_type(target_type)

        if source_galaxy != target_galaxy:
            bridge_edges.append({
                "id": edge.get("id"),
                "source": source,
                "target": target,
                "source_label": source_node.get("label", source),
                "target_label": target_node.get("label", target),
                "type": relation_type,
                "strength": strength,
                "source_galaxy": source_galaxy,
                "target_galaxy": target_galaxy,
                "confidence": confidence_label(min(1.0, 0.35 + strength * 0.55)),
                "explanation": (
                    f"This edge links {source_galaxy} to {target_galaxy} through "
                    f"the relation type '{relation_type}'."
                ),
            })

    central_nodes = sorted(
        [
            node_summary(
                node,
                degree=degree.get(node.get("id"), 0),
                weighted_degree=weighted_degree.get(node.get("id"), 0.0),
            )
            for node in nodes
        ],
        key=lambda item: (item["degree"], item["weighted_degree"]),
        reverse=True,
    )[:10]

    bridge_nodes = []

    for node in nodes:
        node_id = node.get("id")
        type_span = connected_types.get(node_id, set())

        if len(type_span) >= 2:
            summary = node_summary(
                node,
                degree=degree.get(node_id, 0),
                weighted_degree=weighted_degree.get(node_id, 0.0),
            )
            summary["connected_type_span"] = sorted(type_span)
            summary["bridge_reason"] = "This node touches multiple entity types and may act as a cross-system bridge."
            bridge_nodes.append(summary)

    bridge_nodes = sorted(
        bridge_nodes,
        key=lambda item: (len(item.get("connected_type_span", [])), item["degree"], item["weighted_degree"]),
        reverse=True,
    )[:10]

    isolated_nodes = [
        node_summary(node, degree=0, weighted_degree=0.0)
        for node in nodes
        if degree.get(node.get("id"), 0) == 0
    ][:20]

    galaxy_summaries = []

    for galaxy, count in galaxy_counts.most_common():
        galaxy_nodes = [node for node in nodes if galaxy_for_type(node.get("type")) == galaxy]

        galaxy_edges = [
            edge for edge in edges
            if galaxy_for_type(node_by_id.get(edge.get("source"), {}).get("type")) == galaxy
            or galaxy_for_type(node_by_id.get(edge.get("target"), {}).get("type")) == galaxy
        ]

        cross_galaxy_edges = []

        for edge in galaxy_edges:
            source_galaxy = galaxy_for_type(node_by_id.get(edge.get("source"), {}).get("type"))
            target_galaxy = galaxy_for_type(node_by_id.get(edge.get("target"), {}).get("type"))

            if source_galaxy != target_galaxy:
                cross_galaxy_edges.append(edge)

        edge_touch_count = len(galaxy_edges)
        cross_galaxy_edge_count = len(cross_galaxy_edges)
        edge_coverage = edge_touch_count / max(1, count)
        cross_galaxy_support = cross_galaxy_edge_count / max(1, edge_touch_count)
        graph_share = count / max(1, len(nodes))

        # Confidence rewards explicit relational evidence, not raw node count alone.
        # A large galaxy with weak connectivity should not automatically become "strong."
        galaxy_confidence_score = min(
            1.0,
            0.10
            + min(0.20, graph_share)
            + min(0.40, edge_coverage / 2)
            + min(0.20, cross_galaxy_support)
            + (0.10 if count >= 3 else 0.0),
        )

        relation_word = "relation" if edge_touch_count == 1 else "relations"

        galaxy_summaries.append({
            "galaxy": galaxy,
            "node_count": count,
            "edge_touch_count": edge_touch_count,
            "edge_coverage": round(edge_coverage, 3),
            "cross_galaxy_edge_count": cross_galaxy_edge_count,
            "cross_galaxy_support": round(cross_galaxy_support, 3),
            "confidence": confidence_label(galaxy_confidence_score),
            "summary": (
                f"{galaxy} contains {count} visible nodes and touches "
                f"{edge_touch_count} visible {relation_word} in the current Synapse Map."
            ),
        })

    limitations = []

    if not edges:
        limitations.append("No relations were found, so bridge and centrality analysis is limited.")

    if isolated_nodes:
        limitations.append("Some nodes are isolated, which may indicate incomplete metadata or unconnected records.")

    if len(nodes) < 5:
        limitations.append("The map is sparse, so analytical confidence is limited.")

    if galaxy_counts:
        dominant_galaxy, dominant_count = galaxy_counts.most_common(1)[0]
        dominance_ratio = dominant_count / max(1, len(nodes))

        if dominance_ratio >= 0.70:
            limitations.append(
                f"The map is currently dominated by {dominant_galaxy} "
                f"({dominance_ratio:.0%} of visible nodes), so cross-galaxy analysis may be skewed."
            )

    for galaxy, count in galaxy_counts.most_common():
        galaxy_edges = [
            edge for edge in edges
            if galaxy_for_type(node_by_id.get(edge.get("source"), {}).get("type")) == galaxy
            or galaxy_for_type(node_by_id.get(edge.get("target"), {}).get("type")) == galaxy
        ]

        edge_coverage = len(galaxy_edges) / max(1, count)

        if count >= 3 and edge_coverage < 0.5:
            limitations.append(
                f"{galaxy} has {count} visible nodes but low edge coverage "
                f"({edge_coverage:.2f}), so interpretation should remain cautious."
            )

    return {
        "meta": {
            "analysis_version": ANALYSIS_VERSION,
            "policy_version": POLICY_VERSION,
            "generated_at": utc_now(),
            "source_synapse_version": payload.get("meta", {}).get("synapse_version") or payload.get("synapse_version"),
            "read_only": True,
            "mutation_allowed": False,
        },
        "doctrine": {
            "mode": "read_only_perception",
            "observation": True,
            "interpretation": True,
            "recommendation": True,
            "mutation": False,
            "statement": "Synapse Perception improves understanding, not control.",
        },
        "totals": {
            "nodes": len(nodes),
            "edges": len(edges),
            "entity_types": dict(entity_type_counts.most_common()),
            "relation_types": dict(relation_type_counts.most_common()),
            "galaxies": dict(galaxy_counts.most_common()),
        },
        "overview": {
            "summary": (
                f"The Synapse Map currently exposes {len(nodes)} nodes and {len(edges)} relations. "
                f"The strongest visible galaxies are: "
                f"{', '.join([name for name, _ in galaxy_counts.most_common(4)]) or 'none'}."
            ),
            "confidence": confidence_label(min(1.0, 0.25 + len(edges) / 25 + len(nodes) / 50)),
        },
        "galaxy_summaries": galaxy_summaries,
        "central_nodes": central_nodes,
        "bridge_nodes": bridge_nodes,
        "bridge_edges": sorted(
            bridge_edges,
            key=lambda item: item.get("strength", 0),
            reverse=True,
        )[:10],
        "isolated_nodes": isolated_nodes,
        "limitations": limitations,
    }


def get_analysis() -> dict[str, Any]:
    return analyze_synapse_map()
