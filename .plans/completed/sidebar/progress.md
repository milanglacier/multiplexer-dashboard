# Progress

- [x] Checked in an isolated zellij 0.45.1 session: `switch-session` and `focus-pane-id` run in a layout pane move the attached client.
- [x] Checked: zellij sends focus-in and focus-out to a pane that turns on mode 1004.
- [x] Plan written (`plan.md`).
- [x] `--sidebar` flag, staying open, and Escape returning focus.
- [x] Focus events and the refresh rules, with the visibility checks for zellij and tmux.
- [x] Narrow layout: no header, footer, minimum size, agent rows, dialogs.
- [x] Unit tests.
- [x] End-to-end tests.
- [x] README section, `--help` text and AGENTS.md notes.
- [x] `q` quits in the sidebar too, as the user asked after the first
  version, and the footer and help show `q quit` next to `esc back`.

## Findings while implementing

- `focus-last-pane` (zellij) and `last-pane -t $TMUX_PANE` (tmux), run in the
  sidebar, move the client that has the sidebar focused, back to the pane it
  came from in the same tab. Coming back from another tab was not checked.
- With two zellij clients in one session, only the client whose focus is on
  the sidebar moves on Enter. The other client stays.
- zellij resurrects an exited session with every command pane, the sidebar
  too, waiting for Enter. The README says so.
- zellij keeps the mouse press that focuses an unfocused pane, and sends the
  pane only a focus-in and the release. The sidebar counts a release right
  after focus-in as a click that selects without switching. The plan
  assumed the click would reach the pane.
- The plan's README layout, with the sidebar and `children` in a split of
  `default_tab_template`, leaves `children` empty in a tab without content,
  which is the first tab of a default layout and every tab opened later.
  The README uses a `new_tab_template` instead, which covers both.
- A session made with `n` gets the layout that the zellij client started
  with, which is the default layout unless the client got `--layout`.
- In the sidebar the footer puts `? help` and `esc back` right after
  `↵ switch`, since a 30-column pane shows only the first two or three keys.
