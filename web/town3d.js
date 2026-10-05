// The 3D town: built once from /town.json and orbited with the mouse. Every colour and size
// comes from look.js; Python sends only meanings.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import * as LOOK from "./look.js";
import * as L from "./live.js";
import { transit, stations } from "./transit.js";

const NEEDED = ["PX_PER_UNIT", "BACKGROUND", "FACES", "GROUND", "TILE_THICKNESS", "WATER_DROP",
  "TREE", "WALLS", "ALTERNATE_SHADE", "AMBER", "ROOFS", "ROOF_PX", "FOCUS_ROOF", "GLASS",
  "WINDOW", "WEED", "FIRE", "WAREHOUSE", "ROADS", "ROAD_LIFT", "LINES", "TRANSIT", "DITHER",
  "CAMERA", "LABEL", "SCARVES", "CLAWD", "POSES", "SCAFFOLD", "SITE", "FLAG", "LECTERN", "DROP"];
const proj = new THREE.Vector3(), goal = new THREE.Vector3(), offset = new THREE.Vector3(),
  delta = new THREE.Vector3(), world = new THREE.Vector3();
const dropM = new THREE.Matrix4(), dropP = new THREE.Vector3(), dropS = new THREE.Vector3(),
  dropQ = new THREE.Quaternion();
const FIRE = "won't parse";
const ABANDONED = "abandoned";
const HINT = "drag orbit   right-drag pan   scroll zoom   click inspect   Esc clear";

const $ = (id) => document.getElementById(id);
const px = (p) => p / LOOK.PX_PER_UNIT;
const view = { doc: null, scene: null, townGroup: null, liveGroup: null, box: null, walls: null,
  windows: null, fire: null, warehouses: null, roadMeshes: [], strip: null, disc: null,
  dither: null, selected: null, live: null,
  offset: 0, clawds: new Map(), scaffoldMesh: null, sitesMesh: null, flagsMesh: null,
  source: null, mode: L.AUTO, centres: null, labels: new Map(), labelsShown: 0, controls: null,
  drops: new Map(), dropBases: new Map(), townFetchId: 0, reconnectTimer: null };

const town3d = {
  ready: false, error: null, live: false,
  missing: NEEDED.filter((key) => !(key in LOOK)),
  buildings: 0, warehouses: 0, roads: 0, lit: 0, focused: [], dimmed: 0, build_ms: 0, fps: 0,
};
function modeString(mode) {
  return mode.kind === "follow" ? `follow ${mode.n}` : mode.kind;
}

town3d.report = () => ({
  ready: town3d.ready, error: town3d.error, missing: [...town3d.missing],
  buildings: town3d.buildings, warehouses: town3d.warehouses, roads: town3d.roads, lit: town3d.lit,
  focused: [...town3d.focused], dimmed: town3d.dimmed,
  inspector: $("inspector").hidden ? null : $("inspect-title").textContent,
  build_ms: town3d.build_ms, fps: Math.round(town3d.fps),
  clawds: view.clawds.size,
  scaffolded: Object.keys(view.live?.scaffold || {}).length,
  sites: (view.live?.sites || []).length,
  flags: (view.live?.flags || []).length,
  poses: Object.fromEntries([...(view.live?.clawds || new Map()).values()].map((r) => [r.id, r.pose])),
  live: town3d.live,
  scaffold_boxes: view.scaffoldMesh ? view.scaffoldMesh.count : 0,
  mode: modeString(view.mode),
  labels: view.labelsShown,
  line1: $("line1").textContent,
  line2: $("line2").textContent,
  line3: $("line3").textContent,
  version: view.doc?.version ?? null,
  dropping: view.drops.size,
});
window.town3d = town3d;

// k darkens or brightens as drawtown's shade() does on sRGB values.
function colour(rgb, k = 1) {
  return new THREE.Color().setRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, THREE.SRGBColorSpace)
    .multiplyScalar(Math.pow(k, 2.2));
}

function pick(list, x, y) {
  return list[(((x * 73856093) ^ (y * 19349663)) >>> 0) % list.length];
}

function show(text) {
  const box = $("message");
  box.textContent = text;
  box.hidden = false;
}

// One unit box whose faces are shaded like the pixel town's walls, so the scene needs no lights.
function shadedBox() {
  const box = new THREE.BoxGeometry(1, 1, 1);
  const F = LOOK.FACES;
  const faces = [F.px, F.nx, F.top, F.bottom, F.pz, F.nz];
  const shades = new Float32Array(24 * 3);
  for (let v = 0; v < 24; v++) shades.fill(Math.pow(faces[Math.floor(v / 4)], 2.2), v * 3, v * 3 + 3);
  box.setAttribute("color", new THREE.BufferAttribute(shades, 3));
  return box;
}

// Boxes drawn as one instanced mesh; each keeps its colour and the thing it belongs to.
class Boxes {
  constructor() {
    this.items = [];
  }

  // turn is about the vertical axis, in radians.
  add(x, y, z, sx, sy, sz, c, owner = null, turn = 0) {
    this.items.push({ x, y, z, sx, sy, sz, c, owner, turn });
  }

  mesh(box) {
    const n = this.items.length;
    const mesh = new THREE.InstancedMesh(box, new THREE.MeshBasicMaterial({ vertexColors: true }),
      Math.max(1, n));
    mesh.count = n;
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
    const p = new THREE.Vector3(), s = new THREE.Vector3();
    this.items.forEach((b, i) => {
      q.setFromAxisAngle(up, b.turn);
      mesh.setMatrixAt(i, m.compose(p.set(b.x, b.y, b.z), q, s.set(b.sx, b.sy, b.sz)));
      mesh.setColorAt(i, b.c);
    });
    if (n === 0) mesh.setColorAt(0, new THREE.Color());
    mesh.userData.boxes = this;
    return mesh;
  }
}

function ground(doc) {
  const boxes = new Boxes();
  const t = LOOK.TILE_THICKNESS;
  doc.tiles.forEach((row, z) => {
    for (let x = 0; x < row.length; x++) {
      const kind = doc.legend[row[x]];
      const top = kind === "water" ? -LOOK.WATER_DROP : 0;
      const k = 1 - 0.03 * ((x * 7 + z * 13) % 3);
      boxes.add(x + 0.5, top - t / 2, z + 0.5, 1, t, 1, colour(LOOK.GROUND[kind], k));
    }
  });
  return boxes;
}

function trees(doc) {
  const T = LOOK.TREE, trunks = new Boxes(), crowns = new Boxes();
  for (const [x, z] of doc.trees) {
    trunks.add(x + 0.5, T.trunk_height / 2, z + 0.5, T.trunk_width, T.trunk_height,
      T.trunk_width, colour(T.trunk));
    crowns.add(x + 0.5, T.trunk_height + T.crown / 2, z + 0.5, T.crown, T.crown, T.crown,
      colour(pick(T.leaves, x, z)));
  }
  return [trunks, crowns];
}

function addWindows(boxes, cx, cz, side, tier, glass, owner) {
  const W = LOOK.WINDOW;
  const usable = side - 2 * W.margin;
  if (usable < W.width) return;
  const cols = 1 + Math.floor((usable - W.width) / W.spacing);
  const h = px(W.height_px), out = side / 2 + W.depth / 2;
  for (let k = tier.z0 + W.bottom_px; k + W.height_px <= tier.z1 - W.top_px;
    k += W.height_px + W.row_gap_px) {
    const y = px(k + W.height_px / 2);
    for (let i = 0; i < cols; i++) {
      const along = (i - (cols - 1) / 2) * W.spacing;
      boxes.add(cx + out, y, cz + along, W.depth, h, W.width, glass, owner);
      boxes.add(cx - out, y, cz + along, W.depth, h, W.width, glass, owner);
      boxes.add(cx + along, y, cz + out, W.width, h, W.depth, glass, owner);
      boxes.add(cx + along, y, cz - out, W.width, h, W.depth, glass, owner);
    }
  }
}

function addWeeds(boxes, cx, cz, side, owner) {
  const W = LOOK.WEED, r = side / 2 + W.size / 2;
  for (let i = 0; i < W.count; i++) {
    const a = (i / W.count) * Math.PI * 2;
    const dx = Math.cos(a), dz = Math.sin(a), edge = Math.max(Math.abs(dx), Math.abs(dz));
    const h = W.size * (1 + (i % 3));
    boxes.add(cx + (dx / edge) * r, h / 2, cz + (dz / edge) * r, W.size, h, W.size,
      colour(W.colour), owner);
  }
}

function buildings(doc) {
  const walls = new Boxes(), windows = new Boxes(), fires = [];
  const roofs = Object.fromEntries(doc.districts.map((d) => [d.name, d.roof]));
  doc.buildings.forEach((b, index) => {
    const [x, z, size] = b.lot;
    const cx = x + size / 2, cz = z + size / 2;
    const wall = pick(LOOK.WALLS, x, z), glass = colour(LOOK.GLASS[b.glass]);
    b.tiers.forEach((t, i) => {
      const side = t.half / doc.half_w;
      const c = t.amber ? colour(LOOK.AMBER) : colour(wall, i % 2 ? LOOK.ALTERNATE_SHADE : 1);
      walls.add(cx, px(t.z0 + t.z1) / 2, cz, side, px(t.z1 - t.z0), side, c,
        { kind: "building", index, part: "tier" });
      addWindows(windows, cx, cz, side, t, glass, { kind: "building", index, part: "window" });
    });
    const top = b.tiers[b.tiers.length - 1], side = top.half / doc.half_w;
    const roof = LOOK.ROOFS[(roofs[b.district] ?? 0) % LOOK.ROOFS.length];
    walls.add(cx, px(top.z1 + LOOK.ROOF_PX / 2), cz, side, px(LOOK.ROOF_PX), side, colour(roof),
      { kind: "building", index, part: "roof" });
    if (b.problems.includes(FIRE)) fires.push({ x: cx, y: px(top.z1 + LOOK.ROOF_PX), z: cz, side });
    if (b.problems.includes(ABANDONED)) {
      addWeeds(walls, cx, cz, b.tiers[0].half / doc.half_w, { kind: "building", index, part: "weed" });
    }
  });
  return { walls, windows, fires };
}

function warehouses(doc) {
  const W = LOOK.WAREHOUSE, boxes = new Boxes();
  doc.warehouses.forEach((w, index) => {
    const [x, z, size] = w.lot;
    const side = size * W.footprint, h = px(W.height_px);
    const owner = { kind: "warehouse", index, part: "warehouse" };
    boxes.add(x + size / 2, h / 2, z + size / 2, side, h, side, colour(W.wall), owner);
    boxes.add(x + size / 2, h + px(LOOK.ROOF_PX) / 2, z + size / 2, side, px(LOOK.ROOF_PX), side,
      colour(W.roof), owner);
  });
  return boxes;
}

function painted(geometry) {
  const n = geometry.attributes.position.count;
  geometry.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * 3).fill(1), 3));
  return geometry;
}

// Every road as its line's colour over a pale casing, round at every bend, with a station where
// it ends. Roads lie flat on the streets and are painted in order rather than depth-sorted, so a
// later pass always covers an earlier one: casings, then colours, the selection's roads last.
function roadMeshes(roads, lit) {
  const T = LOOK.TRANSIT, y = LOOK.ROAD_LIFT, h = LOOK.ROAD_LIFT / 2;
  const paths = transit(roads, T);
  const toGrey = (rgb) => rgb.map((v, i) => v + (T.grey[i] - v) * T.dim);
  const passes = [];
  const pass = () => {
    const p = { strips: new Boxes(), discs: new Boxes() };
    passes.push(p);
    return p;
  };
  const lay = (p, segments, width, c) => {
    for (const s of segments) {
      const w = width(s), dx = s.b[0] - s.a[0], dz = s.b[1] - s.a[1];
      p.strips.add((s.a[0] + s.b[0]) / 2, y, (s.a[1] + s.b[1]) / 2, Math.hypot(dx, dz), h, w, c,
        null, -Math.atan2(dz, dx));
      p.discs.add(s.a[0], y, s.a[1], w, h, w, c);
      p.discs.add(s.b[0], y, s.b[1], w, h, w, c);
    }
  };
  for (const top of lit ? [false, true] : [false]) {
    const casing = pass(), line = pass();
    roads.forEach((r, k) => {
      const on = !lit || lit.has(r.id);
      if (lit && on !== top) return;
      const rgb = r.kind in LOOK.ROADS && r.kind !== "road" ? LOOK.ROADS[r.kind]
        : LOOK.LINES[r.line % LOOK.LINES.length];
      lay(casing, paths[k], (s) => s.cw, colour(on ? T.casing_colour : toGrey(T.casing_colour)));
      lay(line, paths[k], (s) => s.w, colour(on ? rgb : toGrey(rgb)));
    });
  }
  const ring = pass(), dot = pass();
  for (const s of stations(roads)) {
    const on = !lit || s.roads.some((id) => lit.has(id));
    const [x, z] = [s.tile[0] + 0.5, s.tile[1] + 0.5], d = T.station;
    ring.discs.add(x, y, z, d + 2 * T.ring, h, d + 2 * T.ring, colour(on ? T.ring_colour : toGrey(T.ring_colour)));
    dot.discs.add(x, y, z, d, h, d, colour(on ? T.station_colour : toGrey(T.station_colour)));
  }
  const meshes = [];
  passes.forEach((p, i) => {
    for (const [boxes, geometry] of [[p.strips, view.strip], [p.discs, view.disc]]) {
      if (!boxes.items.length) continue;
      const mesh = boxes.mesh(geometry);
      mesh.material.depthWrite = false;
      mesh.renderOrder = 1 + i;
      meshes.push(mesh);
    }
  });
  return meshes;
}

function setRoads(roads, lit = null) {
  for (const mesh of view.roadMeshes) {
    view.townGroup.remove(mesh);
    mesh.material.dispose();
    mesh.dispose();
  }
  view.roadMeshes = roadMeshes(roads, lit);
  view.townGroup.add(...view.roadMeshes);
  town3d.roads = roads.length;
  town3d.lit = lit ? lit.size : roads.length;
}

function buildingByPath(path) {
  return view.doc.buildings.find((b) => b.path === path);
}

function disposeMesh(mesh) {
  if (!mesh) return;
  mesh.material.dispose();
  mesh.dispose();
}

function disposeTownChild(mesh) {
  if (!mesh) return;
  mesh.material?.dispose();
  if (mesh.geometry && ![view.box, view.strip, view.disc].includes(mesh.geometry)) mesh.geometry.dispose();
  mesh.dispose();
}

function disposeTownGroup() {
  if (!view.townGroup) return;
  for (const child of view.townGroup.children) disposeTownChild(child);
  view.townGroup.clear();
  view.roadMeshes = [];
  view.walls = null;
  view.windows = null;
  view.fire = null;
  view.warehouses = null;
}

function disposeClawd(group) {
  const mat = group.children[0]?.material;
  for (const mesh of group.children) {
    mesh.geometry.dispose();
  }
  mat?.dispose();
}

function mergeBoxes(boxes, colours) {
  const positions = [], colors = [], indices = [];
  const m = new THREE.Matrix4(), p = new THREE.Vector3(), s = new THREE.Vector3();
  const q = new THREE.Quaternion();
  for (const [x, y, z, w, h, d, part] of boxes) {
    const g = view.box.clone();
    g.applyMatrix4(m.compose(p.set(x, y, z), q, s.set(w, h, d)));
    const base = positions.length / 3, c = colour(colours[part]);
    const pos = g.getAttribute("position"), shade = g.getAttribute("color");
    for (let i = 0; i < pos.count; i++) {
      positions.push(pos.getX(i), pos.getY(i), pos.getZ(i));
      colors.push(c.r * shade.getX(i), c.g * shade.getY(i), c.b * shade.getZ(i));
    }
    for (const i of g.getIndex().array) indices.push(base + i);
    g.dispose();
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  out.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  out.setIndex(indices);
  return out;
}

function clawdObject(rec) {
  const C = LOOK.CLAWD;
  const colours = { ...C.colours,
    scarf: LOOK.SCARVES[(rec.scarf ?? 0) % LOOK.SCARVES.length],
    dark: rec.role === "reviewer" ? C.colours.reviewer : C.colours.dark };
  const extra = rec.role === "implementer" ? C.scarf : rec.role === "reviewer" ? C.glasses
    : rec.role === "orchestrator" ? C.hat : [];
  const material = new THREE.MeshBasicMaterial({ vertexColors: true });
  const group = new THREE.Group();
  group.scale.setScalar(C.voxel);
  const frames = C.legs.map((legs) => {
    const mesh = new THREE.Mesh(mergeBoxes([...C.body, ...extra, ...legs], colours), material);
    mesh.visible = false;
    group.add(mesh);
    return mesh;
  });
  frames[0].visible = true;
  group.userData = { frames, role: rec.role, scarf: rec.scarf };
  return group;
}

function lectern(hall) {
  const Lc = LOOK.LECTERN, boxes = new Boxes(), c = colour(Lc.colour);
  const cx = hall[0] + 0.5, cz = hall[1] + 0.5;
  boxes.add(cx, Lc.height / 2, cz, Lc.width, Lc.height, Lc.width, c);
  boxes.add(cx, Lc.height + Lc.top / 4, cz + Lc.width * 0.15, Lc.width * 0.9, Lc.top,
    Lc.width * 0.7, c);
  return boxes;
}

function rebuildScaffold() {
  disposeMesh(view.scaffoldMesh);
  view.scaffoldMesh = null;
  if (!view.live?.scaffold) return;
  const boxes = new Boxes(), S = LOOK.SCAFFOLD;
  for (const [path, scarf] of Object.entries(view.live.scaffold)) {
    const b = buildingByPath(path);
    if (!b) continue;
    const c = colour(LOOK.SCARVES[scarf % LOOK.SCARVES.length]);
    for (const [bx, by, bz, sx, sy, sz] of L.scaffoldBoxes(b, view.doc.half_w, S, LOOK.ROOF_PX,
      LOOK.PX_PER_UNIT)) {
      boxes.add(bx, by, bz, sx, sy, sz, c);
    }
  }
  if (boxes.items.length) {
    view.scaffoldMesh = boxes.mesh(view.box);
    view.liveGroup.add(view.scaffoldMesh);
  }
}

function rebuildSites() {
  disposeMesh(view.sitesMesh);
  view.sitesMesh = null;
  if (!view.live?.sites?.length) return;
  const boxes = new Boxes(), T = LOOK.SITE;
  const { plots, ground } = L.siteBoxes(view.live.sites, view.doc.size, T, LOOK.PX_PER_UNIT);
  const t = LOOK.TILE_THICKNESS;
  for (const [x, z] of ground) {
    const k = 1 - 0.03 * ((x * 7 + z * 13) % 3);
    boxes.add(x + 0.5, -t / 2, z + 0.5, 1, t, 1, colour(LOOK.GROUND.grass, k));
  }
  for (const [bx, by, bz, sx, sy, sz, role, i] of plots) {
    const site = view.live.sites[i];
    const c = role === "slab" ? colour(T.colour)
      : colour(LOOK.SCARVES[site.scarf % LOOK.SCARVES.length]);
    boxes.add(bx, by, bz, sx, sy, sz, c);
  }
  view.sitesMesh = boxes.mesh(view.box);
  view.liveGroup.add(view.sitesMesh);
}

function rebuildFlags() {
  disposeMesh(view.flagsMesh);
  view.flagsMesh = null;
  if (!view.live?.flags?.length) return;
  const boxes = new Boxes(), F = LOOK.FLAG;
  for (const flag of view.live.flags) {
    const b = buildingByPath(flag.building);
    if (!b) continue;
    const [x, z] = b.lot, poleX = x + b.lot[2], poleZ = z;
    const cloth = colour(LOOK.SCARVES[flag.scarf % LOOK.SCARVES.length]);
    boxes.add(poleX, F.pole_height / 2, poleZ, F.pole_width, F.pole_height, F.pole_width,
      colour(F.pole));
    boxes.add(poleX + F.cloth_width / 2, F.pole_height - F.cloth_height / 2, poleZ,
      F.cloth_width, F.cloth_height, F.pole_width, cloth);
  }
  view.flagsMesh = boxes.mesh(view.box);
  view.liveGroup.add(view.flagsMesh);
}

function buildingCentres(doc) {
  const centres = new Map();
  for (const b of doc.buildings) {
    const [x, z, size] = b.lot;
    centres.set(b.path, [x + size / 2, z + size / 2]);
  }
  return centres;
}

function refreshLegend() {
  if (!view.live) return;
  $("line3").textContent = L.legend(view.live, view.mode);
}

function refreshStatus() {
  if (!view.live) return;
  $("line1").textContent = view.live.status[0];
  $("line2").textContent = view.live.status[1];
  refreshLegend();
}

function labelEntry(key, className) {
  let entry = view.labels.get(key);
  if (!entry) {
    const el = document.createElement("div");
    el.className = className;
    $("labels").appendChild(el);
    entry = { el, text: "", opacity: -1, visible: false, left: "", top: "" };
    view.labels.set(key, entry);
  }
  return entry;
}

function showLabel(entry, text, sx, sy, opacity, on) {
  if (entry.text !== text) {
    entry.el.textContent = text;
    entry.text = text;
  }
  if (!on) {
    if (entry.visible) entry.el.style.display = "none";
    entry.visible = false;
    return;
  }
  if (entry.el.style.display === "none") entry.el.style.display = "";
  const left = `${sx}px`, top = `${sy}px`;
  if (entry.left !== left) {
    entry.el.style.left = left;
    entry.left = left;
  }
  if (entry.top !== top) {
    entry.el.style.top = top;
    entry.top = top;
  }
  if (entry.opacity !== opacity) {
    entry.el.style.opacity = String(opacity);
    entry.opacity = opacity;
  }
  entry.visible = true;
}

function placeLabel(key, className, wx, wy, wz, camera, text) {
  world.set(wx, wy, wz);
  const dist = camera.position.distanceTo(world);
  proj.copy(world).project(camera);
  const behind = proj.z < -1 || proj.z > 1;
  const w = window.innerWidth, h = window.innerHeight;
  const sx = (proj.x * 0.5 + 0.5) * w, sy = (-proj.y * 0.5 + 0.5) * h;
  const opacity = behind ? 0 : L.labelOpacity(dist, LOOK.LABEL.fade);
  showLabel(labelEntry(key, className), text, sx, sy, opacity, !behind && opacity > 0);
  return !behind && opacity > 0;
}

function placeLabels(camera, controls) {
  const want = new Set();
  let shown = 0;
  if (view.live) {
    for (const [id, rec] of view.live.clawds) {
      const obj = view.clawds.get(id);
      if (!obj) continue;
      const key = `c:${id}`;
      want.add(key);
      if (placeLabel(key, "label", obj.position.x, obj.position.y + LOOK.LABEL.lift,
        obj.position.z, camera, rec.label)) shown += 1;
    }
    if (view.live.scaffold && view.centres) {
      const paths = L.nearestScaffold(view.live.scaffold, view.centres,
        [controls.target.x, controls.target.z], LOOK.LABEL.max_scaffold);
      for (const path of paths) {
        const [cx, cz] = view.centres.get(path);
        const key = `s:${path}`;
        want.add(key);
        if (placeLabel(key, "label place", cx, LOOK.LABEL.lift, cz, camera, `● ${path}`)) {
          shown += 1;
        }
      }
    }
  }
  if (view.doc?.hall) {
    const key = "hall";
    want.add(key);
    const [hx, hz] = view.doc.hall;
    if (placeLabel(key, "label place", hx + 0.5, LOOK.LABEL.lift, hz + 0.5, camera, "Town Hall")) {
      shown += 1;
    }
  }
  for (const [key, entry] of view.labels) {
    if (want.has(key)) continue;
    entry.el.remove();
    view.labels.delete(key);
  }
  view.labelsShown = shown;
}

function followCamera(camera, controls, dt) {
  const rec = view.live && L.cameraClawd(view.mode, view.live);
  if (!rec) return;
  const obj = view.clawds.get(rec.id);
  if (!obj) return;
  const k = 1 - Math.exp(-LOOK.CAMERA.follow_ease * dt);
  goal.set(obj.position.x, 0, obj.position.z);
  delta.copy(goal).sub(controls.target).multiplyScalar(k);
  controls.target.add(delta);
  clampTarget(controls.target);
  camera.position.add(delta);
  offset.copy(camera.position).sub(controls.target);
  const d = offset.length();
  offset.setLength(d + (LOOK.CAMERA.follow_distance - d) * k);
  camera.position.copy(controls.target).add(offset);
}

function syncLive(tick) {
  const want = new Set(view.live.clawds.keys());
  for (const id of view.clawds.keys()) {
    if (want.has(id)) continue;
    const obj = view.clawds.get(id);
    view.liveGroup.remove(obj);
    disposeClawd(obj);
    view.clawds.delete(id);
  }
  for (const [id, rec] of view.live.clawds) {
    let obj = view.clawds.get(id);
    if (!obj) {
      obj = clawdObject(rec);
      view.clawds.set(id, obj);
      view.liveGroup.add(obj);
      continue;
    }
    if (obj.userData.role !== rec.role || obj.userData.scarf !== rec.scarf) {
      view.liveGroup.remove(obj);
      disposeClawd(obj);
      obj = clawdObject(rec);
      view.clawds.set(id, obj);
      view.liveGroup.add(obj);
    }
  }
  const all = !tick;
  if (all || "scaffold" in tick) {
    view.liveGroup.remove(view.scaffoldMesh);
    rebuildScaffold();
  }
  if (all || "sites" in tick) {
    view.liveGroup.remove(view.sitesMesh);
    rebuildSites();
  }
  if (all || "flags" in tick) {
    view.liveGroup.remove(view.flagsMesh);
    rebuildFlags();
  }
}

function clearClawds() {
  if (!view.scene) return;
  for (const obj of view.clawds.values()) {
    view.liveGroup.remove(obj);
    disposeClawd(obj);
  }
  view.clawds.clear();
}

function captureDropBases(path) {
  const index = view.doc.buildings.findIndex((b) => b.path === path);
  if (index < 0) return;
  const parts = new Set(["tier", "window", "roof"]);
  const bases = [];
  const m = new THREE.Matrix4();
  for (const mesh of [view.walls, view.windows]) {
    if (!mesh) continue;
    mesh.userData.boxes.items.forEach((b, i) => {
      if (b.owner?.kind !== "building" || b.owner.index !== index || !parts.has(b.owner.part)) {
        return;
      }
      mesh.getMatrixAt(i, m);
      bases.push({ mesh, i, base: m.clone() });
    });
  }
  if (bases.length) view.dropBases.set(path, bases);
}

function applyDrops(now) {
  if (!view.drops.size) return;
  for (const [path, start] of view.drops) {
    const elapsed = now - start;
    const lift = L.dropLift(elapsed, LOOK.DROP, LOOK.PX_PER_UNIT);
    const bases = view.dropBases.get(path);
    if (!bases) continue;
    for (const { mesh, i, base } of bases) {
      base.decompose(dropP, dropQ, dropS);
      dropP.y += lift;
      mesh.setMatrixAt(i, dropM.compose(dropP, dropQ, dropS));
      mesh.instanceMatrix.needsUpdate = true;
    }
    if (elapsed >= LOOK.DROP.time) {
      for (const { mesh, i, base } of bases) {
        mesh.setMatrixAt(i, base);
        mesh.instanceMatrix.needsUpdate = true;
      }
      view.drops.delete(path);
      view.dropBases.delete(path);
    }
  }
}

function updateDoc(doc) {
  view.doc = doc;
  checkKinds(doc);
  town3d.buildings = doc.buildings.length;
  town3d.warehouses = doc.warehouses.length;
  town3d.roads = doc.roads.length;
}

async function applyTownDoc(doc) {
  if (!view.scene) {
    updateDoc(doc);
    return;
  }
  const fresh = L.newBuildings(view.doc, doc);
  const keepPath = view.selected?.path ?? null;
  view.drops.clear();
  view.dropBases.clear();
  disposeTownGroup();
  fillTownGroup(doc);
  view.doc = doc;
  view.centres = buildingCentres(doc);
  checkKinds(doc);
  town3d.buildings = doc.buildings.length;
  town3d.warehouses = doc.warehouses.length;
  view.liveGroup.remove(view.scaffoldMesh, view.sitesMesh, view.flagsMesh);
  rebuildScaffold();
  rebuildSites();
  rebuildFlags();
  if (keepPath && doc.buildings.some((b) => b.path === keepPath)) {
    const index = doc.buildings.findIndex((b) => b.path === keepPath);
    await select({ kind: "building", index, part: "tier" });
  } else if (view.selected) {
    clear();
  }
  const now = serverNow();
  for (const path of fresh) {
    view.drops.set(path, now);
    captureDropBases(path);
  }
}

async function refetchTown() {
  const gen = ++view.townFetchId;
  try {
    const res = await fetch("/town.json");
    if (!res.ok || gen !== view.townFetchId) return;
    await applyTownDoc(await res.json());
  } catch {
    /* a newer town fetch wins */
  }
}

function connect() {
  if (view.reconnectTimer) {
    clearTimeout(view.reconnectTimer);
    view.reconnectTimer = null;
  }
  if (view.source) view.source.close();
  const source = new EventSource("/events");
  const stamp = (msg) => { view.offset = L.offsetFor(performance.now() / 1000, msg.t); };
  source.addEventListener("state", (e) => {
    const msg = JSON.parse(e.data);
    stamp(msg);
    clearClawds();
    view.live = L.applyState(msg);
    town3d.live = true;
    if (view.scene) syncLive();
    refreshStatus();
    if (msg.version !== view.doc.version) refetchTown();
  });
  source.addEventListener("tick", (e) => {
    const msg = JSON.parse(e.data);
    stamp(msg);
    if (view.live) {
      view.live = L.applyTick(view.live, msg);
      if (view.scene) syncLive(msg);
      refreshStatus();
    }
  });
  source.addEventListener("town", (e) => {
    const msg = JSON.parse(e.data);
    stamp(msg);
    refetchTown();
  });
  source.onerror = () => {
    $("line2").textContent = "reconnecting…";
    town3d.live = false;
    if (source.readyState === EventSource.CLOSED && !view.reconnectTimer) {
      view.reconnectTimer = setTimeout(() => {
        view.reconnectTimer = null;
        connect();
      }, 300);
    }
  };
  view.source = source;
}

function serverNow() {
  return performance.now() / 1000 - view.offset;
}

function placeClawds(now) {
  if (!view.live) return;
  for (const [id, rec] of view.live.clawds) {
    const obj = view.clawds.get(id);
    if (!obj) continue;
    const at = L.walkPosition(rec, now, view.doc.step_time);
    const lift = L.poseLift(rec, now, LOOK.POSES, LOOK.PX_PER_UNIT);
    const step = at.moving ? 1 + (Math.floor((now - rec.at) / view.doc.step_time) % 2) : 0;
    obj.userData.frames.forEach((m, i) => { m.visible = i === step; });
    const bob = at.moving && step === 1 ? LOOK.CLAWD.bob_px / LOOK.PX_PER_UNIT : 0;
    obj.position.set(at.x, lift + bob, at.z);
    const turn = L.clawdTurn(rec, at.facing, LOOK.POSES.peer.lean_deg);
    obj.rotation.set(turn.x, turn.y, 0, turn.order);
  }
}

function fireMesh(fires, box) {
  const boxes = new Boxes();
  for (const f of fires) {
    for (let k = 0; k < LOOK.FIRE.cubes; k++) boxes.add(f.x, f.y, f.z, 0, 0, 0, colour(LOOK.FIRE.smoke));
  }
  const mesh = boxes.mesh(box);
  mesh.frustumCulled = false;
  mesh.userData.fires = fires;
  return mesh;
}

function burn(mesh, t) {
  const F = LOOK.FIRE, fires = mesh.userData.fires;
  if (!fires.length) return;
  const m = new THREE.Matrix4(), q = new THREE.Quaternion();
  const p = new THREE.Vector3(), s = new THREE.Vector3();
  fires.forEach((f, j) => {
    for (let k = 0; k < F.cubes; k++) {
      const phase = (t * F.speed + k / F.cubes) % 1;
      const smoke = k % 3 === 2, turn = k * 2.4 + t;
      const r = f.side * 0.35 * (1 - phase * 0.5);
      const size = F.size * (smoke ? 1 + phase : 1 - phase * 0.6);
      const rise = phase * (smoke ? F.smoke_rise : F.flame_rise);
      const i = j * F.cubes + k;
      mesh.setMatrixAt(i, m.compose(p.set(f.x + Math.cos(turn) * r, f.y + rise + size / 2,
        f.z + Math.sin(turn) * r), q, s.set(size, size, size)));
      const flame = F.flames[Math.min(F.flames.length - 1, Math.floor(phase * F.flames.length))];
      mesh.setColorAt(i, colour(smoke ? F.smoke : flame));
    }
  });
  mesh.instanceMatrix.needsUpdate = true;
  mesh.instanceColor.needsUpdate = true;
}

function fillTownGroup(doc) {
  view.townGroup.add(ground(doc).mesh(view.box));
  for (const part of trees(doc)) view.townGroup.add(part.mesh(view.box));
  const town = buildings(doc);
  view.walls = town.walls.mesh(view.box);
  view.windows = town.windows.mesh(view.box);
  view.fire = fireMesh(town.fires, view.box);
  view.warehouses = warehouses(doc).mesh(view.box);
  view.townGroup.add(view.walls, view.windows, view.fire, view.warehouses);
  view.townGroup.add(lectern(doc.hall).mesh(view.box));
  setRoads(doc.roads);
}

function build(doc) {
  view.scene = new THREE.Scene();
  view.scene.background = colour(LOOK.BACKGROUND);
  view.box = shadedBox();
  view.strip = painted(new THREE.BoxGeometry(1, 1, 1));
  view.disc = painted(new THREE.CylinderGeometry(0.5, 0.5, 1, 24));
  view.townGroup = new THREE.Group();
  view.liveGroup = new THREE.Group();
  view.scene.add(view.townGroup, view.liveGroup);
  fillTownGroup(doc);
}

function clampTarget(t) {
  const ext = L.siteExtent(view.live?.sites || [], view.doc.size);
  t.set(THREE.MathUtils.clamp(t.x, 0, ext.maxX), 0, THREE.MathUtils.clamp(t.z, 0, ext.maxZ));
}

function makeCamera(doc, canvas) {
  const C = LOOK.CAMERA, [w, h] = doc.size, span = Math.max(w, h);
  const camera = new THREE.PerspectiveCamera(C.fov, window.innerWidth / window.innerHeight, 0.1,
    span * 10);
  const elevation = THREE.MathUtils.degToRad(C.elevation_deg);
  const azimuth = THREE.MathUtils.degToRad(C.azimuth_deg);
  const d = span * C.start_distance;
  camera.position.set(w / 2 + d * Math.cos(elevation) * Math.sin(azimuth), d * Math.sin(elevation),
    h / 2 + d * Math.cos(elevation) * Math.cos(azimuth));
  const controls = new OrbitControls(camera, canvas);
  controls.target.set(w / 2, 0, h / 2);
  controls.enableDamping = true;
  controls.screenSpacePanning = false;
  controls.minDistance = C.min_distance;
  controls.maxDistance = span * C.max_distance;
  controls.maxPolarAngle = THREE.MathUtils.degToRad(C.max_polar_deg);
  controls.addEventListener("change", () => clampTarget(controls.target));
  controls.addEventListener("start", () => {
    if (!view.live) return;
    const prev = view.mode;
    view.mode = L.userMoved(view.mode);
    if (view.mode !== prev) refreshLegend();
  });
  if (doc.live && doc.hall) {
    const fx = doc.hall[0] + 0.5, fz = doc.hall[1] + 0.5;
    const dx = fx - w / 2, dz = fz - h / 2;
    controls.target.x += dx;
    controls.target.z += dz;
    camera.position.x += dx;
    camera.position.z += dz;
  }
  controls.update();
  return { camera, controls };
}

function checkKinds(doc) {
  const wanted = [...Object.values(doc.legend).map((k) => ["GROUND", k]),
    ...doc.buildings.map((b) => ["GLASS", b.glass]),
    ...["road", "highway", "uses", "used by", "backwards", "cycle"].map((k) => ["ROADS", k])];
  for (const [table, key] of wanted) {
    const name = `${table}.${key}`;
    if (!(key in LOOK[table]) && !town3d.missing.includes(name)) town3d.missing.push(name);
  }
}

// A building's boxes take its brightness from the focus; the focused building gets the white roof.
function recolour(dim, focused) {
  const c = new THREE.Color();
  for (const mesh of [view.walls, view.windows]) {
    mesh.userData.boxes.items.forEach((b, i) => {
      const path = view.doc.buildings[b.owner.index].path;
      if (b.owner.part === "roof" && focused.has(path)) {
        mesh.setColorAt(i, colour(LOOK.FOCUS_ROOF));
        return;
      }
      const k = dim && path in dim ? dim[path] : 1;
      mesh.setColorAt(i, c.copy(b.c).multiplyScalar(Math.pow(k, 2.2)));
    });
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }
  town3d.dimmed = dim ? Object.values(dim).filter((k) => k < 1).length : 0;
}

// Repository text only ever reaches the page as textContent.
function inspect(info) {
  $("inspect-title").textContent = info.title;
  $("inspect-facts").textContent = info.facts;
  $("inspect-reasons").replaceChildren(...info.reasons.map((reason) => {
    const item = document.createElement("li");
    item.textContent = reason;
    return item;
  }));
  $("inspector").hidden = false;
}

function dropFocus() {
  recolour(null, new Set());
  setRoads(view.doc.roads);
  town3d.focused = [];
}

function clear() {
  view.selected = null;
  $("inspector").hidden = true;
  dropFocus();
}

async function select(owner) {
  if (!owner) return clear();
  const building = owner.kind === "building";
  const thing = building ? view.doc.buildings[owner.index] : view.doc.warehouses[owner.index];
  view.selected = thing;
  inspect(thing.inspect);
  const query = building ? `module=${encodeURIComponent(thing.path)}`
    : `package=${encodeURIComponent(thing.package)}`;
  try {
    const res = await fetch(`/focus?${query}`);
    if (view.selected !== thing) return;
    if (!res.ok) {
      dropFocus();
      return;
    }
    const answer = await res.json();
    if (view.selected !== thing) return;
    recolour(building ? answer.dim : null, new Set(answer.focused));
    setRoads(view.doc.roads, new Set(answer.lit));
    town3d.focused = answer.focused;
  } catch {
    if (view.selected === thing) dropFocus();
  }
}

// A click is a press and release that barely moved; a drag belongs to the camera.
function pickable(canvas, camera, meshesOf) {
  const ray = new THREE.Raycaster(), at = new THREE.Vector2();
  let down = null;
  canvas.addEventListener("pointerdown", (e) => {
    down = e.button === 0 ? [e.clientX, e.clientY] : null;
  });
  canvas.addEventListener("pointerup", (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    down = null;
    const r = canvas.getBoundingClientRect();
    at.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(at, camera);
    const hit = ray.intersectObjects(meshesOf(), false).find((h) => h.instanceId !== undefined);
    select(hit ? hit.object.userData.boxes.items[hit.instanceId].owner : null);
  });
}

function pressKey(key) {
  if (!view.live) return;
  view.mode = L.pressKey(view.mode, key, view.live);
  refreshLegend();
}

function wire(renderer, camera) {
  pickable(renderer.domElement, camera,
    () => [view.walls, view.windows, view.warehouses].filter(Boolean));
  window.addEventListener("keydown", (e) => {
    if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape") clear();
    else if (/^[0-9]$/.test(e.key)) pressKey(e.key);
  });
  town3d.select = (path) => {
    const index = view.doc.buildings.findIndex((b) => b.path === path);
    return select(index < 0 ? null : { kind: "building", index });
  };
  town3d.press = pressKey;
}

// The scene is drawn to a texture, then to the screen on a grid of DITHER.pixel squares with a
// 4x4 ordered dither between DITHER.levels shades per channel. The texture holds linear colour,
// so the shader converts to sRGB before it quantises, as the screen would.
function ditherPass(renderer) {
  const D = LOOK.DITHER, size = renderer.getDrawingBufferSize(new THREE.Vector2());
  const target = new THREE.WebGLRenderTarget(size.x, size.y, { type: THREE.HalfFloatType, samples: 4 });
  const uniforms = {
    scene: { value: target.texture }, size: { value: size },
    pixel: { value: D.pixel * renderer.getPixelRatio() }, levels: { value: D.levels },
    strength: { value: D.strength },
  };
  const material = new THREE.ShaderMaterial({
    uniforms, depthTest: false, depthWrite: false,
    vertexShader: "varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
    fragmentShader: `
      uniform sampler2D scene; uniform vec2 size; uniform float pixel, levels, strength;
      const float BAYER[16] = float[16](0., 8., 2., 10., 12., 4., 14., 6., 3., 11., 1., 9., 15., 7., 13., 5.);
      vec3 srgb(vec3 c) { return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
      void main() {
        vec2 cell = floor(gl_FragCoord.xy / pixel);
        vec3 c = srgb(texture2D(scene, (cell + 0.5) * pixel / size).rgb);
        int i = int(mod(cell.x, 4.0)) + 4 * int(mod(cell.y, 4.0));
        float t = ((BAYER[i] + 0.5) / 16.0 - 0.5) * strength;
        gl_FragColor = vec4(clamp(floor(c * (levels - 1.0) + 0.5 + t) / (levels - 1.0), 0.0, 1.0), 1.0);
      }`,
  });
  const screen = new THREE.Scene();
  screen.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material));
  const flat = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  return {
    render(scene, camera) {
      renderer.setRenderTarget(target);
      renderer.render(scene, camera);
      renderer.setRenderTarget(null);
      renderer.render(screen, flat);
    },
    resize() {
      renderer.getDrawingBufferSize(size);
      target.setSize(size.x, size.y);
    },
  };
}

function run(renderer, camera, controls) {
  let frames = 0, since = performance.now(), last = since;
  renderer.setAnimationLoop((now) => {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    controls.update();
    burn(view.fire, now / 1000);
    const nowSec = serverNow();
    applyDrops(nowSec);
    placeClawds(nowSec);
    if (view.live) {
      const prev = view.mode;
      view.mode = L.settle(view.mode, view.live);
      if (view.mode !== prev) refreshLegend();
      followCamera(camera, controls, dt);
    }
    placeLabels(camera, controls);
    view.dither.render(view.scene, camera);
    town3d.ready = true;
    frames += 1;
    if (now - since >= 1000) {
      town3d.fps = (frames * 1000) / (now - since);
      frames = 0;
      since = now;
    }
  });
}

async function start() {
  const began = performance.now();
  if (town3d.missing.length) throw new Error(`look.js doesn't define ${town3d.missing.join(", ")}`);
  const res = await fetch("/town.json");
  if (!res.ok) throw new Error(`Couldn't load the town (${res.status}).`);
  const doc = await res.json();
  view.doc = doc;
  view.centres = buildingCentres(doc);
  checkKinds(doc);
  if (town3d.missing.length) throw new Error(`look.js doesn't define ${town3d.missing.join(", ")}`);
  $("line1").textContent = `${doc.repo}: ${doc.buildings.length} buildings, ` +
    `${doc.warehouses.length} warehouses`;
  $("line3").textContent = HINT;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
  } catch {
    town3d.error = "no webgl";
    show("WebGL isn't available in this browser, so the 3D town can't be drawn.");
    if (doc.live) connect();
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  document.body.appendChild(renderer.domElement);
  view.dither = ditherPass(renderer);
  build(doc);
  town3d.buildings = doc.buildings.length;
  town3d.warehouses = doc.warehouses.length;
  const { camera, controls } = makeCamera(doc, renderer.domElement);
  view.controls = controls;
  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    view.dither.resize();
  });
  wire(renderer, camera);
  if (doc.live) connect();
  town3d.build_ms = Math.round(performance.now() - began);
  run(renderer, camera, controls);
}

start().catch((e) => {
  town3d.error = e.message || String(e);
  show(town3d.error);
});
