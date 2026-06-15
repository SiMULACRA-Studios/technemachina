/**
 * Technemachina Synapse Canvas Renderer Wrapper
 * v0.4.5 renderer contract skeleton
 *
 * Purpose:
 * Preserve the current canvas prototype as a renderer module/fallback.
 * This module now defines the renderer-facing contract:
 *
 *   render(viewModel, state)
 *
 * Current implementation still lives in frontend/main.js.
 * Future v0.4.x work will gradually migrate canvas draw logic here.
 */

export const SynapseRendererCanvas = {
  name: "canvas-prototype",
  status: "contract-ready",

  init(container, viewModel, state = {}) {
    return {
      container,
      viewModel,
      state,
      renderer: this.name,
      contract: "SynapseViewModel"
    };
  },

  describeViewModel(viewModel = {}) {
    return {
      renderer: this.name,
      rendererStatus: this.status,
      activeGalaxy: viewModel.activeGalaxy || "All",
      totals: viewModel.totals || null,
      visible: viewModel.visible || null,
      nodeCount: Array.isArray(viewModel.visibleNodes) ? viewModel.visibleNodes.length : 0,
      edgeCount: Array.isArray(viewModel.visibleEdges) ? viewModel.visibleEdges.length : 0,
      galaxySource: viewModel.galaxySource || "unknown"
    };
  },

  render(viewModel = {}, state = {}) {
    const description = this.describeViewModel(viewModel);

    if (typeof window !== "undefined") {
      window.__tmSynapseLastCanvasRendererContract = {
        ...description,
        stateKeys: Object.keys(state || {}),
        renderedAt: new Date().toISOString()
      };
    }

    if (typeof window !== "undefined" && typeof window.drawSynapseMap === "function") {
      window.drawSynapseMap();
    }

    return description;
  },

  destroy() {
    if (typeof window !== "undefined") {
      delete window.__tmSynapseLastCanvasRendererContract;
    }
  }
};
