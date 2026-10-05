"""Terminal output (ANSI colour, row diffing) and keyboard input."""

import os
import select
import shutil
import sys
import termios
import tty
from dataclasses import dataclass

PIXEL = "\u2588\u2588"  # two full blocks make one square pixel
_SKIP = object()
SYNC_BEGIN = "\x1b[?2026h"
SYNC_END = "\x1b[?2026l"
RESET = "\x1b[0m"

KEYMAP = {"w": "up", "a": "left", "s": "down", "d": "right",
          "e": "interact", " ": "interact", "\r": "interact", "\n": "interact",
          "q": "quit", "\x03": "quit"}
ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}


def rgb_to_256(c):
    r, g, b = (round(v / 255 * 5) for v in c)
    return 16 + 36 * r + 6 * g + b


_codes = {}


def color_code(c, truecolor):
    key = (c, truecolor)
    code = _codes.get(key)
    if code is None:
        if truecolor:
            r, g, b = c
            code = f"\x1b[38;2;{r};{g};{b}m"
        else:
            code = f"\x1b[38;5;{rgb_to_256(c)}m"
        _codes[key] = code
    return code


@dataclass(frozen=True)
class Overlay:
    x: float
    y: int
    text: str
    fg: tuple[int, int, int]
    bg: tuple[int, int, int]
    bold: bool = False


def pixel_col(x):
    return int(x * 2)


def _bg_code(c, truecolor):
    if truecolor:
        r, g, b = c
        return f"\x1b[48;2;{r};{g};{b}m"
    return f"\x1b[48;5;{rgb_to_256(c)}m"


def _style(fg, bg, bold, truecolor):
    bold_code = "\x1b[1m" if bold else ""
    return f"{bold_code}{color_code(fg, truecolor)}{_bg_code(bg, truecolor)}"


def _pixel_run_parts(row, truecolor):
    parts = []
    last = None
    for c in row:
        if c != last:
            parts.append(color_code(c, truecolor))
            last = c
        parts.append(PIXEL)
    return parts


def encode_row(row, truecolor):
    parts = _pixel_run_parts(row, truecolor)
    parts.append(RESET)
    return "".join(parts)


def compose_row(fb_row, overlays, truecolor):
    if not overlays:
        return encode_row(fb_row, truecolor)
    width = len(fb_row) * 2
    chars = [" "] * width
    for i, c in enumerate(fb_row):
        chars[i * 2:i * 2 + 2] = [PIXEL[0], PIXEL[1]]
    for ov in overlays:
        col = pixel_col(ov.x)
        style = _style(ov.fg, ov.bg, ov.bold, truecolor)
        n = min(len(ov.text), width - col)
        if n:
            chars[col] = f"{style}{ov.text[:n]}"
            for j in range(1, n):
                chars[col + j] = _SKIP
    end = 0
    for ov in overlays:
        end = max(end, pixel_col(ov.x) + len(ov.text))
    if end % 2 == 1 and end // 2 < len(fb_row):
        px = fb_row[end // 2]
        fill = f"{color_code(px, truecolor)}{PIXEL[0]}"
        if end < width:
            chars[end] = fill
    parts = []
    i = 0
    while i < width:
        if chars[i] is _SKIP:
            i += 1
        elif isinstance(chars[i], str) and len(chars[i]) > 1:
            parts.append(chars[i])
            i += 1
        else:
            run = []
            while i < width and chars[i] is not _SKIP and not (
                    isinstance(chars[i], str) and len(chars[i]) > 1):
                if i % 2 == 0:
                    run.append(fb_row[i // 2])
                i += 1
            if run:
                parts.extend(_pixel_run_parts(run, truecolor))
    parts.append(RESET)
    return "".join(parts)


class Screen:
    """Turns framebuffers into escape sequences, redrawing only changed rows."""

    def __init__(self, truecolor):
        self.truecolor = truecolor
        self.invalidate()

    def invalidate(self):
        self.prev_rows = []
        self.prev_status = []

    def frame(self, fb, status, overlays=()):
        by_row = {}
        for ov in overlays:
            by_row.setdefault(ov.y, []).append(ov)
        out = [SYNC_BEGIN]
        composed = []
        for y, row in enumerate(fb.rows):
            line = compose_row(row, by_row.get(y, ()), self.truecolor)
            composed.append(line)
            if y < len(self.prev_rows) and self.prev_rows[y] == line:
                continue
            out.append(f"\x1b[{y + 1};1H{line}")
        for i, line in enumerate(status):
            if i < len(self.prev_status) and self.prev_status[i] == line:
                continue
            out.append(f"\x1b[{fb.h + i + 1};1H{RESET}{line}{RESET}\x1b[K")
        self.prev_rows = composed
        self.prev_status = list(status)
        out.append(SYNC_END)
        return "".join(out)


def parse_keys(data, keymap=KEYMAP):
    keys = []
    i = 0
    while i < len(data):
        ch = data[i]
        if ch == "\x1b":
            if i + 2 < len(data) and data[i + 1] in "[O" and data[i + 2] in ARROWS:
                keys.append(ARROWS[data[i + 2]])
                i += 3
                continue
            j = i + 1
            if j < len(data) and data[j] in "[O":
                j += 1
                while j < len(data) and not ("\x40" <= data[j] <= "\x7e"):
                    j += 1
                j += 1
            i = j
            continue
        key = keymap.get(ch.lower())
        if key:
            keys.append(key)
        i += 1
    return keys


def supports_truecolor():
    return os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


class Terminal:
    """Alternate screen, hidden cursor, no echo, no line wrap; restored on exit."""

    def __enter__(self):
        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        self.write("\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J")
        return self

    def __exit__(self, *exc):
        self.write(f"{RESET}\x1b[?7h\x1b[?25h\x1b[?1049l")
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

    def write(self, s):
        sys.stdout.write(s)
        sys.stdout.flush()

    def read(self, timeout):
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return ""
        return os.read(self.fd, 1024).decode("utf-8", errors="ignore")

    @staticmethod
    def size():
        s = shutil.get_terminal_size((80, 24))
        return s.columns, s.lines
