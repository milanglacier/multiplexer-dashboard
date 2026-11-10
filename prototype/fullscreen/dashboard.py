#!/usr/bin/env python3
"""Fullscreen prototype of the dashboard, layout A, in stdlib Python without
curses.

Draws on the alternate screen with raw escape sequences: 24-bit Rose Pine
colors (light or dark, from the terminal's background color), synchronized
output, line-by-line redraws, SGR mouse input and centered dialogs over a
dimmed screen. Mock data only; actions show the command the real app would
run, and the list is printed on exit.

    python3 dashboard.py [--context outside|tmux|zellij|herdr|nested]
                         [--theme auto|light|dark] [--no-bg]

Keys: j/k or arrows move, Alt+j/k (or Alt+arrows) jump between
multiplexers, Tab switches lists, Enter switches, / filters,
n new, r rename, x kill, ? help, q quits. Prototype only: C cycles the
context, T toggles the theme. Mouse: click selects, a second click switches,
the wheel scrolls.
"""

import argparse
import os
import re
import select
import signal
import sys
import termios
import time
import tty
import unicodedata

# ---------------------------------------------------------------- mock data

DATA = {
    "zellij": [
        dict(name="dotfiles", tabs=["dotfiles", "dotfiles/config"], cwd="~/Desktop/dotfiles", age="3h"),
        dict(name="duanyan-tui", tabs=["duanyan-tui", "duanyan-tui/crates"], cwd="~/Desktop/personal-projects/duanyan-tui", age="1d"),
        dict(name="pi-mono", tabs=["pi-mono"], cwd="~/Desktop/personal-projects/pi-mono", age="20m"),
        dict(name="old-notes", tabs=[], cwd="~/notes", age="6d", exited=True),
    ],
    "herdr": [
        dict(name="agent-scratch", id="w4R", tabs=["1"], cwd="~/Desktop/personal-projects/agent-scratch", age="2h"),
        dict(name="multiplexer-dashboard", id="w53", tabs=["1", "2"], cwd="~/Desktop/personal-projects/multiplexer-dashboard", age="1h"),
        dict(name="herdr", id="w60", tabs=["1"], cwd="~/Desktop/personal-projects/herdr", age="4d"),
    ],
    "tmux": [
        dict(name="~", tabs=["zsh", "btop"], cwd="~", age="2d", attached=True),
        dict(name="scratch", tabs=["zsh"], cwd="~", age="5h"),
        dict(name="monopi", tabs=["nvim", "pi", "zsh"], cwd="~/Desktop/personal-projects/monopi", age="40m"),
    ],
}
AGENTS = [
    dict(mux="zellij", session="dotfiles", tab="dotfiles", pane="terminal_2", name="claude"),
    dict(mux="zellij", session="duanyan-tui", tab="duanyan-tui", pane="terminal_1", name="claude"),
    dict(mux="zellij", session="duanyan-tui", tab="duanyan-tui/crates", pane="terminal_5", name="codex"),
    dict(mux="herdr", session="multiplexer-dashboard", tab="1", pane="w53:pB", name="claude", status="working"),
    dict(mux="herdr", session="herdr", tab="1", pane="w60:p2", name="opencode", status="idle"),
    dict(mux="herdr", session="agent-scratch", tab="1", pane="w4R:p1", name="pi", status="blocked"),
    dict(mux="tmux", session="monopi", tab="2:pi", pane="%7", name="pi"),
    dict(mux="tmux", session="~", tab="1:zsh", pane="%2", name="gemini"),
]
# key: (label, listed multiplexers in order, current session per multiplexer)
CONTEXTS = [
    ("outside", "outside any multiplexer", ["zellij", "herdr", "tmux"], {}),
    ("tmux", "in tmux", ["tmux"], {"tmux": "~"}),
    ("zellij", "in zellij", ["zellij"], {"zellij": "dotfiles"}),
    ("herdr", "in herdr", ["herdr"], {"herdr": "multiplexer-dashboard"}),
    ("nested", "zellij in tmux", ["zellij", "tmux"], {"zellij": "dotfiles", "tmux": "~"}),
]

# ---------------------------------------------------------------- theme

# Rose Pine and Rose Pine Dawn, as in the herdr config.
PALETTES = {
    "dark": dict(base="#191724", surface="#1f1d2e", overlay="#26233a", muted="#6e6a86", subtle="#908caa",
                 text="#e0def4", love="#eb6f92", gold="#f6c177", rose="#ebbcba", pine="#31748f",
                 foam="#9ccfd8", iris="#c4a7e7", hl_low="#21202e", hl_med="#403d52", hl_high="#524f67"),
    "light": dict(base="#faf4ed", surface="#fffaf3", overlay="#f2e9e1", muted="#9893a5", subtle="#797593",
                  text="#575279", love="#b4637a", gold="#ea9d34", rose="#d7827e", pine="#286983",
                  foam="#56949f", iris="#907aa9", hl_low="#f4ede8", hl_med="#dfdad9", hl_high="#cecacd"),
}


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


class Theme:
    def __init__(self, dark, dim=0.0):
        colors = {k: hexrgb(v) for k, v in PALETTES["dark" if dark else "light"].items()}
        if dim:
            # Behind a dialog: every color fades toward the background.
            colors = {k: v if k == "base" else mix(v, colors["base"], dim) for k, v in colors.items()}
        self.__dict__.update(colors)
        self.dark, self.dimmed = dark, dim > 0

    def mux(self, name):
        return {"zellij": self.foam, "herdr": self.iris, "tmux": self.rose}[name]

    def agent(self, name):
        return {"claude": self.gold, "codex": self.foam, "opencode": self.iris, "pi": self.rose}.get(name, self.pine)


# ---------------------------------------------------------------- painting

RESET = "\x1b[0m"
_DEFAULT = object()


class Canvas:
    """Settings that every paint call reads: the theme and whether the app
    paints its own background."""
    theme = Theme(True)
    paint_bg = True


def sgr(fg=None, bg=None, bold=False, dim=False, italic=False, underline=False):
    codes = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if italic:
        codes.append("3")
    if underline:
        codes.append("4")
    if fg is not None:
        codes.append("38;2;%d;%d;%d" % fg)
    if bg is not None:
        codes.append("48;2;%d;%d;%d" % bg)
    return "\x1b[" + ";".join(codes) + "m" if codes else ""


def paint(text, fg=None, bg=_DEFAULT, **kw):
    if not text:
        return ""
    if bg is _DEFAULT:
        bg = Canvas.theme.base if Canvas.paint_bg else None
    pre = sgr(fg, bg, **kw)
    return pre + text + RESET if pre else text


class Pen:
    """Paints segments on one background, such as a selected row's."""

    def __init__(self, bg=_DEFAULT):
        self.bg = bg

    def __call__(self, text, fg=None, **kw):
        kw.setdefault("bg", self.bg)
        return paint(text, fg, **kw)


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def cell_width(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def width(s):
    return sum(cell_width(c) for c in ANSI_RE.sub("", s))


def cut(s, start, end=None):
    """The cells start..end of a painted string, with the colors in effect at
    start carried over."""
    out, active, n, i, started = [], "", 0, 0, False
    while i < len(s):
        m = ANSI_RE.match(s, i)
        if m:
            seq = m.group()
            i = m.end()
            if seq.endswith("m"):
                active = "" if seq in (RESET, "\x1b[m") else active + seq
                if started:
                    out.append(seq)
            continue
        cw = cell_width(s[i])
        if end is not None and n + cw > end:
            break
        if n >= start:
            if not started:
                out.append(active)
                started = True
            out.append(s[i])
        n += cw
        i += 1
    return "".join(out) + RESET


def fit(s, w, pen=None):
    """Truncates or pads a painted string to exactly w cells."""
    pen = pen or Pen()
    if w <= 0:
        return ""
    if width(s) > w:
        s = cut(s, 0, w - 1) + pen("…", Canvas.theme.muted)
    return s + pen(" " * (w - width(s)))


def lr(left, right, w, pen=None):
    rw = width(right)
    return fit(right, w, pen) if rw >= w else fit(left, w - rw, pen) + right


def overlay(base, x, s):
    return cut(base, 0, x) + s + cut(base, x + width(s))


def gradient(text, c1, c2, fg):
    n = max(1, len(text) - 1)
    return "".join(paint(ch, fg, mix(c1, c2, i / n), bold=True) for i, ch in enumerate(text))


def raw(line):
    """A captured pane line (with its own escape sequences) on the app's
    background, faded when the screen is dimmed."""
    t = Canvas.theme
    pre = (sgr(bg=t.base) if Canvas.paint_bg else "") + ("\x1b[2m" if t.dimmed else "")
    return pre + line.replace(RESET, RESET + pre) + RESET


def plural(n, unit):
    return f"{n} {unit}" + ("" if n == 1 else "s")


# ---------------------------------------------------------------- terminal


class Term:
    """Raw mode, the alternate screen, mouse reporting and a line-diffing
    renderer, all on /dev/tty."""

    def __init__(self):
        self.fd = os.open("/dev/tty", os.O_RDWR)
        self.saved = termios.tcgetattr(self.fd)
        self.prev = []

    def write(self, s):
        os.write(self.fd, s.encode())

    def __enter__(self):
        tty.setraw(self.fd)
        # Alternate screen, hidden cursor, button and wheel mouse in SGR form.
        self.write("\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1006h")
        return self

    def __exit__(self, *exc):
        self.write("\x1b[?1006l\x1b[?1000l\x1b[0m\x1b[?25h\x1b[?1049l")
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

    def size(self):
        sz = os.get_terminal_size(self.fd)
        return sz.columns, sz.lines

    def background_is_dark(self):
        """Asks the terminal for its background color (OSC 11). None when it
        does not answer."""
        self.write("\x1b]11;?\x1b\\")
        buf, deadline = b"", time.monotonic() + 0.25
        while time.monotonic() < deadline:
            r, _, _ = select.select([self.fd], [], [], deadline - time.monotonic())
            if not r:
                break
            buf += os.read(self.fd, 256)
            if buf.endswith((b"\x07", b"\x1b\\")):
                break
        m = re.search(rb"rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)", buf)
        if not m:
            return None
        r, g, b = (int(x, 16) / (16 ** len(x) - 1) for x in m.groups())
        return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5

    def invalidate(self):
        self.prev = []

    def draw(self, lines):
        # Synchronized output keeps the terminal from showing half a frame.
        out = ["\x1b[?2026h"]
        if len(self.prev) != len(lines):
            out.append("\x1b[0m\x1b[2J")
            self.prev = []
        for y, line in enumerate(lines):
            if y >= len(self.prev) or self.prev[y] != line:
                out.append(f"\x1b[{y + 1};1H{line}{RESET}")
        out.append("\x1b[?2026l")
        self.write("".join(out))
        self.prev = lines

    def events(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return []
        data = os.read(self.fd, 4096).decode("utf-8", "replace")
        evs, i = [], 0
        while i < len(data):
            m = MOUSE_RE.match(data, i)
            if m:
                b, x, y, kind = int(m[1]), int(m[2]) - 1, int(m[3]) - 1, m[4]
                if kind == "M":
                    evs.append(("mouse", b & ~0b11100, x, y))
                i = m.end()
                continue
            m = KEY_SEQ_RE.match(data, i)
            seq = m.group() if m else data[i]
            i = m.end() if m else i + 1
            evs.append(("key", key_name(seq)))
        return evs


def key_name(seq):
    if seq in KEY_NAMES:
        return KEY_NAMES[seq]
    m = MOD_KEY_RE.fullmatch(seq)
    if m:
        # xterm modifier parameter: 1 + shift(1) + alt(2) + ctrl(4).
        bits = int(m[1]) - 1
        mods = [n for b, n in ((4, "ctrl"), (2, "alt"), (1, "shift")) if bits & b]
        base = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end"}[m[2]]
        return "+".join(mods + [base])
    if len(seq) == 2 and seq[0] == "\x1b":
        # ESC before a key is how terminals send Alt with that key.
        return "alt+" + KEY_NAMES.get(seq[1], seq[1])
    return seq


MOUSE_RE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
# A lone ESC is the Escape key; ESC followed by [ or O starts a sequence,
# and ESC followed by any other key is Alt with that key.
KEY_SEQ_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z~]|\x1bO[A-Za-z]|\x1b[\s\S]")
# Modified arrows and Home/End, such as ESC [ 1 ; 3 A for Alt+Up.
MOD_KEY_RE = re.compile(r"\x1b\[1;(\d+)([A-DHF])")
KEY_NAMES = {
    "\x1b[A": "up", "\x1bOA": "up", "\x1b[B": "down", "\x1bOB": "down",
    "\x1b[C": "right", "\x1bOC": "right", "\x1b[D": "left", "\x1bOD": "left",
    "\x1b[H": "home", "\x1b[1~": "home", "\x1b[F": "end", "\x1b[4~": "end",
    "\x1b[5~": "pgup", "\x1b[6~": "pgdown", "\t": "tab", "\x1b[Z": "shift+tab",
    "\r": "enter", "\n": "enter", "\x7f": "backspace", "\x08": "backspace", "\x1b": "esc",
    "\x03": "ctrl+c", "\x15": "ctrl+u", "\x0e": "down", "\x10": "up",
}

# ---------------------------------------------------------------- app

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
UNSAFE = re.compile(r"[^A-Za-z0-9_~-]")


class App:
    def __init__(self, ctx, dark):
        self.ctx = next(i for i, c in enumerate(CONTEXTS) if c[0] == ctx)
        self.dark = dark
        self.focus = 0  # 0 sessions, 1 agents
        self.cur = [0, 0]
        self.offset = [0, 0]  # first visible row of each list
        self.filter = ""
        self.mode = None  # filter, rename, new, kill, help
        self.input = ""
        self.target = None
        self.toast = None  # (text, warn, expiry)
        self.log = []
        self.frame = 0
        self.hits = []

    # ------------------------------------------------------------ model

    @property
    def c(self):
        return CONTEXTS[self.ctx]

    def inside(self, mux):
        return mux in self.c[3]

    def is_current(self, mux, name):
        return self.c[3].get(mux) == name

    def agents_of(self, mux, name):
        return [a for a in AGENTS if a["mux"] == mux and a["session"] == name]

    def match(self, *fields):
        q = self.filter.lower()
        return not q or any(q in f.lower() for f in fields)

    def rows(self, which):
        rows = []
        for mux in self.c[2]:
            if which == 0:
                block = [("s", mux, s) for s in DATA[mux] if self.match(s["name"])]
            else:
                block = [("a", mux, a) for a in AGENTS
                         if a["mux"] == mux and self.match(a["name"], a["session"], a["tab"])]
            if block:
                rows.append(("g", mux, len(block)))
                rows += block
        return rows

    def items(self, which):
        return [r for r in self.rows(which) if r[0] != "g"]

    def clamp(self):
        for w in (0, 1):
            self.cur[w] = max(0, min(self.cur[w], len(self.items(w)) - 1))

    def selected(self):
        items = self.items(self.focus)
        return items[self.cur[self.focus]] if items else None

    # ------------------------------------------------------------ actions

    def say(self, text, warn=False):
        self.toast = (text, warn, time.monotonic() + 4)

    def run(self, cmds, closes):
        self.log.append(f"# {self.c[1]}\n" + "\n".join(cmds) + ("\n# the dashboard exits here" if closes else ""))
        self.say(cmds[-1] + ("   (would exit)" if closes else ""))

    def switch_cmds(self, it):
        kind, mux, x = it
        inside = self.inside(mux)
        if kind == "s":
            if mux == "tmux":
                return [f"tmux switch-client -c \"$client\" -t '={x['name']}'" if inside
                        else f"exec tmux attach-session -t '={x['name']}'"]
            if mux == "zellij":
                c = f"zellij action switch-session '{x['name']}'" if inside else f"exec zellij attach '{x['name']}'"
                return [c + ("   # resurrects it" if x.get("exited") else "")]
            return [f"herdr workspace focus {x['id']}"] + ([] if inside else ["exec herdr"])
        if mux == "tmux":
            if inside:
                return [f"tmux switch-client -c \"$client\" -t '{x['pane']}'"]
            return [f"tmux select-window -t '{x['pane']}' \\; select-pane -t '{x['pane']}'",
                    f"exec tmux attach-session -t '{x['pane']}'"]
        if mux == "zellij":
            if not inside:
                return [f"zellij --session '{x['session']}' action focus-pane-id {x['pane']}",
                        f"exec zellij attach '{x['session']}'"]
            if self.is_current("zellij", x["session"]):
                return [f"zellij action focus-pane-id {x['pane']}"]
            return [f"zellij action switch-session '{x['session']}' --pane-id {x['pane']}"]
        return [f"herdr agent focus {x['pane']}"] + ([] if inside else ["exec herdr"])

    def rename(self, it, name):
        _, mux, s = it
        old, new = s["name"], UNSAFE.sub("-", name)
        if not new or new == old:
            return
        cmd = {"tmux": f"tmux rename-session -t '={old}' '{new}'",
               "zellij": f"zellij --session '{old}' action rename-session '{new}'",
               "herdr": f"herdr workspace rename {s.get('id')} '{new}'"}[mux]
        for a in self.agents_of(mux, old):
            a["session"] = new
        if self.c[3].get(mux) == old:
            self.c[3][mux] = new
        s["name"] = new
        self.run([cmd], False)

    def kill(self, it):
        _, mux, s = it
        cmd = {"tmux": f"tmux kill-session -t '={s['name']}'",
               "zellij": f"zellij {'delete' if s.get('exited') else 'kill'}-session '{s['name']}'",
               "herdr": f"herdr workspace close {s.get('id')}"}[mux]
        DATA[mux].remove(s)
        AGENTS[:] = [a for a in AGENTS if not (a["mux"] == mux and a["session"] == s["name"])]
        self.clamp()
        self.run([cmd], False)

    def create(self, mux, name):
        d = "~/Desktop/personal-projects/multiplexer-dashboard"
        base = UNSAFE.sub("-", name or "multiplexer-dashboard")
        n, i = base, 1
        while any(s["name"] == n for s in DATA[mux]):
            n, i = f"{base}-{i}", i + 1
        inside = self.inside(mux)
        cmds = {
            "tmux": [f"tmux new-session -d -s '{n}' -c {d}", f"tmux switch-client -c \"$client\" -t '={n}'"]
            if inside else [f"exec tmux new-session -s '{n}' -c {d}"],
            "zellij": [f"zellij action switch-session '{n}' --cwd {d}"] if inside
            else [f"cd {d} && exec zellij --session '{n}'"],
            "herdr": [f"herdr workspace create --cwd {d} --label '{n}' --focus"] + ([] if inside else ["exec herdr"]),
        }[mux]
        DATA[mux].append(dict(name=n, id="wNEW", tabs=["1"], cwd=d, age="0s"))
        self.run(cmds, True)

    # ------------------------------------------------------------ input

    def handle(self, ev):
        """Returns False to quit."""
        if ev[0] == "mouse":
            return self.mouse(*ev[1:])
        k = ev[1]
        if k == "ctrl+c":
            return False
        if self.mode:
            self.prompt_key(k)
            return True
        n = len(self.items(self.focus))
        if k in ("j", "down"):
            self.cur[self.focus] = min(n - 1, self.cur[self.focus] + 1)
        elif k in ("k", "up"):
            self.cur[self.focus] = max(0, self.cur[self.focus] - 1)
        elif k in ("alt+j", "alt+down", "alt+k", "alt+up"):
            self.jump_group(1 if k in ("alt+j", "alt+down") else -1)
        elif k in ("g", "home"):
            self.cur[self.focus] = 0
        elif k in ("G", "end"):
            self.cur[self.focus] = n - 1
        elif k in ("tab", "shift+tab", "h", "l", "left", "right"):
            self.focus = 1 - self.focus
        elif k == "enter":
            it = self.selected()
            if it:
                self.run(self.switch_cmds(it), True)
        elif k == "/":
            self.mode, self.input = "filter", self.filter
        elif k == "?":
            self.mode = "help"
        elif k == "n":
            it = self.selected()
            self.target = it[1] if it else self.c[2][0]
            self.mode, self.input = "new", ""
        elif k in ("r", "x"):
            it = self.selected()
            if not it or it[0] != "s":
                self.say("Rename and kill apply to a session. Press Tab to switch lists.", True)
            elif k == "r" and it[2].get("exited"):
                self.say("An exited zellij session cannot be renamed.", True)
            else:
                self.target = it
                self.mode = "rename" if k == "r" else "kill"
                self.input = it[2]["name"] if k == "r" else ""
        elif k == "C":
            self.ctx, self.filter = (self.ctx + 1) % len(CONTEXTS), ""
        elif k == "T":
            self.dark = not self.dark
        elif k in ("q", "esc"):
            if not self.filter:
                return False
            self.filter = ""
        return True

    def prompt_key(self, k):
        mode = self.mode
        if mode == "help":
            self.mode = None
            return
        if mode == "kill":
            self.mode = None
            if k in ("y", "Y", "enter"):
                self.kill(self.target)
            return
        if k == "esc":
            if mode == "filter":
                self.filter = ""
            self.mode, self.input = None, ""
            return
        if k in ("enter", "up", "down"):
            v, self.mode, self.input = self.input, None, ""
            if mode == "rename":
                self.rename(self.target, v)
            elif mode == "new":
                self.create(self.target, v)
            elif k != "enter":
                self.handle(("key", k))
            return
        if k == "backspace":
            self.input = self.input[:-1]
        elif k == "ctrl+u":
            self.input = ""
        elif len(k) == 1 and k.isprintable():
            self.input += k
        if mode == "filter":
            self.filter, self.cur = self.input, [0, 0]

    def mouse(self, button, x, y):
        if self.mode:
            if self.mode == "help":
                self.mode = None
            return True
        if button in (64, 65):
            for h in self.hits:
                if h[1] <= x < h[2] and h[4] == "panel" and h[0][0] <= y < h[0][1]:
                    self.focus = h[3]
            n = len(self.items(self.focus))
            d = -1 if button == 64 else 1
            self.cur[self.focus] = max(0, min(n - 1, self.cur[self.focus] + d))
            return True
        if button == 0:
            for (y0, y1), x0, x1, which, idx in self.hits:
                if idx != "panel" and y0 == y and x0 <= x < x1:
                    again = self.focus == which and self.cur[which] == idx
                    self.focus, self.cur[which] = which, idx
                    if again:
                        self.handle(("key", "enter"))
        return True

    def jump_group(self, d):
        """Moves to the first item of the next or previous multiplexer."""
        items = self.items(self.focus)
        if not items:
            return
        firsts = [i for i, r in enumerate(items) if i == 0 or items[i - 1][1] != r[1]]
        cur = self.cur[self.focus]
        if d > 0:
            nxt = [i for i in firsts if i > cur]
            self.cur[self.focus] = nxt[0] if nxt else firsts[0]
        else:
            prv = [i for i in firsts if i < cur]
            self.cur[self.focus] = prv[-1] if prv else firsts[-1]

    def tick(self):
        self.frame += 1
        if self.toast and time.monotonic() > self.toast[2]:
            self.toast = None

    # ------------------------------------------------------------ view

    def render(self, cols, rows):
        self.hits = []
        self.clamp()
        dim = 0.55 if self.mode in ("rename", "new", "kill", "help") else 0.0
        Canvas.theme = Theme(self.dark, dim)
        t = Canvas.theme
        if cols < 40 or rows < 12:
            msg = paint("Make the window bigger (at least 40×12).", t.subtle)
            return [fit("", cols)] * (rows // 2) + [fit("  " + msg, cols)] + [fit("", cols)] * (rows - rows // 2 - 1)

        H = rows - 2
        wide = cols >= 72
        lw = max(34, min(46, cols * 2 // 5)) if wide else cols
        sh = max(4, (H * 11 + 19) // 20)
        body = self.list_panel(0, "Sessions", 0, 1, lw, sh) + self.list_panel(1, "Agents", 0, 1 + sh, lw, H - sh)
        if wide:
            body = [l + r for l, r in zip(body, self.preview(cols - lw, H))]
        lines = [self.header(cols)] + body + [self.footer(cols)]

        if dim:
            Canvas.theme = Theme(self.dark)
            dialog = self.dialog(cols)
            x0, y0 = (cols - width(dialog[0])) // 2, max(1, (rows - len(dialog)) // 2 - 1)
            for i, d in enumerate(dialog):
                if y0 + i < rows:
                    lines[y0 + i] = overlay(lines[y0 + i], x0, d)
        return lines

    def header(self, cols):
        t = Canvas.theme
        pill = gradient(" ◇ multiplexer dashboard ", t.iris, t.rose, t.base)
        groups = paint(" › ", t.muted).join(paint(g, t.mux(g), bold=True) for g in self.c[2])
        left = pill + paint("  " + self.c[1] + "   ", t.subtle) + groups
        n_s, n_a = len(self.items(0)), len(self.items(1))
        right = paint(plural(n_s, "session"), t.text) + paint(" · ", t.muted) + paint(plural(n_a, "agent") + " ", t.gold)
        return lr(left, right, cols)

    def panel(self, title, extra, note, body, w, h, focused):
        t = Canvas.theme
        bc = t.iris if focused else t.hl_high
        border = lambda s: paint(s, bc)
        chip = (paint(f" {title} ", t.base, t.iris, bold=True) if focused
                else paint(f" {title} ", t.subtle, bold=True))
        room = w - 6 - width(chip)
        if extra and width(extra) > room:
            extra = cut(extra, 0, max(0, room - 1)) + paint("…", t.muted)
        top = border("╭─") + chip + extra
        top += border("─" * max(0, w - width(top) - 1) + "╮")
        out = [top]
        for i in range(h - 2):
            out.append(border("│") + fit(body[i] if i < len(body) else "", w - 2) + border("│"))
        note = paint(f" {note} ", t.muted) if note else ""
        out.append(border("╰" + "─" * max(0, w - 3 - width(note))) + note + border("─╯" if note else "─╯"[1:]))
        out[-1] = fit(out[-1], w)
        return out

    def list_panel(self, which, title, x, y, w, h):
        t = Canvas.theme
        rows = self.rows(which)
        items = [r for r in rows if r[0] != "g"]
        focused = self.focus == which
        sel = items[self.cur[which]] if items else None
        ih, iw = h - 2, w - 2
        # Scroll only when the cursor leaves the view, so that rows stay
        # under the mouse; keep a group's header with its first item.
        start = self.offset[which]
        if sel:
            i = rows.index(sel)
            top = i - 1 if i > 0 and rows[i - 1][0] == "g" else i
            if top < start:
                start = top
            elif i >= start + ih:
                start = i - ih + 1
        start = self.offset[which] = max(0, min(start, len(rows) - ih))
        self.hits.append(((y, y + h), x, x + w, which, "panel"))
        body = []
        for r in rows[start:start + ih]:
            if r[0] == "g":
                body.append(self.group_row(r[1], r[2], iw))
                continue
            is_sel = r is sel
            pen = Pen(t.hl_med if is_sel and focused else t.hl_low if is_sel else _DEFAULT)
            accent = pen("▌", t.iris) if is_sel and focused else pen(" ")
            line = self.session_row(r, iw - 1, pen, is_sel) if r[0] == "s" else self.agent_row(r[2], iw - 1, pen, is_sel)
            self.hits.append(((y + 1 + len(body), 0), x + 1, x + 1 + iw, which, items.index(r)))
            body.append(accent + line)
        if not rows:
            body = ["", paint(f"  no match for “{self.filter}”" if self.filter else "  nothing here", t.muted, italic=True)]
        note = f"{self.cur[which] + 1}/{len(items)}" if items else ""
        return self.panel(title, "", note, body, w, h, focused)

    def group_row(self, mux, count, w):
        t = Canvas.theme
        name = paint(" " + mux + " ", t.mux(mux), bold=True)
        tail = paint(f" {count} ", t.muted)
        return name + paint("─" * max(0, w - width(name) - width(tail)), t.hl_med) + tail

    def session_row(self, r, w, pen, is_sel):
        t = Canvas.theme
        _, mux, s = r
        cur = self.is_current(mux, s["name"])
        mark = pen("● ", t.love) if cur else pen("  ")
        if s.get("exited"):
            name = pen(s["name"], t.muted, italic=True)
        else:
            name = pen(s["name"], t.text, bold=cur or is_sel)
        left = pen(" ") + mark + name
        if s.get("attached") and not cur and w >= 40:
            left += pen(" attached", t.muted)
        if s.get("exited"):
            right = pen(f"exited {s['age']} ", t.muted, italic=True)
        else:
            n = len(self.agents_of(mux, s["name"]))
            right = pen(f"◆{n} ", t.gold) if n else ""
            if w >= 32:
                unit = "win" if mux == "tmux" else "tab"
                right += pen(f"{plural(len(s['tabs']), unit):<6} ", t.muted)
        return lr(left, right, w, pen)

    def status(self, a, pen, wide):
        t = Canvas.theme
        st = a.get("status")
        if not st:
            return ""
        if st == "working":
            glyph, color, bold = SPINNER[self.frame % len(SPINNER)], t.gold, False
        elif st == "blocked":
            # Pulses, since it waits for the user.
            glyph, bold = "●", True
            color = t.love if (self.frame // 6) % 2 == 0 else mix(t.love, t.base, 0.45)
        else:
            glyph, color, bold = {"idle": ("○", t.foam, False), "done": ("✓", t.pine, False)}[st]
        return pen(f"{glyph} {st} " if wide else f"{glyph} ", color, bold=bold)

    def agent_row(self, a, w, pen, is_sel):
        t = Canvas.theme
        c = t.agent(a["name"])
        left = (pen(" ") + pen("◆ ", c) + pen(f"{a['name']:<9}", c, bold=is_sel)
                + pen(a["session"], t.text) + pen(" › " + a["tab"], t.muted))
        return lr(left, self.status(a, pen, w >= 38), w, pen)

    def preview(self, w, h):
        t = Canvas.theme
        it = self.selected()
        extra, note, info, screen = "", "", "", []
        sep = paint(" › ", t.muted)
        if it and it[0] == "a":
            a = it[2]
            s = next((s for s in DATA[a["mux"]] if s["name"] == a["session"]), {})
            extra = paint(" " + a["mux"], t.mux(a["mux"]), bold=True) + sep + paint(a["session"], t.text) + sep + paint(a["tab"], t.subtle) + " "
            note = "pane " + a["pane"]
            info = paint(a["name"], t.agent(a["name"]), bold=True) + paint(" · " + s.get("cwd", ""), t.subtle)
            if a.get("status"):
                info += paint(" · ", t.muted) + self.status(a, Pen(), True)
            screen = agent_screen(a)
        elif it:
            _, mux, s = it
            extra = paint(" " + mux, t.mux(mux), bold=True) + sep + paint(s["name"], t.text) + " "
            if s.get("exited"):
                screen = ["", paint(f"This session exited {s['age']} ago.", t.subtle),
                          paint("Enter resurrects it; x deletes it.", t.muted)]
                info = paint("exited", t.muted, italic=True)
            else:
                unit = "window" if mux == "tmux" else "tab"
                info = (paint(s["cwd"], t.subtle) + paint(" · ", t.muted) + paint(plural(len(s["tabs"]), unit), t.subtle)
                        + paint(" · ", t.muted) + paint("up " + s.get("age", "?"), t.subtle))
                extra += paint("› " + s["tabs"][0] + " ", t.subtle)
                screen = shell_screen(s)
                for a in self.agents_of(mux, s["name"]):
                    if a["tab"] == s["tabs"][0]:
                        screen = agent_screen(a)
                note = "focused pane"
        body = [" " + info, paint("─" * (w - 2), t.hl_med)] + [" " + raw(l) for l in screen] if it else []
        return self.panel("Preview", extra, note, body, w, h, False)

    def footer(self, cols):
        t = Canvas.theme
        if self.mode == "filter":
            left = (paint(" / ", t.base, t.gold, bold=True) + paint(" " + self.input, t.text)
                    + paint(" ", bg=t.text) + paint("   enter keep · esc clear", t.muted))
            n = len(self.items(0)) + len(self.items(1))
            return lr(left, paint(f"{n} matches ", t.muted), cols)
        if self.toast:
            text, warn, _ = self.toast
            icon = paint(" ! ", t.base, t.love, bold=True) if warn else paint(" → ", t.base, t.pine, bold=True)
            return fit(icon + paint(" " + text, t.love if warn else t.text), cols)
        keys = [("↵", "switch"), ("⇥", "focus"), ("/", "filter"), ("n", "new"), ("r", "rename"),
                ("x", "kill"), ("?", "help"), ("q", "quit")]
        left = ""
        for k, v in keys:
            piece = paint(f" {k} ", t.text, t.overlay, bold=True) + paint(f" {v}  ", t.muted)
            if width(left) + width(piece) > cols - 30:
                break
            left += piece
        right = paint(f"/{self.filter} ", t.gold, bold=True) if self.filter else ""
        right += paint("proto: C context · T theme ", t.hl_high)
        return lr(" " + left, right, cols)

    # ------------------------------------------------------------ dialogs

    def dialog(self, cols):
        t = Canvas.theme
        pen = Pen(t.surface)
        dw = min(60, cols - 4)
        iw = dw - 4
        caret = paint(" ", bg=t.iris)
        key = lambda k, label, bg=t.overlay, fg=t.text: pen(" ") + paint(f" {k} ", fg, bg, bold=True) + pen(f" {label} ", t.subtle)

        def field(value):
            v = value[-(iw - 4):]
            return paint(" " + v, t.text, t.overlay) + caret + paint(" " * max(0, iw - 3 - width(v)), bg=t.overlay)

        accent = t.iris
        if self.mode == "rename":
            _, mux, s = self.target
            title = "Rename session"
            lines = ["", pen(mux, t.mux(mux), bold=True) + pen(" › ", t.muted) + pen(s["name"], t.text), "",
                     field(self.input), "", key("enter", "rename") + key("esc", "cancel")]
        elif self.mode == "new":
            mux = self.target
            title = "New session"
            lines = ["", pen("in ", t.subtle) + pen(mux, t.mux(mux), bold=True)
                     + pen("  ~/Desktop/personal-projects/multiplexer-dashboard", t.muted), "",
                     field(self.input), pen("empty: named after the directory", t.muted, italic=True), "",
                     key("enter", "create") + key("esc", "cancel")]
        elif self.mode == "kill":
            _, mux, s = self.target
            accent = t.love
            verb = "Delete" if s.get("exited") else "Kill"
            title = f"{verb} session"
            agents = self.agents_of(mux, s["name"])
            lines = ["", pen(f"{verb} ", t.text) + pen(mux, t.mux(mux), bold=True) + pen(" session ", t.text)
                     + pen(s["name"], t.text, bold=True) + pen("?", t.text)]
            if agents:
                names = ", ".join(a["name"] for a in agents)
                verb_s = "stops" if len(agents) == 1 else "stop"
                lines.append(pen(f"Its {plural(len(agents), 'agent')} ({names}) {verb_s} with it.", t.love))
            if self.is_current(mux, s["name"]):
                lines.append(pen("This is the session you are in.", t.love))
            lines += ["", key("y", verb.lower(), t.love, t.base) + key("n", "cancel")]
        else:
            title = "Keys"
            rows = [("j k ↑ ↓", "move"), ("alt+j/k", "next / previous multiplexer"), ("g G", "first / last"), ("Tab", "sessions ⇄ agents"),
                    ("Enter", "switch to the session or agent"), ("/", "filter as you type"),
                    ("n", "new session"), ("r", "rename session"), ("x", "kill session"),
                    ("mouse", "click selects, again switches"), ("q Esc", "close")]
            lines = [""] + [pen(f"{k:<9}", t.iris, bold=True) + pen(v, t.text) for k, v in rows] + \
                    ["", pen("any key closes this", t.muted, italic=True)]

        border = lambda s: paint(s, accent, t.surface)
        chip = paint(f" {title} ", t.base, accent, bold=True)
        top = border("╭─") + chip + border("─" * max(0, dw - 4 - width(chip)) + "─╮")
        out = [top]
        for l in lines:
            out.append(border("│") + pen(" ") + fit(l, iw, pen) + pen(" ") + border("│"))
        out.append(border("╰" + "─" * (dw - 2) + "╯"))
        return out


# Mock pane captures as `tmux capture-pane -e` would return them: with the
# pane's own escape sequences, in its 16-color palette.
def shell_screen(s):
    ps = lambda cmd: [f"\x1b[1;34m{s['cwd']}\x1b[0m\x1b[35m  main\x1b[0m", f"\x1b[32m❯\x1b[0m {cmd}"]
    return (ps("git status -sb") + ["\x1b[32m## main...origin/main\x1b[0m", "\x1b[31m M\x1b[0m README.md",
                                    "\x1b[31m??\x1b[0m notes.md", ""]
            + ps("git log --oneline -3") + ["\x1b[33ma1b2c3d\x1b[0m Describe the session order",
                                            "\x1b[33m9f8e7d6\x1b[0m Add the herdr workspace label",
                                            "\x1b[33m5a4b3c2\x1b[0m Initial commit", ""]
            + ps("\x1b[7m \x1b[0m"))


def agent_screen(a):
    if a["name"] == "claude":
        return ["\x1b[35m╭──────────────────────────────────────╮\x1b[0m",
                f"\x1b[35m│\x1b[0m ✻ Claude Code  \x1b[2m~/{a['session'][:20]:<20}\x1b[0m\x1b[35m│\x1b[0m",
                "\x1b[35m╰──────────────────────────────────────╯\x1b[0m", "",
                "\x1b[1m> \x1b[0madd a preview pane to the dashboard", "",
                "\x1b[32m●\x1b[0m \x1b[1mRead\x1b[0m(dashboard.py)", "\x1b[2m  ⎿  Read 412 lines\x1b[0m",
                "\x1b[32m●\x1b[0m \x1b[1mUpdate\x1b[0m(dashboard.py)",
                "\x1b[2m  ⎿  Updated with \x1b[0m\x1b[32m18 additions\x1b[0m\x1b[2m and \x1b[0m\x1b[31m4 removals\x1b[0m",
                "\x1b[32m    + preview = self.preview(cols - lw, H)\x1b[0m",
                "\x1b[31m    - preview = []\x1b[0m", "",
                "\x1b[33m✻ Thinking…\x1b[0m \x1b[2m(esc to interrupt)\x1b[0m"]
    if a["name"] == "codex":
        return ["\x1b[1m>_ OpenAI Codex\x1b[0m\x1b[2m  model: gpt-5.5\x1b[0m", "",
                "\x1b[36m›\x1b[0m explain the popup placement code", "",
                "\x1b[32m•\x1b[0m \x1b[1mExplored\x1b[0m", "\x1b[2m  └ Read popup.sh, ui.rs\x1b[0m", "",
                "The popup sits below the cursor when it fits, else above it,",
                "and falls back to the pane's bottom left without a cursor."]
    if a["name"] == "pi":
        return ["\x1b[1mpi\x1b[0m", "", "\x1b[1;31mAllow bash: rm -rf target/ ?\x1b[0m  [y/N]"]
    if a["name"] == "opencode":
        return ["", "\x1b[1m  opencode\x1b[0m\x1b[2m  build · claude-opus-5-5\x1b[0m", "", "\x1b[2m  Waiting for input.\x1b[0m"]
    return ["\x1b[34m✦\x1b[0m \x1b[1mSummarize the open PRs\x1b[0m", "", "3 PRs are open; #41 is ready to merge."]


# ---------------------------------------------------------------- main


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--context", choices=[c[0] for c in CONTEXTS], default="outside")
    p.add_argument("--theme", choices=["auto", "light", "dark"], default="auto")
    p.add_argument("--no-bg", action="store_true", help="keep the terminal's own background")
    args = p.parse_args()
    Canvas.paint_bg = not args.no_bg

    resized = []
    signal.signal(signal.SIGWINCH, lambda *_: resized.append(1))
    with Term() as term:
        dark = {"light": False, "dark": True}.get(args.theme)
        if dark is None:
            dark = term.background_is_dark() is not False
        app = App(args.context, dark)
        while True:
            if resized:
                resized.clear()
                term.invalidate()
            cols, rows = term.size()
            term.draw(app.render(cols, rows))
            try:
                evs = term.events(0.08)
            except InterruptedError:
                continue
            if not evs:
                app.tick()
                continue
            if not all(app.handle(e) for e in evs):
                break
    if app.log:
        print("Commands the dashboard would have run:")
        for e in app.log:
            print("\n" + e)


if __name__ == "__main__":
    main()
