# Tabs under sessions

## Problem Statement

The Sessions list shows each session with its number of tabs ("3 tabs"),
but not the tabs themselves. To find a tab, or to go straight to one, I
have to switch to the session first and then look for the tab there. The
Agents list shows the tabs that hold an agent, but most tabs hold no agent.

## Solution

The Sessions list can show each session's tabs as rows indented under the
session. A tab is a tmux window, a zellij tab or a herdr tab.

- Tabs are hidden by default. The tab count on the session row, such as
  "3 tabs", tells how many there are. The indent alone shows which rows
  are tabs; there is no expand or collapse marker.
- `l` (or `→`) shows the tabs of the session under the cursor, and `h` (or
  `←`) hides them. On a tab row, `h` hides the tabs of its session and puts
  the cursor on the session.
- `L` shows the tabs of every session, and `H` hides them all.
- `--tabs collapsed|expanded` sets how the dashboard starts. The default is
  `collapsed`. `--tabs expanded` starts with the tabs of every session
  shown. `h`, `l`, `H` and `L` still work after that, so the flag only sets
  the starting state.
- The cursor can land on a tab. The preview shows the tab's focused pane,
  and Enter switches to that tab.
- The filter also matches tab names.

Example, with the tabs of `work` shown:

```
  zellij ─────────────── 3
▌ ● work        ◆2 3 tabs
      1 editor        ◆1
      2 shell
      3 logs
    notes          1 tab
    scratch       2 tabs
```

The multiplexers already report every tab in the calls the dashboard makes
today, so showing tabs needs no new call on refresh:

- tmux: `list-panes -a` gives each pane's window index, name and active
  flag. Adding `#{window_id}` to the format gives a stable window id.
- zellij: `action list-tabs -j -s` gives each tab's `tab_id`, `position`,
  `name` and `active`.
- herdr: `tab list` gives each tab's `tab_id`, `workspace_id`, `number` and
  `label`. `workspace list` gives each workspace's `active_tab_id`.

## User Stories

Seeing tabs

1. As a user, I want to see the tabs of a session indented under it, so that I can find a tab without switching to the session first.
2. As a user, I want tabs hidden by default, so that the list stays short when I have many sessions.
3. As a user, I want tab rows indented a little deeper than session names, and no wider than that, so that the nesting is clear and a narrow sidebar keeps its width for names.
4. As a user, I want each tab row to show the tab's number and name, so that it reads the way the multiplexer's own tab bar does.
5. As a user, I want the tab that is active in its session marked, so that I know which tab a switch to the session lands on.
6. As a user, I want each tab row to show how many agents it holds, highlighted when one of them waits for me, so that I can find the tab that needs me.
7. As a user, I want exited zellij sessions to show no tabs, since zellij does not report their tabs.

Expanding and collapsing

8. As a user, I want `l` or `→` to show the tabs of the selected session.
9. As a user, I want `h` or `←` to hide the tabs of the selected session.
10. As a user on a tab row, I want `h` to hide the tabs and put the cursor on the session, so that I do not lose my place.
11. As a user, I want `L` to show the tabs of every session and `H` to hide them all.
12. As a user, I want the shown or hidden state of each session to stay the same when the lists refresh.
13. As a user, I want a session that appears later, such as one I create with `n`, to follow the last `H` or `L`, or the `--tabs` flag when I pressed neither.
14. As a user, I want `h`, `l`, `H` and `L` to do nothing in the Agents list.

Start-up flag

15. As a user, I want `--tabs expanded` in my key binding, so that the dashboard opens with every tab shown.
16. As a user, I want `--tabs collapsed` to be accepted and to mean the default, so that I can say it explicitly in a binding or an alias.

Using a tab row

17. As a user, I want to move the cursor onto a tab row with `j` and `k`, so that I can pick a tab.
18. As a user, I want the preview to show the focused pane of the selected tab.
19. As a user, I want Enter on a tab row to switch to that session and that tab, inside or outside a multiplexer.
20. As a sidebar user, I want Enter on the tab that holds the sidebar to do the same as Escape, since there is nowhere to switch to.
21. As a user, I want `r` and `x` on a tab row to tell me that they work on sessions, so that I never kill a session when I meant a tab.

Filtering

22. As a user, I want the filter to match tab names too, so that I can type a tab's name to find it.
23. As a user, I want a session whose name does not match, but whose tab does, to show with only the matching tabs under it.

Narrow panes

24. As a sidebar user, I want tab rows to fit a pane of about 30 columns. The tab name is cut before the agent count is dropped.

## Implementation Decisions

Model

- A new `Tab` dataclass: `mux`, `session_key`, `session` (the name), `id`, `index`, `name`, `active`, `pane` (the tab's focused pane, for the preview) and `path` (that pane's directory).
  - `id` is the tmux window id (`@3`), the zellij `tab_id` or the herdr `tab_id`.
  - `index` is the number the multiplexer's own tab bar shows: the tmux window index, the zellij `position` plus one, or the herdr `number`.
- `Group` gets `tabs: list[Tab]`, sorted by session order, then by `index`, as agents are.
- `Session.tabs` stays the tab count. A background zellij session can report a count but no tabs; `h` and `l` then do nothing on it.
- tmux agents get `tab_id` set to the window id, so that every backend can count the agents of a tab by `Agent.tab_id == Tab.id`.

Backends

- tmux: add `#{window_id}` to `TMUX_PANE_FORMAT`. `tmux_snapshot` groups panes by session and window into tabs. A tab's focused pane follows the rule a session uses today: the active pane, then the last pane, then the first, never the dashboard's own pane.
- zellij: `parse_zellij_panes` already reads `list-tabs`. It also returns the tabs. A tab's focused pane is its focused tiled pane, then a floating one, as for the session. When `list-tabs` fails, the tabs come from the panes' `tab_id`, `tab_name` and `tab_position`.
- herdr: `parse_herdr` turns each tab of `tab list` into a `Tab` of its workspace. A tab is active when its id is the workspace's `active_tab_id`. Its pane is one of its panes from `pane list`. The preview asks herdr for the tab's focused pane through `pane layout`, as the session preview does today.

Switching to a tab

- Each backend gets `switch_tab(tab, inside, current) -> Plan`.
  - tmux: `switch-client -t @ID` inside, `attach-session -t @ID` outside. A window target selects the session and the window, as the pane target does for agents.
  - zellij inside, same session: `zellij action go-to-tab-by-id ID`.
  - zellij inside, another session: `zellij action switch-session S --tab-position N`, where N is the tab bar number, the zellij position plus one.
  - zellij outside: `zellij attach S` with the `--zellij-focus-pane` helper. The helper already runs `go-to-tab-by-id`. It learns to accept an empty pane and then stops after the tab.
  - herdr: `herdr tab focus ID`, with `attach=["herdr"]` outside, as for workspaces.
- `App.switch` handles tab rows. In a sidebar, Enter on the active tab of the current session calls `back()`, as Enter on the current session does.

Rows and expansion state

- `Row` gets kind `"tab"` and a `tab` field. `item_key` of a tab is `("tab", mux, session_key, tab.id)`.
- The App keeps `tabs_default: bool`, set from `--tabs`, and `expanded: dict[tuple[str, str], bool]`, keyed by `(mux, session_key)`, for the sessions the user toggled. A session is expanded when it has an entry that says so, or else when `tabs_default` is true.
- `H` and `L` set `tabs_default` and clear `expanded`, so that they apply to every session, also to the ones that appear later.
- `rename` moves a zellij session's entry to the new name, since zellij keys sessions by name.
- `build_rows` takes a function that says whether a session is expanded. In the Sessions list, an expanded session is followed by a row for each of its tabs.
- The group header count stays the number of sessions.
- After `h`, `l`, `H` or `L`, the cursor stays on the same session, found by `item_key`, and on a tab row `h` moves it to the session. The list counts as touched, so that a refresh keeps the cursor where it is.
- `h`, `l`, `H` and `L` on a session with no tabs, or on an exited one, do nothing.

Filter

- While a filter is set, a session shows when its name or one of its tab names matches.
- An expanded session that matches shows all its tabs. A collapsed one shows only its tabs whose name matches, so that a match through a tab is always visible.
- `x` and `r` on a tab row say: "Rename and kill work on sessions. Press h to go to the session."

View

- `session_row` stays as it is: the current-session dot, then the name.
- A tab row starts two cells to the right of where session names start, so that a tab is always indented deeper than its session's name, and the indent costs only two cells in a narrow sidebar. It shows the tab's index and name, the active tab in bold text color and the others in subtle color, and on the right the tab's agent count, `◆N`, in `love` and bold when one of its agents is blocked or in error, as on the session row.
- When the row is too narrow, the name ends with `…` before the agent count is dropped.
- The preview of a tab row shows `mux › session › tab` in the panel title, the pane directory and the pane count in the info line, and the capture of the tab's focused pane. `preview_target` returns the tab's pane, with the session for zellij and herdr.
- The help dialog lists `h l ← →` (hide or show the session's tabs) and `H L` (hide or show every session's tabs). The footer stays as it is.

Flag

- `--tabs {collapsed,expanded}`, default `collapsed`. `--help` says "start with each session's tabs hidden or shown".
- `Options` gets `expand_tabs: bool`.

Documentation

- README: add `h` `l` and `H` `L` to the Keys table, and `--tabs` to the options synopsis and list.
- AGENTS.md: nothing new unless implementing finds a pitfall, such as a zellij tab switch that does not move the client.

## Testing Decisions

- Unit tests:
  - The tmux, zellij and herdr parsers return the tabs from the existing fixtures, with the right index, name, active flag and focused pane. The tmux fixture gets the window id column.
  - `build_rows` without tabs expanded, with one session expanded, with every session expanded, and with a filter that matches a session name, a tab name only, and both.
  - `l` on a session adds its tab rows and keeps the cursor on the session. `h` on a tab row removes them and puts the cursor on the session. `H` and `L` change every session and also a session that appears in a later load.
  - The expansion state survives a refresh, and a zellij rename keeps it.
  - `--tabs expanded` starts with every session expanded. `--tabs collapsed` and no flag start with none.
  - Enter on a tab row runs the right plan for each backend, inside and outside, and in a sidebar Enter on the active tab of the current session runs the back command.
  - `r` and `x` on a tab row only show the message.
  - Rendering: the tab row starts two cells right of the session name, at 160 and at 24 columns.
- End-to-end tests, in `scripts/e2e.sh`:
  - tmux: a session with two windows. `l`, then `j` to the second window, then Enter: the client is on that window.
  - zellij: a session with two tabs, through a key binding pane. Enter on the other tab of the same session moves the client to it. Enter on a tab of another session switches to that session and that tab.
  - herdr: Enter on a tab focuses it.

## Out of Scope

- Renaming, closing or creating tabs.
- Showing panes under tabs.
- Reordering tabs.
- Tabs in the Agents list. Agent rows already name their tab.
- Remembering the expansion state across runs. The dashboard stores nothing on disk.

## Further Notes

- Checked while implementing (zellij 0.46.0, tmux 3.8, herdr 0.9.5):
  - `go-to-tab-by-id` run in a key binding pane moves that pane's client, and from outside the session it moves the session's only client.
  - `switch-session --tab-position` takes the tab bar number, which starts at 1, not the zellij position: 1 lands on the first tab and 2 on the second.
  - zellij's `is_focused` in `list-panes -a` holds per tab: each tab has one focused pane, with or without a client.
  - herdr's `pane list` marks one focused pane across all workspaces, so a tab's pane falls back to its first pane and the preview asks `pane layout` for the focused one. `herdr tab focus` also focuses the tab's workspace.
  - `tmux attach-session -t @ID` lands on that window.
