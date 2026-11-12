# multiplexer-dashboard

## Problem Statement

I work in three terminal multiplexers: zellij, herdr and tmux. Each has its
own session picker: zellij's session-manager plugin, tmux's `choose-tree -S`,
and herdr's sidebar and goto picker. They look and behave differently, and
each shows only its own sessions. Only herdr's sidebar shows the coding
agents (claude, codex, opencode, pi, and so on) that run in my panes; in tmux
and zellij I have to remember which session and tab each agent lives in.
Outside any multiplexer there is no picker at all: I have to know which
multiplexer holds the session I want and type its attach command.

## Solution

`multiplexer-dashboard`: one fullscreen terminal app that lists sessions and
coding agents and switches to the one I pick. It opens in a floating pane
from a key binding in tmux, zellij and herdr, replacing zellij's
session-manager and tmux's `choose-tree -S`, or runs directly in a shell
outside any multiplexer.

The screen follows layout A of the prototypes: a left column with a Sessions
list above an Agents list, both grouped by multiplexer, and on the right a
preview of the selected session's focused pane or the selected agent's pane,
in that pane's own colors. Enter switches to the selected session, or jumps
to the selected agent's pane. The app also filters as you type, and creates,
renames and kills sessions.

Inside a multiplexer the app lists only that multiplexer, the way
`multiplexer-new-session` picks the current one. When nested (zellij inside
tmux), it lists each multiplexer it runs in. Outside any multiplexer it lists
every installed one, in the order zellij, herdr, tmux, and switching replaces
the app with an attaching client.

The app is a single executable Python script that uses only the standard
library of Python 3.9 or later, so it can be copied into any `bin` directory.

## User Stories

Opening and layout

1. As a tmux user, I want a key binding that opens the dashboard in a floating pane, so that I can pick a session without leaving my work.
2. As a zellij user, I want the dashboard in a floating pane in place of the session-manager plugin, so that zellij and tmux pick sessions the same way.
3. As a herdr user, I want the dashboard as a herdr popup command, so that I get the same picker in herdr.
4. As a user in a plain shell, I want to run `multiplexer-dashboard` and see every multiplexer's sessions, so that I can attach to any of them from one place.
5. As a user, I want sessions and agents grouped under zellij, herdr and tmux headers in that order, so that the hierarchy is the same everywhere.
6. As a user inside one multiplexer, I want only that multiplexer's sessions and agents, so that every row is one I can switch to.
7. As a user of zellij inside tmux, I want both multiplexers listed, each switching its own client, so that nesting does not hide sessions.
8. As a user, I want the Sessions list above the Agents list in a left column, like herdr's sidebar, so that I see both at once.
9. As a user, I want a preview of the selected session's focused pane or the selected agent's pane, so that I can tell similar sessions apart before switching.
10. As a user, I want the preview in the pane's own colors, so that it looks like the pane I will land in.
11. As a user with a narrow popup, I want the preview to disappear below about 72 columns, so that the lists stay readable.
12. As a user with a tiny window, I want a message asking for at least 40×12 cells instead of a broken layout.
13. As a user, I want the selected row and the focused list clearly highlighted, so that I always know what Enter does.
14. As a user, I want a header with the context (outside, in tmux, ...) and session and agent counts, so that I know what I am looking at.
15. As a user, I want a footer with the main keys, so that I do not need to read documentation.
16. As a user, I want a help dialog (`?`) with every key, so that I can find the rarer ones.

Sessions

17. As a user, I want each session row to show its name, its number of tabs or windows, and how many agents run in it, so that I can recognize it.
18. As a user, I want the session I am in marked, so that I do not switch to it by mistake.
19. As a tmux user, I want sessions attached by another client marked, so that I know someone or something else is there.
20. As a zellij user, I want exited sessions that zellij can resurrect listed and dimmed, with their age, so that I can bring one back.
21. As a zellij user, I want Enter on an exited session to resurrect it, so that I do not need `zellij attach` by hand.
22. As a herdr user, I want the workspaces of the default herdr server listed as sessions, as `multiplexer-new-session` treats them, so that herdr fits the same model.
23. As a user, I want sessions in each multiplexer's own order (creation order for zellij and tmux, workspace number for herdr), so that the list matches what the multiplexer shows.

Agents

24. As a user, I want every coding agent across all sessions listed with its name, session and tab, so that I can find an agent without remembering where I started it.
25. As a user, I want Enter on an agent to switch to its session, tab and pane, so that I land in front of it.
26. As a herdr user, I want herdr's own agent status (working, idle, blocked, done) shown, so that I can see which agent needs me.
27. As a herdr user, I want blocked agents to stand out, so that an agent waiting for permission is not forgotten.
28. As a user, I want agents recognized by their program (claude, codex, opencode, pi, gemini, aider, amp, crush, goose, cursor-agent and others), even when they run through node or another interpreter, so that the list is complete.
29. As a user with a less common agent, I want to add program names to the recognized list without editing the script, so that my agent shows up.
30. As a user, I want sessions to show their agent count, so that I can see from the Sessions list where my agents are.

Switching

31. As a tmux user inside tmux, I want Enter to switch the client that opened the dashboard, so that the right terminal changes session.
32. As a zellij user inside zellij, I want Enter to switch the current client to the selected session, and to the agent's pane when an agent is selected.
33. As a herdr user inside herdr, I want Enter to focus the selected workspace or agent.
34. As a user outside any multiplexer, I want Enter to replace the dashboard with an attaching client focused on the selected session or agent pane, so that it works like `tmux attach` or `zellij attach`.
35. As a user, I want the dashboard to close after a successful switch, so that I do not have to close the popup myself.
36. As a user, I want a failed switch to show the multiplexer's error in the dashboard instead of closing it, so that I know what went wrong.

Filtering and navigation

37. As a user, I want `/` to filter both lists as I type, matching session names and agent names, sessions and tabs, so that I can narrow a long list quickly.
38. As a user, I want Escape to clear the filter, and Enter to keep it and go back to moving, so that filtering never traps me.
39. As a user, I want j/k and the up/down keys to move, g/G and Home/End to jump to the ends, and Tab to switch between the lists.
40. As a user, I want Alt+j/k (or Alt+arrows) to jump to the next or previous multiplexer group, so that I can move quickly in a long list.
41. As a user, I want to click a row to select it, click it again to switch, and scroll a list with the mouse wheel.
42. As a user, I want the lists to scroll only when the cursor leaves the view, so that a row does not move away from the mouse pointer.
43. As a user, I want q or Escape to close the dashboard without doing anything.

Managing sessions

44. As a user, I want `n` to create a session, named the way `multiplexer-new-session` names it (`~` for the home directory, the repository name inside a git repository, the directory name otherwise), so that names stay the same whichever tool created them.
45. As a user, I want to type a name in the new-session dialog, with an empty name meaning the automatic name, so that I can name a session for one part of a repository.
46. As a user outside any multiplexer, I want the new-session dialog to target the multiplexer of the selected row, and Tab in the dialog to cycle through the listed multiplexers, so that I can create a session in any of them.
47. As a user, I want creating a session whose name exists to switch to that session instead, as `multiplexer-new-session` does, so that I do not get duplicates.
48. As a user, I want `r` to rename the selected session in a dialog prefilled with the current name.
49. As a user, I want `x` to kill the selected session after a confirmation that names the agents that will stop with it, and warns when it is the current session.
50. As a zellij user, I want `x` on an exited session to delete it, so that I can clean up sessions I will not resurrect.
51. As a user, I want names sanitized the way `multiplexer-new-session` does (every character other than a letter, a digit, `_`, `-` or `~` becomes `-`), so that a name is valid in all three multiplexers.

Freshness and speed

52. As a user, I want the dashboard to open at once and fill in the lists as soon as the multiplexers answer, so that a slow multiplexer does not block the others.
53. As a user, I want the lists refreshed every few seconds while the dashboard is open, and on Ctrl+L, so that new agents and sessions appear without reopening it and a garbled screen can be repainted.
54. As a user, I want the preview to update shortly after the cursor stops, without making the cursor lag.
55. As a user, I want a multiplexer that is not installed to be left out, and one that fails (such as a herdr server that is not running) to show the reason in its group header, so that one broken multiplexer does not break the dashboard.

Look and terminal behavior

56. As a user, I want the Rose Pine colors in a dark terminal and Rose Pine Dawn in a light one, detected from the terminal's background color, so that it matches the rest of my setup.
57. As a user, I want `--theme light|dark` to override detection, so that it works in terminals that do not report their background.
58. As a user, I want `--no-bg` to keep the terminal's own background, so that it blends into a terminal with a different background.
59. As a user, I want my terminal restored (screen, cursor, mouse mode, line settings) however the dashboard exits, including on an error or Ctrl+C.
60. As a user, I want the dashboard to redraw correctly after the popup or terminal is resized.

Portability

61. As a user, I want a single file that needs only Python 3.9 or later, so that I can drop it into my dotfiles `bin` and use it on NixOS, other Linux and macOS.
62. As a user, I want command-line flags matching `multiplexer-new-session` (`--multiplexer`, `--client`, `--dir`), so that key bindings look the same.

## Implementation Decisions

Delivery and language

- One executable file, `multiplexer-dashboard`, with a Python 3 shebang and no file extension, like the scripts in the dotfiles `bin`.
- Python 3.9 or later, standard library only, and no `curses`. Python 3.9 rules out `match`, `X | Y` type unions evaluated at runtime (use `typing.Optional`/`Union` or `from __future__ import annotations`), `tomllib`, and `zip(strict=...)`.
- The file has these sections, from the bottom up: the terminal layer, the painting helpers, the multiplexer backends, the pure model, the view, and the app controller. Only the terminal layer and the backends' command runner touch the outside world.

Terminal layer (from the fullscreen prototype)

- All terminal I/O goes through `/dev/tty` in raw mode. Stdout and stderr are left alone, so that errors after exit reach the shell.
- On start it enters the alternate screen, hides the cursor, and turns on SGR mouse reporting (modes 1000 and 1006). On exit, including on exceptions and signals, it restores all of them and the saved termios settings.
- Each frame is a list of exactly-`cols`-wide painted lines. Only lines that changed since the last frame are written, inside synchronized-output markers (mode 2026). A resize (SIGWINCH) or a change in line count forces a full redraw.
- Input parsing turns a read into events. ESC followed by `[` or `O` starts a CSI/SS3 sequence. A lone ESC is Escape. ESC followed by any other key is Alt with that key. `ESC [ 1 ; m X` adds modifiers (shift 1, alt 2, ctrl 4) to arrows and Home/End. `ESC [ < b ; x ; y M` is a mouse press, and the m form (release) is ignored. Several keys in one read become several events. The Kitty keyboard protocol is not used.
- Theme detection writes an OSC 11 query and waits up to 250 ms for an `rgb:` reply. A relative luminance below 0.5 means dark, and no reply means dark.
- Colors are 24-bit SGR from the Rose Pine and Rose Pine Dawn palettes. Captured pane content keeps its own escape sequences, limited to SGR (see Preview).
- Width uses `unicodedata`: East Asian Wide and Fullwidth characters count 2 cells, combining characters 0, everything else 1. Truncation keeps escape sequences and adds `…`. Overlays (dialogs) cut base lines at cell positions and carry the active SGR state across the cut.
- Dialogs (new, rename, kill, help) are centered boxes drawn over the screen, which is redrawn with every color mixed toward the background.

Model (pure, unit-tested)

- A snapshot holds one entry per listed multiplexer: its name, an optional error, its sessions and its agents. A session has a name, a multiplexer-specific id (herdr workspace id, tmux session id), the directory of its focused pane, its creation time, its number of tabs or windows, and flags for attached, exited and current. An agent has its multiplexer, session, tab (name and index), pane id, agent name, directory, and an optional status (herdr only).
- Context detection reads `TMUX`, `ZELLIJ` and `HERDR_ENV=1`. With any of them set, the listed multiplexers are the detected ones. With none, they are the installed ones (found on `PATH`). Either way the order is zellij, herdr, tmux. `--multiplexer` limits the list to one multiplexer and counts as inside it when its variable is set.
- Rows for each list come from the snapshot and the filter: a group header per multiplexer with matching items, then its items. The filter is a case-insensitive substring match on session names, and on agent name, session and tab.
- Each list keeps a cursor (an item index) and a scroll offset. The offset changes only when the cursor would leave the view, and keeps a group's header visible above its first item.

Backends (one per multiplexer)

- Each backend has three parts. Pure parsers turn a command's output into model objects. Pure command builders return argument lists for each action. A command runner (`subprocess.run`, no shell, with a timeout) is the only impure part, and every backend shares it.
- Agent detection matches a pane's foreground command against a list of agent program names. When the foreground program is an interpreter (node, bun, deno, python), the name comes from its arguments: the basename of the first argument that is not an option, for example `.../bin/gemini`. The default list is claude, codex, opencode, pi, gemini, aider, amp, crush, goose, cursor-agent, qwen, droid and copilot. `MULTIPLEXER_DASHBOARD_AGENTS` (comma-separated) adds names. There is no config file.
- tmux:
  - Sessions come from `list-sessions -F` with name, id, created, windows, attached and path, tab-separated.
  - Panes come from one `list-panes -a -F` call with session, window index and name, pane id, `pane_current_command`, `pane_pid` and path.
  - For interpreter panes, the arguments come from one `ps -A -o pid=,ppid=,args=` snapshot: the deepest descendant of the pane's process that is in the agent list. This works on Linux and macOS.
  - The current session comes from `display-message -p` for `--client`, or for the calling client.
- zellij:
  - Sessions come from `list-sessions --no-formatting`, parsing the name, the "Created … ago" age, `(current)`, and the EXITED marker for resurrectable sessions.
  - Panes come from `zellij --session NAME action list-panes -a -j` for each running session, run in parallel threads. Plugin panes are skipped.
  - Agents come from `pane_command`, the foreground command line (checked against zellij 0.45.1). Tabs are counted as distinct `tab_id` values.
  - The current session is `ZELLIJ_SESSION_NAME`.
- herdr:
  - Workspaces come from `herdr workspace list`, and agents with their status from `herdr agent list`, both JSON on the default server.
  - The tab count and the agents' tab names come from the workspace and tab commands; the exact call is chosen during implementation.
  - The current workspace is the one marked focused, and only counts when the app runs inside herdr.
  - When the server does not answer, the group header shows "server not running". Creating a herdr session then starts the server in the background, as `multiplexer-new-session` does.
- All `HERDR_*` variables are passed through unchanged, because herdr inside herdr talks to the running server through them.

Actions (built as argument lists; the prototype's command log holds the full matrix)

- Switching to a session:
  - tmux: `switch-client -c CLIENT -t =NAME` inside, `attach-session -t =NAME` outside.
  - zellij: `action switch-session NAME` inside, `attach NAME` outside. This resurrects an exited session.
  - herdr: `workspace focus ID`, and outside also starting `herdr` to attach.
- Jumping to an agent:
  - tmux: `switch-client -t PANE` inside. Outside: select the pane's window and the pane, then attach to the session.
  - zellij: `action focus-pane-id` when the agent is in the current session, `action switch-session SESSION --pane-id PANE` otherwise, and outside `zellij --session SESSION action focus-pane-id PANE` before attaching.
  - herdr: `agent focus PANE`, and outside also attaching.
- Outside a multiplexer, the app restores the terminal and then `exec`s the attach command (`os.execvp`), so that the client replaces the dashboard.
- Creating a session reimplements `multiplexer-new-session`'s behavior inside the script, so that the script stays standalone:
  - the directory label and name sanitizing;
  - switching to an existing name instead of creating a duplicate;
  - the directory: the current directory by default, `--dir` overrides it, and inside herdr it is the current pane's directory;
  - the per-multiplexer create commands.
- Renaming:
  - tmux: `rename-session -t =OLD NEW`.
  - zellij: `zellij --session OLD action rename-session NEW`.
  - herdr: `workspace rename ID NEW`.
  - Exited zellij sessions cannot be renamed.
- Killing:
  - tmux: `kill-session -t =NAME`.
  - zellij: `kill-session NAME`, or `delete-session NAME` for an exited session.
  - herdr: `workspace close ID`.
  - Killing the current session is allowed after the warning.
- A successful switch exits with status 0. A failed command shows its stderr as a toast and keeps the dashboard open. Create, rename and kill refresh the snapshot. Create also switches to the new session and exits.

Loading, refresh and preview

- The first frame draws at once with empty groups marked as loading. A worker thread loads each multiplexer's snapshot and posts it to the main loop through a queue, and the main loop's `select` wakes on a self-pipe.
- The snapshot is reloaded every 2 seconds while the dashboard is open, and on Ctrl+L, which also forces a full redraw. A reload keeps each cursor on the same session or agent when it still exists.
- The preview is captured 100 ms after the cursor stops, on a worker thread, and cached per pane until the next refresh:
  - tmux: `capture-pane -e -p -t PANE`, or `-t =SESSION:` for a session's active pane.
  - zellij: `zellij --session SESSION action dump-screen --ansi --pane-id PANE`. Checked to work from outside the session.
  - herdr: `herdr pane read PANE --source visible --format ansi`.
- For a session row, the preview pane is the focused pane of the session's active tab.
- Captured text is sanitized: SGR sequences are kept, and every other escape sequence and control character is dropped. Trailing blank lines are dropped, and the bottom of the capture that fits is shown.

Key bindings and flags

- Keys:
  - j/k and up/down move. g/G and Home/End jump to the ends. Alt+j/k and Alt+up/down jump between groups.
  - Tab switches between the lists.
  - Enter switches. `/` filters. `n` creates, `r` renames, `x` kills.
  - Ctrl+L refreshes and redraws the screen, `?` opens the help, q or Escape quits, and Ctrl+C always quits.
- Mouse: a click selects, a click on the selected row switches, and the wheel moves the cursor in the list under the pointer.
- Flags: `--multiplexer tmux|zellij|herdr`, `--client CLIENT` (tmux), `--dir DIR` (new sessions), `--theme auto|light|dark`, and `--no-bg`.

Integration (documented in the README; changing the dotfiles is a follow-up)

- tmux 3.8: `bind tab new-pane -x60% -y50% -X20% -Y25% -E "multiplexer-dashboard --client '#{client_name}'"` replaces the `choose-tree -hks` binding. The exact floating-pane flags are checked against the existing binding.
- zellij: `Run "multiplexer-dashboard" { floating true; close_on_exit true; }`, with a width and height, replaces the `LaunchOrFocusPlugin "session-manager"` bindings.
- herdr: a `[[keys.command]]` entry of type popup with `command = "multiplexer-dashboard"`, with a width and height.

## Testing Decisions

- A good test checks behavior visible from outside the code under test: the rows and text on the screen, the commands that would run, the session the client ends up in. It never checks private helpers or internal state.
- **Seam 1, pure unit tests** (stdlib `unittest`; the tests load the extensionless script with `importlib.machinery.SourceFileLoader`):
  - parsers for each multiplexer's output, fed fixtures recorded from tmux 3.8, zellij 0.45.1 and herdr 0.9.5: sessions, panes, exited zellij sessions, herdr's server-not-running error;
  - agent detection, including interpreter panes from a `ps` snapshot;
  - context detection from environment variables and installed multiplexers;
  - row grouping, filtering, cursor and scroll rules, and keeping the cursor across a refresh;
  - the command builders for every action × multiplexer × inside/outside, and the new-session naming rules;
  - the input parser (keys, Alt, modifiers, mouse, several keys in one read) and the ANSI width, cut, fit and sanitize helpers.
- The unit tests run on Python 3.9 (through `uv run --python 3.9`) and on the current Python, so that features newer than 3.9 are caught.
- **Seam 2, end-to-end tests:** a bash script that runs the real script in a private tmux harness, the same pattern as duanyan-tui's `scripts/e2e.sh` and the pitfalls listed in its AGENTS.md.
  - The harness server uses its own socket and no config file. Screens are read with `capture-pane`, polling until the expected text appears, with no fixed sleeps. `KEEP=1` keeps the temporary directory.
  - The multiplexers under test are isolated from mine:
    - tmux through `TMUX_TMPDIR`;
    - zellij through a temporary `HOME` and its config and cache directories;
    - herdr through a temporary `HOME` and `XDG_CONFIG_HOME`, every `HERDR_*` variable unset, and `onboarding = false`.
    - Each is stopped in cleanup.
  - Fake agents are small scripts named `claude`, `codex`, and so on, on a temporary `PATH`, that sleep in the foreground. One is started through a fake interpreter to cover argument-based detection. herdr statuses are set with `herdr pane report-agent`.
  - Each test starts the dashboard with `--theme dark`, so that the OSC 11 query does not affect timing.
  - Scenarios:
    - Outside: all three groups in order, and Enter attaches the right client.
    - Inside tmux: only tmux, Enter switches the calling client (checked with `display-message`), and agent Enter lands on the agent's pane id.
    - Inside zellij (launched from a floating pane binding): only zellij, switching sessions, jumping to a pane in another session, and an exited session shown and resurrected.
    - Inside herdr: only workspaces, and the agent status text.
    - Nested zellij in tmux.
    - Filtering.
    - New, rename and kill, checked through each multiplexer's own list command.
    - Mouse clicks sent as SGR sequences, and Alt keys.
    - Resizing below 72 columns hides the preview.
    - The preview shows text from the selected pane.
    - After quitting, the shell prompt works and `stty` matches the saved settings.
  - A scenario is skipped with a message when its multiplexer is not installed.
- A Nix devShell provides tmux, zellij, herdr, jq and Python for both test seams, as duanyan-tui's does.

## Out of Scope

- Detecting agent status (working, idle, blocked) for tmux and zellij. Only herdr's own status is shown.
- herdr sessions (servers) other than the default one, and herdr's remote machines.
- Navigating tabs, windows or panes other than agents' panes. The dashboard switches sessions and jumps to agents only.
- A config file, fuzzy ranking, custom themes, and color fallbacks for terminals without 24-bit color.
- The Kitty keyboard protocol, bracketed paste in the dialogs, and Windows.
- Starting agents, sending prompts to agents, and session layouts.
- Changing the dotfiles' key bindings. The README documents them, and switching the dotfiles over is a separate step.

## Further Notes

- Prototypes live under `prototype/`: the HTML layout comparison, the Go/Bubble Tea version, the inline Python version, and the fullscreen stdlib Python version this spec builds on. They hold mock data only and are not part of the product.
- Checked against the real tools so far:
  - zellij lists another session's panes from outside it;
  - zellij's `pane_command` is the foreground command line;
  - zellij's `dump-screen --ansi --pane-id` works on another session;
  - `herdr agent list` returns agents with `agent_status`;
  - tmux's `pane_current_command` names the foreground program.
- To check while implementing, and to cover in the end-to-end tests:
  - whether `tmux switch-client -t %PANE` also selects the pane's window and pane;
  - whether zellij can rename a session other than the current one, and focus a pane in another session before attaching;
  - how `list-sessions` marks exited zellij sessions in 0.45.1;
  - where herdr reports a workspace's tab count and an agent's tab name;
  - which client tmux switches when the dashboard runs in a tmux 3.8 floating pane without `--client`.
- `multiplexer-new-session` stays as it is. The dashboard reimplements its naming rules so that it has no dependency on it. If the two drift apart, the script's header comment is the reference.
