// The live watch's logic, with no drawing, so node --test can check it. Python decides where
// each Clawd goes; this only works out where it is now and what the camera should look at.

export const AUTO = { kind: "auto" };
export const PAUSED = { kind: "paused" };
export const follow = (n) => ({ kind: "follow", n });
const HINTS = "drag orbit  scroll zoom  click inspect  Esc clear";

export function offsetFor(clientSeconds, t) {
  return clientSeconds - t;
}

// Python's crowd interpolates between path[path_i] and path[path_i + 1] by walk_t and moves on
// one tile per step_time; this walks on from where the record left off.
export function walkPosition(rec, now, stepTime) {
  const path = rec.path || [];
  if (rec.pose !== "walk" || path.length < 2) {
    return { x: rec.tile[0] + 0.5, z: rec.tile[1] + 0.5, facing: rec.facing, moving: false, step: 0 };
  }
  const last = path.length - 1;
  const progress = rec.path_i + rec.walk_t + Math.max(0, now - rec.at) / stepTime;
  if (progress >= last) {
    const [x, z] = path[last], [px, pz] = path[last - 1];
    return { x: x + 0.5, z: z + 0.5, facing: [x - px, z - pz], moving: false, step: last };
  }
  const i = Math.floor(progress), f = progress - i;
  const [ax, az] = path[i], [bx, bz] = path[i + 1];
  return { x: ax + 0.5 + (bx - ax) * f, z: az + 0.5 + (bz - az) * f, facing: [bx - ax, bz - az],
    moving: true, step: i };
}

export function poseLift(rec, now, poses, pxPerUnit) {
  const elapsed = Math.max(0, now - rec.at);
  if (rec.pose === "hop") {
    const { heights_px: heights, time } = poses.hop;
    const i = Math.floor(elapsed / time);
    if (i >= heights.length) return 0;
    const f = (elapsed - i * time) / time;
    return (heights[i] * 4 * f * (1 - f)) / pxPerUnit;
  }
  if (rec.pose === "hammer") {
    const { time, bounces, height_px: h } = poses.hammer;
    if (elapsed >= time) return 0;
    return (h * Math.abs(Math.sin((Math.PI * bounces * elapsed) / time))) / pxPerUnit;
  }
  return 0;
}

// drawtown.drop_offset: ease-out with a slight overshoot.
export function dropLift(elapsed, drop, pxPerUnit) {
  if (elapsed <= 0) return drop.height_px / pxPerUnit;
  if (elapsed >= drop.time) return 0;
  const u = elapsed / drop.time;
  return (drop.height_px * (1 - u) ** 2 * (1 + 0.12 * Math.sin(u * Math.PI))) / pxPerUnit;
}

export function applyState(msg) {
  return {
    version: msg.version,
    clawds: new Map(msg.clawds.map((r) => [r.id, { ...r, at: msg.t }])),
    scaffold: msg.scaffold, sites: msg.sites, flags: msg.flags, status: msg.status,
    camera: msg.camera,
  };
}

export function applyTick(live, msg) {
  for (const r of msg.clawds || []) live.clawds.set(r.id, { ...r, at: msg.t });
  for (const id of msg.gone || []) live.clawds.delete(id);
  for (const key of ["scaffold", "sites", "flags", "status", "camera"]) {
    if (key in msg) live[key] = msg[key];
  }
  return live;
}

const byFollow = (live, n) => [...live.clawds.values()].find((r) => r.follow === n) || null;

export function pressKey(mode, key, live) {
  if (key === "0") return AUTO;
  if (/^[1-9]$/.test(key) && byFollow(live, Number(key))) return follow(Number(key));
  return mode;
}

export function userMoved(mode) {
  return PAUSED;
}

export function settle(mode, live) {
  return mode.kind === "follow" && !byFollow(live, mode.n) ? AUTO : mode;
}

export function cameraClawd(mode, live) {
  if (mode.kind === "follow") return byFollow(live, mode.n);
  if (mode.kind === "auto" && live.camera) return live.clawds.get(live.camera) || null;
  return null;
}

export function legend(live, mode) {
  const parts = ["0 auto", ...[...live.clawds.values()].filter((r) => r.follow != null)
    .sort((a, b) => a.follow - b.follow).map((r) => `${r.follow} ${r.team || "?"}`)];
  const state = mode.kind === "follow" ? `[following ${mode.n}]`
    : mode.kind === "paused" ? "[paused, 0 resumes]" : "[auto]";
  return `${parts.join("  ")}  ·  ${HINTS}   ${state}`;
}

export function labelOpacity(distance, fade) {
  if (distance <= fade.start) return 1;
  if (distance >= fade.end) return 0;
  return 1 - (distance - fade.start) / (fade.end - fade.start);
}

export function nearestScaffold(scaffold, centres, target, n = 8) {
  return Object.keys(scaffold).filter((p) => centres.has(p))
    .map((p) => [p, Math.hypot(centres.get(p)[0] - target[0], centres.get(p)[1] - target[1])])
    .sort((a, b) => a[1] - b[1] || (a[0] < b[0] ? -1 : 1)).slice(0, n).map(([p]) => p);
}

export function newBuildings(oldDoc, newDoc) {
  const had = new Set(oldDoc.buildings.map((b) => b.path));
  return new Set(newDoc.buildings.filter((b) => !had.has(b.path)).map((b) => b.path));
}

export function clawdTurn(rec, facing, leanDeg) {
  const y = Math.atan2(facing[0], facing[1]);
  const x = rec.pose === "peer" ? (leanDeg * Math.PI) / 180 : 0;
  return { x, y, order: "YXZ" };
}

export function siteExtent(sites, size) {
  const [gridW, gridH] = size;
  let maxX = gridW, maxZ = gridH;
  for (const site of sites || []) {
    maxX = Math.max(maxX, site.tile[0] + site.size);
    maxZ = Math.max(maxZ, site.tile[1] + site.size);
  }
  return { maxX, maxZ };
}

function siteOverflows(site, gridW, gridH) {
  const [tx, tz] = site.tile;
  return tz >= gridH || tx >= gridW;
}

export function siteBoxes(sites, size, T, pxPerUnit) {
  const [gridW, gridH] = size;
  const plots = [];
  let maxZ = gridH - 1, maxX = gridW - 1;
  for (let i = 0; i < sites.length; i++) {
    const site = sites[i];
    const [tx, tz] = site.tile;
    maxZ = Math.max(maxZ, tz + site.size - 1);
    maxX = Math.max(maxX, tx + site.size - 1);
    const w = T.width * site.size;
    const slabH = T.height_px / pxPerUnit;
    const frameH = T.frame_px / pxPerUnit;
    const f = T.frame;
    const cx = tx + site.size / 2, cz = tz + site.size / 2;
    plots.push([cx, slabH / 2, cz, w, slabH, w, "slab", i]);
    plots.push([cx, frameH / 2, cz + w / 2, w, frameH, f, "frame", i]);
    plots.push([cx, frameH / 2, cz - w / 2, w, frameH, f, "frame", i]);
    plots.push([cx + w / 2, frameH / 2, cz, f, frameH, w, "frame", i]);
    plots.push([cx - w / 2, frameH / 2, cz, f, frameH, w, "frame", i]);
  }
  const ground = new Set();
  if (sites.some((site) => siteOverflows(site, gridW, gridH))) {
    const xMax = Math.max(gridW - 1, maxX);
    for (let z = gridH; z <= maxZ; z++) {
      for (let x = 0; x <= xMax; x++) ground.add(`${x},${z}`);
    }
    for (const site of sites) {
      const [tx, tz] = site.tile;
      for (let dz = 0; dz < site.size; dz++) {
        for (let dx = 0; dx < site.size; dx++) {
          const x = tx + dx, z = tz + dz;
          if (x >= gridW || z >= gridH) ground.add(`${x},${z}`);
        }
      }
    }
  }
  return { plots, ground: [...ground].map((key) => key.split(",").map(Number)) };
}

export function scaffoldBoxes(b, halfW, S, roofPx, pxPerUnit) {
  const [x, z, size] = b.lot;
  const cx = x + size / 2, cz = z + size / 2;
  const bottom = b.tiers[0], top = b.tiers[b.tiers.length - 1];
  const side = bottom.half / halfW;
  const hPx = top.z1 + roofPx + S.over_px;
  const h = hPx / pxPerUnit;
  const n = Math.max(1, Math.round(hPx / S.rail_every_px));
  const off = side / 2 + S.gap;
  const poleX = [cx - off, cx + off], poleZ = [cz - off, cz + off];
  const boxes = [];
  for (const px of poleX) {
    for (const pz of poleZ) boxes.push([px, h / 2, pz, S.pole, h, S.pole]);
  }
  const span = side + 2 * S.gap + S.pole;
  for (let i = 1; i <= n; i++) {
    const y = (h * i) / n;
    boxes.push([cx, y, poleZ[0], span, S.rail, S.rail]);
    boxes.push([cx, y, poleZ[1], span, S.rail, S.rail]);
    boxes.push([poleX[0], y, cz, S.rail, S.rail, span]);
    boxes.push([poleX[1], y, cz, S.rail, S.rail, span]);
  }
  return boxes;
}
