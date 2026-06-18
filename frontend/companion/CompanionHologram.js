import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.179.1/build/three.module.js";

const DEFAULT_STATE = Object.freeze({
  status: "idle",
  selectedNode: null,
  mode: "hero",
});

function createRadialTexture({
  size = 256,
  inner = "rgba(255,255,255,1)",
  middle = "rgba(220,238,255,0.28)",
  outer = "rgba(170,210,255,0)",
} = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;

  const context = canvas.getContext("2d");
  const center = size / 2;

  const gradient = context.createRadialGradient(
    center,
    center,
    0,
    center,
    center,
    center,
  );

  gradient.addColorStop(0, inner);
  gradient.addColorStop(0.22, middle);
  gradient.addColorStop(1, outer);

  context.fillStyle = gradient;
  context.fillRect(0, 0, size, size);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;

  return texture;
}

function createBeamTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 512;

  const context = canvas.getContext("2d");

  const horizontal = context.createLinearGradient(
    0,
    0,
    canvas.width,
    0,
  );

  horizontal.addColorStop(0, "rgba(190,220,255,0)");
  horizontal.addColorStop(0.4, "rgba(225,241,255,0.12)");
  horizontal.addColorStop(0.49, "rgba(255,255,255,0.7)");
  horizontal.addColorStop(0.51, "rgba(255,255,255,0.7)");
  horizontal.addColorStop(0.6, "rgba(225,241,255,0.12)");
  horizontal.addColorStop(1, "rgba(190,220,255,0)");

  context.fillStyle = horizontal;
  context.fillRect(0, 0, canvas.width, canvas.height);

  context.globalCompositeOperation = "destination-in";

  const vertical = context.createLinearGradient(
    0,
    0,
    0,
    canvas.height,
  );

  vertical.addColorStop(0, "rgba(255,255,255,0)");
  vertical.addColorStop(0.18, "rgba(255,255,255,0.45)");
  vertical.addColorStop(0.76, "rgba(255,255,255,0.7)");
  vertical.addColorStop(1, "rgba(255,255,255,0)");

  context.fillStyle = vertical;
  context.fillRect(0, 0, canvas.width, canvas.height);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;

  return texture;
}

function cubicBezierPoint(p0, p1, p2, p3, t) {
  const inverse = 1 - t;

  return new THREE.Vector3(
    inverse ** 3 * p0.x
      + 3 * inverse ** 2 * t * p1.x
      + 3 * inverse * t ** 2 * p2.x
      + t ** 3 * p3.x,
    inverse ** 3 * p0.y
      + 3 * inverse ** 2 * t * p1.y
      + 3 * inverse * t ** 2 * p2.y
      + t ** 3 * p3.y,
    inverse ** 3 * p0.z
      + 3 * inverse ** 2 * t * p1.z
      + 3 * inverse * t ** 2 * p2.z
      + t ** 3 * p3.z,
  );
}

function createWatcherLidPoints({ upper, z = 0 }) {
  const left = upper
    ? new THREE.Vector3(-1.88, -0.006, z)
    : new THREE.Vector3(-1.84, 0.004, z);
  const right = upper
    ? new THREE.Vector3(1.84, 0.004, z)
    : new THREE.Vector3(1.88, -0.006, z);

  const control1 = upper
    ? new THREE.Vector3(-1.18, 0.887910, z)
    : new THREE.Vector3(-0.98, -0.616604, z);

  const control2 = upper
    ? new THREE.Vector3(0.98, 0.813917, z)
    : new THREE.Vector3(1.17, -0.554944, z);

  const points = [];
  const segments = 180;

  for (let index = 0; index <= segments; index += 1) {
    points.push(
      cubicBezierPoint(
        left,
        control1,
        control2,
        right,
        index / segments,
      ),
    );
  }

  return points;
}

function createRibbonGeometry({
  points,
  width,
  endpointWidth = 0.08,
}) {
  const positions = [];
  const indices = [];

  for (let index = 0; index < points.length; index += 1) {
    const previous = points[Math.max(0, index - 1)];
    const next = points[Math.min(points.length - 1, index + 1)];

    const tangent = new THREE.Vector3()
      .subVectors(next, previous)
      .normalize();

    const normal = new THREE.Vector3(
      -tangent.y,
      tangent.x,
      0,
    ).normalize();

    const progress = index / (points.length - 1);
    const centerStrength = Math.sin(progress * Math.PI);
    const localWidth = THREE.MathUtils.lerp(
      endpointWidth,
      width,
      centerStrength ** 0.65,
    );

    const offset = normal.multiplyScalar(localWidth / 2);

    const left = points[index].clone().add(offset);
    const right = points[index].clone().sub(offset);

    positions.push(left.x, left.y, left.z);
    positions.push(right.x, right.y, right.z);

    if (index < points.length - 1) {
      const base = index * 2;

      indices.push(
        base,
        base + 1,
        base + 2,
        base + 1,
        base + 3,
        base + 2,
      );
    }
  }

  const geometry = new THREE.BufferGeometry();

  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(positions, 3),
  );

  geometry.setIndex(indices);

  return geometry;
}

function createRibbon({
  points,
  width,
  endpointWidth,
  opacity,
  color,
  blending,
  zOffset = 0,
}) {
  const shifted = points.map((point) =>
    point.clone().add(
      new THREE.Vector3(0, 0, zOffset),
    ),
  );

  const geometry = createRibbonGeometry({
    points: shifted,
    width,
    endpointWidth,
  });

  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity,
    blending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });

  return new THREE.Mesh(geometry, material);
}

function createTerminalCap({
  x,
  y,
  z,
  scaleX,
  scaleY,
  opacity,
}) {
  const cap = new THREE.Mesh(
    new THREE.CircleGeometry(1, 48),
    new THREE.MeshBasicMaterial({
      color: 0xd8eaff,
      transparent: true,
      opacity,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );

  cap.position.set(x, y, z);
  cap.scale.set(scaleX, scaleY, 1);

  return cap;
}

function createLine(points, material, closed = false, renderOrder = 0) {
  const finalPoints = closed
    ? [...points, points[0].clone()]
    : points;

  const geometry = new THREE.BufferGeometry().setFromPoints(
    finalPoints,
  );

  const line = new THREE.Line(geometry, material);

  line.renderOrder = renderOrder;

  return line;
}

function createEllipse({
  radiusX,
  radiusY,
  z = 0,
  material,
  segments = 180,
  renderOrder = 0,
}) {
  const points = [];

  for (let index = 0; index < segments; index += 1) {
    const angle = (index / segments) * Math.PI * 2;

    points.push(
      new THREE.Vector3(
        Math.cos(angle) * radiusX,
        Math.sin(angle) * radiusY,
        z,
      ),
    );
  }

  return createLine(points, material, true, renderOrder);
}

function createArc({
  radiusX,
  radiusY,
  start,
  end,
  z = 0,
  offsetX = 0,
  offsetY = 0,
  material,
  segments = 96,
  renderOrder = 0,
}) {
  const points = [];

  for (let index = 0; index <= segments; index += 1) {
    const angle = THREE.MathUtils.degToRad(
      THREE.MathUtils.lerp(start, end, index / segments),
    );

    points.push(
      new THREE.Vector3(
        Math.cos(angle) * radiusX + offsetX,
        Math.sin(angle) * radiusY + offsetY,
        z,
      ),
    );
  }

  return createLine(points, material, false, renderOrder);
}

function createGlobe() {
  const group = new THREE.Group();
  const radius = 2.14;

  const majorMaterial = new THREE.LineBasicMaterial({
    color: 0xc3dcff,
    transparent: true,
    opacity: 0.068,
    depthWrite: false,
  });

  const minorMaterial = new THREE.LineBasicMaterial({
    color: 0x87afe4,
    transparent: true,
    opacity: 0.006,
    depthWrite: false,
  });

  const depthMaterial = new THREE.LineBasicMaterial({
    color: 0xe2f0ff,
    transparent: true,
    opacity: 0.038,
    depthWrite: false,
  });

  function latitude(degrees, material) {
    const angle = THREE.MathUtils.degToRad(degrees);
    const y = Math.sin(angle) * radius;
    const ringRadius = Math.cos(angle) * radius;
    const points = [];

    for (let index = 0; index < 180; index += 1) {
      const theta = (index / 180) * Math.PI * 2;

      points.push(
        new THREE.Vector3(
          Math.cos(theta) * ringRadius,
          y,
          Math.sin(theta) * ringRadius,
        ),
      );
    }

    return createLine(points, material, true);
  }

  function longitude(degrees, material) {
    const rotation = THREE.MathUtils.degToRad(degrees);
    const points = [];

    for (let index = 0; index < 180; index += 1) {
      const theta = (index / 180) * Math.PI * 2;
      const radial = Math.sin(theta) * radius;

      points.push(
        new THREE.Vector3(
          radial * Math.cos(rotation),
          Math.cos(theta) * radius,
          radial * Math.sin(rotation),
        ),
      );
    }

    return createLine(points, material, true);
  }

  [-50, -25, 0, 25, 50].forEach((degrees) => {
    group.add(
      latitude(
        degrees,
        Math.abs(degrees) <= 25
          ? majorMaterial
          : depthMaterial,
      ),
    );
  });

  [0, 36, 72, 108, 144].forEach((degrees) => {
    group.add(
      longitude(
        degrees,
        degrees === 0 || degrees === 108
          ? majorMaterial
          : minorMaterial,
      ),
    );
  });

  group.rotation.x = -0.07;
  group.rotation.y = 0.12;

  return group;
}

function createNexus() {
  const group = new THREE.Group();

  const wideTexture = createRadialTexture({
    inner: "rgba(255,255,255,0.48)",
    middle: "rgba(210,234,255,0.2)",
    outer: "rgba(160,205,255,0)",
  });

  const middleTexture = createRadialTexture({
    inner: "rgba(255,255,255,0.34)",
    middle: "rgba(218,238,255,0.18)",
    outer: "rgba(160,205,255,0)",
  });

  const tightTexture = createRadialTexture({
    inner: "rgba(255,255,255,0.96)",
    middle: "rgba(235,246,255,0.32)",
    outer: "rgba(180,220,255,0)",
  });

  const wideHalo = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: wideTexture,
      transparent: true,
      opacity: 0.78,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );

  wideHalo.scale.set(1.04, 0.72, 1);
  wideHalo.position.z = -0.015;
  wideHalo.renderOrder = 46;
  group.add(wideHalo);

  const middleHalo = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: middleTexture,
      transparent: true,
      opacity: 0.58,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );

  middleHalo.scale.set(0.68, 0.48, 1);
  middleHalo.position.z = 0.025;
  middleHalo.renderOrder = 50;
  group.add(middleHalo);

  const tightHalo = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: tightTexture,
      transparent: true,
      opacity: 0.86,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );

  tightHalo.scale.set(0.14, 0.19, 1);
  tightHalo.position.z = 0.055;
  tightHalo.renderOrder = 54;
  group.add(tightHalo);

  const core = new THREE.Mesh(
    new THREE.CircleGeometry(0.0082, 32),
    new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 1,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );

  core.position.z = 0.085;
  core.renderOrder = 58;
  group.add(core);

  return group;
}

function createBeamSegment({
  y,
  height,
  width,
  opacity,
  z = 0,
  renderOrder = 0,
}) {
  const material = new THREE.MeshBasicMaterial({
    map: createBeamTexture(),
    transparent: true,
    opacity,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });

  const beam = new THREE.Mesh(
    new THREE.PlaneGeometry(width, height),
    material,
  );

  beam.position.set(0, y, z);
  beam.renderOrder = renderOrder;

  return beam;
}

function createVerticalAxis() {
  const group = new THREE.Group();

  group.add(
    createBeamSegment({
      y: 1.66,
      height: 2.08,
      width: 1.34,
      opacity: 0.23,
      z: -0.08,
      renderOrder: 12,
    }),
  );

  group.add(
    createBeamSegment({
      y: -1.72,
      height: 2.18,
      width: 1.46,
      opacity: 0.25,
      z: -0.08,
      renderOrder: 12,
    }),
  );

  group.add(
    createBeamSegment({
      y: 1.7,
      height: 1.78,
      width: 0.68,
      opacity: 0.25,
      z: 0,
      renderOrder: 18,
    }),
  );

  group.add(
    createBeamSegment({
      y: -1.76,
      height: 1.92,
      width: 0.82,
      opacity: 0.28,
      z: 0,
      renderOrder: 18,
    }),
  );

  group.add(
    createBeamSegment({
      y: -2.08,
      height: 1.02,
      width: 1.62,
      opacity: 0.22,
      z: -0.03,
      renderOrder: 16,
    }),
  );

  group.add(
    createBeamSegment({
      y: 1.8,
      height: 1.22,
      width: 0.022,
      opacity: 0.1,
      z: 0.06,
      renderOrder: 22,
    }),
  );

  group.add(
    createBeamSegment({
      y: -1.76,
      height: 1.34,
      width: 0.024,
      opacity: 0.11,
      z: 0.06,
      renderOrder: 22,
    }),
  );

  return group;
}

function createProjectionBase() {
  const group = new THREE.Group();

  const outerTexture = createRadialTexture({
    inner: "rgba(225,242,255,0.2)",
    middle: "rgba(175,215,255,0.08)",
    outer: "rgba(120,175,255,0)",
  });

  const coreTexture = createRadialTexture({
    inner: "rgba(255,255,255,0.62)",
    middle: "rgba(205,232,255,0.18)",
    outer: "rgba(140,195,255,0)",
  });

  const midTexture = createRadialTexture({
    inner: "rgba(240,248,255,0.32)",
    middle: "rgba(190,224,255,0.12)",
    outer: "rgba(130,190,255,0)",
  });

  const outer = new THREE.Mesh(
    new THREE.PlaneGeometry(4.18, 1.06),
    new THREE.MeshBasicMaterial({
      map: outerTexture,
      transparent: true,
      opacity: 0.62,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );

  const core = new THREE.Mesh(
    new THREE.PlaneGeometry(1.62, 0.38),
    new THREE.MeshBasicMaterial({
      map: coreTexture,
      transparent: true,
      opacity: 0.78,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );

  const mid = new THREE.Mesh(
    new THREE.PlaneGeometry(2.72, 0.54),
    new THREE.MeshBasicMaterial({
      map: midTexture,
      transparent: true,
      opacity: 0.68,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );

  const reflectionTexture = createRadialTexture({
    inner: "rgba(255,255,255,0.68)",
    middle: "rgba(210,234,255,0.22)",
    outer: "rgba(140,195,255,0)",
  });

  const reflection = new THREE.Mesh(
    new THREE.PlaneGeometry(0.88, 0.2),
    new THREE.MeshBasicMaterial({
      map: reflectionTexture,
      transparent: true,
      opacity: 0.84,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );

  outer.position.z = -0.02;
  mid.position.z = 0;
  core.position.z = 0.02;
  reflection.position.z = 0.07;

  outer.renderOrder = 8;
  mid.renderOrder = 10;
  core.renderOrder = 12;
  reflection.renderOrder = 18;

  group.add(outer);
  group.add(mid);
  group.add(core);
  group.add(reflection);

  group.position.set(0, -2.1, 0);

  return group;
}

function createWatcherEye() {
  const group = new THREE.Group();

  const upperPoints = createWatcherLidPoints({
    upper: true,
    z: 0.15,
  });

  const lowerPoints = createWatcherLidPoints({
    upper: false,
    z: 0.15,
  });

  group.add(
    createRibbon({
      points: upperPoints,
      width: 0.092,
      endpointWidth: 0.042,
      opacity: 0.1,
      color: 0xd8eaff,
      blending: THREE.AdditiveBlending,
      zOffset: -0.05,
    }),
  );

  group.add(
    createRibbon({
      points: lowerPoints,
      width: 0.074,
      endpointWidth: 0.038,
      opacity: 0.07,
      color: 0xd8eaff,
      blending: THREE.AdditiveBlending,
      zOffset: -0.05,
    }),
  );

  group.add(
    createRibbon({
      points: upperPoints,
      width: 0.04,
      endpointWidth: 0.024,
      opacity: 0.9,
      color: 0xffffff,
      blending: THREE.AdditiveBlending,
    }),
  );

  group.add(
    createRibbon({
      points: lowerPoints,
      width: 0.024,
      endpointWidth: 0.02,
      opacity: 0.72,
      color: 0xffffff,
      blending: THREE.AdditiveBlending,
    }),
  );

  group.add(
    createRibbon({
      points: upperPoints.slice(54, 128),
      width: 0.046,
      endpointWidth: 0.006,
      opacity: 0.36,
      color: 0xffffff,
      blending: THREE.AdditiveBlending,
      zOffset: 0.018,
    }),
  );

  group.add(
    createRibbon({
      points: lowerPoints.slice(62, 122),
      width: 0.03,
      endpointWidth: 0.004,
      opacity: 0.24,
      color: 0xe7f4ff,
      blending: THREE.AdditiveBlending,
      zOffset: 0.018,
    }),
  );

  group.add(
    createTerminalCap({
      x: -1.7,
      y: 0,
      z: 0.151,
      scaleX: 0.14,
      scaleY: 0.022,
      opacity: 0.16,
    }),
  );

  group.add(
    createTerminalCap({
      x: 1.7,
      y: 0.001,
      z: 0.151,
      scaleX: 0.14,
      scaleY: 0.022,
      opacity: 0.16,
    }),
  );

  const irisOuter = new THREE.LineBasicMaterial({
    color: 0xb7d3f5,
    transparent: true,
    opacity: 0.14,
    depthWrite: false,
  });

  const irisContourPrimary = new THREE.LineBasicMaterial({
    color: 0xe9f4ff,
    transparent: true,
    opacity: 0.58,
    depthWrite: false,
  });

  const irisContourSecondary = new THREE.LineBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0.36,
    depthWrite: false,
  });

  const chamberRear = new THREE.LineBasicMaterial({
    color: 0x9fc5f5,
    transparent: true,
    opacity: 0.2,
    depthWrite: false,
  });

  const chamberNear = new THREE.LineBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0.58,
    depthWrite: false,
  });

  const chamberConnector = new THREE.LineBasicMaterial({
    color: 0xd7ecff,
    transparent: true,
    opacity: 0.26,
    depthWrite: false,
  });

  const chamberSegment = new THREE.LineBasicMaterial({
    color: 0xf7fbff,
    transparent: true,
    opacity: 0.4,
    depthWrite: false,
  });

  const chamberShadow = new THREE.Mesh(
    new THREE.CircleGeometry(0.37, 80),
    new THREE.MeshBasicMaterial({
      color: 0x000206,
      transparent: true,
      opacity: 0.28,
      depthWrite: true,
    }),
  );

  chamberShadow.position.z = 0.025;
  chamberShadow.renderOrder = 24;
  chamberShadow.scale.set(1.02, 0.78, 1);
  group.add(chamberShadow);

  group.add(
    createEllipse({
      radiusX: 0.52,
      radiusY: 0.29,
      z: 0.07,
      material: irisOuter,
      renderOrder: 28,
    }),
  );

  group.add(
    createArc({
      radiusX: 0.42,
      radiusY: 0.232,
      start: 22,
      end: 144,
      z: 0.135,
      offsetX: -0.014,
      offsetY: 0.012,
      material: irisContourPrimary,
      segments: 72,
      renderOrder: 40,
    }),
  );

  group.add(
    createArc({
      radiusX: 0.49,
      radiusY: 0.262,
      start: 210,
      end: 310,
      z: 0.128,
      offsetX: 0.022,
      offsetY: -0.01,
      material: irisContourSecondary,
      segments: 64,
      renderOrder: 38,
    }),
  );

  group.add(
    createArc({
      radiusX: 0.56,
      radiusY: 0.3,
      start: -170,
      end: -34,
      z: 0.045,
      offsetX: -0.024,
      offsetY: -0.02,
      material: chamberRear,
      segments: 72,
      renderOrder: 26,
    }),
  );

  group.add(
    createArc({
      radiusX: 0.5,
      radiusY: 0.255,
      start: -24,
      end: 96,
      z: 0.06,
      offsetX: 0.032,
      offsetY: 0.018,
      material: chamberRear,
      segments: 56,
      renderOrder: 27,
    }),
  );

  group.add(
    createArc({
      radiusX: 0.245,
      radiusY: 0.138,
      start: 202,
      end: 342,
      z: 0.172,
      offsetX: 0.008,
      offsetY: -0.006,
      material: chamberNear,
      segments: 72,
      renderOrder: 48,
    }),
  );

  group.add(
    createArc({
      radiusX: 0.29,
      radiusY: 0.155,
      start: 14,
      end: 120,
      z: 0.164,
      offsetX: -0.01,
      offsetY: 0.008,
      material: chamberNear,
      segments: 56,
      renderOrder: 46,
    }),
  );

  group.add(
    createArc({
      radiusX: 0.86,
      radiusY: 0.39,
      start: 42,
      end: 118,
      z: 0.108,
      offsetX: -0.02,
      offsetY: 0.015,
      material: chamberConnector,
      segments: 56,
      renderOrder: 34,
    }),
  );

  group.add(
    createArc({
      radiusX: 0.88,
      radiusY: 0.37,
      start: 222,
      end: 302,
      z: 0.104,
      offsetX: 0.024,
      offsetY: -0.016,
      material: chamberConnector,
      segments: 56,
      renderOrder: 34,
    }),
  );

  group.add(
    createLine(
      [
        new THREE.Vector3(-0.15, 0.055, 0.152),
        new THREE.Vector3(-0.055, 0.022, 0.152),
      ],
      chamberSegment,
      false,
      50,
    ),
  );

  group.add(
    createLine(
      [
        new THREE.Vector3(0.06, -0.024, 0.152),
        new THREE.Vector3(0.17, -0.066, 0.152),
      ],
      chamberSegment,
      false,
      50,
    ),
  );

  group.add(
    createLine(
      [
        new THREE.Vector3(-0.19, -0.036, 0.064),
        new THREE.Vector3(-0.112, -0.078, 0.064),
      ],
      chamberRear,
      false,
      28,
    ),
  );

  const pupil = new THREE.Mesh(
    new THREE.CircleGeometry(0.25, 88),
    new THREE.MeshBasicMaterial({
      color: 0x000206,
      transparent: true,
      opacity: 0.94,
      depthWrite: true,
    }),
  );

  pupil.position.z = 0.076;
  pupil.renderOrder = 30;
  pupil.scale.set(0.76, 1, 1);
  group.add(pupil);

  const nexus = createNexus();
  nexus.position.z = 0.23;
  nexus.renderOrder = 52;
  group.add(nexus);

  return group;
}

function disposeObject(object) {
  object.traverse((child) => {
    child.geometry?.dispose();

    if (child.material) {
      const materials = Array.isArray(child.material)
        ? child.material
        : [child.material];

      materials.forEach((material) => {
        material.map?.dispose();
        material.dispose();
      });
    }
  });
}

export class CompanionHologram {
  constructor() {
    this.container = null;
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.root = null;
    this.globe = null;
    this.eye = null;
    this.axis = null;
    this.base = null;
    this.resizeObserver = null;
    this.intersectionObserver = null;
    this.visible = true;
    this.mounted = false;
    this.state = { ...DEFAULT_STATE };
  }

  mount(container) {
    if (!(container instanceof HTMLElement)) {
      throw new TypeError(
        "CompanionHologram.mount requires an HTMLElement.",
      );
    }

    if (this.mounted) {
      throw new Error("CompanionHologram is already mounted.");
    }

    this.container = container;
    this.scene = new THREE.Scene();

    this.camera = new THREE.PerspectiveCamera(
      34,
      1,
      0.1,
      100,
    );

    this.camera.position.set(0, 0, 7.75);

    this.renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: "low-power",
      premultipliedAlpha: true,
    });

    this.renderer.setPixelRatio(
      Math.min(window.devicePixelRatio || 1, 2),
    );

    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.domElement.className =
      "companion-hologram-canvas";

    this.container.appendChild(this.renderer.domElement);

    this.root = new THREE.Group();
    this.scene.add(this.root);

    this.globe = createGlobe();
    this.globe.position.set(0, 0.08, -0.74);
    this.root.add(this.globe);

    this.axis = createVerticalAxis();
    this.axis.position.set(0, 0, -0.2);
    this.root.add(this.axis);

    this.eye = createWatcherEye();
    this.eye.position.set(0, 0.18, 1.18);
    this.eye.scale.set(1.02, 0.88, 0.96);
    this.root.add(this.eye);

    this.base = createProjectionBase();
    this.base.position.z = -0.05;
    this.root.add(this.base);

    this.root.rotation.x = -0.015;
    this.root.rotation.y = 0.025;
    this.root.scale.setScalar(
      this.state.mode === "mini" ? 0.8 : 1.1,
    );

    this.resizeObserver = new ResizeObserver(() => {
      this.resize();
    });

    this.resizeObserver.observe(this.container);

    this.intersectionObserver = new IntersectionObserver(
      ([entry]) => {
        this.visible = Boolean(entry?.isIntersecting);

        if (this.visible) {
          this.render();
        }
      },
      { threshold: 0.01 },
    );

    this.intersectionObserver.observe(this.container);

    this.mounted = true;
    this.resize();
    this.render();

    return this;
  }

  setState(nextState = {}) {
    this.state = {
      ...this.state,
      ...nextState,
    };

    this.render();
    return this;
  }

  setSelectedNode(selectedNode = null) {
    this.state.selectedNode = selectedNode;
    this.render();
    return this;
  }

  setMode(mode = "hero") {
    if (!["hero", "mini"].includes(mode)) {
      throw new RangeError(
        'CompanionHologram mode must be "hero" or "mini".',
      );
    }

    this.state.mode = mode;

    if (this.root) {
      this.root.scale.setScalar(
        mode === "mini" ? 0.8 : 1.1,
      );
    }

    this.render();
    return this;
  }

  resize() {
    if (!this.mounted || !this.container || !this.renderer) {
      return this;
    }

    const width = Math.max(this.container.clientWidth, 1);
    const height = Math.max(this.container.clientHeight, 1);

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);

    this.render();
    return this;
  }

  render() {
    if (
      !this.mounted
      || !this.visible
      || !this.renderer
      || !this.scene
      || !this.camera
    ) {
      return this;
    }

    this.renderer.render(
      this.scene,
      this.camera,
    );

    return this;
  }

  dispose() {
    if (!this.mounted) {
      return;
    }

    this.resizeObserver?.disconnect();
    this.intersectionObserver?.disconnect();

    if (this.root) {
      disposeObject(this.root);
      this.scene?.remove(this.root);
    }

    if (this.renderer) {
      this.renderer.dispose();
      this.renderer.forceContextLoss();
      this.renderer.domElement.remove();
    }

    this.container = null;
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.root = null;
    this.globe = null;
    this.eye = null;
    this.axis = null;
    this.base = null;
    this.resizeObserver = null;
    this.intersectionObserver = null;
    this.visible = false;
    this.mounted = false;
    this.state = { ...DEFAULT_STATE };
  }
}
