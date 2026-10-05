#!/usr/bin/env python3
"""CodeTown: walk the Claude Code mascot around a tiny isometric town.

    python3 town.py            # auto-detects truecolor
    python3 town.py --256      # force 256-colour mode
"""

import signal
import sys
import textwrap
import time

import game
import render
import term
import world

FPS = 24
STATUS_LINES = 3
MIN_COLS, MIN_LINES = 40, 16

MSG_STYLE = "\x1b[1;38;5;230;48;5;58m"
HINT_STYLE = "\x1b[38;5;245m"
IDLE_TEXT = "Tokenville. Wander around, talk to villagers, read signs, knock on doors."
HINT_TEXT = "WASD / arrows: move (up = up-right)   E / space: talk & look   Q: quit"


def status_lines(g, cols):
    text = g.message or g.prompt() or IDLE_TEXT
    width = max(10, cols - 2)
    wrapped = (textwrap.wrap(text, width) + ["", ""])[:2]
    style = MSG_STYLE if g.message else HINT_STYLE
    lines = [f"{style} {w.ljust(width)} " if g.message else f"{style} {w}" for w in wrapped]
    lines.append(f"{HINT_STYLE} {HINT_TEXT[:width]}")
    return lines


def too_small(t, cols, lines):
    msg = f"Make the window at least {MIN_COLS}x{MIN_LINES} (bigger is nicer!)"
    t.write(f"\x1b[2J\x1b[{max(1, lines // 2)};1H{msg[:cols]}")


def run(truecolor):
    g = game.Game(world.load())
    screen = term.Screen(truecolor)
    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    with term.Terminal() as t:
        t.write("\x1b]0;CodeTown\x07")
        last = time.monotonic()
        timeout = 0.0
        cols = lines = 0
        while True:
            if resized[0]:
                resized[0] = False
                cols, lines = t.size()
                screen.invalidate()
                t.write("\x1b[2J")
                if cols < MIN_COLS or lines < MIN_LINES:
                    too_small(t, cols, lines)
            for key in term.parse_keys(t.read(timeout)):
                if key == "quit":
                    return
                if key == "interact":
                    g.interact()
                else:
                    g.press(key)
            now = time.monotonic()
            g.update(min(0.1, now - last))
            last = now
            if cols >= MIN_COLS and lines >= MIN_LINES:
                fb = render.render_scene(g, cols // 2, lines - STATUS_LINES)
                t.write(screen.frame(fb, status_lines(g, cols)))
            timeout = max(0.0, 1 / FPS - (time.monotonic() - now))


def main():
    truecolor = term.supports_truecolor() and "--256" not in sys.argv
    if "--truecolor" in sys.argv:
        truecolor = True
    if not sys.stdin.isatty():
        sys.exit("CodeTown needs an interactive terminal.")
    try:
        run(truecolor)
    except KeyboardInterrupt:
        pass
    print("Thanks for visiting Tokenville!")


if __name__ == "__main__":
    main()
