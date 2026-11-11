"""Unit tests for multiplexer-dashboard: the parsers of each multiplexer's
output, agent detection, context detection, the rows and cursor rules, the
commands of every action, session naming, input parsing, the ANSI helpers
and the rendered screen.

The fixtures were recorded from tmux 3.8, zellij 0.45.1 and herdr 0.9.5 in
an isolated environment, with home paths replaced by /home/me. Record a
fixture again when its command or format string changes.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_script():
    loader = importlib.machinery.SourceFileLoader(
        "multiplexer_dashboard", str(ROOT / "multiplexer-dashboard")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


md = load_script()


def fixture(path: str) -> str:
    return (FIXTURES / path).read_text()


def plain(s: str) -> str:
    """A painted string without its escape sequences."""
    return md.ANSI_RE.sub("", s)


NAMES = md.agent_names({})


class FakeRunner:
    """Answers commands from a table of argument-list prefixes and records
    every command it is asked to run."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = []

    def __call__(self, args, timeout=5.0):
        args = list(args)
        self.calls.append(args)
        best = None
        for prefix, result in self.answers.items():
            if tuple(args[: len(prefix)]) == prefix and (
                best is None or len(prefix) > len(best[0])
            ):
                best = (prefix, result)
        if best is None:
            return md.Result(0, "", "")
        result = best[1]
        if isinstance(result, str):
            return md.Result(0, result, "")
        return result


# ---------------------------------------------------------------- agents


class AgentDetectionTest(unittest.TestCase):
    def test_program_names(self):
        self.assertEqual(md.detect_agent(["claude"], NAMES), "claude")
        self.assertEqual(md.detect_agent(["/usr/bin/codex", "--yolo"], NAMES), "codex")
        self.assertEqual(md.detect_agent(["cursor-agent"], NAMES), "cursor-agent")
        self.assertIsNone(md.detect_agent(["bash"], NAMES))
        self.assertIsNone(md.detect_agent([], NAMES))

    def test_interpreter_arguments(self):
        node = ["node", "/usr/lib/node_modules/@google/gemini-cli/bin/gemini"]
        self.assertEqual(md.detect_agent(node, NAMES), "gemini")
        self.assertEqual(
            md.detect_agent(["node", "--no-warnings", "/x/codex.js"], NAMES), "codex"
        )
        self.assertEqual(md.detect_agent(["python3.12", "-m", "aider"], NAMES), "aider")
        self.assertEqual(md.detect_agent(["bun", "/x/bin/opencode"], NAMES), "opencode")
        # Only the first argument that is not an option counts.
        self.assertIsNone(md.detect_agent(["node", "server.js", "claude"], NAMES))
        # A program that is not an interpreter is not looked into.
        self.assertIsNone(md.detect_agent(["vim", "claude"], NAMES))

    def test_icons(self):
        icons = [md.agent_icon(n) for n in md.DEFAULT_AGENTS]
        self.assertEqual(len(set(icons)), len(icons))
        self.assertNotIn(md.CUSTOM_AGENT_ICON, icons)
        self.assertEqual({md.width(i) for i in icons}, {1})
        self.assertEqual(md.agent_icon("claude"), "✻")
        self.assertEqual(md.agent_icon("myagent"), md.CUSTOM_AGENT_ICON)

    def test_status_icons_differ_from_agent_icons(self):
        statuses = list(md.STATUS_ICONS.values())
        self.assertEqual(len(set(statuses)), len(statuses))
        self.assertEqual({md.width(i) for i in statuses}, {1})
        agents = set(md.AGENT_ICONS.values()) | {md.CUSTOM_AGENT_ICON}
        self.assertFalse(agents & set(statuses))

    def test_extra_names_from_the_environment(self):
        names = md.agent_names({"MULTIPLEXER_DASHBOARD_AGENTS": " kimi, ,myagent "})
        self.assertEqual(md.detect_agent(["kimi"], names), "kimi")
        self.assertEqual(md.detect_agent(["node", "/x/myagent"], names), "myagent")
        self.assertEqual(md.detect_agent(["claude"], names), "claude")
        self.assertIsNone(md.detect_agent(["kimi"], NAMES))

    def test_deepest_agent_below_a_pane(self):
        tree = md.ProcessTree(fixture("tmux/ps.txt"))
        # The gemini pane runs node directly.
        self.assertEqual(tree.agent_under(2682080, NAMES), "gemini")
        # A shell pane whose child runs codex.
        self.assertEqual(tree.agent_under(2682068, NAMES), "codex")
        # A shell pane without an agent below it.
        self.assertIsNone(tree.agent_under(2682074, NAMES))
        # The deepest of nested agents wins.
        nested = md.ProcessTree(
            "10 1 zsh\n11 10 node /x/bin/claude\n12 11 node /x/bin/gemini\n"
        )
        self.assertEqual(nested.agent_under(10, NAMES), "gemini")


# ---------------------------------------------------------------- tmux


class TmuxTest(unittest.TestCase):
    def test_sessions_in_creation_order(self):
        sessions = md.parse_tmux_sessions(fixture("tmux/list-sessions.txt"))
        # Created in the same second, so the session id breaks the tie.
        self.assertEqual([s.name for s in sessions], ["~", "monopi", "with space"])
        self.assertEqual([s.id for s in sessions], ["$0", "$1", "$2"])
        self.assertEqual([s.tabs for s in sessions], [2, 2, 1])
        self.assertEqual([s.attached for s in sessions], [False, True, False])

    def load(self, current="$1", **extra):
        runner = FakeRunner(
            {
                ("tmux", "list-sessions"): fixture("tmux/list-sessions.txt"),
                ("tmux", "list-panes"): fixture("tmux/list-panes.txt"),
                ("ps",): fixture("tmux/ps.txt"),
                ("tmux", "display-message"): current + "\n",
                **extra,
            }
        )
        return md.Tmux(runner, {}).load(inside=True), runner

    def test_agents_and_focused_panes(self):
        group, _ = self.load()
        self.assertIsNone(group.error)
        agents = [(a.name, a.session, a.tab_index, a.tab, a.pane) for a in group.agents]
        self.assertEqual(
            agents,
            [
                ("codex", "~", 0, "codex", "%0"),
                ("claude", "monopi", 1, "claude", "%3"),
                ("gemini", "monopi", 1, "claude", "%4"),
            ],
        )
        monopi = group.sessions[1]
        self.assertEqual((monopi.pane, monopi.path), ("%3", "/home/me/proj/repo-a"))
        self.assertTrue(monopi.current)
        self.assertFalse(group.sessions[0].current)

    def test_own_pane_is_not_the_focused_pane(self):
        # The dashboard's floating pane is the active one; the pane that was
        # active before it is previewed instead.
        group, _ = self.load()
        self.assertEqual(group.sessions[1].pane, "%3")
        env = {"TMUX_PANE": "%3"}
        runner = FakeRunner(
            {
                ("tmux", "list-sessions"): fixture("tmux/list-sessions.txt"),
                ("tmux", "list-panes"): fixture("tmux/list-panes.txt"),
            }
        )
        group = md.Tmux(runner, env).load(inside=True)
        self.assertEqual(group.sessions[1].pane, "%4")

    def test_current_session_of_a_named_client(self):
        runner = FakeRunner(
            {
                ("tmux", "list-sessions"): fixture("tmux/list-sessions.txt"),
                ("tmux", "list-clients"): "/dev/pts/3\t$0\n/dev/pts/7\t$2\n",
            }
        )
        group = md.Tmux(runner, {}, client="/dev/pts/7").load(inside=True)
        self.assertEqual([s.current for s in group.sessions], [False, False, True])

    def test_no_server_is_an_empty_group(self):
        missing = md.Result(1, "", "no server running on /tmp/tmux-1000/default\n")
        runner = FakeRunner({("tmux", "list-sessions"): missing})
        group = md.Tmux(runner, {}).load(inside=False)
        self.assertEqual((group.sessions, group.error), ([], None))

    def test_ps_runs_only_for_interpreter_panes(self):
        panes = "$0\t0\tzsh\t1\t1\t0\t%0\tclaude\t100\t/home/me\n"
        runner = FakeRunner(
            {
                ("tmux", "list-sessions"): "~\t$0\t1\t1\t0\t/home/me\n",
                ("tmux", "list-panes"): panes,
            }
        )
        group = md.Tmux(runner, {}).load(inside=False)
        self.assertEqual([a.name for a in group.agents], ["claude"])
        self.assertNotIn(["ps", "-A", "-o", "pid=,ppid=,args="], runner.calls)


# ---------------------------------------------------------------- zellij


class ZellijTest(unittest.TestCase):
    def test_sessions(self):
        sessions = md.parse_zellij_sessions(fixture("zellij/list-sessions.txt"), 1000.0)
        self.assertEqual([s.name for s in sessions], ["zdots2", "zplain"])
        running, exited = sessions
        self.assertEqual(running.created, 1000.0 - 241)
        self.assertFalse(running.exited)
        self.assertTrue(exited.exited)
        self.assertEqual(exited.age, "3m")
        self.assertIsNone(exited.created)

    def test_current_marker(self):
        sessions = md.parse_zellij_sessions(
            fixture("zellij/list-sessions-inside.txt"), 1000.0
        )
        self.assertEqual([s.current for s in sessions], [True, False])

    def test_running_sessions_in_creation_order_then_exited(self):
        text = (
            "new [Created 5s ago] \n"
            "gone [Created 1h ago] (EXITED - attach to resurrect)\n"
            "old [Created 2days 3h ago] \n"
        )
        sessions = md.parse_zellij_sessions(text, 1e6)
        self.assertEqual([s.name for s in sessions], ["old", "new", "gone"])

    def test_durations(self):
        self.assertEqual(md.parse_duration("1m 30s"), 90)
        self.assertEqual(md.parse_duration("2days 3h"), 2 * 86400 + 3 * 3600)
        self.assertEqual(md.parse_duration("1year"), 365.25 * 86400)
        self.assertEqual(md.parse_duration("2months"), 2 * 30.44 * 86400)
        self.assertEqual(md.parse_duration("4s 120ms"), 4)

    def test_panes(self):
        s = md.Session("zellij", "zdots2")
        agents = md.parse_zellij_panes(
            s,
            fixture("zellij/list-panes.json"),
            fixture("zellij/list-tabs.json"),
            NAMES,
        )
        # Plugin panes and the exited pane are skipped; gemini runs in node.
        self.assertEqual(
            [(a.name, a.pane, a.tab, a.tab_id) for a in agents],
            [
                ("claude", "terminal_1", "Tab #1", "0"),
                ("gemini", "terminal_3", "Tab #1", "0"),
            ],
        )
        # list-tabs counts a tab that has no panes yet.
        self.assertEqual(s.tabs, 2)
        # No tab is active without a client, so the first tab's focused
        # terminal pane is the session's pane.
        self.assertEqual((s.pane, s.path), ("terminal_3", "/home/me/proj/plain"))
        # The dashboard's own pane is skipped.
        md.parse_zellij_panes(
            s,
            fixture("zellij/list-panes.json"),
            fixture("zellij/list-tabs.json"),
            NAMES,
            own_pane="terminal_3",
        )
        self.assertEqual(s.pane, "terminal_0")

    def test_load(self):
        runner = FakeRunner(
            {
                ("zellij", "list-sessions"): fixture("zellij/list-sessions.txt"),
                ("zellij", "--session", "zdots2", "action", "list-panes"): fixture(
                    "zellij/list-panes.json"
                ),
                ("zellij", "--session", "zdots2", "action", "list-tabs"): fixture(
                    "zellij/list-tabs.json"
                ),
            }
        )
        env = {"ZELLIJ_SESSION_NAME": "zdots2"}
        group = md.Zellij(runner, env).load(inside=True)
        self.assertEqual([s.current for s in group.sessions], [True, False])
        self.assertEqual(len(group.agents), 2)
        # The exited session is not asked for its panes.
        self.assertFalse(any("zplain" in c for c in runner.calls))

    def test_no_sessions_is_an_empty_group(self):
        none = md.Result(1, "No active zellij sessions found.\n", "")
        group = md.Zellij(FakeRunner({("zellij",): none}), {}).load(inside=False)
        self.assertEqual((group.sessions, group.error), ([], None))

    def test_clients(self):
        text = "CLIENT_ID ZELLIJ_PANE_ID RUNNING_COMMAND\n1         terminal_2     codex x\n"
        self.assertEqual(md.parse_zellij_clients(text), [("1", "terminal_2")])
        self.assertEqual(
            md.parse_zellij_clients("CLIENT_ID ZELLIJ_PANE_ID RUNNING_COMMAND\n"), []
        )

    def test_focus_after_attach(self):
        header = "CLIENT_ID ZELLIJ_PANE_ID RUNNING_COMMAND\n"
        answers = iter(
            [
                header,
                header + "1 terminal_0 N/A\n",
                header + "1 terminal_1 claude\n",
                header + "1 terminal_2 codex\n",
            ]
        )

        def runner(args, timeout=5.0):
            calls.append(args[4:])
            return md.Result(0, next(answers) if args[4] == "list-clients" else "", "")

        calls = []
        with mock.patch.object(md.time, "sleep"):
            self.assertEqual(md.zellij_focus_pane("zc", "1", "terminal_2", runner), 0)
        self.assertEqual(
            calls,
            [
                ["list-clients"],
                ["list-clients"],
                ["go-to-tab-by-id", "1"],
                ["list-clients"],
                ["focus-next-pane"],
                ["list-clients"],
            ],
        )


# ---------------------------------------------------------------- herdr


class HerdrTest(unittest.TestCase):
    def parse(self, inside=True):
        return md.parse_herdr(
            fixture("herdr/workspaces.json"),
            fixture("herdr/tabs.json"),
            fixture("herdr/panes.json"),
            fixture("herdr/agents.json"),
            inside,
        )

    def test_workspaces_as_sessions(self):
        group = self.parse()
        s = group.sessions
        self.assertEqual([x.name for x in s], ["repo-a", "plain"])
        self.assertEqual([x.id for x in s], ["w1", "w2"])
        self.assertEqual([x.tabs for x in s], [2, 1])
        self.assertEqual([x.current for x in s], [True, False])
        self.assertEqual((s[0].pane, s[0].path), ("w1:p1", "/home/me/proj/repo-a"))
        self.assertEqual(s[1].pane, "w2:p1")

    def test_focused_workspace_is_current_only_inside(self):
        self.assertEqual(
            [x.current for x in self.parse(inside=False).sessions], [False] * 2
        )

    def test_agents_with_status_and_tab(self):
        agents = [
            (a.name, a.session, a.tab, a.pane, a.status) for a in self.parse().agents
        ]
        self.assertEqual(
            agents,
            [
                ("claude", "repo-a", "1", "w1:p1", "blocked"),
                ("codex", "repo-a", "build", "w1:p2", "working"),
                ("gemini", "plain", "1", "w2:p1", "idle"),
            ],
        )

    def test_server_not_running(self):
        err = md.Result(1, "", fixture("herdr/server-not-running.txt"))
        group = md.Herdr(FakeRunner({("herdr",): err}), {}).load(inside=False)
        self.assertEqual(group.error, "server not running")
        self.assertEqual(group.sessions, [])

    def test_current_pane_directory(self):
        current = '{"result":{"pane":{"cwd":"/a","foreground_cwd":"/b"}}}'
        runner = FakeRunner({("herdr", "pane", "current"): current})
        env = {"HERDR_PANE_ID": "w1:p1"}
        self.assertEqual(md.Herdr(runner, env).default_dir(inside=True), "/b")
        self.assertIsNone(md.Herdr(runner, env).default_dir(inside=False))

    def test_session_preview_reads_the_tab_focused_pane(self):
        runner = FakeRunner(
            {
                ("herdr", "pane", "layout"): fixture("herdr/layout.json"),
                ("herdr", "pane", "read"): fixture("herdr/pane-read.txt"),
            }
        )
        s = md.Session("herdr", "repo-a", id="w1", pane="w1:p1")
        md.Herdr(runner, {}).capture("w1:p1", s)
        self.assertEqual(runner.calls[-1][:4], ["herdr", "pane", "read", "w1:p2"])


# ---------------------------------------------------------------- context


class ContextTest(unittest.TestCase):
    def installed(self, *names):
        return lambda m: m in names

    def test_outside_lists_installed_in_order(self):
        ctx = md.detect_context({}, self.installed("tmux", "zellij", "herdr"))
        self.assertEqual(ctx.listed, ["zellij", "herdr", "tmux"])
        self.assertEqual(ctx.inside, set())
        self.assertEqual(ctx.label, "outside any multiplexer")
        ctx = md.detect_context({}, self.installed("tmux"))
        self.assertEqual(ctx.listed, ["tmux"])

    def test_inside_lists_only_the_detected(self):
        env = {"TMUX": "/tmp/tmux-1000/default,1,0"}
        ctx = md.detect_context(env, self.installed("tmux", "zellij"))
        self.assertEqual((ctx.listed, ctx.inside), (["tmux"], {"tmux"}))
        self.assertEqual(ctx.label, "in tmux")
        ctx = md.detect_context({"HERDR_ENV": "1"}, self.installed("herdr"))
        self.assertEqual(ctx.listed, ["herdr"])
        # HERDR_ENV must be 1.
        ctx = md.detect_context({"HERDR_ENV": "0"}, self.installed("herdr"))
        self.assertEqual(ctx.inside, set())

    def test_nested(self):
        env = {"TMUX": "x", "ZELLIJ": "0"}
        ctx = md.detect_context(env, self.installed())
        self.assertEqual(ctx.listed, ["zellij", "tmux"])
        self.assertEqual(ctx.label, "in zellij and tmux")

    def test_multiplexer_option(self):
        env = {"TMUX": "x", "ZELLIJ": "0"}
        ctx = md.detect_context(env, self.installed(), "tmux")
        self.assertEqual((ctx.listed, ctx.inside), (["tmux"], {"tmux"}))
        ctx = md.detect_context({}, self.installed("tmux"), "herdr")
        self.assertEqual((ctx.listed, ctx.inside), (["herdr"], set()))


# ---------------------------------------------------------------- rows


def groups():
    tmux = md.Group(
        "tmux",
        [md.Session("tmux", "~", id="$0"), md.Session("tmux", "monopi", id="$1")],
        [md.Agent("tmux", "monopi", "$1", "pi", 2, "%7", "pi")],
    )
    zellij = md.Group(
        "zellij",
        [md.Session("zellij", "dotfiles"), md.Session("zellij", "old", exited=True)],
        [
            md.Agent(
                "zellij", "dotfiles", "dotfiles", "main", 0, "terminal_2", "claude"
            ),
            md.Agent(
                "zellij", "dotfiles", "dotfiles", "docs", 1, "terminal_5", "codex"
            ),
        ],
    )
    return [zellij, tmux]


class RowsTest(unittest.TestCase):
    def test_grouped_rows(self):
        rows = md.build_rows(groups(), md.SESSIONS, "")
        self.assertEqual(
            [(r.kind, r.mux, r.session.name if r.session else r.count) for r in rows],
            [
                ("group", "zellij", 2),
                ("session", "zellij", "dotfiles"),
                ("session", "zellij", "old"),
                ("group", "tmux", 2),
                ("session", "tmux", "~"),
                ("session", "tmux", "monopi"),
            ],
        )

    def test_filter(self):
        rows = md.build_rows(groups(), md.SESSIONS, "MONO")
        self.assertEqual([r.kind for r in rows], ["group", "session"])
        # Agents match on their name, session or tab.
        names = lambda q: [
            r.agent.name for r in md.build_rows(groups(), md.AGENTS, q) if r.agent
        ]
        self.assertEqual(names("codex"), ["codex"])
        self.assertEqual(names("dotf"), ["claude", "codex"])
        self.assertEqual(names("docs"), ["codex"])
        self.assertEqual(md.build_rows(groups(), md.AGENTS, "nothing"), [])

    def test_empty_loading_and_failing_groups(self):
        g = [
            md.Group("zellij", loading=True),
            md.Group("herdr", error="server not running"),
            md.Group("tmux"),
        ]
        rows = md.build_rows(g, md.SESSIONS, "")
        self.assertEqual(
            [(r.mux, r.note) for r in rows],
            [("zellij", "loading…"), ("herdr", "server not running"), ("tmux", "")],
        )
        # The agents list and a filtered list show only groups with items.
        self.assertEqual(md.build_rows(g, md.AGENTS, ""), [])
        self.assertEqual(md.build_rows(g, md.SESSIONS, "x"), [])

    def test_scroll_only_when_the_cursor_leaves_the_view(self):
        rows = md.build_rows(groups(), md.SESSIONS, "")
        # Rows 0..5; a view of 3 rows.
        self.assertEqual(md.scroll_offset(rows, 1, 0, 3), 0)
        self.assertEqual(md.scroll_offset(rows, 2, 0, 3), 0)
        self.assertEqual(md.scroll_offset(rows, 4, 0, 3), 2)
        self.assertEqual(md.scroll_offset(rows, 5, 2, 3), 3)
        self.assertEqual(md.scroll_offset(rows, 4, 3, 3), 3)
        # Going up to a group's first item shows the group's header.
        self.assertEqual(md.scroll_offset(rows, 4, 4, 3), 3)
        self.assertEqual(md.scroll_offset(rows, 1, 3, 3), 0)
        # The offset never leaves blank rows at the end.
        self.assertEqual(md.scroll_offset(rows, 5, 0, 10), 0)

    def test_jump_between_groups(self):
        items = md.items_of(md.build_rows(groups(), md.SESSIONS, ""))
        self.assertEqual(md.jump_group(items, 0, 1), 2)
        self.assertEqual(md.jump_group(items, 1, 1), 2)
        self.assertEqual(md.jump_group(items, 3, 1), 0)
        self.assertEqual(md.jump_group(items, 3, -1), 2)
        self.assertEqual(md.jump_group(items, 2, -1), 0)
        self.assertEqual(md.jump_group(items, 0, -1), 2)


def make_app(listed=("zellij", "tmux"), inside=(), runner=None, env=None, **options):
    ctx = md.Context(list(listed), set(inside))
    return md.App(
        ctx,
        md.Options(**options),
        runner or FakeRunner(),
        env if env is not None else {"HOME": "/home/me"},
    )


class CursorTest(unittest.TestCase):
    def test_cursor_stays_on_top_until_moved(self):
        app = make_app()
        app.set_group(groups()[1])
        self.assertEqual(app.selected().session.name, "~")
        app.set_group(groups()[0])
        self.assertEqual(app.selected().session.name, "dotfiles")

    def test_cursor_follows_its_item_across_a_refresh(self):
        app = make_app()
        for g in groups():
            app.set_group(g)
        app.handle(md.Event("key", "G"))
        self.assertEqual(app.selected().session.name, "monopi")
        zellij = groups()[0]
        zellij.sessions.insert(0, md.Session("zellij", "new"))
        app.set_group(zellij)
        self.assertEqual(app.selected().session.name, "monopi")
        # When the item is gone, the cursor stays in range.
        app.set_group(md.Group("tmux"))
        self.assertEqual(app.selected().session.name, "old")

    def test_keys_move_and_switch_lists(self):
        app = make_app()
        for g in groups():
            app.set_group(g)
        keys = lambda *ks: [app.handle(md.Event("key", k)) for k in ks]
        keys("j", "j")
        self.assertEqual(app.selected().session.name, "~")
        keys("alt+k")
        self.assertEqual(app.selected().session.name, "dotfiles")
        keys("alt+down")
        self.assertEqual(app.selected().session.name, "~")
        keys("home")
        self.assertEqual(app.selected().session.name, "dotfiles")
        keys("tab", "end")
        self.assertEqual(app.selected().agent.name, "pi")
        keys("k")
        self.assertEqual(app.selected().agent.name, "codex")

    def test_filter_mode(self):
        app = make_app()
        for g in groups():
            app.set_group(g)
        for k in ["/", "m", "o", "n"]:
            app.handle(md.Event("key", k))
        self.assertEqual(app.filter, "mon")
        self.assertEqual(app.selected().session.name, "monopi")
        app.handle(md.Event("key", "enter"))
        self.assertEqual((app.mode, app.filter), (None, "mon"))
        app.handle(md.Event("key", "esc"))
        self.assertEqual(app.filter, "")
        self.assertIsNone(app.result)
        app.handle(md.Event("key", "/"))
        app.handle(md.Event("key", "x"))
        app.handle(md.Event("key", "esc"))
        self.assertEqual((app.mode, app.filter), (None, ""))
        app.handle(md.Event("key", "q"))
        result = app.result
        assert result is not None
        self.assertEqual(result.code, 0)


# ---------------------------------------------------------------- actions


class CommandsTest(unittest.TestCase):
    def test_tmux(self):
        t = md.Tmux(FakeRunner(), {}, client="/dev/pts/3")
        s = md.Session("tmux", "monopi", id="$1")
        a = md.Agent("tmux", "monopi", "$1", "pi", 2, "%7", "pi")
        self.assertEqual(
            t.switch_session(s, True).steps,
            [["tmux", "switch-client", "-c", "/dev/pts/3", "-t", "$1"]],
        )
        self.assertEqual(
            t.switch_session(s, False).attach, ["tmux", "attach-session", "-t", "$1"]
        )
        self.assertEqual(
            t.switch_agent(a, True, None).steps,
            [["tmux", "switch-client", "-c", "/dev/pts/3", "-t", "%7"]],
        )
        outside = t.switch_agent(a, False, None)
        self.assertEqual(
            (outside.steps, outside.attach),
            ([], ["tmux", "attach-session", "-t", "%7"]),
        )
        self.assertEqual(
            t.create("new", "/d", True).steps,
            [
                ["tmux", "new-session", "-d", "-s", "new", "-c", "/d"],
                ["tmux", "switch-client", "-c", "/dev/pts/3", "-t", "=new"],
            ],
        )
        self.assertEqual(
            t.create("new", "/d", False).attach,
            ["tmux", "new-session", "-s", "new", "-c", "/d"],
        )
        self.assertEqual(
            t.rename(s, "x").steps, [["tmux", "rename-session", "-t", "$1", "x"]]
        )
        self.assertEqual(t.kill(s).steps, [["tmux", "kill-session", "-t", "$1"]])
        # Without --client, tmux picks the client.
        plain_tmux = md.Tmux(FakeRunner(), {})
        self.assertEqual(
            plain_tmux.switch_session(s, True).steps,
            [["tmux", "switch-client", "-t", "$1"]],
        )

    def test_zellij(self):
        z = md.Zellij(FakeRunner(), {})
        s = md.Session("zellij", "dots")
        gone = md.Session("zellij", "old", exited=True)
        a = md.Agent(
            "zellij", "dots", "dots", "main", 0, "terminal_2", "claude", tab_id="4"
        )
        self.assertEqual(
            z.switch_session(s, True).steps,
            [["zellij", "action", "switch-session", "dots"]],
        )
        self.assertEqual(
            z.switch_session(gone, False).attach, ["zellij", "attach", "old"]
        )
        self.assertEqual(
            z.switch_agent(a, True, "dots").steps,
            [["zellij", "action", "focus-pane-id", "terminal_2"]],
        )
        self.assertEqual(
            z.switch_agent(a, True, "other").steps,
            [["zellij", "action", "switch-session", "dots", "--pane-id", "terminal_2"]],
        )
        outside = z.switch_agent(a, False, None)
        self.assertEqual(outside.attach, ["zellij", "attach", "dots"])
        self.assertEqual(
            outside.helper,
            [
                sys.executable,
                md.SCRIPT,
                "--zellij-focus-pane",
                "dots",
                "4",
                "terminal_2",
            ],
        )
        self.assertEqual(
            z.create("new", "/d", True).steps,
            [["zellij", "action", "switch-session", "new", "--cwd", "/d"]],
        )
        created = z.create("new", "/d", False)
        self.assertEqual(
            (created.attach, created.cwd), (["zellij", "--session", "new"], "/d")
        )
        self.assertEqual(
            z.rename(s, "x").steps,
            [["zellij", "--session", "dots", "action", "rename-session", "x"]],
        )
        self.assertEqual(z.kill(s).steps, [["zellij", "kill-session", "dots"]])
        self.assertEqual(z.kill(gone).steps, [["zellij", "delete-session", "old"]])

    def test_herdr(self):
        h = md.Herdr(FakeRunner(), {})
        s = md.Session("herdr", "repo", id="w1")
        a = md.Agent("herdr", "repo", "w1", "1", 1, "w1:p2", "codex")
        inside = h.switch_session(s, True)
        self.assertEqual(
            (inside.steps, inside.attach),
            ([["herdr", "workspace", "focus", "w1"]], None),
        )
        self.assertEqual(h.switch_session(s, False).attach, ["herdr"])
        self.assertEqual(
            h.switch_agent(a, True, None).steps, [["herdr", "agent", "focus", "w1:p2"]]
        )
        self.assertEqual(h.switch_agent(a, False, None).attach, ["herdr"])
        self.assertEqual(
            h.create("new", "/d", True).steps,
            [
                [
                    "herdr",
                    "workspace",
                    "create",
                    "--cwd",
                    "/d",
                    "--label",
                    "new",
                    "--focus",
                ]
            ],
        )
        self.assertEqual(
            h.rename(s, "x").steps, [["herdr", "workspace", "rename", "w1", "x"]]
        )
        self.assertEqual(h.kill(s).steps, [["herdr", "workspace", "close", "w1"]])


class ActionsTest(unittest.TestCase):
    def app(self, inside=("tmux",), answers=None, **options):
        runner = FakeRunner(answers)
        app = make_app(listed=("tmux",), inside=inside, runner=runner, **options)
        app.set_group(groups()[1])
        return app, runner

    def test_switch_inside_exits_after_the_commands(self):
        app, runner = self.app()
        app.handle(md.Event("key", "j"))
        app.handle(md.Event("key", "enter"))
        self.assertEqual(runner.calls, [["tmux", "switch-client", "-t", "$1"]])
        self.assertEqual((app.result.code, app.result.plan), (0, None))

    def test_switch_outside_hands_over_to_the_client(self):
        app, runner = self.app(inside=())
        app.handle(md.Event("key", "enter"))
        self.assertEqual(runner.calls, [])
        self.assertEqual(app.result.plan.attach, ["tmux", "attach-session", "-t", "$0"])

    def test_failed_switch_shows_the_error(self):
        failure = md.Result(1, "", "can't find session: $1\n")
        app, _ = self.app(answers={("tmux", "switch-client"): failure})
        app.handle(md.Event("key", "j"))
        app.handle(md.Event("key", "enter"))
        self.assertIsNone(app.result)
        self.assertEqual(app.toast[:2], ("can't find session: $1", True))

    def test_enter_on_the_current_session_closes(self):
        app, runner = self.app()
        app.groups["tmux"].sessions[0].current = True
        app.handle(md.Event("key", "enter"))
        self.assertEqual((runner.calls, app.result.code), ([], 0))

    def test_click_selects_and_a_second_click_switches(self):
        app, runner = self.app()
        app.render(100, 30)
        row = next(h for h in app.hits if h.which == md.SESSIONS and h.index == 1)
        app.handle(md.Event("mouse", button=0, x=row.x0, y=row.y0))
        self.assertEqual(app.selected().session.name, "monopi")
        self.assertIsNone(app.result)
        app.handle(md.Event("mouse", button=0, x=row.x0, y=row.y0))
        self.assertEqual(runner.calls, [["tmux", "switch-client", "-t", "$1"]])

    def test_wheel_moves_the_list_under_the_pointer(self):
        app, _ = self.app()
        app.render(100, 30)
        agents = next(h for h in app.hits if h.which == md.AGENTS and h.index < 0)
        app.handle(md.Event("mouse", button=65, x=agents.x0 + 2, y=agents.y0 + 2))
        self.assertEqual(app.focus, md.AGENTS)

    def test_rename(self):
        app, runner = self.app()
        app.handle(md.Event("key", "r"))
        self.assertEqual((app.mode, app.input), ("rename", "~"))
        for k in ["ctrl+u", "a", ".", "b", "enter"]:
            app.handle(md.Event("key", k))
        self.assertEqual(runner.calls, [["tmux", "rename-session", "-t", "$0", "a-b"]])
        self.assertIsNone(app.result)

    def test_rename_and_kill_need_a_session(self):
        app, _ = self.app()
        app.handle(md.Event("key", "tab"))
        app.handle(md.Event("key", "x"))
        self.assertIsNone(app.mode)
        self.assertTrue(app.toast[1])

    def test_kill_asks_first(self):
        app, runner = self.app()
        app.handle(md.Event("key", "j"))
        app.handle(md.Event("key", "x"))
        lines = [plain(line) for line in app.render(100, 30)]
        self.assertTrue(any("Kill tmux session monopi?" in line for line in lines))
        self.assertTrue(
            any("Its 1 agent (pi) stops with it." in line for line in lines)
        )
        app.handle(md.Event("key", "n"))
        self.assertEqual(runner.calls, [])
        app.handle(md.Event("key", "x"))
        app.handle(md.Event("key", "y"))
        self.assertEqual(runner.calls, [["tmux", "kill-session", "-t", "$1"]])
        self.assertEqual([s.name for s in app.groups["tmux"].sessions], ["~"])

    def test_create_switches_to_an_existing_name(self):
        answers = {
            (
                "tmux",
                "list-sessions",
            ): "~\t$0\t1\t1\t0\t/home/me\nrepo\t$4\t2\t1\t0\t/r\n",
            ("git",): "/work/repo\n",
        }
        app, runner = self.app(answers=answers, directory="/work/repo/sub")
        for k in ["n", "enter"]:
            app.handle(md.Event("key", k))
        self.assertEqual(runner.calls[-1], ["tmux", "switch-client", "-t", "$4"])
        self.assertEqual(app.result.code, 0)

    def test_create_a_new_session(self):
        answers = {("git",): md.Result(128, "", "not a git repository")}
        app, runner = self.app(answers=answers, directory="/work/my.dir")
        app.handle(md.Event("key", "n"))
        lines = [plain(line) for line in app.render(100, 30)]
        self.assertTrue(any("empty: my-dir" in line for line in lines))
        for k in ["enter"]:
            app.handle(md.Event("key", k))
        self.assertEqual(
            runner.calls[-2:],
            [
                ["tmux", "new-session", "-d", "-s", "my-dir", "-c", "/work/my.dir"],
                ["tmux", "switch-client", "-t", "=my-dir"],
            ],
        )

    def test_new_dialog_cycles_the_multiplexers(self):
        app = make_app(listed=("zellij", "herdr", "tmux"))
        app.handle(md.Event("key", "n"))
        self.assertEqual(app.new_mux, "zellij")
        app.handle(md.Event("key", "tab"))
        app.handle(md.Event("key", "tab"))
        self.assertEqual(app.new_mux, "tmux")
        app.handle(md.Event("key", "tab"))
        self.assertEqual(app.new_mux, "zellij")


class NamingTest(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(md.sanitize_name("a.b/c:d e"), "a-b-c-d-e")
        self.assertEqual(md.sanitize_name("~_ok-1"), "~_ok-1")
        self.assertEqual(md.sanitize_name("café"), "café")

    def test_directory_label(self):
        self.assertEqual(md.dir_label("/home/me", "/home/me", None), "~")
        self.assertEqual(md.dir_label("/home/me/", "/home/me", "/home/me"), "~")
        self.assertEqual(md.dir_label("/w/repo/src", "/home/me", "/w/repo"), "repo")
        self.assertEqual(md.dir_label("/w/plain", "/home/me", None), "plain")
        self.assertEqual(md.dir_label("/", "/home/me", None), "/")


# ---------------------------------------------------------------- input


class InputTest(unittest.TestCase):
    def keys(self, data):
        return [e.key if e.kind == "key" else e for e in md.parse_input(data)]

    def test_plain_keys_and_several_in_one_read(self):
        self.assertEqual(self.keys("jk\r\t/"), ["j", "k", "enter", "tab", "/"])
        self.assertEqual(self.keys("\x03\x0c\x7f"), ["ctrl+c", "ctrl+l", "backspace"])

    def test_escape_and_alt(self):
        self.assertEqual(self.keys("\x1b"), ["esc"])
        self.assertEqual(self.keys("\x1bj\x1bk"), ["alt+j", "alt+k"])
        self.assertEqual(self.keys("\x1b\x1b[A"), ["alt+up"])

    def test_sequences_and_modifiers(self):
        self.assertEqual(
            self.keys("\x1b[A\x1bOB\x1b[H\x1b[4~"), ["up", "down", "home", "end"]
        )
        self.assertEqual(self.keys("\x1b[1;3A\x1b[1;3B"), ["alt+up", "alt+down"])
        self.assertEqual(self.keys("\x1b[1;5H\x1b[1;2F"), ["ctrl+home", "shift+end"])

    def test_mouse(self):
        events = md.parse_input("\x1b[<0;10;5M\x1b[<0;10;5m\x1b[<65;3;4Mj")
        self.assertEqual(
            events,
            [
                md.Event("mouse", button=0, x=9, y=4),
                md.Event("mouse", button=65, x=2, y=3),
                md.Event("key", "j"),
            ],
        )
        # Modifier bits are dropped.
        self.assertEqual(md.parse_input("\x1b[<16;1;1M")[0].button, 0)

    def test_late_terminal_replies_are_ignored(self):
        self.assertEqual(self.keys("\x1b]11;rgb:1919/1717/2424\x1b\\q"), ["q"])

    def test_background_color_reply(self):
        self.assertTrue(md.luminance_is_dark(b"\x1b]11;rgb:1919/1717/2424\x07"))
        self.assertFalse(md.luminance_is_dark(b"\x1b]11;rgb:faf4/f4f4/eded\x1b\\"))
        self.assertIsNone(md.luminance_is_dark(b""))


# ---------------------------------------------------------------- ANSI


class AnsiTest(unittest.TestCase):
    def test_width(self):
        self.assertEqual(md.width("abc"), 3)
        self.assertEqual(md.width("\x1b[1;38;2;1;2;3mab\x1b[0m"), 2)
        self.assertEqual(md.width("日本"), 4)
        self.assertEqual(md.width("é"), 1)

    def test_cut_carries_colors(self):
        s = "\x1b[31mabc\x1b[0mdef"
        self.assertEqual(md.cut(s, 1, 4), "\x1b[31mbc\x1b[0md\x1b[0m")
        self.assertEqual(plain(md.cut("日本語", 0, 3)), "日")

    def test_fit(self):
        md.Canvas.paint_bg = False
        try:
            self.assertEqual(plain(md.fit("abcdef", 4)), "abc…")
            self.assertEqual(plain(md.fit("ab", 4)), "ab  ")
            self.assertEqual(md.width(md.fit("日本語", 4)), 4)
        finally:
            md.Canvas.paint_bg = True

    def test_sanitize_capture(self):
        text = (
            "\x1b[?25l\x1b[1;31mred\x1b[0m\x1b]0;title\x07 ok\r\n"
            "a\tb\x07\n"
            "\x1b[38:2::1:2:3mcolon\x1b[m\x1b[2J\n"
            "   \n"
            "\n"
        )
        self.assertEqual(
            md.sanitize_capture(text),
            ["\x1b[1;31mred\x1b[0m ok", "a       b", "\x1b[38:2::1:2:3mcolon\x1b[m"],
        )

    def test_resets_background(self):
        self.assertTrue(md.resets_background(""))
        self.assertTrue(md.resets_background("0"))
        self.assertTrue(md.resets_background("1;49"))
        self.assertTrue(md.resets_background("22"))
        self.assertFalse(md.resets_background("38;5;0"))
        self.assertFalse(md.resets_background("38;2;0;0;0;1"))
        self.assertTrue(md.resets_background("38;2;0;0;0;0"))


# ---------------------------------------------------------------- screen


class ScreenTest(unittest.TestCase):
    def app(self):
        app = make_app(env={"HOME": "/home/me"})
        for g in groups():
            app.set_group(g)
        return app

    def test_every_line_fills_the_width(self):
        app = self.app()
        for cols, rows in [(120, 30), (60, 20), (40, 12), (30, 8)]:
            lines = app.render(cols, rows)
            self.assertEqual(len(lines), rows)
            self.assertEqual({md.width(line) for line in lines}, {cols})

    def test_layout(self):
        app = self.app()
        app.groups["tmux"].sessions[1].current = True
        lines = [plain(line) for line in app.render(120, 30)]
        text = "\n".join(lines)
        self.assertIn("outside any multiplexer", lines[0])
        self.assertIn("4 sessions · 3 agents", lines[0])
        self.assertIn("Sessions", lines[1])
        self.assertIn("Preview", lines[1])
        self.assertLess(text.index("zellij ─"), text.index("tmux ─"))
        self.assertIn("● monopi", text)
        self.assertIn("exited", text)
        self.assertIn("✻ claude dotfiles › main", text)
        self.assertIn("◎ codex  dotfiles › docs", text)
        self.assertIn("?  help", lines[-1])

    def test_agent_names_line_up_with_the_widest(self):
        app = self.app()
        app.groups["tmux"].agents.append(
            md.Agent("tmux", "~", "$0", "w", 0, "%9", "cursor-agent")
        )
        text = "\n".join(plain(line) for line in app.render(120, 30))
        self.assertIn("➤ cursor-agent ~ › w", text)
        self.assertIn("✻ claude       dotfiles › main", text)

    def test_agent_name_column_has_a_cap(self):
        app = self.app()
        app.groups["tmux"].agents.append(
            md.Agent("tmux", "~", "$0", "w", 0, "%9", "a-very-long-agent-name")
        )
        text = "\n".join(plain(line) for line in app.render(120, 30))
        self.assertIn("◇ a-very-long-a… ~ › w", text)
        self.assertIn("✻ claude         dotfiles › main", text)

    def test_filter_keeps_the_agent_name_column(self):
        app = self.app()
        app.filter = "claude"
        text = "\n".join(plain(line) for line in app.render(120, 30))
        self.assertIn("✻ claude dotfiles › main", text)
        app.groups["tmux"].agents[0] = md.Agent(
            "tmux", "monopi", "$1", "pi", 2, "%7", "opencode"
        )
        text = "\n".join(plain(line) for line in app.render(120, 30))
        self.assertIn("✻ claude   dotfiles › main", text)

    def test_narrow_hides_the_preview(self):
        app = self.app()
        self.assertNotIn("Preview", plain(app.render(71, 30)[1]))
        self.assertIn("Preview", plain(app.render(72, 30)[1]))

    def test_too_small(self):
        lines = [plain(line) for line in self.app().render(39, 20)]
        self.assertTrue(
            any("Make the window at least 40×12." in line for line in lines)
        )

    def test_preview_shows_the_capture(self):
        app = self.app()
        key = md.item_key(app.selected())
        app.previews[key] = md.Preview(
            app.generation["zellij"], ["\x1b[32mhello\x1b[0m"]
        )
        lines = [plain(line) for line in app.render(120, 30)]
        self.assertTrue(any("hello" in line for line in lines))

    def test_herdr_status_and_group_error(self):
        app = make_app(listed=("herdr",), inside=("herdr",))
        app.set_group(
            md.Group(
                "herdr",
                [md.Session("herdr", "repo", id="w1")],
                [
                    md.Agent(
                        "herdr", "repo", "w1", "1", 1, "w1:p1", "pi", status="blocked"
                    )
                ],
            )
        )
        text = "\n".join(plain(line) for line in app.render(120, 30))
        self.assertIn("× blocked", text)
        app.set_group(md.Group("herdr", error="server not running"))
        text = "\n".join(plain(line) for line in app.render(120, 30))
        self.assertIn("server not running", text)

    def test_help(self):
        app = self.app()
        app.handle(md.Event("key", "?"))
        text = "\n".join(plain(line) for line in app.render(120, 30))
        self.assertIn("next / previous multiplexer", text)
        app.handle(md.Event("key", "x"))
        self.assertIsNone(app.mode)


if __name__ == "__main__":
    unittest.main()
