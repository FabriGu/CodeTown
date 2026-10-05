import { test } from "node:test";
import assert from "node:assert/strict";
import { lanes, route, transit, stations } from "./transit.js";

const LOOK = { width: 0.08, casing: 0.02, spacing: 0.12, band: 0.9, fill: 0.75 };
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);
const nearPt = (p, q) => { near(p[0], q[0]); near(p[1], q[1]); };

test("lines sharing a street run side by side, centred and in line order", () => {
  const lane = lanes([
    { id: 0, line: 3, tiles: [[0, 0], [1, 0]] },
    { id: 1, line: 1, tiles: [[1, 0], [0, 0]] },
  ], LOOK);
  near(lane(1, [0, 0], [1, 0]).o, -0.06);
  near(lane(3, [1, 0], [0, 0]).o, 0.06);
});

test("roads of one line share its lane", () => {
  const lane = lanes([
    { id: 0, line: 2, tiles: [[0, 0], [1, 0], [2, 0]] },
    { id: 1, line: 2, tiles: [[0, 0], [1, 0], [1, 1]] },
  ], LOOK);
  near(lane(2, [0, 0], [1, 0]).o, 0);
});

test("a crowded street narrows its lanes to stay inside the band", () => {
  const roads = Array.from({ length: 30 }, (_, i) => ({ id: i, line: i, tiles: [[0, 0], [0, 1]] }));
  const lane = lanes(roads, LOOK);
  near(lane(29, [0, 0], [0, 1]).o - lane(0, [0, 0], [0, 1]).o, 0.9 * 29 / 30);
  assert.ok(lane(0, [0, 0], [0, 1]).w < LOOK.width);
});

test("a turn meets at the corner of its two lanes", () => {
  const segs = route([[0, 0], [1, 0], [1, 1]], (i) => ({ o: i === 0 ? 0.1 : -0.2, w: 1, cw: 1 }));
  assert.equal(segs.length, 2);
  nearPt(segs[0].a, [0.5, 0.6]);
  nearPt(segs[0].b, [1.3, 0.6]);
  nearPt(segs[1].b, [1.3, 1.5]);
});

test("changing lane on a straight is a 45 degree jog", () => {
  const segs = route([[0, 0], [1, 0], [2, 0]], (i) => ({ o: i === 0 ? 0 : 0.2, w: 1, cw: 1 }));
  assert.equal(segs.length, 3);
  const [x0, z0] = segs[1].a, [x1, z1] = segs[1].b;
  near(Math.abs(x1 - x0), Math.abs(z1 - z0));
});

test("every road gets a route and every end a station", () => {
  const roads = [
    { id: 0, line: 0, tiles: [[0, 0], [1, 0], [2, 0]] },
    { id: 1, line: 1, tiles: [[2, 0], [2, 1]] },
  ];
  assert.equal(transit(roads, LOOK).length, 2);
  const at = stations(roads).find((s) => `${s.tile}` === "2,0");
  assert.deepEqual(at.roads, [0, 1]);
});
