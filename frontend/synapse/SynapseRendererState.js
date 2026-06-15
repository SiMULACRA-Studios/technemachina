// Technemachina Synapse Renderer State Capsule
// v0.4.8 skeleton
//
// Purpose:
// Create a single state capsule describing the current Synapse renderer view.
// This can later be shared with the companion console, map UI, and daemon awareness bridge.

export function createSynapseRendererState({
  activeGalaxy = "All",
  activeRenderer = "canvas",
  availableRenderers = [],
  viewModel = {},
  rendererContract = {},
  source = "synapse-data-adapter-test"
} = {}) {
  return {
    stateVersion: "v0.4.8",
    source,
    generatedAt: new Date().toISOString(),
    activeGalaxy,
    activeRenderer,
    availableRenderers,
    viewModel: {
      version: viewModel.version || "unknown",
      galaxySource: viewModel.galaxySource || "unknown",
      totals: viewModel.totals || null,
      visible: viewModel.visible || null,
      galaxyBreakdown: viewModel.galaxyBreakdown || []
    },
    rendererContract,
    boundary: {
      readOnly: true,
      memoryMutation: false,
      oracleGateRequiredForMutation: true
    }
  };
}

export function publishSynapseRendererState(state) {
  if (typeof window !== "undefined") {
    window.__tmSynapseRendererState = state;
  }
  return state;
}
