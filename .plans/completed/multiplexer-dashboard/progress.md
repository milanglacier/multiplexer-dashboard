# Progress

- [x] Prototypes: HTML layout comparison, Go/Bubble Tea, inline Python, fullscreen Python (`prototype/`).
- [x] Layout chosen: A (sidebar + preview). Language chosen: stdlib Python, 3.9 or later, fullscreen, no curses.
- [x] Spec written (`plan.md`).
- [x] Implementation: `multiplexer-dashboard`.
- [x] Unit tests (`tests/`, fixtures recorded from tmux 3.8, zellij 0.45.1 and herdr 0.9.5), run by `make check` on Python 3.9 and the current Python.
- [x] End-to-end tests (`scripts/e2e.sh`, `make e2e`), covering every scenario of the spec.
- [x] README with the key bindings for tmux, zellij and herdr.
- [ ] Switch the dotfiles' key bindings over (out of scope, a separate step).

## Answers to the spec's open questions

- `tmux switch-client -t %PANE` selects the pane's window and the pane, and
  so does `attach-session -t %PANE`. Agent jumps in tmux are one command.
- Without `--client`, tmux switches the client that opened the floating
  pane, even with another client attached (checked by the e2e test).
- zellij renames another session from outside it with
  `zellij --session OLD action rename-session NEW`.
- zellij cannot focus a pane in another session before attaching:
  `focus-pane-id` from outside the session moves no client, and the client
  that attaches afterwards does not land on that pane. See "Changes from
  the spec".
- `list-sessions --no-formatting` marks an exited session with
  `(EXITED - attach to resurrect)`, and its age counts from when it exited.
- herdr reports a workspace's tab count as `tab_count` in `workspace list`,
  and an agent's tab as `tab_id`, whose label comes from `tab list`.

## Changes from the spec

- tmux sessions are targeted by session id (`$N`) rather than `=NAME`, so
  that a name with `:` or `.` still works. Creating a session still switches
  to `=NAME`.
- The tmux current session for `--client` comes from `list-clients`, since
  `display-message -c` does not change the format's target.
- tmux 3.8's `new-pane` expands no formats in its command, so the README's
  tmux binding wraps it in `run-shell -C`. A floating pane needs no `-E`;
  `-O` makes it modal.
- zellij's tab count comes from `list-tabs`, also used to find the active
  tab: a background session can have tabs without panes.
- Outside zellij, an agent jump attaches and starts a background helper
  (`--zellij-focus-pane`, not shown in `--help`). It waits for the new
  client, then moves it with `go-to-tab-by-id` and `focus-next-pane`. It
  runs only when the session has no client, since those actions move the
  session's first client.
- The session preview skips the dashboard's own pane (`TMUX_PANE`,
  `ZELLIJ_PANE_ID`), and uses the pane that was focused before it.
- Enter on the current session closes the dashboard without a command.
- Until the user moves a list's cursor, the cursor stays on the first row
  while the multiplexers answer, instead of following whichever answered
  first.
