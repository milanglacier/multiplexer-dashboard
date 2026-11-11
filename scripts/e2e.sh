#!/usr/bin/env bash
# End-to-end tests: runs multiplexer-dashboard in real tmux, zellij and herdr
# sessions, sends keys and mouse reports, and checks the screen and where
# each multiplexer's client ends up.
#
# Run inside `nix develop`, which provides tmux, zellij, herdr and jq:
#   nix develop -c scripts/e2e.sh
#
# The multiplexers under test get a temporary HOME, XDG directories,
# TMUX_TMPDIR and PATH, and none of the HERDR_* variables, so that nothing
# reaches the user's own sessions. A separate tmux server, the harness,
# plays the terminal: each check runs the dashboard or a multiplexer client
# in one of its windows and reads the window with capture-pane. A check
# whose multiplexer is not installed is skipped. Set KEEP=1 to keep the
# temporary directory.

# No `set -e`: a failed check is counted and the run continues.
set -uo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
dash="$root/multiplexer-dashboard"
command -v tmux >/dev/null || { echo "tmux not found" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 2; }
have() { command -v "$1" >/dev/null; }

# Unix socket paths are limited to about 100 bytes, and the multiplexers
# put their sockets under this directory, so it stays short.
tmp=$(mktemp -d /tmp/mdx.XXXXXX)

# Every multiplexer, including the harness, runs isolated from the user's.
for v in $(env | sed -n 's/^\(HERDR_[A-Za-z0-9_]*\)=.*/\1/p'); do unset "$v"; done
unset TMUX TMUX_PANE ZELLIJ ZELLIJ_SESSION_NAME ZELLIJ_PANE_ID MULTIPLEXER_DASHBOARD_AGENTS
export HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/config" XDG_CACHE_HOME="$tmp/cache" \
    XDG_DATA_HOME="$tmp/data" XDG_STATE_HOME="$tmp/state" XDG_RUNTIME_DIR="$tmp/run" \
    TMUX_TMPDIR="$tmp/tmux" ZELLIJ_CONFIG_DIR="$tmp/config/zellij" \
    PATH="$tmp/bin:$PATH" SHELL="$tmp/bin/mux-shell"
mkdir -p "$HOME" "$XDG_CONFIG_HOME/herdr" "$ZELLIJ_CONFIG_DIR" "$XDG_CACHE_HOME" \
    "$XDG_DATA_HOME" "$XDG_STATE_HOME" "$XDG_RUNTIME_DIR" "$TMUX_TMPDIR" "$tmp/bin" \
    "$tmp/lib/node_modules/gemini/bin" "$tmp/proj/repo/sub" "$tmp/proj/plain"
chmod 700 "$XDG_RUNTIME_DIR"
git -C "$tmp/proj/repo" init -q

t() { tmux -L harness -f /dev/null "$@"; }

cleanup() {
    t kill-server 2>/dev/null
    tmux kill-server 2>/dev/null
    have zellij && zellij kill-all-sessions -y >/dev/null 2>&1
    have herdr && herdr server stop >/dev/null 2>&1
    if [[ -z "${KEEP:-}" ]]; then rm -rf "$tmp"; else echo "kept $tmp"; fi
}
trap cleanup EXIT

# The shell of every multiplexer, with a known prompt.
cat >"$tmp/bin/mux-shell" <<'EOF'
#!/bin/sh
exec env PS1='$ ' bash --norc --noprofile "$@"
EOF
# Runs a command outside the harness tmux.
cat >"$tmp/bin/clean" <<'EOF'
#!/bin/sh
exec env -u TMUX -u TMUX_PANE "$@"
EOF
# Fake agents print a line and wait. tmux and zellij name a pane's program
# after argv[0], so `exec -a` gives each its name. gemini runs as an
# argument of node, as the real one does.
cat >"$tmp/lib/agent-loop" <<'EOF'
printf '\033[1;35mfake %s\033[0m in %s\n' "$FAKE_NAME" "$PWD"
trap exit TERM HUP
while :; do sleep 1000 & wait; done
EOF
for a in claude codex opencode pi amp; do
    cat >"$tmp/bin/$a" <<EOF
#!/usr/bin/env bash
FAKE_NAME=$a exec -a $a bash $tmp/lib/agent-loop
EOF
done
cp "$tmp/lib/agent-loop" "$tmp/lib/node_modules/gemini/bin/gemini"
cat >"$tmp/bin/gemini" <<EOF
#!/usr/bin/env bash
FAKE_NAME=gemini exec -a node bash $tmp/lib/node_modules/gemini/bin/gemini
EOF
chmod +x "$tmp/bin/"*

failures=0
screen() { t capture-pane -p -t "$1"; }

# wait_for PANE TEXT [SECONDS]: polls the screen until TEXT appears.
wait_for() {
    local pane=$1 text=$2 deadline=$((SECONDS + ${3:-15}))
    while ((SECONDS < deadline)); do
        [[ "$(screen "$pane")" == *"$text"* ]] && return 0
        sleep 0.1
    done
    echo "FAIL: [$pane] timed out waiting for: $text" >&2
    screen "$pane" | sed 's/^/    | /' >&2
    failures=$((failures + 1))
    return 1
}

# wait_gone PANE TEXT: polls until TEXT is no longer on the screen.
wait_gone() {
    local deadline=$((SECONDS + 15))
    while ((SECONDS < deadline)); do
        [[ "$(screen "$1")" != *"$2"* ]] && return 0
        sleep 0.1
    done
    echo "FAIL: [$1] still showing: $2" >&2
    screen "$1" | sed 's/^/    | /' >&2
    failures=$((failures + 1))
    return 1
}

check() {
    local what=$1 got=$2 want=$3
    if [[ "$got" == "$want" ]]; then
        echo "ok: $what"
    else
        echo "FAIL: $what: got [$got], want [$want]" >&2
        failures=$((failures + 1))
    fi
}

# eventually WHAT WANT COMMAND...: polls COMMAND until it prints WANT.
eventually() {
    local what=$1 want=$2 got deadline=$((SECONDS + 15))
    shift 2
    while :; do
        got=$("$@" 2>/dev/null)
        [[ "$got" == "$want" ]] && break
        ((SECONDS < deadline)) || break
        sleep 0.1
    done
    check "$what" "$got" "$want"
}

step() { echo "== $*"; }
skip() { echo "skip: $*"; }

# row_of PANE TEXT: the 1-based row of the first line that holds TEXT.
row_of() { screen "$1" | grep -n -F -m1 -- "$2" | cut -d: -f1; }

# selected PANE: the row the cursor is on in the focused list.
selected() { screen "$1" | grep -m1 '▌' | sed 's/^.*▌ *//; s/  .*//'; }

# click PANE X Y: a left-button press and release at the 1-based cell X, Y.
click() {
    t send-keys -t "$1" -l $'\e'"[<0;$2;$3M"
    t send-keys -t "$1" -l $'\e'"[<0;$2;$3m"
}

# filter PANE TEXT: filters the lists, keeps the filter and waits for it.
filter() {
    t send-keys -t "$1" -l "/$2"
    wait_for "$1" " /  $2" >/dev/null
    t send-keys -t "$1" Enter
    wait_gone "$1" " /  $2" >/dev/null
}

# A dashboard in a harness window, outside every multiplexer.
open_outside() {
    t new-window -d -t e2e -n "$1" \
        "cd $tmp/proj/plain && clean $dash --theme dark ${2:-}; echo EXIT=\$?; sleep 600"
    wait_for "e2e:$1" "outside any multiplexer" >/dev/null
}

t new-session -d -s e2e -n main -x 130 -y 40
t set -g default-size 130x40

# ---------------------------------------------------------------- setup

step "setup: tmux sessions"
tm() { tmux -f /dev/null "$@"; }
tm new-session -d -s alpha -c "$tmp/proj/repo" -x 120 -y 30
tm new-window -d -t alpha: -n agent -c "$tmp/proj/repo" amp
tm new-session -d -s beta -c "$tmp/proj/plain" -x 120 -y 30
tm send-keys -t beta: gemini Enter
tm new-session -d -s spare -c "$tmp/proj/plain"
tm new-session -d -s victim -c "$tmp/proj/plain"
amp_pane=$(tm display -p -t alpha:agent '#{pane_id}')
gemini_pane=$(tm display -p -t beta: '#{pane_id}')
# The dashboard opens in a modal floating pane, with and without --client.
# new-pane does not expand formats in its command, so run-shell -C does.
tm bind -n M-d run-shell -C "new-pane -O -x90% -y90% -X5% -Y5% -c '#{pane_current_path}' \
    \"$dash --theme dark --client '#{client_name}'\""
tm bind -n M-e new-pane -O -x90% -y90% -X5% -Y5% "$dash --theme dark"

if have zellij; then
    step "setup: zellij sessions"
    cat >"$ZELLIJ_CONFIG_DIR/config.kdl" <<EOF
show_startup_tips false
show_release_notes false
keybinds {
    shared_except "locked" {
        bind "Alt d" {
            Run "$dash" "--theme" "dark" {
                floating true
                close_on_exit true
                width "90%"
                height "90%"
                x "5%"
                y "5%"
            }
        }
    }
}
EOF
    # A layout, since tabs added to a background session before a client
    # attaches get no panes.
    cat >"$tmp/zone.kdl" <<EOF
layout {
    tab name="code" focus=true {
        pane
        pane command="claude"
    }
    tab name="second" cwd="$tmp/proj/plain" {
        pane command="codex"
    }
}
EOF
    (
        cd "$tmp/proj/repo" || exit
        zellij --layout "$tmp/zone.kdl" attach --create-background zone
        for s in ztwo zgone zdel zkill; do zellij attach --create-background $s; done
    )
    for s in zgone zdel; do
        deadline=$((SECONDS + 10))
        until zellij --session $s action list-panes -j >/dev/null 2>&1 || ((SECONDS > deadline)); do
            sleep 0.1
        done
        # Saved before it is killed, so that zellij can resurrect it.
        zellij --session $s action save-session
        zellij kill-session $s
    done
    eventually "zellij lists the exited sessions" 2 \
        sh -c 'zellij list-sessions --no-formatting | grep -c EXITED'
fi

if have herdr; then
    step "setup: herdr workspaces"
    cat >"$XDG_CONFIG_HOME/herdr/config.toml" <<EOF
onboarding = false

[[keys.command]]
key = "prefix+alt+d"
type = "popup"
command = "$dash --theme dark"
width = 120
height = 34
EOF
    (cd "$tmp" && nohup herdr server >/dev/null 2>&1 &)
    deadline=$((SECONDS + 10))
    until herdr workspace list >/dev/null 2>&1 || ((SECONDS > deadline)); do sleep 0.1; done
    hpane() { herdr workspace create --cwd "$1" --label "$2" --no-focus | jq -r .result.root_pane.pane_id; }
    hone_pane=$(hpane "$tmp/proj/repo" hone)
    htwo_pane=$(hpane "$tmp/proj/plain" htwo)
    hpane "$tmp/proj/plain" hdoomed >/dev/null
    herdr pane run "$hone_pane" pi >/dev/null
    herdr pane run "$htwo_pane" opencode >/dev/null
    deadline=$((SECONDS + 10))
    until [[ $(herdr agent list | jq '.result.agents | length') == 2 ]] || ((SECONDS > deadline)); do
        sleep 0.1
    done
    herdr pane report-agent --source e2e --agent pi --state blocked "$hone_pane" >/dev/null
    workspace_id() { herdr workspace list | jq -r --arg l "$1" '.result.workspaces[] | select(.label == $l) | .workspace_id'; }
    focused_workspace() { herdr workspace list | jq -r '.result.workspaces[] | select(.focused) | .label'; }
fi

# ---------------------------------------------------------------- outside

step "outside: every multiplexer, in the order zellij, herdr, tmux"
open_outside out
w=e2e:out
wait_for $w "✦ gemini" && echo "ok: an agent that runs in node is found by its argument"
wait_for $w "↯ amp" >/dev/null
rows=""
for m in zellij herdr tmux; do
    have $m && rows+="$(row_of $w "│ $m ─") "
done
check "groups in order" "$(tr ' ' '\n' <<<"$rows" | grep . | sort -n | tr '\n' ' ')" "$rows"
if have zellij; then
    wait_for $w "exited" && echo "ok: an exited zellij session is listed"
fi
if have herdr; then
    wait_for $w "× blocked" && echo "ok: herdr's agent status"
fi
check "the cursor starts on the first session" \
    "$(screen $w | grep -A1 -m1 '│ [a-z]* ─' | tail -1 | grep -c '▌')" 1

step "outside: Alt keys jump between multiplexers"
if have zellij && have herdr; then
    first=$(selected $w)
    t send-keys -t $w M-j
    wait_for $w "▌   hone" && echo "ok: alt+j"
    t send-keys -t $w M-k
    wait_for $w "▌   $first" && echo "ok: alt+k"
fi

step "outside: filter, preview"
filter $w amp
t send-keys -t $w Tab
wait_for $w "fake amp" && echo "ok: the preview shows the agent's pane"
check "the filter hides other agents" "$(screen $w | grep -c '✦ gemini')" 0
t send-keys -t $w Escape
wait_for $w "✦ gemini" >/dev/null && echo "ok: escape clears the filter"

step "outside: help, ctrl+l"
t send-keys -t $w '?'
wait_for $w "next / previous multiplexer" && echo "ok: help"
t send-keys -t $w x
wait_gone $w "next / previous multiplexer"
t send-keys -t $w C-l
wait_for $w "✦ gemini" >/dev/null && echo "ok: ctrl+l redraws"

step "outside: below 72 columns the preview is hidden"
t resize-window -t $w -x 70
wait_gone $w "Preview" && echo "ok: no preview at 70 columns"
t resize-window -t $w -x 36
wait_for $w "Make the window at least 40×12." && echo "ok: too small"
t resize-window -t $w -x 130
wait_for $w "Preview" && echo "ok: the preview is back"

step "outside: a click selects, a second click attaches"
t send-keys -t $w Tab
row=$(row_of $w "beta ")
click $w 6 "$row"
wait_for $w "▌   beta" && echo "ok: a click selects"
click $w 6 "$row"
eventually "the attached tmux client is in beta" beta tm list-clients -F '#{session_name}'
t kill-window -t $w

step "outside: Enter on a tmux agent attaches to its pane"
open_outside tagent
filter e2e:tagent gemini
t send-keys -t e2e:tagent Tab Enter
eventually "the tmux client is on the gemini pane" "$gemini_pane" tm list-clients -F '#{pane_id}'
t kill-window -t e2e:tagent

if have zellij; then
    step "outside: Enter on a zellij agent attaches to its pane"
    open_outside zagent
    filter e2e:zagent codex
    t send-keys -t e2e:zagent Tab Enter
    codex_pane=$(zellij --session zone action list-panes -j |
        jq -r '.[] | select(.pane_command // "" | startswith("codex")) | "terminal_\(.id)"')
    eventually "the zellij client is on the codex pane" "$codex_pane" \
        sh -c 'zellij --session zone action list-clients | awk "NR > 1 { print \$2 }"'
    t kill-window -t e2e:zagent
else
    skip "zellij not installed"
fi

if have herdr; then
    step "outside: Enter on a herdr agent attaches with its workspace focused"
    open_outside hagent
    filter e2e:hagent opencode
    t send-keys -t e2e:hagent Tab Enter
    wait_for e2e:hagent "fake opencode" && echo "ok: the herdr client shows the agent"
    check "herdr focused htwo" "$(focused_workspace)" htwo
    t kill-window -t e2e:hagent
else
    skip "herdr not installed"
fi

# ---------------------------------------------------------------- tmux

step "inside tmux: only tmux, Enter switches the client that opened it"
t new-window -d -t e2e -n tin "clean tmux attach -t =alpha"
t new-window -d -t e2e -n tother "clean tmux attach -t =spare"
wait_for e2e:tin '$' >/dev/null
client=$(tm list-clients -F '#{client_name} #{session_name}' | awk '$2 == "alpha" { print $1 }')
t send-keys -t e2e:tin M-d
wait_for e2e:tin "in tmux" && echo "ok: the context is tmux"
check "only tmux is listed" "$(screen e2e:tin | grep -c -e 'zellij ─' -e 'herdr ─')" 0
wait_for e2e:tin "● alpha" && echo "ok: the current session is marked"
filter e2e:tin beta
t send-keys -t e2e:tin Enter
eventually "the client switched to beta" beta \
    tm display -p -c "$client" '#{session_name}'
check "the other client stayed" "$(tm list-clients -F '#{session_name}' | sort | tr '\n' ' ')" "beta spare "
eventually "the floating pane closed" 0 \
    sh -c 'tmux list-panes -a -F "#{pane_floating_flag}" | grep -c 1'

step "inside tmux: Enter on an agent lands on its pane"
t send-keys -t e2e:tin M-d
wait_for e2e:tin "in tmux" >/dev/null
filter e2e:tin amp
t send-keys -t e2e:tin Tab Enter
eventually "the client is on the amp pane" "$amp_pane" tm display -p -c "$client" '#{pane_id}'

step "inside tmux: without --client, tmux switches the calling client"
t send-keys -t e2e:tin M-e
wait_for e2e:tin "in tmux" >/dev/null
filter e2e:tin beta
t send-keys -t e2e:tin Enter
eventually "the calling client switched to beta" beta \
    tm display -p -c "$client" '#{session_name}'
check "the other client stayed" "$(tm list-clients -F '#{session_name}' | sort | tr '\n' ' ')" "beta spare "

step "inside tmux: a new session from the directory, then the same name again"
t send-keys -t e2e:tin M-d
wait_for e2e:tin "in tmux" >/dev/null
t send-keys -t e2e:tin n
wait_for e2e:tin "empty: plain" && echo "ok: the automatic name"
t send-keys -t e2e:tin -l made
t send-keys -t e2e:tin Enter
eventually "the client is in the new session" made tm display -p -c "$client" '#{session_name}'
t send-keys -t e2e:tin M-d
wait_for e2e:tin "in tmux" >/dev/null
t send-keys -t e2e:tin n
t send-keys -t e2e:tin -l beta
t send-keys -t e2e:tin Enter
eventually "an existing name switches to it" beta tm display -p -c "$client" '#{session_name}'
check "no duplicate session" "$(tm list-sessions -F '#{session_name}' | grep -c '^beta')" 1
t kill-window -t e2e:tin
t kill-window -t e2e:tother

# ---------------------------------------------------------------- zellij

zclients() { zellij --session "$1" action list-clients 2>/dev/null | awk 'NR > 1 { print $2 }'; }

if have zellij; then
    step "inside zellij: only zellij, switching sessions"
    t new-window -d -t e2e -n zin "clean zellij attach zone"
    eventually "a zellij client attached" 1 sh -c 'zellij --session zone action list-clients | awk "NR > 1" | wc -l'
    t send-keys -t e2e:zin M-d
    wait_for e2e:zin "in zellij" && echo "ok: the context is zellij"
    check "only zellij is listed" "$(screen e2e:zin | grep -c -e 'tmux ─' -e 'herdr ─')" 0
    wait_for e2e:zin "● zone" && echo "ok: the current session is marked"
    filter e2e:zin ztwo
    t send-keys -t e2e:zin Enter
    eventually "the client switched to ztwo" 1 sh -c 'zellij --session ztwo action list-clients | awk "NR > 1" | wc -l'

    step "inside zellij: Enter on an agent in another session"
    t send-keys -t e2e:zin M-d
    wait_for e2e:zin "in zellij" >/dev/null
    filter e2e:zin codex
    t send-keys -t e2e:zin Tab Enter
    eventually "the client is on the codex pane in zone" "$codex_pane" zclients zone

    step "inside zellij: Enter on an agent in the current session"
    t send-keys -t e2e:zin M-d
    wait_for e2e:zin "in zellij" >/dev/null
    filter e2e:zin claude
    t send-keys -t e2e:zin Tab Enter
    claude_pane=$(zellij --session zone action list-panes -j |
        jq -r '.[] | select(.pane_command // "" | startswith("claude")) | "terminal_\(.id)"')
    eventually "the client is on the claude pane" "$claude_pane" zclients zone

    step "inside zellij: Enter on an exited session resurrects it"
    t send-keys -t e2e:zin M-d
    wait_for e2e:zin "in zellij" >/dev/null
    filter e2e:zin zgone
    t send-keys -t e2e:zin Enter
    eventually "zgone runs again" 0 sh -c 'zellij list-sessions --no-formatting | grep "^zgone " | grep -c EXITED'
    eventually "the client is in zgone" 1 sh -c 'zellij --session zgone action list-clients | awk "NR > 1" | wc -l'
    t kill-window -t e2e:zin
fi

# ---------------------------------------------------------------- herdr

if have herdr; then
    step "inside herdr: only workspaces, with the agent status"
    t new-window -d -t e2e -n hin "clean herdr"
    wait_for e2e:hin '$' >/dev/null
    t send-keys -t e2e:hin C-b
    sleep 0.3
    t send-keys -t e2e:hin M-d
    wait_for e2e:hin "in herdr" && echo "ok: the context is herdr"
    check "only herdr is listed" "$(screen e2e:hin | grep -c -e 'tmux ─' -e 'zellij ─')" 0
    wait_for e2e:hin "blocked" && echo "ok: the agent status"
    filter e2e:hin hone
    t send-keys -t e2e:hin Enter
    eventually "herdr focused hone" hone focused_workspace
    wait_gone e2e:hin "in herdr" && echo "ok: the popup closed"
    t kill-window -t e2e:hin
fi

# ---------------------------------------------------------------- nested

step "nested: zellij inside tmux lists both"
sock=$(tm display -p -t alpha: '#{socket_path}')
t new-window -d -t e2e -n nested \
    "clean env TMUX=$sock,1,0 ZELLIJ=0 ZELLIJ_SESSION_NAME=zone $dash --theme dark; sleep 600"
wait_for e2e:nested "in zellij and tmux" && echo "ok: the context"
wait_for e2e:nested "✦ gemini" >/dev/null
have zellij && wait_for e2e:nested "◎ codex" >/dev/null
check "zellij and tmux listed, without herdr" \
    "$(screen e2e:nested | grep -c -e '│ zellij ─' -e '│ tmux ─' -e '│ herdr ─')" \
    "$(have zellij && echo 4 || echo 2)"
t kill-window -t e2e:nested

# ---------------------------------------------------------------- manage

step "rename and kill, checked through each multiplexer"
open_outside manage
w=e2e:manage
wait_for $w "✦ gemini" >/dev/null
filter $w spare
t send-keys -t $w r
wait_for $w "Rename session" >/dev/null
t send-keys -t $w C-u
t send-keys -t $w -l "spare.b"
t send-keys -t $w Enter
eventually "tmux renamed spare to spare-b" spare-b \
    sh -c 'tmux list-sessions -F "#{session_name}" | grep spare'
t send-keys -t $w Escape
filter $w victim
t send-keys -t $w x
wait_for $w "Kill tmux session victim?" && echo "ok: the kill dialog"
t send-keys -t $w y
eventually "tmux killed victim" 0 sh -c 'tmux list-sessions -F "#{session_name}" | grep -c victim'
t send-keys -t $w Escape
if have zellij; then
    filter $w zkill
    t send-keys -t $w x y
    eventually "zellij killed zkill" 0 \
        sh -c 'zellij list-sessions --no-formatting | grep "^zkill " | grep -vc EXITED'
    t send-keys -t $w Escape
    filter $w zdel
    t send-keys -t $w x
    wait_for $w "Delete zellij session zdel?" && echo "ok: the delete dialog"
    t send-keys -t $w y
    eventually "zellij deleted zdel" 0 sh -c 'zellij list-sessions --no-formatting | grep -c "^zdel "'
    t send-keys -t $w Escape
    filter $w ztwo
    t send-keys -t $w r C-u
    t send-keys -t $w -l "ztwo-b"
    t send-keys -t $w Enter
    eventually "zellij renamed ztwo" 1 sh -c 'zellij list-sessions --no-formatting | grep -c "^ztwo-b "'
    t send-keys -t $w Escape
fi
if have herdr; then
    filter $w htwo
    t send-keys -t $w r C-u
    t send-keys -t $w -l "htwo-b"
    t send-keys -t $w Enter
    eventually "herdr renamed htwo" "htwo-b" \
        sh -c 'herdr workspace list | jq -r ".result.workspaces[].label" | grep htwo'
    t send-keys -t $w Escape
    filter $w hdoomed
    t send-keys -t $w x y
    eventually "herdr closed hdoomed" "" \
        sh -c 'herdr workspace list | jq -r ".result.workspaces[].label" | grep hdoomed'
    t send-keys -t $w Escape
fi

step "outside: new session in the selected row's multiplexer, named after the repository"
t kill-window -t $w
open_outside new "--dir $tmp/proj/repo/sub"
w=e2e:new
filter $w beta
t send-keys -t $w n
wait_for $w "empty: repo" && echo "ok: named after the repository"
wait_for $w "in tmux" >/dev/null
t send-keys -t $w Enter
eventually "tmux created repo" "$tmp/proj/repo/sub" tm display -p -t '=repo:' '#{session_path}'
eventually "the client attached to it" repo tm list-clients -F '#{session_name}'
t kill-window -t $w

if have herdr; then
    step "outside: Tab in the new-session dialog cycles the multiplexers"
    open_outside newh
    w=e2e:newh
    t send-keys -t $w n
    wait_for $w "New session" >/dev/null
    for _ in 1 2 3; do
        screen $w | grep -q "in herdr" && break
        t send-keys -t $w Tab
        sleep 0.2
    done
    wait_for $w "in herdr" && echo "ok: tab reached herdr"
    t send-keys -t $w -l fresh
    t send-keys -t $w Enter
    eventually "herdr created and focused fresh" fresh focused_workspace
    t kill-window -t $w
fi

# ---------------------------------------------------------------- terminal

step "after quitting, the shell and the terminal settings are back"
t new-window -d -t e2e -n sh "clean env PS1='$ ' bash --norc --noprofile"
wait_for e2e:sh '$' >/dev/null
t send-keys -t e2e:sh -l "s=\$(stty -g); $dash --theme dark; echo \"exit=\$? same=\$([ \"\$s\" = \"\$(stty -g)\" ] && echo yes)\""
t send-keys -t e2e:sh Enter
wait_for e2e:sh "outside any multiplexer" >/dev/null
t send-keys -t e2e:sh q
wait_for e2e:sh "exit=0 same=yes" && echo "ok: q restores the terminal"
t send-keys -t e2e:sh -l "$dash --theme dark; echo \"exit=\$? same=\$([ \"\$s\" = \"\$(stty -g)\" ] && echo yes)\""
t send-keys -t e2e:sh Enter
wait_for e2e:sh "outside any multiplexer" >/dev/null
t send-keys -t e2e:sh C-c
wait_for e2e:sh "exit=0 same=yes" && echo "ok: ctrl+c restores the terminal"
t send-keys -t e2e:sh -l "echo still-works"
t send-keys -t e2e:sh Enter
wait_for e2e:sh "still-works" >/dev/null && echo "ok: the shell prompt works"

if ((failures)); then
    echo "$failures failure(s)" >&2
    exit 1
fi
echo "all e2e checks passed"
