// Roads drawn as a transit map, after Vignelli's subway diagram: every building's roads are one
// line, lines sharing a street run side by side in a fixed order instead of on top of each other,
// and a line only turns square or jogs across at 45 degrees. Pure: road tiles in, flat segments
// out, in tile units, so it can be tested without a browser.

const edgeKey = (a, b) => (a[0] < b[0] || (a[0] === b[0] && a[1] < b[1])) ? `${a}|${b}` : `${b}|${a}`;

// Which way a lane moves sideways on the street edge a->b: across the direction of travel.
const across = (a, b) => (b[0] !== a[0] ? [0, 1] : [1, 0]);

// Each line's lane on every street edge: its place among the lines there, centred on the street.
// A crowded street narrows its lanes so the bundle never spills past the band.
export function lanes(roads, look) {
  const lines = new Map();
  for (const r of roads) {
    for (let i = 0; i + 1 < r.tiles.length; i++) {
      const key = edgeKey(r.tiles[i], r.tiles[i + 1]);
      const here = lines.get(key) || new Set();
      here.add(r.line);
      lines.set(key, here);
    }
  }
  const found = new Map();
  for (const [key, here] of lines) {
    const order = [...here].sort((a, b) => a - b);
    const step = Math.min(look.spacing, look.band / order.length);
    const w = Math.min(look.width, step * look.fill);
    const cw = Math.min(w + 2 * look.casing, step);
    order.forEach((line, rank) =>
      found.set(`${line}@${key}`, { o: (rank - (order.length - 1) / 2) * step, w, cw }));
  }
  return (line, a, b) => found.get(`${line}@${edgeKey(a, b)}`);
}

// One road as straight segments, each with the line width and casing width of its lane. Turns
// meet at the corner of the two lanes; a change of lane on a straight is a 45 degree jog.
export function route(tiles, lane) {
  const n = tiles.length;
  if (n < 2) return [];
  const centre = (t) => [t[0] + 0.5, t[1] + 0.5];
  const shift = (c, d, o) => [c[0] + d[0] * o, c[1] + d[1] * o];
  const segments = [];
  const go = (to, l) => {
    segments.push({ a: from, b: to, w: l.w, cw: l.cw });
    from = to;
  };
  let from = shift(centre(tiles[0]), across(tiles[0], tiles[1]), lane(0).o);
  for (let i = 1; i + 1 < n; i++) {
    const inn = lane(i - 1), out = lane(i);
    const dIn = across(tiles[i - 1], tiles[i]), dOut = across(tiles[i], tiles[i + 1]);
    const c = centre(tiles[i]);
    if (dIn[0] !== dOut[0]) {
      go([c[0] + dIn[0] * inn.o + dOut[0] * out.o, c[1] + dIn[1] * inn.o + dOut[1] * out.o], inn);
    } else if (Math.abs(out.o - inn.o) > 1e-9) {
      const along = [tiles[i + 1][0] - tiles[i - 1][0], tiles[i + 1][1] - tiles[i - 1][1]]
        .map((v) => Math.sign(v));
      const half = Math.abs(out.o - inn.o) / 2;
      go(shift(shift(c, dIn, inn.o), along, -half), inn);
      go(shift(shift(c, dIn, out.o), along, half), { w: Math.min(inn.w, out.w), cw: Math.min(inn.cw, out.cw) });
    }
  }
  go(shift(centre(tiles[n - 1]), across(tiles[n - 2], tiles[n - 1]), lane(n - 2).o), lane(n - 2));
  return segments;
}

export function transit(roads, look) {
  const lane = lanes(roads, look);
  return roads.map((r) => route(r.tiles, (i) => lane(r.line, r.tiles[i], r.tiles[i + 1])));
}

// Where roads end: one station per building front or dock, drawn once however many lines stop.
export function stations(roads) {
  const found = new Map();
  for (const r of roads) {
    for (const t of [r.tiles[0], r.tiles.at(-1)]) {
      if (!t) continue;
      const here = found.get(`${t}`) || { tile: t, roads: [] };
      here.roads.push(r.id);
      found.set(`${t}`, here);
    }
  }
  return [...found.values()];
}
