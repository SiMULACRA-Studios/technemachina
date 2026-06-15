// Technemachina Synapse Controls
// v0.4.0 skeleton
//
// Purpose:
// Future home for zoom, pan, orbit, reset, focus, drag mode, and camera transitions.

export const SynapseControls = {
  defaultMode: "pan",
  museumZoom: 0.32,
  orbitSpeed: 0.000085,

  describe() {
    return {
      defaultMode: this.defaultMode,
      museumZoom: this.museumZoom,
      orbitSpeed: this.orbitSpeed,
      doctrine: "Click selects. Drag navigates. Blank space is calm."
    };
  }
};
