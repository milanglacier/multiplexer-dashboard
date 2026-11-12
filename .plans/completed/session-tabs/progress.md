# Progress

- [x] Plan written (`plan.md`).
- [x] `Tab` model and the tab parsers for tmux, zellij and herdr.
- [x] Tab rows, expansion state, `h` `l` `H` `L`, and the filter.
- [x] Switching to a tab in each backend.
- [x] Tab rows in the view, the preview and the help dialog.
- [x] `--tabs` flag.
- [x] Unit tests.
- [x] End-to-end tests.
- [x] README and `--help` text.

Notes:

- zellij's `switch-session --tab-position` counts from 1, so the plan's
  decision now passes the tab bar number. The other open questions in the
  plan's Further Notes are answered there.
- The tmux pane fixture got its window id column by hand, with the ids
  tmux gives windows in creation order, instead of a new recording.
- An expanded session that matches the filter only through a tab shows only
  the matching tabs, as user story 23 asks; it shows all its tabs only when
  its own name matches.
