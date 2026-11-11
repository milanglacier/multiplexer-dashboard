## Writing

Write in plain, simple language everywhere: code comments, docstrings, docs,
commit messages and explanations to the user. Use complete sentences, and
say what a thing does instead of coining a name for it.

The text in the repo must read as the final, clean version, with no trace of
the back and forth it took to get there. Code, comments and docs describe
only current behavior. Only commit messages and plans may contrast new
behavior with earlier behavior.

## Designing features

The dashboard is one executable file, `multiplexer-dashboard`, that users
drop into a `bin` directory. Keep it that way:

- Standard library only, Python 3.9 or later, and no `curses`.
- Ask each multiplexer for its state through its own CLI, and use its own
  commands for actions. Store nothing on disk; there is no config file.
- `prototype/` holds mock prototypes. They are not part of the product and
  are not checked.

## Build and test

Run everything inside the devShell, which provides Python, uv, ruff,
pyrefly, tmux, zellij, herdr and jq:

```sh
nix develop -c make check
```

After changing Python code, including tests, run `make check` and fix any
failures. `make check` runs the unit tests on Python 3.9 and on the current
Python. Any change to terminal handling, key routing or a multiplexer
command must also pass the end-to-end tests:

```sh
nix develop -c make e2e
```

## Plans

Design plans live in `.plans/{active,completed}/<name>/plan.md`, with
progress in `progress.md` next to each plan. Completed plans are history and
may be out of date; the code is current.

# Notes and Rabbit Holes

Knowledge the code does not show. When adding a note, describe the problem
and the outcome to preserve, not a step-by-step patch.

- **Never touch the user's own multiplexers.** You are probably running
  inside one of them, and a kill or rename can reach the user's real
  sessions. Run tests and ad-hoc checks in the isolated environment that
  `scripts/e2e.sh` sets up; a temporary `HOME` alone is not enough.
- **zellij's `focus-pane-id` and `switch-session` work only in a pane
  opened by a key binding**, as the dashboard is. From outside the session,
  or in a pane that `zellij --session S run` opened, they move no client.
  Test zellij switching through a key binding, as `scripts/e2e.sh` does.
