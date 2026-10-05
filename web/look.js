// How the 3D town looks: every colour, size and camera setting. This is the designer's file.
// Colours are [r, g, b] from 0 to 255, starting from drawtown's palette. Heights in px are the
// pixel town's; PX_PER_UNIT turns them into tiles. town3d.js names any key it needs that's
// missing here, so a restyle that drops one fails loudly.

// iso.TILE_W / √2: a tower is as tall, for its footprint, as in the pixel town.
export const PX_PER_UNIT = 12 / Math.SQRT2;
export const BACKGROUND = [30, 66, 112];
// How bright each face of every box is, like drawtown's tier walls. +Z is the pixel town's
// left wall and +X its right; the other two only show when you orbit round.
export const FACES = { top: 1.08, bottom: 0.5, pz: 0.95, px: 0.74, nz: 0.86, nx: 0.66 };

export const GROUND = {
  grass: [86, 156, 70], water: [60, 124, 196], quay: [150, 112, 74], dock: [150, 112, 74],
  street: [164, 160, 166], avenue: [148, 144, 149], lot: [178, 142, 98],
  plot: [124, 152, 122], vacant: [170, 134, 92], site: [232, 128, 48],
};
export const TILE_THICKNESS = 0.2;
export const WATER_DROP = 0.12;
export const TREE = {
  trunk: [122, 82, 50], leaves: [[60, 128, 58], [70, 140, 62], [52, 116, 52]],
  trunk_width: 0.14, trunk_height: 0.35, crown: 0.55,
};

export const WALLS = [[222, 208, 182], [210, 200, 186], [218, 196, 170], [200, 192, 180]];
export const ALTERNATE_SHADE = 0.84;
export const AMBER = [236, 160, 40];
export const ROOFS = [[84, 108, 150], [150, 92, 76], [88, 132, 102], [132, 104, 156],
  [160, 138, 84], [80, 132, 140], [152, 102, 124], [112, 112, 124]];
export const ROOF_PX = 2;
export const FOCUS_ROOF = [250, 250, 250];
export const GLASS = { lit: [240, 212, 140], dark: [46, 52, 70], door: [100, 62, 40], board: [138, 98, 62] };
export const WINDOW = {
  width: 0.16, depth: 0.03, spacing: 0.32, margin: 0.12,
  height_px: 2, row_gap_px: 2, bottom_px: 2, top_px: 1,
};
export const WEED = { colour: [70, 120, 52], size: 0.08, count: 14 };
export const FIRE = {
  flames: [[255, 214, 90], [255, 140, 40], [255, 72, 32]], smoke: [92, 92, 100],
  cubes: 12, size: 0.16, speed: 0.6, flame_rise: 0.9, smoke_rise: 2.2,
};

export const WAREHOUSE = { wall: [122, 136, 152], roof: [86, 92, 104], height_px: 9, footprint: 0.9 };

export const ROADS = {
  road: [82, 84, 96], highway: [58, 60, 70], uses: [80, 168, 255], "used by": [236, 96, 196],
  backwards: [232, 112, 36], cycle: [214, 46, 46],
};
export const ROAD_LIFT = 0.012;
// Every import is always drawn, as a transit map after Vignelli's subway diagram: each building's
// roads are one line in one of LINES (no reds or oranges, which mean cycle and backwards), on a
// pale casing that keeps lines sharing a street apart. Sizes are in tiles; band is how much of a
// street a bundle may fill, fill how much of its lane a line takes once a street gets crowded.
// When something is selected, every road that isn't its own moves dim of the way to grey.
export const LINES = [[0, 57, 166], [0, 147, 60], [252, 204, 10], [185, 51, 173], [0, 161, 222],
  [153, 102, 51], [108, 190, 69], [0, 98, 100], [120, 80, 200], [196, 160, 0]];
export const TRANSIT = {
  width: 0.1, casing: 0.025, spacing: 0.14, band: 0.92, fill: 0.78,
  casing_colour: [246, 244, 238], grey: [150, 150, 156], dim: 0.72,
  station: 0.3, ring: 0.07, station_colour: [252, 252, 250], ring_colour: [30, 30, 34],
};
// The finished picture goes through an ordered dither on a coarse grid, like the terminal
// town's half-block pixels. pixel is in CSS pixels; levels is shades per colour channel.
export const DITHER = { pixel: 1, levels: 12, strength: 1 };

// Distances are in tiles; start and max are multiples of the town's longer side.
export const CAMERA = {
  fov: 35, elevation_deg: 35, azimuth_deg: 45, start_distance: 1.2,
  min_distance: 3, max_distance: 3, max_polar_deg: 85,
  follow_ease: 2.5, follow_distance: 18,
};

export const LABEL = { fade: { start: 30, end: 70 }, lift: 0.35, max_scaffold: 8 };

// Watch. SCARVES are watch's team palette, in the order watch.json assigns them.
export const SCARVES = [[165, 91, 91], [140, 113, 35], [165, 165, 74], [85, 89, 49],
  [103, 165, 41], [27, 89, 22], [49, 140, 49], [91, 165, 103]];
// A Clawd is boxes in voxels: [x, y, z, width, height, depth, part], feet at y = 0, facing +z.
export const CLAWD = {
  voxel: 0.08,
  colours: { body: [217, 119, 87], dark: [178, 92, 64], eyes: [28, 24, 22],
    reviewer: [150, 150, 156], glasses: [30, 26, 24], hat: [60, 60, 70] },
  body: [[0, 5, 0, 7, 2, 4, "body"], [0, 3.5, 0, 9, 1, 4, "body"], [0, 2.5, 0, 7, 1, 4, "dark"],
    [-1.5, 5.3, 2.05, 1, 1, 0.1, "eyes"], [1.5, 5.3, 2.05, 1, 1, 0.1, "eyes"]],
  legs: [
    [[-3, 1, 0, 1, 2, 1, "dark"], [-1, 1, 0, 1, 2, 1, "dark"], [1, 1, 0, 1, 2, 1, "dark"], [3, 1, 0, 1, 2, 1, "dark"]],
    [[-3, 1, 0, 1, 2, 1, "dark"], [-1, 1.5, 0, 1, 1, 1, "dark"], [1, 1, 0, 1, 2, 1, "dark"], [3, 1.5, 0, 1, 1, 1, "dark"]],
    [[-3, 1.5, 0, 1, 1, 1, "dark"], [-1, 1, 0, 1, 2, 1, "dark"], [1, 1.5, 0, 1, 1, 1, "dark"], [3, 1, 0, 1, 2, 1, "dark"]],
  ],
  scarf: [[0, 4.2, 0, 7.4, 0.6, 4.4, "scarf"], [2.4, 3.4, 2.3, 1, 1.4, 0.3, "scarf"]],
  glasses: [[-1.5, 5.3, 2.15, 1.6, 1.4, 0.12, "glasses"], [1.5, 5.3, 2.15, 1.6, 1.4, 0.12, "glasses"],
    [0, 5.5, 2.15, 1.4, 0.3, 0.12, "glasses"]],
  hat: [[0, 6.5, 0, 5, 1, 3.6, "hat"], [0, 7.5, 0, 3.4, 1, 2.6, "hat"], [0, 8.4, 0, 2, 0.8, 1.6, "hat"],
    [0, 9.1, 0, 0.8, 0.6, 0.8, "hat"]],
  bob_px: 1,
};
export const POSES = { hammer: { time: 0.5, bounces: 3, height_px: 3 },
  hop: { heights_px: [15, 8, 4], time: 0.15 }, peer: { lean_deg: 18 } };
export const SCAFFOLD = { pole: 0.12, rail: 0.08, rail_every_px: 6, gap: 0.06, over_px: 3 };
export const SITE = { colour: [232, 128, 48], width: 0.7, height_px: 0.5, frame: 0.05, frame_px: 1.5 };
export const FLAG = { pole: [220, 220, 228], pole_height: 1.1, pole_width: 0.04,
  cloth_width: 0.36, cloth_height: 0.22 };
export const LECTERN = { colour: [120, 90, 60], width: 0.42, height: 0.55, top: 0.12 };
export const DROP = { height_px: 48, time: 0.42 };
