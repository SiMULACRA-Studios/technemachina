// Technemachina Synapse Data Adapter
// v0.4.2 enriched adapter
//
// Purpose:
// Normalize Synapse map/analysis data before it reaches any renderer.
// This keeps truth/data separate from visual presentation.
//
// v0.4.2 adds derived galaxies when the backend map does not provide
// a top-level galaxies object.

export function inferSynapseNodeKind(node = {}) {
  return (
    node.entity_type ||
    node.type ||
    node?.skin?.node_class ||
    node?.metadata?.record_type ||
    "unknown"
  );
}

export function inferSynapseGalaxyName(node = {}) {
  const kind = String(inferSynapseNodeKind(node)).toLowerCase();
  const label = String(node.label || "").toLowerCase();

  if (kind.includes("memory") || kind.includes("layer")) return "Memory / Governance";
  if (kind.includes("milestone")) return "Milestones";
  if (kind.includes("project") || kind.includes("doctrine")) return "Doctrine / Project Context";
  if (kind.includes("knowledge") || kind.includes("source") || kind.includes("record")) return "Knowledge";
  if (kind.includes("thread") || kind.includes("candidate")) return "Threads / Candidates";

  if (label.includes("memory")) return "Memory / Governance";
  if (label.includes("milestone")) return "Milestones";
  if (label.includes("doctrine")) return "Doctrine / Project Context";
  if (label.includes("knowledge")) return "Knowledge";
  if (label.includes("thread") || label.includes("candidate")) return "Threads / Candidates";

  return "Unclassified";
}

export function deriveSynapseGalaxies(nodes = []) {
  const galaxies = {};

  for (const node of nodes) {
    const galaxyName = inferSynapseGalaxyName(node);

    if (!galaxies[galaxyName]) {
      galaxies[galaxyName] = {
        name: galaxyName,
        nodeCount: 0,
        nodeIds: [],
        types: {}
      };
    }

    const kind = inferSynapseNodeKind(node);
    galaxies[galaxyName].nodeCount += 1;
    galaxies[galaxyName].nodeIds.push(node.id);
    galaxies[galaxyName].types[kind] = (galaxies[galaxyName].types[kind] || 0) + 1;
  }

  return galaxies;
}

export function normalizeSynapseMap(rawMap = {}) {
  const nodes = Array.isArray(rawMap.nodes) ? rawMap.nodes : [];
  const edges = Array.isArray(rawMap.edges) ? rawMap.edges : [];

  const providedGalaxies =
    rawMap.galaxies && typeof rawMap.galaxies === "object"
      ? rawMap.galaxies
      : null;

  const galaxies = providedGalaxies || deriveSynapseGalaxies(nodes);

  return {
    version: rawMap.version || rawMap.synapse_version || rawMap.map_version || "derived-v0.4.2",
    generatedAt: rawMap.generated_at || rawMap.generatedAt || rawMap.created_at || null,
    nodes,
    edges,
    galaxies,
    galaxySource: providedGalaxies ? "backend" : "derived",
    raw: rawMap
  };
}

export function summarizeSynapseData(normalized = {}) {
  const nodes = normalized.nodes || [];
  const edges = normalized.edges || [];
  const galaxies = normalized.galaxies || {};

  return {
    nodeCount: nodes.length,
    edgeCount: edges.length,
    galaxyCount: Object.keys(galaxies).length,
    galaxySource: normalized.galaxySource || "unknown",
    galaxies: Object.values(galaxies).map((galaxy) => ({
      name: galaxy.name,
      nodeCount: galaxy.nodeCount || 0,
      typeCount: Object.keys(galaxy.types || {}).length
    }))
  };
}


export function createSynapseViewModel(normalized = {}, options = {}) {
  const activeGalaxy = options.activeGalaxy || "All";

  const allNodes = normalized.nodes || [];
  const allEdges = normalized.edges || [];

  const visibleNodes =
    activeGalaxy === "All"
      ? allNodes
      : allNodes.filter((node) => inferSynapseGalaxyName(node) === activeGalaxy);

  const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));

  const visibleEdges =
    activeGalaxy === "All"
      ? allEdges
      : allEdges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target));

  const summary = summarizeSynapseData(normalized);

  return {
    activeGalaxy,
    version: normalized.version || "unknown",
    generatedAt: normalized.generatedAt || null,
    galaxySource: normalized.galaxySource || "unknown",
    totals: {
      nodes: allNodes.length,
      edges: allEdges.length,
      galaxies: summary.galaxyCount
    },
    visible: {
      nodes: visibleNodes.length,
      edges: visibleEdges.length
    },
    visibleNodes,
    visibleEdges,
    galaxyBreakdown: summary.galaxies,
    normalized
  };
}

