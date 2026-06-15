// Technemachina Synapse Selection
// v0.4.0 skeleton
//
// Purpose:
// Future home for hit testing, selected star, selected bridge, active card,
// focus animation, and connected-node highlighting.

export function createSelectionState() {
  return {
    selectedNodeId: null,
    selectedBridge: null,
    activePerceptionCard: null,
    connectedNodeIds: []
  };
}
