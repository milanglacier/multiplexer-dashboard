#!/usr/bin/env python3
"""Inline prototype of the dashboard, layout A, in stdlib Python.

Draws a block of rows below the shell prompt (no alternate screen) with raw
ANSI escape sequences and the terminal's own 16-color palette, so it follows
the terminal theme. Mock data only; actions print the command the real app
would run, and the list is printed on exit.

    python3 dashboard_inline.py [--context outside|tmux|zellij|herdr|nested]
                                [--rows N] [--keep]

Keys: j/k or arrows move, Tab switches lists, Enter switches, / filters,
q or Esc quits. --keep leaves the last frame in the scrollback on exit.
"""

import argparse
import os
import re
import select
import shutil
import signal
import sys
import termios
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
        dict(name="agent-scratch", id="w4R", tabs=["1"], cwd="~/Desktop/personal-projects/agent-scratch"),
        dict(name="multiplexer-dashboard", id="w53", tabs=["1", "2"], cwd="~/Desktop/personal-projects/multiplexer-dashboard"),
        dict(name="herdr", id="w60", tabs=["1"], cwd="~/Desktop/personal-projects/herdr"),
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
CONTEXTS = {
    "outside": ("outside any multiplexer", ["zellij", "herdr", "tmux"], {}),
    "tmux": ("in tmux", ["tmux"], {"tmux": "~"}),
    "zellij": ("in zellij", ["zellij"], {"zellij": "dotfiles"}),
    "herdr": ("in herdr", ["herdr"], {"herdr": "multiplexer-dashboard"}),
    "nested": ("zellij in tmux", ["zellij", "tmux"], {"zellij": "dotfiles", "tmux": "~"}),
}

# ---------------------------------------------------------------- styling

# SGR codes from the terminal's 16-color palette only.
RESET = "\x1b[0m"
MUX = {"zellij": "1;36", "herdr": "1;35", "tmux": "1;31"}
STATUS = {"working": ("33", None), "idle": ("36", "○"), "blocked": ("1;31", "●"), "done": ("34", "✓")}
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def sgr(code, text):
    return f"\x1b[{code}m{text}{RESET}" if code else text


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def cell_width(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def width(s):
    return sum(cell_width(c) for c in ANSI_RE.sub("", s))


def truncate(s, w):
    """Cuts a string with escape sequences to w cells, keeping the sequences."""
    if width(s) <= w:
        return s
    out, n, i = [], 0, 0
    while i < len(s):
        m = ANSI_RE.match(s, i)
        if m:
            out.append(m.group())
            i = m.end()
            continue
        cw = cell_width(s[i])
        if n + cw > w - 1:
            break
        out.append(s[i])
        n += cw
        i += 1
    return "".join(out) + "…" + " " * (w - 1 - n) + RESET


def fit(s, w):
    s = truncate(s, w)
    return s + " " * max(0, w - width(s))


def lr(left, right, w):
    rw = width(right)
    return fit(right, w) if rw >= w else fit(left, w - rw) + right


# ---------------------------------------------------------------- terminal


class Term:
    """Raw keyboard input and an in-place redraw of a block of rows."""

    def __init__(self, keep):
        self.fd = os.open("/dev/tty", os.O_RDWR)
        self.out = open(self.fd, "w", buffering=1, closefd=False)
        self.old = termios.tcgetattr(self.fd)
        self.drawn = 0
        self.keep = keep

    def __enter__(self):
        tty.setcbreak(self.fd)  # no echo, no line buffering; Ctrl-C stays a signal
        self.out.write("\x1b[?25l")  # hide the cursor
        return self

    def __exit__(self, *exc):
        if self.drawn and not self.keep:
            self.out.write(self._home() + "\x1b[J")
        elif self.drawn:
            self.out.write("\r\n")
        self.out.write("\x1b[?25h")
        self.out.flush()
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

    def _home(self):
        return "\r" + (f"\x1b[{self.drawn - 1}A" if self.drawn > 1 else "")

    def draw(self, lines, clear=False):
        buf = self._home() if self.drawn else ""
        if clear:
            buf += "\x1b[J"
        buf += "\r\n".join("\x1b[2K" + l + RESET for l in lines)
        self.out.write(buf)
        self.out.flush()
        self.drawn = len(lines)

    def keys(self, timeout):
        """Returns the keys read within timeout; a read can hold several."""
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return []
        data = os.read(self.fd, 1024).decode("utf-8", "replace")
        keys, i = [], 0
        while i < len(data):
            m = KEY_SEQ_RE.match(data, i)
            if m:
                seq = m.group()
                i = m.end()
            else:
                seq = data[i]
                i += 1
            keys.append(KEY_NAMES.get(seq, seq))
        return keys


# A lone ESC is the Escape key; ESC followed by [ or O starts a sequence.
KEY_SEQ_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z~]|\x1bO[A-Za-z]")
KEY_NAMES = {
    "\x1b[A": "up", "\x1bOA": "up", "\x1b[B": "down", "\x1bOB": "down",
    "\t": "tab", "\x1b[Z": "shift+tab", "\r": "enter", "\n": "enter",
    "\x7f": "backspace", "\x08": "backspace", "\x1b": "esc", "\x15": "ctrl+u",
}


# ---------------------------------------------------------------- app


class App:
    def __init__(self, ctx, rows):
        self.label, self.groups, self.current = CONTEXTS[ctx]
        self.max_rows = rows
        self.focus = 0  # 0 sessions, 1 agents
        self.cur = [0, 0]
        self.filter = ""
        self.filtering = False
        self.toast = ""
        self.log = []
        self.frame = 0

    def match(self, *fields):
        q = self.filter.lower()
        return not q or any(q in f.lower() for f in fields)

    def rows(self, which):
        rows = []
        for mux in self.groups:
            if which == 0:
                block = [("s", mux, s) for s in DATA[mux] if self.match(s["name"])]
            else:
                block = [("a", mux, a) for a in AGENTS if a["mux"] == mux and self.match(a["name"], a["session"], a["tab"])]
            if block:
                rows.append(("g", mux, len(block)))
                rows.extend(block)
        return rows

    def items(self, which):
        return [r for r in self.rows(which) if r[0] != "g"]

    def selected(self):
        items = self.items(self.focus)
        self.cur[self.focus] = max(0, min(self.cur[self.focus], len(items) - 1))
        return items[self.cur[self.focus]] if items else None

    # ------------------------------------------------------------ rows

    def group_row(self, mux, count, w):
        name, tail = sgr(MUX[mux], f" {mux} "), sgr("90", f" {count} ")
        return fit(name + sgr("90", "─" * max(0, w - width(name) - width(tail))) + tail, w)

    def session_row(self, mux, s, w):
        cur = self.current.get(mux) == s["name"]
        mark = sgr("31", "● ") if cur else "  "
        name = sgr("2;3", s["name"]) if s.get("exited") else sgr("1" if cur else "", s["name"])
        if s.get("attached") and not cur:
            name += sgr("90", " attached")
        if s.get("exited"):
            right = sgr("2;3", f"exited {s['age']} ")
        else:
            n = sum(a["mux"] == mux and a["session"] == s["name"] for a in AGENTS)
            unit = "win" if mux == "tmux" else "tab"
            count = len(s["tabs"])
            right = (sgr("33", f"◆{n} ") if n else "") + sgr("90", f"{count} {unit}{'s' if count > 1 else ' '} ")
        return lr("  " + mark + name, right, w)

    def agent_row(self, a, w):
        st = a.get("status")
        right = ""
        if st:
            code, glyph = STATUS[st]
            glyph = glyph or SPINNER[self.frame % len(SPINNER)]
            right = sgr(code, f"{glyph} {st} " if w >= 40 else f"{glyph} ")
        left = "  " + sgr("33", "◆ " + a["name"].ljust(9)) + a["session"] + sgr("90", " › " + a["tab"])
        return lr(left, right, w)

    def highlight(self, line, w, focused):
        # Selection in reverse video: readable in any palette, light or dark.
        plain_text = fit(ANSI_RE.sub("", line), w - 1)
        if focused:
            return sgr("35", "▌") + sgr("7", plain_text)
        return sgr("90", "▌") + sgr("1", plain_text)

    def panel(self, title, note, body, w, h, focused):
        bc = "35" if focused else "90"
        title = sgr("1" if focused else "90", f" {title} ")
        top = sgr(bc, "╭─") + title + sgr(bc, "─" * max(0, w - 3 - width(title)) + "╮")
        lines = [top]
        for i in range(h - 2):
            lines.append(sgr(bc, "│") + fit(body[i] if i < len(body) else "", w - 2) + sgr(bc, "│"))
        note = sgr("90", f" {note} ") if note else ""
        lines.append(sgr(bc, "╰" + "─" * max(0, w - 3 - width(note))) + note + sgr(bc, "─╯"))
        return lines

    def list_panel(self, which, title, w, h):
        rows, items = self.rows(which), self.items(which)
        focused = self.focus == which
        sel = items[self.cur[which]] if items and self.cur[which] < len(items) else None
        ih = h - 2
        start = 0
        if sel and len(rows) > ih:
            start = max(0, min(rows.index(sel) - ih // 2, len(rows) - ih))
        body = []
        for r in rows[start:start + ih]:
            kind = r[0]
            if kind == "g":
                body.append(self.group_row(r[1], r[2], w - 2))
                continue
            line = self.session_row(r[1], r[2], w - 2) if kind == "s" else self.agent_row(r[2], w - 2)
            body.append(self.highlight(line, w - 2, focused) if r is sel else line)
        if not rows:
            body.append(sgr("2;3", f"  no match for “{self.filter}”"))
        note = f"{self.cur[which] + 1}/{len(items)}" if items else ""
        return self.panel(title, note, body, w, h, focused)

    def preview(self, w, h):
        it = self.selected()
        title, note, body = "Preview", "", []
        if it and it[0] == "a":
            a = it[2]
            title, note, body = f"Preview · {a['mux']} › {a['session']} › {a['tab']}", "pane " + a["pane"], agent_screen(a)
        elif it:
            s = it[2]
            if s.get("exited"):
                title, body = f"Preview · {it[1]} › {s['name']}", ["", sgr("2", f"This session exited {s['age']} ago.")]
            else:
                title, note = f"Preview · {it[1]} › {s['name']} › {s['tabs'][0]}", s["cwd"]
                body = shell_screen(s)
                for a in AGENTS:
                    if a["mux"] == it[1] and a["session"] == s["name"] and a["tab"] == s["tabs"][0]:
                        body = agent_screen(a)
        return self.panel(title, note, [" " + l for l in body], w, h, False)

    def render(self, cols, rows):
        h = min(self.max_rows, rows - 1)
        H = h - 2
        wide = cols >= 72
        lw = max(34, min(46, cols * 2 // 5)) if wide else cols
        sh = max(4, (H * 11 + 19) // 20)
        left = self.list_panel(0, "Sessions", lw, sh) + self.list_panel(1, "Agents", lw, H - sh)
        if wide:
            left = [l + r for l, r in zip(left, self.preview(cols - lw, H))]
        n_s, n_a = len(self.items(0)), len(self.items(1))
        header = lr(sgr("1;7;35", " ◇ dashboard ") + sgr("90", "  " + self.label + "  ·  ")
                    + sgr("90", " › ").join(sgr(MUX[g], g) for g in self.groups),
                    sgr("90", f"{n_s} sessions · {n_a} agents "), cols)
        return [header] + left + [self.footer(cols)]

    def footer(self, cols):
        if self.filtering:
            return fit(sgr("1;33", " / ") + self.filter + sgr("7", " ") + sgr("90", "   enter keep · esc clear"), cols)
        if self.toast:
            return fit(sgr("34", " " + self.toast), cols)
        keys = "".join(sgr("1;35", " " + k) + sgr("90", " " + v + " ")
                       for k, v in [("↵", "switch"), ("⇥", "focus"), ("/", "filter"), ("q", "quit")])
        return lr(keys, sgr("1;33", f"/{self.filter} ") if self.filter else "", cols)

    # ------------------------------------------------------------ input

    def handle(self, k):
        """Returns False to quit."""
        self.toast = ""
        if self.filtering:
            if k == "esc":
                self.filter, self.filtering = "", False
            elif k in ("enter", "down", "up"):
                self.filtering = False
            elif k == "backspace":
                self.filter = self.filter[:-1]
            elif k == "ctrl+u":
                self.filter = ""
            elif len(k) == 1 and k.isprintable():
                self.filter += k
            self.cur = [0, 0] if self.filtering else self.cur
            return True
        n = len(self.items(self.focus))
        if k in ("j", "down"):
            self.cur[self.focus] = min(n - 1, self.cur[self.focus] + 1)
        elif k in ("k", "up"):
            self.cur[self.focus] = max(0, self.cur[self.focus] - 1)
        elif k in ("tab", "shift+tab"):
            self.focus = 1 - self.focus
        elif k == "/":
            self.filtering = True
        elif k == "enter":
            it = self.selected()
            if it:
                cmd = switch_cmd(it, self.current)
                self.log.append(cmd)
                self.toast = f"→ {cmd}   (would exit)"
        elif k in ("q", "esc"):
            if self.filter:
                self.filter = ""
            else:
                return False
        return True


def switch_cmd(it, current):
    kind, mux, x = it
    inside = mux in current
    if kind == "s":
        return {
            "tmux": f"tmux switch-client -t '={x['name']}'" if inside else f"exec tmux attach-session -t '={x['name']}'",
            "zellij": f"zellij action switch-session '{x['name']}'" if inside else f"exec zellij attach '{x['name']}'",
            "herdr": f"herdr workspace focus {x.get('id')}" + ("" if inside else " && exec herdr"),
        }[mux]
    return {
        "tmux": f"tmux switch-client -t '{x['pane']}'",
        "zellij": f"zellij action switch-session '{x['session']}' --pane-id {x['pane']}",
        "herdr": f"herdr agent focus {x['pane']}",
    }[mux]


# Mock pane captures, as raw escape sequences the way `tmux capture-pane -e`
# returns them: the preview passes them through.
def shell_screen(s):
    ps = lambda cmd: [f"\x1b[1;34m{s['cwd']}\x1b[0;35m  main\x1b[0m", f"\x1b[32m❯\x1b[0m {cmd}"]
    return (ps("git status -sb") + ["\x1b[32m## main...origin/main\x1b[0m", "\x1b[31m M\x1b[0m README.md", ""]
            + ps("git log --oneline -2") + ["\x1b[33ma1b2c3d\x1b[0m Describe the session order",
                                            "\x1b[33m9f8e7d6\x1b[0m Add the herdr workspace label"])


def agent_screen(a):
    if a["name"] == "claude":
        return ["\x1b[1m> \x1b[0madd a preview pane to the dashboard", "",
                "\x1b[32m●\x1b[0m \x1b[1mRead\x1b[0m(dashboard.py)", "\x1b[2m  ⎿  Read 412 lines\x1b[0m",
                "\x1b[32m●\x1b[0m \x1b[1mUpdate\x1b[0m(dashboard.py)",
                "\x1b[2m  ⎿  \x1b[0m\x1b[32m18 additions\x1b[0m\x1b[2m and \x1b[0m\x1b[31m4 removals\x1b[0m", "",
                "\x1b[33m✻ Thinking…\x1b[0m \x1b[2m(esc to interrupt)\x1b[0m"]
    if a["name"] == "codex":
        return ["\x1b[1m>_ OpenAI Codex\x1b[0m", "", "\x1b[36m›\x1b[0m explain the popup placement code", "",
                "\x1b[32m•\x1b[0m \x1b[1mExplored\x1b[0m", "\x1b[2m  └ Read popup.sh, ui.rs\x1b[0m"]
    if a["name"] == "pi":
        return ["\x1b[1mpi\x1b[0m", "", "\x1b[1;31mAllow bash: rm -rf target/ ?\x1b[0m  [y/N]"]
    return ["", f"\x1b[2m  {a['name']}: waiting for input.\x1b[0m"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--context", choices=CONTEXTS, default="outside")
    p.add_argument("--rows", type=int, default=20)
    p.add_argument("--keep", action="store_true")
    args = p.parse_args()

    app = App(args.context, args.rows)
    resized = []
    signal.signal(signal.SIGWINCH, lambda *_: resized.append(1))
    with Term(args.keep) as term:
        clear = False
        while True:
            cols, rows = shutil.get_terminal_size()
            term.draw(app.render(cols, rows), clear)
            clear = False
            try:
                keys = term.keys(0.11)
            except InterruptedError:
                keys = []
            if resized:
                # The terminal may have reflowed the block; erase from its
                # start and redraw.
                resized.clear()
                clear = True
            if not keys:
                app.frame += 1
                continue
            if not all(app.handle(k) for k in keys):
                break
    if app.log:
        print("Commands the dashboard would have run:")
        print("\n".join(app.log))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
