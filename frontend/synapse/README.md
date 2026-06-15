# Synapse Frontend Modules

Status: v0.4.0 skeleton  
Purpose: Separate Synapse data, rendering, controls, labels, selection, companion surface, perception panel, and museum preset.

## Why this exists

The current Synapse Map prototype works, but too much logic is stacked inside `frontend/main.js`.

v0.4.x begins the render-engine split.

The canvas renderer remains the working prototype.

The future Three.js renderer becomes the museum-grade artifact engine.

## Modules

- `SynapseDataAdapter.js` — normalizes `/synapse/map` and `/synapse/analysis`.
- `SynapseRendererCanvas.js` — wrapper/fallback for current canvas renderer.
- `SynapseRendererThree.js` — future Three.js/WebGL museum renderer.
- `SynapseControls.js` — zoom, pan, orbit, reset, focus, drag mode.
- `SynapseLabels.js` — label visibility and clutter discipline.
- `SynapseSelection.js` — selected nodes, bridge paths, focus state.
- `SynapseCompanion.js` — map-local companion surface.
- `SynapsePerceptionPanel.js` — perception cards/detail drawer/map-only logic.
- `SynapseMuseumPreset.js` — default museum artifact visual doctrine.

## Rule

Do not break the current prototype.

Do not keep patching `main.js` forever.

Create module boundaries first, then migrate safely.
