// Technemachina Synapse Renderer Registry
// v0.4.7 defensive renderer registry
//
// Purpose:
// Select renderer modules through a single registry instead of hardcoding renderer choice.
// Defensively returns a contract even if a renderer is planned or incomplete.

import { SynapseRendererCanvas } from "./SynapseRendererCanvas.js";
import { SynapseRendererThree } from "./SynapseRendererThree.js";

const registry = {
  canvas: SynapseRendererCanvas,
  three: SynapseRendererThree
};

export function listSynapseRenderers() {
  return Object.entries(registry).map(([key, renderer]) => ({
    key,
    name: renderer.name,
    status: renderer.status
  }));
}

export function getSynapseRenderer(key = "canvas") {
  return registry[key] || registry.canvas;
}

export function createFallbackRendererContract(rendererKey = "canvas", renderer = {}, viewModel = {}) {
  return {
    renderer: renderer.name || rendererKey,
    rendererStatus: renderer.status || "unknown",
    activeGalaxy: viewModel.activeGalaxy || "All",
    totals: viewModel.totals || null,
    visible: viewModel.visible || null,
    nodeCount: Array.isArray(viewModel.visibleNodes) ? viewModel.visibleNodes.length : 0,
    edgeCount: Array.isArray(viewModel.visibleEdges) ? viewModel.visibleEdges.length : 0,
    galaxySource: viewModel.galaxySource || "unknown",
    fallback: true,
    message: "Renderer returned no contract, so registry produced a fallback contract."
  };
}

export function createSynapseRendererContract(rendererKey = "canvas", viewModel = {}, state = {}) {
  const renderer = getSynapseRenderer(rendererKey);

  if (typeof renderer.render === "function") {
    const result = renderer.render(viewModel, state);
    return result || createFallbackRendererContract(rendererKey, renderer, viewModel);
  }

  return createFallbackRendererContract(rendererKey, renderer, viewModel);
}
