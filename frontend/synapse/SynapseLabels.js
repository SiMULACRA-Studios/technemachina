// Technemachina Synapse Labels
// v0.4.0 skeleton
//
// Purpose:
// Future home for label discipline.
// Labels must not overwhelm the museum artifact view.

export function shouldShowSynapseLabel({ node, zoom = 1, selected = false, connected = false }) {
  if (selected) return true;
  if (connected && zoom >= 1.18) return true;
  if (node?.entity_type === "milestone" && zoom >= 0.72) return true;
  if (zoom >= 1.85) return true;
  return false;
}
