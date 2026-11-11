# multiplexer-dashboard

A herdr-style sidebar for [tmux](https://github.com/tmux/tmux) and
[zellij](https://zellij.dev), and for [herdr](https://herdr.dev) itself:
press one key and
see every session and every coding agent (claude, codex, opencode, pi,
gemini and others) in one place, with a live preview of each. Press Enter to
jump there.

- Press the key binding inside tmux, zellij or herdr to open the dashboard
  in a floating pane, pick a session or an agent, and land on it.
- Run `multiplexer-dashboard` in a plain shell, such as right after you SSH
  into a machine, to see the sessions of every installed multiplexer and
  attach to one.
- Create, rename and kill sessions without remembering each multiplexer's
  commands.

## Why

The best part of herdr is its sidebar: it shows your workspaces and your
agents, so you always know which agent is working, which one is waiting for
you, and where it lives.

herdr now puts its effort into its desktop and mobile apps, which are built on
herdr-core and do not work with the herdr TUI. The TUI is likely to be
gradually abandoned, the way Arc was. I do not want my favorite feature to die
with it.

<details>
<summary>Why Arc is the right comparison, and why not fork the TUI</summary>

The herdr TUI and herdr-core are separate programs. In
[herdr's FAQ](https://herdr.dev/), herdr says: "They don't share agents, so
what runs in one doesn't show up in the other." About the TUI's future, the
FAQ says only that "Herdr TUI keeps working." It does not say whether the TUI
will get new features or fixes, or for how long.

Arc went the same way. The Browser Company stopped adding features to Arc in
May 2025 to work on its next browser, Dia, and kept Arc working. In October
2026 it
[announced](https://techcrunch.com/2026/10/22/arc-browser-sunsets-december-22-as-the-browser-company-doubles-down-on-dia/)
that Arc stops working on December 22, 2026.

The herdr TUI is open source, so anyone can fork it, and with a coding agent
anyone can keep changing the fork. The code is the easy part. A project also
lives on its community and ecosystem. When upstream moves on to its next
product, they split. Some users move to the herdr app, and many who dislike
the move are left without a home. It is hard to bring them back together under
a fork, and the community around it would be small and fragile. tmux and zellij already have a large, settled
community and ecosystem, so the dashboard builds on them instead.

</details>

The apps also mean lock-in at both ends: the machine you work on must
run the herdr-core server, and the device you work from must run
herdr's desktop or mobile app. A classic TUI has no lock-in. It works
in any terminal, over any SSH client, from a laptop or a phone, and
the server needs nothing but a shell and the multiplexer.

So this dashboard brings the sidebar to tmux and zellij, which have worked
this way for years and are not going anywhere. herdr is supported too,
since the dashboard already speaks to the other two.

## Install

It is one file that needs Python 3.9 or later and nothing else:

```sh
curl -L -o ~/.local/bin/multiplexer-dashboard \
  https://raw.githubusercontent.com/milanglacier/multiplexer-dashboard/main/multiplexer-dashboard
chmod +x ~/.local/bin/multiplexer-dashboard
```

## Set up a key binding

Bind a key to open the dashboard in a floating pane. Give the pane enough
room: below about 72 columns the preview is hidden.

tmux 3.8 (`~/.tmux.conf`):

```tmux
bind tab new-pane -O -x80% -y80% -X10% -Y10% -c '#{pane_current_path}' multiplexer-dashboard
```

zellij (`~/.config/zellij/config.kdl`):

```kdl
bind "Tab" {
    Run "multiplexer-dashboard" {
        floating true
        close_on_exit true
        width "80%"
        height "80%"
        x "10%"
        y "10%"
    };
    SwitchToMode "Normal"
}
```

herdr:

```toml
[[keys.command]]
key = "prefix+alt+d"
type = "popup"
command = "multiplexer-dashboard"
width = 140
height = 40
```

## Keep it open in a sidebar

`multiplexer-dashboard --sidebar` shows only the Sessions and Agents lists,
so it fits a pane of about 30 columns. Inside a multiplexer it stays open:
Enter takes you to the session or agent and the pane stays, Escape gives
focus back to the pane you came from, and `q` quits.

zellij: to give every tab of every session a sidebar, including the sessions
that you create with `n`, add a `new_tab_template` to your default layout,
`~/.config/zellij/layouts/default.kdl`. This one keeps the tab bar and the
status bar:

```kdl
layout {
    new_tab_template {
        pane size=1 borderless=true {
            plugin location="tab-bar"
        }
        pane split_direction="vertical" {
            pane size=32 command="multiplexer-dashboard" close_on_exit=true {
                args "--sidebar"
            }
            pane focus=true
        }
        pane size=2 borderless=true {
            plugin location="status-bar"
        }
    }
}
```

tmux: open a sidebar on the left of the current window:

```sh
tmux split-window -hbf -l 32 multiplexer-dashboard --sidebar
```

With `set -g focus-events on`, tmux tells the sidebar when it gets focus.
Without it, a key press or a click in the sidebar counts as focus.

Every tab runs its own sidebar, with its own cursor and filter. A sidebar
refreshes every 2 seconds while it has focus and every 5 seconds while it is
on screen. A sidebar in a tab that is not on screen only checks every few
seconds whether it is shown again, so many tabs stay cheap.

When zellij brings back an exited session, it waits for Enter in each pane
before it starts the pane's command, and the sidebar's too.

## Keys

| Key             | Action                             |
| --------------- | ---------------------------------- |
| `j` `k` `↑` `↓` | move                               |
| `Alt+j` `Alt+k` | next / previous multiplexer        |
| `Tab`           | switch between sessions and agents |
| `Enter`         | go to the session or agent         |
| `/`             | filter as you type                 |
| `n` `r` `x`     | new / rename / kill session        |
| `?`             | show every key                     |
| `q` `Escape`    | close                              |

The mouse works too: click to select, click again to go there, and scroll
to move.

<details>
<summary>Options and details</summary>

```
multiplexer-dashboard [--multiplexer tmux|zellij|herdr] [--client CLIENT]
                      [--dir DIR] [--theme auto|light|dark] [--no-bg]
                      [--sidebar]
```

- `--multiplexer` lists only one multiplexer.
- `--client` is the tmux client to switch, for a binding that opens the
  dashboard on behalf of another client.
- `--dir` is the directory of new sessions. It defaults to the current
  directory, and inside herdr to the current pane's directory.
- `--theme` picks Rose Pine (dark) or Rose Pine Dawn (light). By default the
  dashboard follows the terminal's background color.
- `--no-bg` keeps the terminal's own background.
- `--sidebar` shows only the lists, and inside a multiplexer stays open
  after a switch. See [Keep it open in a sidebar](#keep-it-open-in-a-sidebar).
  herdr has a sidebar of its own, and in herdr Escape does nothing.

Inside a multiplexer the dashboard lists only that multiplexer, or each one
it runs in when they are nested. herdr workspaces appear as sessions, and
herdr agents show herdr's own status: working, idle, blocked or done.

A new session with an empty name is named after the git repository or the
directory it starts in. If a session with that name exists, the dashboard
switches to it instead.

Each agent has its own icon. To detect more agent programs, list their
names. These agents share the icon `◇`:

```sh
export MULTIPLEXER_DASHBOARD_AGENTS=kimi,myagent
```

</details>

## Development

```sh
nix develop -c make check   # format, lint, type check and unit tests
nix develop -c make e2e     # end-to-end tests in isolated tmux, zellij and herdr sessions
```

## License

[GPL-3.0](LICENSE)
