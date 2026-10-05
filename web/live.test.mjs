import { test } from "node:test";
import assert from "node:assert/strict";
import * as L from "./live.js";
import { SCAFFOLD, SITE, PX_PER_UNIT, ROOF_PX } from "./look.js";

const walker = { id: "a", pose: "walk", tile: [0, 0], facing: [1, 0], follow: 1, team: "world",
  path: [[0, 0], [1, 0], [2, 0]], path_i: 0, walk_t: 0, at: 10 };

test("offsetFor maps client seconds to server t", () => {
  const serverT = 100.5;
  const clientSeconds = 200.25;
  const offset = L.offsetFor(clientSeconds, serverT);
  assert.ok(Math.abs(clientSeconds - offset - serverT) < 1e-9);
});

test("a walk advances one tile per step_time from path_i + walk_t", () => {
  assert.deepEqual(L.walkPosition(walker, 10, 0.16), { x: 0.5, z: 0.5, facing: [1, 0], moving: true, step: 0 });
  const half = L.walkPosition(walker, 10.08, 0.16);
  assert.ok(Math.abs(half.x - 1.0) < 1e-9 && half.z === 0.5 && half.moving);
  const done = L.walkPosition(walker, 20, 0.16);
  assert.deepEqual(done, { x: 2.5, z: 0.5, facing: [1, 0], moving: false, step: 2 });
});

test("a walk resumes from walk_t", () => {
  const p = L.walkPosition({ ...walker, path_i: 1, walk_t: 0.5 }, 10, 0.16);
  assert.ok(Math.abs(p.x - 2.0) < 1e-9);
});

test("standing Clawds stand on their tile facing their way", () => {
  const p = L.walkPosition({ ...walker, pose: "idle", tile: [4, 7], facing: [0, 1] }, 99, 0.16);
  assert.deepEqual(p, { x: 4.5, z: 7.5, facing: [0, 1], moving: false, step: 0 });
});

test("hops fall 15, 8 then 4 px and stop", () => {
  const poses = { hop: { heights_px: [15, 8, 4], time: 0.15 }, hammer: { time: 0.5, bounces: 3, height_px: 3 } };
  const hop = { pose: "hop", at: 0 };
  assert.ok(Math.abs(L.poseLift(hop, 0.075, poses, 1) - 15) < 1e-9);
  assert.ok(Math.abs(L.poseLift(hop, 0.225, poses, 1) - 8) < 1e-9);
  assert.equal(L.poseLift(hop, 1.0, poses, 1), 0);
  assert.equal(L.poseLift({ pose: "hammer", at: 0 }, 0.6, poses, 1), 0);
  assert.ok(L.poseLift({ pose: "hammer", at: 0 }, 0.08, poses, 1) > 0);
});

test("a dropping building starts 48 px up and lands at 0.42 s", () => {
  const drop = { height_px: 48, time: 0.42 };
  assert.equal(L.dropLift(0, drop, 1), 48);
  assert.equal(L.dropLift(0.42, drop, 1), 0);
  assert.ok(L.dropLift(0.21, drop, 1) > 0 && L.dropLift(0.21, drop, 1) < 48);
});

test("state then ticks keep a map of records stamped with their time", () => {
  let live = L.applyState({ t: 1, version: 1, clawds: [walker], scaffold: {}, sites: [], flags: [], status: ["a", ""], camera: null });
  assert.equal(live.clawds.get("a").at, 1);
  live = L.applyTick(live, { t: 2, clawds: [{ ...walker, pose: "idle" }], camera: "a" });
  assert.equal(live.clawds.get("a").pose, "idle");
  assert.equal(live.clawds.get("a").at, 2);
  assert.equal(live.camera, "a");
  live = L.applyTick(live, { t: 3, gone: ["a"], status: ["b", ""] });
  assert.equal(live.clawds.size, 0);
  assert.deepEqual(live.status, ["b", ""]);
});

test("keys: digits follow, 0 is auto, moving the camera pauses, a gone Clawd ends a follow", () => {
  const live = L.applyState({ t: 0, version: 1, clawds: [walker], scaffold: {}, sites: [], flags: [], status: ["", ""], camera: "a" });
  assert.deepEqual(L.pressKey(L.AUTO, "1", live), L.follow(1));
  assert.deepEqual(L.pressKey(L.AUTO, "2", live), L.AUTO);
  assert.deepEqual(L.pressKey(L.follow(1), "0", live), L.AUTO);
  assert.deepEqual(L.userMoved(L.AUTO), L.PAUSED);
  assert.deepEqual(L.userMoved(L.follow(1)), L.PAUSED);
  assert.deepEqual(L.pressKey(L.PAUSED, "0", live), L.AUTO);
  assert.equal(L.cameraClawd(L.AUTO, live).id, "a");
  assert.equal(L.cameraClawd(L.follow(1), live).id, "a");
  assert.equal(L.cameraClawd(L.PAUSED, live), null);
  const empty = L.applyTick(live, { t: 1, gone: ["a"] });
  assert.deepEqual(L.settle(L.follow(1), empty), L.AUTO);
});

test("the legend lists follow numbers and the mode", () => {
  const live = L.applyState({ t: 0, version: 1, clawds: [walker, { ...walker, id: "b", follow: 2, team: "render" }, { ...walker, id: "o", follow: null, team: null }], scaffold: {}, sites: [], flags: [], status: ["", ""], camera: null });
  assert.equal(L.legend(live, L.AUTO),
    "0 auto  1 world  2 render  ·  drag orbit  scroll zoom  click inspect  Esc clear   [auto]");
  assert.ok(L.legend(live, L.follow(2)).endsWith("[following 2]"));
  assert.ok(L.legend(live, L.PAUSED).endsWith("[paused, 0 resumes]"));
});

test("labels fade between start and end", () => {
  const fade = { start: 30, end: 60 };
  assert.equal(L.labelOpacity(10, fade), 1);
  assert.equal(L.labelOpacity(45, fade), 0.5);
  assert.equal(L.labelOpacity(90, fade), 0);
});

test("the 8 scaffolded buildings nearest the target", () => {
  const centres = new Map(Array.from({ length: 10 }, (_, i) => [`p${i}`, [i, 0]]));
  const scaffold = Object.fromEntries([...centres.keys()].map((p) => [p, 0]));
  assert.deepEqual(L.nearestScaffold(scaffold, centres, [9, 0]), ["p9", "p8", "p7", "p6", "p5", "p4", "p3", "p2"]);
  assert.deepEqual(L.nearestScaffold({ missing: 0 }, centres, [0, 0]), []);
});

test("new buildings are the paths the old town didn't have", () => {
  const old = { buildings: [{ path: "a" }] }, now = { buildings: [{ path: "a" }, { path: "b" }] };
  assert.deepEqual([...L.newBuildings(old, now)], ["b"]);
});

test("clawdTurn peers lean forward in the YXZ frame", () => {
  const lean = 18;
  const peer = L.clawdTurn({ pose: "peer" }, [1, 0], lean);
  assert.ok(peer.x > 0);
  assert.equal(peer.order, "YXZ");
  const idle = L.clawdTurn({ pose: "idle" }, [1, 0], lean);
  assert.equal(idle.x, 0);
  assert.equal(idle.order, "YXZ");
  assert.ok(Math.abs(L.clawdTurn({ pose: "idle" }, [1, 0], lean).y - Math.PI / 2) < 1e-9);
  assert.ok(Math.abs(L.clawdTurn({ pose: "idle" }, [0, 1], lean).y) < 1e-9);
  assert.ok(Math.abs(L.clawdTurn({ pose: "idle" }, [-1, 0], lean).y + Math.PI / 2) < 1e-9);
  assert.ok(Math.abs(L.clawdTurn({ pose: "idle" }, [0, -1], lean).y - Math.PI) < 1e-9);
});

test("peer lean tilts up toward +x for an east-facing Clawd", () => {
  const x = (18 * Math.PI) / 180, y = Math.PI / 2;
  const sinX = Math.sin(x), cosX = Math.cos(x), sinY = Math.sin(y), cosY = Math.cos(y);
  const upY = cosX, upZ = sinX;
  const upX = sinY * upZ, upZ2 = cosY * upZ;
  assert.ok(upX > 0, "lean should push the top toward +x when facing east");
  assert.ok(Math.abs(upZ2) < 1e-9, "lean should not push the top along z when facing east");
});

function assertScaffold(b, halfW) {
  const boxes = L.scaffoldBoxes(b, halfW, SCAFFOLD, ROOF_PX, PX_PER_UNIT);
  const [x, z, size] = b.lot;
  const cx = x + size / 2, cz = z + size / 2;
  const bottom = b.tiers[0], top = b.tiers[b.tiers.length - 1];
  const side = bottom.half / halfW;
  const hPx = top.z1 + ROOF_PX + SCAFFOLD.over_px;
  const h = hPx / PX_PER_UNIT;
  const n = Math.max(1, Math.round(hPx / SCAFFOLD.rail_every_px));
  const poles = boxes.filter(([, , , sx, sy, sz]) => sx === SCAFFOLD.pole && sz === SCAFFOLD.pole);
  const rails = boxes.filter(([, , , sx, sy, sz]) => sy === SCAFFOLD.rail);
  assert.equal(poles.length, 4);
  assert.equal(rails.length, 4 * n);
  for (const [px, , pz, sx, sy, sz] of poles) {
    assert.ok(Math.abs(px - cx) - sx / 2 >= side / 2 - 1e-9);
    assert.ok(Math.abs(pz - cz) - sz / 2 >= side / 2 - 1e-9);
    assert.ok(sy > (top.z1 + ROOF_PX) / PX_PER_UNIT);
    assert.ok(Math.abs(sy - h) < 1e-9);
  }
  const railYs = [...new Set(rails.map(([, y]) => y))].sort((a, b) => a - b);
  assert.ok(railYs[0] > 0);
  assert.ok(Math.abs(railYs[railYs.length - 1] - h) < 1e-9);
  const span = side + 2 * SCAFFOLD.gap + SCAFFOLD.pole;
  for (const [, , , sx, , sz] of rails) {
    assert.ok(Math.max(sx, sz) + 1e-9 >= span);
    assert.ok(Math.max(sx, sz) + 1e-9 >= side);
  }
}

test("scaffoldBoxes stands outside a one-tile building", () => {
  assertScaffold({ lot: [4, 13, 1], tiers: [{ half: 6, z0: 0, z1: 2 }] }, 6);
});

test("scaffoldBoxes rings a taller multi-tier building", () => {
  assertScaffold({
    lot: [10, 10, 3],
    tiers: [{ half: 18, z0: 0, z1: 12 }, { half: 12, z0: 12, z1: 24 }],
  }, 6);
});

test("siteBoxes gives no overflow ground for an in-grid site", () => {
  const { plots, ground } = L.siteBoxes(
    [{ tile: [10, 10], size: 1, scarf: 0 }], [65, 93], SITE, PX_PER_UNIT);
  assert.equal(ground.length, 0);
  assert.equal(plots.filter((p) => p[6] === "slab").length, 1);
});

test("siteBoxes lays ground for sites past the town front", () => {
  const size = [65, 93];
  const { ground } = L.siteBoxes([{ tile: [20, 94], size: 1, scarf: 0 }], size, SITE, PX_PER_UNIT);
  assert.equal(ground.length, 65 * 2);
  assert.ok(ground.every(([x, z]) => x >= 0 && x < 65 && z >= 93 && z <= 94));
});

test("siteBoxes keeps slabs flat and frames above them within the tile", () => {
  const site = { tile: [20, 94], size: 1, scarf: 0 };
  const { plots } = L.siteBoxes([site], [65, 93], SITE, PX_PER_UNIT);
  const [tx, tz] = site.tile;
  const slab = plots.find((p) => p[6] === "slab");
  const frames = plots.filter((p) => p[6] === "frame");
  const slabTopPx = (slab[1] + slab[4] / 2) * PX_PER_UNIT;
  assert.ok(slabTopPx <= 1 + 1e-9);
  for (const frame of frames) {
    const topPx = (frame[1] + frame[4] / 2) * PX_PER_UNIT;
    assert.ok(topPx > slabTopPx);
    assert.ok(topPx <= 2 + 1e-9);
    assert.ok(frame[0] - frame[3] / 2 >= tx - 1e-9);
    assert.ok(frame[0] + frame[3] / 2 <= tx + site.size + 1e-9);
    assert.ok(frame[2] - frame[5] / 2 >= tz - 1e-9);
    assert.ok(frame[2] + frame[5] / 2 <= tz + site.size + 1e-9);
  }
});
