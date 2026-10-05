"""Render one frame to a PNG without a terminal: python3 snapshot.py out.png [options]."""

import argparse
import random
import struct
import zlib

import game
import render
import world


def write_png(path, fb, scale):
    raw = bytearray()
    for row in fb.rows:
        line = bytearray()
        for c in row:
            line += bytes(c) * scale
        for _ in range(scale):
            raw.append(0)
            raw += line

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    header = struct.pack(">IIBBBBB", fb.w * scale, fb.h * scale, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("--size", default="100x56", help="viewport in pixels, WxH")
    p.add_argument("--at", help="place Clawd at tile X,Y")
    p.add_argument("--facing", default="0,1")
    p.add_argument("--time", type=float, default=0.0)
    p.add_argument("--scale", type=int, default=6)
    args = p.parse_args()
    w, h = map(int, args.size.split("x"))
    g = game.Game(world.load(), rng=random.Random(1))
    if args.at:
        g.player.place(*map(int, args.at.split(",")))
    g.player.facing = tuple(map(int, args.facing.split(",")))
    g.update(args.time)
    write_png(args.out, render.render_scene(g, w, h), args.scale)


if __name__ == "__main__":
    main()
