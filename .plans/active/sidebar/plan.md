# Sidebar mode

## Problem Statement

The dashboard opens in a floating pane from a key binding and closes after
a switch. To see which sessions exist and where my agents run, I have to
press the key each time. herdr's sidebar is always on screen, next to the
work. In zellij I want the same: a narrow pane in every tab, set in the
layout, that lists sessions and agents and stays open.

The current dashboard does not fit in such a pane:

- it exits after every switch, and `q` and Escape quit, which leaves an
  empty pane in the layout;
- the preview takes room a narrow pane does not have, and the pane is
  already next to the panes it would preview;
- the header and the minimum size of 40×12 assume a popup;
- a layout pane in every tab means one dashboard process per tab, and each
  one reloads every session every 2 seconds.

## Solution

A `--sidebar` flag runs the dashboard as a sidebar: a fixed pane that stays
next to the work.

- It shows the Sessions and Agents lists only, at any width.
- Inside a multiplexer it stays open after a switch. Escape returns focus to
  the pane you came from instead of quitting.
- It fits a pane of about 30 columns.
- It refreshes often only while it has focus, less often while it is on
  screen without focus, and barely at all while its tab is hidden.

Users add it to zellij's `default_tab_template`, so that every tab of every
session gets one, including sessions that `n` creates. The same flag works
in a tmux split.

Two facts, checked against zellij 0.45.1 in an isolated session, make this
work without new switching code:

- `switch-session` and `focus-pane-id` run in a layout pane move the
  attached client. The limit in CLAUDE.md applies to panes with no client
  behind them (`zellij --session S run`, or calls from outside the
  session), not to layout panes.
- zellij sends focus-in (`ESC [ I`) and focus-out (`ESC [ O`) to a pane that
  turns on mode 1004.

## User Stories

Setup

1. As a zellij user, I want to put the dashboard in `default_tab_template`, so that every tab has the lists next to my work.
2. As a zellij user, I want sessions created with `n` to get the pane too, so that I do not have to set it up for each session.
3. As a tmux user, I want to run `multiplexer-dashboard --sidebar` in a split, so that tmux gets the same pane.
4. As a user, I want `--sidebar` in a floating pane or a plain shell to show the narrow lists without the preview, so that I can try the layout anywhere.

Staying open

5. As a user, I want the pane to stay open after Enter switches me to another session, so that the old session still has its pane when I come back.
6. As a user, I want Enter on an agent in the current session to move focus to that agent and leave the pane open.
7. As a user, I want Escape to give focus back to the pane I came from, so that I can glance at the list and return.
8. As a user, I want Enter on the current session to do the same as Escape, since there is nowhere to switch to.
9. As a user, I want `q` to do nothing in the fixed pane, so that I do not close it by mistake.
10. As a user, I want Ctrl+C to quit, so that I can still stop it.
11. As a user, I want a session created with `n` to switch me to it and leave the pane open.
12. As a user outside any multiplexer, I want `--sidebar` to keep the usual behavior, where the attaching client replaces the dashboard.

Narrow layout

13. As a user, I want the lists without the preview at every width, so that widening the pane does not bring the preview back.
14. As a user with a narrow pane, I want no header, so that the lists get every row. The panel titles and their counts already say what each list holds.
15. As a user, I want the footer to show `esc back` instead of `q quit`.
16. As a user, I want the pane to work down to about 24×10 cells, and show the size message only below that.
17. As a user, I want agent rows to keep the agent name and session, and drop the tab when the row is too narrow.

Refresh and cost

18. As a user, I want the lists refreshed every 2 seconds while the pane has focus, as in the popup.
19. As a user, I want the lists refreshed at once when I move focus to the pane, so that I never act on a stale list.
20. As a user, I want the lists refreshed every 5 seconds while the pane is on screen without focus, so that a glance shows recent state.
21. As a user with many tabs, I want a pane in a hidden tab to make one cheap call every few seconds and load everything only when its tab is shown, so that twenty panes do not keep the multiplexer busy.
22. As a tmux user without `focus-events on`, I want a key press or a click in the pane to count as focus, so that the pane still refreshes while I use it.

## Implementation Decisions

The flag and the mode

- `--sidebar` sets `sidebar` on `Options`. In sidebar mode, the view never draws the preview and the App never captures previews.
- "Stays open" applies only inside a multiplexer. Outside, a switch still ends the dashboard with the attaching plan.

Staying open

- In sidebar mode, `App.execute` sets no `Exit` when the plan has no `attach`. It sets a short toast instead (for example "switched to ztwo") and starts a refresh.
- Escape, with no dialog and no filter, runs the backend's "return focus" command. Enter on the current session runs the same command.
  - zellij: `zellij action focus-last-pane`.
  - tmux: `tmux last-pane`. It acts on the pane's own window.
  - herdr: no command. herdr has its own sidebar, and its CLI has no "last pane" action.
- `q` is ignored in the list. Ctrl+C still quits.
- A create plan with no `attach` keeps the pane open, as switching does.

Terminal layer

- In sidebar mode, `Term` also turns on mode 1004 and turns it off on exit with the other modes.
- `parse_input` turns `ESC [ I` and `ESC [ O` into `Event("focus", key="in")` and `Event("focus", key="out")`. Outside sidebar mode, these sequences never arrive.

Focus and refresh

- The App keeps `focused` (bool) and `visible` (bool). It starts with `focused = False` and `visible = True`.
- A focus-in, a key press or a mouse press sets `focused = True`. A focus-out sets it to `False`. A focus-in also starts a refresh at once.
- The time to the next full load is 2 s while focused, 5 s while visible without focus, and none while hidden. Outside sidebar mode it stays 2 s, as today.
- While not focused, a visibility check runs every 3 s on the worker thread. It posts `visible` to the inbox. When `visible` turns true, a full load starts at once.
  - zellij: `zellij action list-clients` gives each client's focused pane. The pane is visible when one of those panes is in the dashboard's own tab. The pane-to-tab map comes from the last `list-panes` of the current session, so the zellij backend keeps the dashboard's own tab id from its last load.
  - tmux: `tmux display-message -p -t $TMUX_PANE '#{window_active} #{session_attached}'`. The pane is visible when both are nonzero.
  - herdr: no check. The pane counts as always visible.
- `App.timeout` includes the next visibility check, so the main loop wakes for it.
- Keys, resizes and new data already wake the main loop at once, so the 0.5 s upper bound in `App.timeout` has no timed work behind it. In sidebar mode, that bound applies only while focused. Without focus, the loop waits until the next visibility check or the next full load, so that a pane in a hidden tab does not redraw twice a second.

View

- In sidebar mode, the body is the two lists at full width at any number of columns.
- There is no header in sidebar mode. The lists start on the first row.
- The footer's last key is `esc back` instead of `q quit`. The help dialog says the same.
- The minimum size is 24×10 in sidebar mode, and 40×12 otherwise.
- `agent_row` drops ` › TAB` before it cuts the session name, when the row is narrower than the name, session and tab. The name column keeps the width from `agent_name_width` in every mode, so that the names line up.
- Dialogs get narrower to fit the pane. The rename, new and kill dialogs are at most `cols - 2` wide.

Processes

- Each tab in `default_tab_template` runs its own dashboard process, about 20 MB each. Each has its own cursor and filter. The SIGHUP handler already exits when zellij closes the tab.

Documentation

- README: a section on keeping the dashboard in a fixed pane, with a zellij `default_tab_template` that keeps the tab bar and status bar, and a tmux split command. It says that every tab runs its own process and that hidden tabs stay cheap.
- `--help` describes `--sidebar` as "show only the lists; inside a multiplexer, stay open after a switch".
- Reword the zellij note in AGENTS.md so that it covers layout panes too: `switch-session` and `focus-pane-id` move a client only when they run in a pane with a client behind it, such as a pane opened by a key binding or a layout pane.

Example zellij layout for the README:

```kdl
layout {
    default_tab_template {
        pane size=1 borderless=true { plugin location="tab-bar"; }
        pane split_direction="vertical" {
            pane size=32 command="multiplexer-dashboard" close_on_exit=true {
                args "--sidebar"
            }
            children
        }
        pane size=2 borderless=true { plugin location="status-bar"; }
    }
}
```

## Testing Decisions

- Unit tests (seam 1):
  - `parse_input` turns `ESC [ I` and `ESC [ O` into focus events, also mixed with keys in one read.
  - In sidebar mode, `render` draws no preview at 160 columns, draws no header, draws down to 24×10 and shows the size message below that.
  - In a narrow agent row, the tab goes before the session is cut.
  - In sidebar mode without focus, `App.timeout` returns the time to the next visibility check or full load, not 0.5 s. With focus, and outside sidebar mode, it still returns at most 0.5 s.
  - In sidebar mode, Enter on a session in another session runs `switch-session` and leaves `result` unset. Enter on the current session and Escape run `focus-last-pane` (zellij) or `last-pane` (tmux). `q` does nothing. Ctrl+C quits.
  - Outside a multiplexer in sidebar mode, Enter still exits with the attaching plan.
  - The refresh times: 2 s focused, 5 s visible, no full load while hidden, an immediate load on focus-in and when the pane becomes visible again. A key press counts as focus.
  - The visibility parsers for zellij `list-clients` with the pane-to-tab map, and for the tmux `display-message` reply.
- End-to-end tests (seam 2), in `scripts/e2e.sh`:
  - zellij: a session whose layout puts `--sidebar` in `default_tab_template`. From the pane, Enter on another session moves the client, and the old session's pane still runs. Enter on an agent in the same session focuses it, and the pane still runs. Escape returns focus to the previous pane (checked with `list-clients`). `n` creates a session that has the pane too.
  - zellij: a click on the pane while it is not focused focuses it and selects the row.
  - tmux: a `--sidebar` split. Enter switches the client and the pane stays. Escape runs `last-pane`.
  - A narrow pane (30 columns) shows both lists and no preview.

## Out of Scope

- Sharing one process or one snapshot between the panes of different tabs. That needs a socket or a file, and the dashboard stores nothing on disk.
- Marking the agent pane that has focus in this tab.
- Keeping the cursor or filter the same across tabs and sessions.
- Setting up the pane for every tmux window with hooks. The README shows only the split command.
- A zellij plugin.

## Further Notes

- To check while implementing:
  - whether `focus-last-pane` and `last-pane` run in the pane move the right client, and return to the pane before the dashboard pane when focus came from another tab;
  - which client moves when two clients are attached to the same zellij session;
  - whether zellij brings back the pane's command when it resurrects an exited session, or waits for Enter;
  - whether the first click on an unfocused zellij pane also reaches the pane.
