# Progress

- [x] Read the zellij 0.46 release notes, the docs on the Inbox and OSC 7501, and the 0.46 source of `list-panes`.
- [x] Checked in an isolated zellij 0.46 session: `list-panes -a -j` prints `program_status` and `attention` for panes that sent OSC 7501.
- [x] zellij 0.46 in the devShell (`flake.nix`).
- [x] Status from `program_status`, and the `error` status with the icon `×`.
- [x] Unit tests.
- [x] End-to-end tests, with the two fixes that zellij 0.46 needs (see below).
- [x] README and module docstring.
- [x] Plan written (`plan.md`), after the work.
- [ ] Checks by the user (see below).

## Findings while implementing

- In the JSON of `list-panes -a -j`, a pane that sent `state=blocked:kind=permission` has this `program_status`:
  `[{"id": null, "state": "Blocked", "kind": "Permission", "progress": null, "app": null, "title": null, "msg": null, "updated_ms": ...}]`.
  Its `attention` is `{"status": "NeedsYou", "source": "ProgramStatus", "seen": false, ...}`.
  A pane that sent `state=working:id=sub/a` and then `state=idle` has two records: the root `Idle` and the subtask `Working`.
- `program_status` and `attention` are filled in for every terminal pane, also in a session without a client.
- Zellij changes a pane's `program_status` only when the program reports a state or clears it, or when the pane resets. Marking a pane seen changes only its `attention` summary.
- zellij 0.46 writes no layout when `save-session` runs right after a session starts. The session is then not resurrectable after `kill-session`, and the e2e setup listed one of its two exited sessions. A second save a moment later writes the layout. The e2e setup repeats the save until the session's `session-layout.kdl` exists. In 0.46 each session has its own folder under `session_info`, named by a hash, with the session's name in `session-metadata.kdl`.
- The e2e test "Enter on a zellij agent attaches to its pane" pressed Enter before the zellij agents had loaded, so Enter did nothing. It now waits for the agent's row. It passed on 0.45.1 only by timing.
- `list-clients` prints the same columns in 0.46. Client ids now start at 2 in a new session, since zellij no longer reuses them.
- zellij writes its log to `/tmp/zellij-<uid>`, also in the isolated e2e environment, next to the logs of the user's own sessions.
- In one e2e run on zellij 0.45.1, before the fixes above, the check waiting for `▌   ztwo` failed once. It did not fail in any 0.46 run, and it was not looked into.
- The devShell was tested on x86_64 Linux only. The aarch64 Linux and macOS binaries are pinned and their checksums checked, but they were not run.

## To verify as a user

With zellij 0.46 and real agents, in your own sessions:

- [x] Claude Code (2.1.295 or later) and Pi in a zellij pane show their status. Checked by the user.
- [x] When Claude Code or Pi asks for input, its row shows `× blocked`. Checked by the user.
- [ ] If your zellij config has an `attention` block, the status still shows. The dashboard was not tested with any `attention` option set.

Not checked by the user:

- `× error`. A real agent rarely reports an error on demand. The end-to-end tests cover it with a fake agent that sends `state=error`.
- Agents other than Claude Code and Pi. They send the same OSC 7501 sequence, so the user takes the two that work as enough.
- zellij 0.45 or earlier. Without `program_status` in the JSON, an agent gets no status; the unit tests cover this with a pane that has none.
- How often the sidebar refreshes. This work does not change it, and the unit tests of the sidebar cover it. The refresh of a sidebar that is not on screen cannot be watched by hand.
- `nix develop` on macOS and aarch64 Linux. This is for development, not for users. Those binaries are pinned and their checksums checked, but they were not run.

An agent whose status reporting is turned off, such as with `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` for Claude Code or `PI_PROGRAM_STATUS=0` for Pi, shows no status. This is expected.

Decisions left to you:

- [x] Whether `done` should turn back into `idle` once you have looked at the pane. Decided: no. The dashboard shows what zellij reports, and zellij keeps `done` in `program_status` until the agent reports something else.
- [x] Whether the work is ready to commit. Committed on the branch `zellij-agent-status`.
