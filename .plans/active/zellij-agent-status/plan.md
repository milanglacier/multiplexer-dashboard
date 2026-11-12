# Agent status in zellij

## Problem Statement

The dashboard shows the status of each agent (working, blocked, done,
idle) only for herdr, because herdr reports its own agents and their
status. Agents in zellij and tmux show no status, so I cannot see at a
glance which agent waits for me unless I run it in herdr.

Zellij 0.46 adds support for OSC 7501, an escape sequence that programs,
mostly coding agents, use to report their status: `idle`, `working`,
`done`, `blocked` (with a kind: permission, question or auth) and `error`.
Zellij shows these statuses on pane frames and in its Inbox. Many agents
already send it with no setup, among them Claude Code 2.1.295, Codex
0.163, Pi, Crush, OpenCode 2.1, Copilot CLI, Qwen Code, goose and Droid.
Gemini CLI, Cursor CLI and Aider do not send it yet.

## Solution

Read the status from zellij and show it as the dashboard shows herdr's.

Zellij's documentation names no command that prints the status, but the
0.46 source shows that `zellij action list-panes -a -j`, which the dashboard
already runs for each session, includes it in each pane's JSON:

- `program_status`: the list of statuses that the program in the pane
  reported. The record whose `id` is null is the program's own status. The
  records with an id, such as `sub/a`, are its subtasks.
- `attention`: zellij's own summary of the pane, which also counts the
  bell, desktop notifications, new output in an unfocused pane and output
  that went quiet.

The dashboard uses `program_status`, because `attention` would mark an
agent as needing the user when it only printed something.

## User Stories

1. As a zellij user, I want each agent row to show the status that the agent reports, so that I see which agent works, waits or is done without opening its pane.
2. As a zellij user, I want a blocked agent highlighted, and the agent count of its session highlighted, as for herdr.
3. As a zellij user, I want an agent that reports an error highlighted in the same way, since it also waits for me.
4. As a user of zellij 0.45 or earlier, I want the dashboard to work as before, with no status.
5. As a user of an agent that does not report its status, I want its row to show no status rather than a wrong one.
6. As a developer, I want the devShell to provide zellij 0.46, so that `make e2e` tests the status with a real zellij.

## Implementation Decisions

Reading the status

- `zellij_status(pane)` returns the `state` of the `program_status` record whose `id` is null, in lower case, or None when there is no such record.
- `parse_zellij_panes` passes it to `Agent.status`. The agent detection itself does not change: a pane is an agent when its foreground program is one of the known names.
- The states that zellij prints are capitalized (`"Working"`). The dashboard lowercases them, so that `working`, `blocked`, `done` and `idle` match herdr's.

Showing the status

- `error` is a new status that only zellij reports. It shares the icon `×` with `blocked`, as the user asked, and keeps its own word, so that a wide row shows `× error`.
- `ALERT_STATUSES = ("blocked", "error")`. An agent row and the `◆` agent count of a session are highlighted when an agent has one of them, where they were highlighted only for `blocked` before.
- The dashboard shows the state that zellij keeps in `program_status` and adds no rules of its own, as the user decided. Zellij keeps a state until the program reports another one or clears it, or the pane resets. Looking at the pane changes only zellij's `attention` summary, so `done` stays `done` until the agent reports something else.

devShell

- nixos-unstable has zellij 0.45.1. The flake takes zellij's 0.46.0 release binaries: the statically linked musl builds on Linux and the official builds on macOS, each pinned by hash. Each hash was checked against the release's checksum of the binary inside the tarball.
- Once nixpkgs has zellij 0.46 or later, the flake uses it instead, with no change to the flake.

Documentation

- README: zellij 0.46 agents that report their status show it, and can also show error.
- The module docstring says that zellij 0.46 reports the status that an agent sends with OSC 7501.

## Testing Decisions

- Unit tests:
  - The zellij `list-panes` fixture gets a `program_status` for the claude pane, in the shape zellij 0.46 prints: a root record `Working` and a subtask record `Blocked`. The claude agent gets `working`, and the subtask does not count. The gemini pane has no `program_status`, as with zellij 0.45, and gets no status.
  - A rendered agent row shows `× error`.
  - `error` shares the icon of `blocked`; every other status icon is unique.
- End-to-end tests, in `scripts/e2e.sh`:
  - The fake agents send `ESC ] 7501 ; state=$FAKE_STATUS ESC \` when FAKE_STATUS is set. Only the zellij sessions get `FAKE_STATUS=error`, so tmux and herdr are not affected.
  - Outside any multiplexer, the dashboard shows `× error` for a zellij agent.

## Out of Scope

- tmux. tmux has no status for a pane, and it drops OSC 7501.
- Using zellij's `attention` summary, its `seen` flag, the `kind` of a blocked status, or `progress` and `msg`.
- Rules of the dashboard's own that change a status, such as turning `done` into `idle` once the user has seen the pane.
- Statuses of subtasks.
- zellij's Inbox and its actions, such as `go-to-next-attention`.

## Further Notes

- To check while implementing:
  - the JSON that `list-panes -a -j` prints for a pane that sent OSC 7501;
  - whether the e2e tests that passed on zellij 0.45.1 still pass on 0.46.
