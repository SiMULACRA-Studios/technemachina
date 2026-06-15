// Technemachina Synapse Perception Panel
// v0.4.0 skeleton
//
// Purpose:
// Future home for central signals, bridge candidates, detail drawer,
// Map Only mode, and perception card behavior.

export function describeSynapsePerceptionPanel() {
  return {
    role: "read_only_perception_surface",
    canExplain: true,
    canMutateMemory: false,
    oracleGateRequiredForMutation: true
  };
}
