// Prototype of the multiplexer dashboard, layout A (sidebar + preview), in
// Bubble Tea v2. Everything here is mock data: no multiplexer is queried and
// no command runs. Each action shows the command the real app would run, and
// the list is printed on exit.
//
//	go run . [-context outside|tmux|zellij|herdr|nested] [-theme auto|light|dark] [-inline]
//
// Prototype-only keys: C cycles the context, T toggles light/dark.
package main

import (
	"flag"
	"fmt"
	"image/color"
	"os"
	"regexp"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

// ---------------------------------------------------------------- mock data

type session struct {
	Name, ID, Cwd, Age string
	Tabs               []string
	Exited, Attached   bool
}

type agent struct {
	Mux, Session, Tab, Pane, Name string
	Status                        string // only herdr reports one
}

func mockData() (map[string][]*session, []*agent) {
	data := map[string][]*session{
		"zellij": {
			{Name: "dotfiles", Tabs: []string{"dotfiles", "dotfiles/config"}, Cwd: "~/Desktop/dotfiles", Age: "3h"},
			{Name: "duanyan-tui", Tabs: []string{"duanyan-tui", "duanyan-tui/crates"}, Cwd: "~/Desktop/personal-projects/duanyan-tui", Age: "1d"},
			{Name: "pi-mono", Tabs: []string{"pi-mono"}, Cwd: "~/Desktop/personal-projects/pi-mono", Age: "20m"},
			{Name: "old-notes", Cwd: "~/notes", Age: "6d", Exited: true},
		},
		"herdr": {
			{Name: "agent-scratch", ID: "w4R", Tabs: []string{"1"}, Cwd: "~/Desktop/personal-projects/agent-scratch"},
			{Name: "multiplexer-dashboard", ID: "w53", Tabs: []string{"1", "2"}, Cwd: "~/Desktop/personal-projects/multiplexer-dashboard"},
			{Name: "herdr", ID: "w60", Tabs: []string{"1"}, Cwd: "~/Desktop/personal-projects/herdr"},
		},
		"tmux": {
			{Name: "~", Tabs: []string{"zsh", "btop"}, Cwd: "~", Age: "2d", Attached: true},
			{Name: "scratch", Tabs: []string{"zsh"}, Cwd: "~", Age: "5h"},
			{Name: "monopi", Tabs: []string{"nvim", "pi", "zsh"}, Cwd: "~/Desktop/personal-projects/monopi", Age: "40m"},
		},
	}
	agents := []*agent{
		{Mux: "zellij", Session: "dotfiles", Tab: "dotfiles", Pane: "terminal_2", Name: "claude"},
		{Mux: "zellij", Session: "duanyan-tui", Tab: "duanyan-tui", Pane: "terminal_1", Name: "claude"},
		{Mux: "zellij", Session: "duanyan-tui", Tab: "duanyan-tui/crates", Pane: "terminal_5", Name: "codex"},
		{Mux: "herdr", Session: "multiplexer-dashboard", Tab: "1", Pane: "w53:pB", Name: "claude", Status: "working"},
		{Mux: "herdr", Session: "herdr", Tab: "1", Pane: "w60:p2", Name: "opencode", Status: "idle"},
		{Mux: "herdr", Session: "agent-scratch", Tab: "1", Pane: "w4R:p1", Name: "pi", Status: "blocked"},
		{Mux: "tmux", Session: "monopi", Tab: "2:pi", Pane: "%7", Name: "pi"},
		{Mux: "tmux", Session: "~", Tab: "1:zsh", Pane: "%2", Name: "gemini"},
	}
	return data, agents
}

type muxContext struct {
	Key, Label string
	Groups     []string // listed multiplexers, in display order
	Inside     []string
	Current    map[string]string
}

var contexts = []*muxContext{
	{Key: "outside", Label: "outside any multiplexer", Groups: []string{"zellij", "herdr", "tmux"}, Current: map[string]string{}},
	{Key: "tmux", Label: "in tmux", Groups: []string{"tmux"}, Inside: []string{"tmux"}, Current: map[string]string{"tmux": "~"}},
	{Key: "zellij", Label: "in zellij", Groups: []string{"zellij"}, Inside: []string{"zellij"}, Current: map[string]string{"zellij": "dotfiles"}},
	{Key: "herdr", Label: "in herdr", Groups: []string{"herdr"}, Inside: []string{"herdr"}, Current: map[string]string{"herdr": "multiplexer-dashboard"}},
	{Key: "nested", Label: "zellij in tmux", Groups: []string{"zellij", "tmux"}, Inside: []string{"zellij", "tmux"}, Current: map[string]string{"zellij": "dotfiles", "tmux": "~"}},
}

// ---------------------------------------------------------------- theme

// Rose Pine Dawn and Rose Pine, as in the herdr config.
type theme struct {
	base, surface, overlay, muted, subtle, text, love, gold, rose, pine, foam, iris, hlLow, hlMed, hlHigh color.Color
}

func newTheme(dark bool) theme {
	c := lipgloss.Color
	if dark {
		return theme{c("#191724"), c("#1f1d2e"), c("#26233a"), c("#6e6a86"), c("#908caa"), c("#e0def4"),
			c("#eb6f92"), c("#f6c177"), c("#ebbcba"), c("#31748f"), c("#9ccfd8"), c("#c4a7e7"),
			c("#21202e"), c("#403d52"), c("#524f67")}
	}
	return theme{c("#faf4ed"), c("#fffaf3"), c("#f2e9e1"), c("#9893a5"), c("#797593"), c("#575279"),
		c("#b4637a"), c("#ea9d34"), c("#d7827e"), c("#286983"), c("#56949f"), c("#907aa9"),
		c("#f4ede8"), c("#dfdad9"), c("#cecacd")}
}

func (t theme) mux(name string) color.Color {
	switch name {
	case "zellij":
		return t.foam
	case "herdr":
		return t.iris
	}
	return t.rose
}

// ---------------------------------------------------------------- text helpers

var plain = lipgloss.NewStyle()

// fit truncates or pads a styled string to exactly w cells.
func fit(s string, w int, pad lipgloss.Style) string {
	if w <= 0 {
		return ""
	}
	if lipgloss.Width(s) > w {
		s = ansi.Truncate(s, w, "…")
	}
	if n := w - lipgloss.Width(s); n > 0 {
		s += pad.Render(strings.Repeat(" ", n))
	}
	return s
}

// lr puts right at the right edge and truncates left to make room for it.
func lr(left, right string, w int, pad lipgloss.Style) string {
	rw := lipgloss.Width(right)
	if rw >= w {
		return fit(right, w, pad)
	}
	return fit(left, w-rw, pad) + right
}

func plural(n int, unit string) string {
	if n == 1 {
		return fmt.Sprintf("%d %s", n, unit)
	}
	return fmt.Sprintf("%d %ss", n, unit)
}

// painter adds the selection background to every segment of a row.
type painter struct{ bg color.Color }

func (p painter) st(s lipgloss.Style) lipgloss.Style {
	if p.bg != nil {
		return s.Background(p.bg)
	}
	return s
}
func (p painter) r(s lipgloss.Style, text string) string { return p.st(s).Render(text) }

// ---------------------------------------------------------------- model

const (
	rowGroup = iota
	rowSession
	rowAgent
)

type row struct {
	kind  int
	mux   string
	s     *session
	a     *agent
	count int
}

const (
	listSessions = iota
	listAgents
)

type hit struct{ y, x0, x1, list, idx int }

type (
	frameMsg time.Time
	toastMsg int
)

type model struct {
	w, h      int
	dark      bool
	themeLock bool // -theme light/dark ignores the terminal's answer
	th        theme

	data   map[string][]*session
	agents []*agent
	ctx    int

	focus  int
	cur    [2]int
	filter string

	mode   string // "", filter, rename, kill, new
	input  string
	target row
	newMux string

	toast     string
	toastWarn bool
	toastSeq  int
	log       []string

	frame  int
	hits   []hit
	inline bool // draw below the prompt instead of on the alternate screen
}

func (m *model) c() *muxContext { return contexts[m.ctx] }

func (m *model) inside(mux string) bool {
	for _, x := range m.c().Inside {
		if x == mux {
			return true
		}
	}
	return false
}

func (m *model) isCurrent(mux, name string) bool { return m.c().Current[mux] == name }

func (m *model) agentsOf(mux, name string) []*agent {
	var out []*agent
	for _, a := range m.agents {
		if a.Mux == mux && a.Session == name {
			out = append(out, a)
		}
	}
	return out
}

func (m *model) matches(fields ...string) bool {
	q := strings.ToLower(m.filter)
	if q == "" {
		return true
	}
	for _, f := range fields {
		if strings.Contains(strings.ToLower(f), q) {
			return true
		}
	}
	return false
}

func (m *model) rows(list int) []row {
	var rows []row
	for _, mux := range m.c().Groups {
		var block []row
		if list == listSessions {
			for _, s := range m.data[mux] {
				if m.matches(s.Name) {
					block = append(block, row{kind: rowSession, mux: mux, s: s})
				}
			}
		} else {
			for _, a := range m.agents {
				if a.Mux == mux && m.matches(a.Name, a.Session, a.Tab) {
					block = append(block, row{kind: rowAgent, mux: mux, a: a})
				}
			}
		}
		if len(block) > 0 {
			rows = append(rows, row{kind: rowGroup, mux: mux, count: len(block)})
			rows = append(rows, block...)
		}
	}
	return rows
}

func selectable(rows []row) []row {
	var out []row
	for _, r := range rows {
		if r.kind != rowGroup {
			out = append(out, r)
		}
	}
	return out
}

func (m *model) clamp() {
	for l := range m.cur {
		n := len(selectable(m.rows(l)))
		m.cur[l] = max(0, min(m.cur[l], n-1))
	}
}

func (m *model) selected() (row, bool) {
	items := selectable(m.rows(m.focus))
	if m.cur[m.focus] < len(items) {
		return items[m.cur[m.focus]], true
	}
	return row{}, false
}

// ---------------------------------------------------------------- update

func (m *model) Init() tea.Cmd {
	cmds := []tea.Cmd{tick()}
	if !m.themeLock {
		cmds = append(cmds, tea.RequestBackgroundColor)
	}
	return tea.Batch(cmds...)
}

func tick() tea.Cmd {
	return tea.Tick(110*time.Millisecond, func(t time.Time) tea.Msg { return frameMsg(t) })
}

func (m *model) say(text string, warn bool) tea.Cmd {
	m.toast, m.toastWarn = text, warn
	m.toastSeq++
	seq := m.toastSeq
	return tea.Tick(4*time.Second, func(time.Time) tea.Msg { return toastMsg(seq) })
}

func (m *model) run(cmds []string, closes bool) tea.Cmd {
	entry := "# " + m.c().Label + "\n" + strings.Join(cmds, "\n")
	if closes {
		entry += "\n# the dashboard exits here"
	}
	m.log = append(m.log, entry)
	text := "→ " + cmds[len(cmds)-1]
	if closes {
		text += "   (would exit)"
	}
	return m.say(text, false)
}

func (m *model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.w, m.h = msg.Width, msg.Height
		if m.inline {
			m.h = min(m.h, 22)
		}
	case tea.BackgroundColorMsg:
		if !m.themeLock {
			m.dark = msg.IsDark()
			m.th = newTheme(m.dark)
		}
	case frameMsg:
		m.frame++
		return m, tick()
	case toastMsg:
		if int(msg) == m.toastSeq {
			m.toast = ""
		}
	case tea.MouseClickMsg:
		if msg.Button == tea.MouseLeft {
			for _, h := range m.hits {
				if msg.Y == h.y && msg.X >= h.x0 && msg.X < h.x1 {
					again := m.focus == h.list && m.cur[h.list] == h.idx
					m.focus, m.cur[h.list] = h.list, h.idx
					if again {
						return m, m.enter()
					}
				}
			}
		}
	case tea.MouseWheelMsg:
		d := 1
		if msg.Button == tea.MouseWheelUp {
			d = -1
		}
		m.move(d)
	case tea.KeyPressMsg:
		return m, m.key(msg)
	}
	return m, nil
}

func (m *model) move(d int) {
	n := len(selectable(m.rows(m.focus)))
	if n > 0 {
		m.cur[m.focus] = max(0, min(n-1, m.cur[m.focus]+d))
	}
}

var unsafeName = regexp.MustCompile(`[^A-Za-z0-9_~-]`)

func (m *model) key(msg tea.KeyPressMsg) tea.Cmd {
	k := msg.String()
	if k == "ctrl+c" {
		return tea.Quit
	}
	if m.mode != "" {
		return m.promptKey(msg)
	}
	switch k {
	case "j", "down", "ctrl+n":
		m.move(1)
	case "k", "up", "ctrl+p":
		m.move(-1)
	case "g", "home":
		m.cur[m.focus] = 0
	case "G", "end":
		m.cur[m.focus] = len(selectable(m.rows(m.focus))) - 1
	case "tab", "shift+tab":
		m.focus = 1 - m.focus
	case "enter":
		return m.enter()
	case "/":
		m.mode, m.input = "filter", m.filter
	case "n":
		m.newMux = m.c().Groups[0]
		if r, ok := m.selected(); ok {
			m.newMux = r.mux
		}
		m.mode, m.input = "new", ""
	case "r", "x":
		r, ok := m.selected()
		switch {
		case !ok || r.kind != rowSession:
			return m.say("Rename and kill apply to a session row. Press Tab to switch lists.", true)
		case k == "r" && r.s.Exited:
			return m.say("An exited zellij session cannot be renamed.", true)
		}
		m.target = r
		m.mode, m.input = map[string]string{"r": "rename", "x": "kill"}[k], ""
		if k == "r" {
			m.input = r.s.Name
		}
	case "C":
		m.ctx = (m.ctx + 1) % len(contexts)
		m.filter = ""
	case "T":
		m.dark, m.themeLock = !m.dark, true
		m.th = newTheme(m.dark)
	case "esc", "q":
		if m.filter != "" {
			m.filter = ""
			return nil
		}
		return tea.Quit
	}
	return nil
}

func (m *model) promptKey(msg tea.KeyPressMsg) tea.Cmd {
	k := msg.String()
	if m.mode == "kill" {
		m.mode = ""
		if k == "y" || k == "Y" {
			return m.kill(m.target)
		}
		return nil
	}
	switch k {
	case "esc":
		if m.mode == "filter" {
			m.filter = ""
		}
		m.mode, m.input = "", ""
	case "enter", "down", "up":
		mode, v := m.mode, m.input
		m.mode, m.input = "", ""
		switch mode {
		case "rename":
			return m.rename(m.target, v)
		case "new":
			return m.create(m.newMux, v)
		case "filter":
			if k == "down" {
				m.move(1)
			} else if k == "up" {
				m.move(-1)
			}
		}
	case "backspace":
		if r := []rune(m.input); len(r) > 0 {
			m.input = string(r[:len(r)-1])
		}
	case "ctrl+u":
		m.input = ""
	default:
		if msg.Text == "" || msg.Mod&tea.ModCtrl != 0 {
			return nil
		}
		m.input += msg.Text
	}
	if m.mode == "filter" {
		m.filter = m.input
		m.cur = [2]int{}
	}
	return nil
}

// ---------------------------------------------------------------- actions

func (m *model) enter() tea.Cmd {
	r, ok := m.selected()
	if !ok {
		return nil
	}
	return m.run(m.switchCmds(r), true)
}

func (m *model) switchCmds(r row) []string {
	in := m.inside(r.mux)
	if r.kind == rowSession {
		s := r.s
		switch r.mux {
		case "tmux":
			if in {
				return []string{fmt.Sprintf(`tmux switch-client -c "$client" -t '=%s'`, s.Name)}
			}
			return []string{fmt.Sprintf(`exec tmux attach-session -t '=%s'`, s.Name)}
		case "zellij":
			c := fmt.Sprintf("exec zellij attach '%s'", s.Name)
			if in {
				c = fmt.Sprintf("zellij action switch-session '%s'", s.Name)
			}
			if s.Exited {
				c += "   # resurrects it"
			}
			return []string{c}
		}
		out := []string{"herdr workspace focus " + s.ID}
		if !in {
			out = append(out, "exec herdr")
		}
		return out
	}
	a := r.a
	switch a.Mux {
	case "tmux":
		if in {
			return []string{fmt.Sprintf(`tmux switch-client -c "$client" -t '%s'`, a.Pane)}
		}
		return []string{fmt.Sprintf(`tmux select-window -t '%s' \; select-pane -t '%s'`, a.Pane, a.Pane),
			fmt.Sprintf("exec tmux attach-session -t '%s'", a.Pane)}
	case "zellij":
		switch {
		case !in:
			return []string{fmt.Sprintf("zellij --session '%s' action focus-pane-id %s", a.Session, a.Pane),
				fmt.Sprintf("exec zellij attach '%s'", a.Session)}
		case m.isCurrent("zellij", a.Session):
			return []string{"zellij action focus-pane-id " + a.Pane}
		}
		return []string{fmt.Sprintf("zellij action switch-session '%s' --pane-id %s", a.Session, a.Pane)}
	}
	out := []string{"herdr agent focus " + a.Pane}
	if !in {
		out = append(out, "exec herdr")
	}
	return out
}

func (m *model) rename(r row, name string) tea.Cmd {
	old, n := r.s.Name, unsafeName.ReplaceAllString(name, "-")
	if n == "" || n == old {
		return nil
	}
	cmd := map[string]string{
		"tmux":   fmt.Sprintf("tmux rename-session -t '=%s' '%s'", old, n),
		"zellij": fmt.Sprintf("zellij --session '%s' action rename-session '%s'", old, n),
		"herdr":  fmt.Sprintf("herdr workspace rename %s '%s'", r.s.ID, n),
	}[r.mux]
	for _, a := range m.agents {
		if a.Mux == r.mux && a.Session == old {
			a.Session = n
		}
	}
	if m.c().Current[r.mux] == old {
		m.c().Current[r.mux] = n
	}
	r.s.Name = n
	return m.run([]string{cmd}, false)
}

func (m *model) kill(r row) tea.Cmd {
	s := r.s
	cmd := map[string]string{
		"tmux":   fmt.Sprintf("tmux kill-session -t '=%s'", s.Name),
		"zellij": fmt.Sprintf("zellij kill-session '%s'", s.Name),
		"herdr":  "herdr workspace close " + s.ID,
	}[r.mux]
	if s.Exited {
		cmd = fmt.Sprintf("zellij delete-session '%s'", s.Name)
	}
	list := m.data[r.mux]
	for i, x := range list {
		if x == s {
			m.data[r.mux] = append(list[:i:i], list[i+1:]...)
			break
		}
	}
	kept := m.agents[:0]
	for _, a := range m.agents {
		if !(a.Mux == r.mux && a.Session == s.Name) {
			kept = append(kept, a)
		}
	}
	m.agents = kept
	m.clamp()
	return m.run([]string{cmd}, false)
}

func (m *model) create(mux, name string) tea.Cmd {
	const dir = "~/Desktop/personal-projects/multiplexer-dashboard"
	if name == "" {
		name = "multiplexer-dashboard"
	}
	base := unsafeName.ReplaceAllString(name, "-")
	n := base
	exists := func(n string) bool {
		for _, s := range m.data[mux] {
			if s.Name == n {
				return true
			}
		}
		return false
	}
	// The real app follows multiplexer-new-session: an existing name is a
	// switch, not a duplicate. The prototype always creates.
	for i := 1; exists(n); i++ {
		n = fmt.Sprintf("%s-%d", base, i)
	}
	in := m.inside(mux)
	var cmds []string
	switch mux {
	case "tmux":
		if in {
			cmds = []string{fmt.Sprintf("tmux new-session -d -s '%s' -c %s", n, dir), fmt.Sprintf(`tmux switch-client -c "$client" -t '=%s'`, n)}
		} else {
			cmds = []string{fmt.Sprintf("exec tmux new-session -s '%s' -c %s", n, dir)}
		}
	case "zellij":
		if in {
			cmds = []string{fmt.Sprintf("zellij action switch-session '%s' --cwd %s", n, dir)}
		} else {
			cmds = []string{fmt.Sprintf("cd %s && exec zellij --session '%s'", dir, n)}
		}
	default:
		cmds = []string{fmt.Sprintf("herdr workspace create --cwd %s --label '%s' --focus", dir, n)}
		if !in {
			cmds = append(cmds, "exec herdr")
		}
	}
	m.data[mux] = append(m.data[mux], &session{Name: n, ID: "wNEW", Tabs: []string{"1"}, Cwd: dir, Age: "0s"})
	return m.run(cmds, true)
}

// ---------------------------------------------------------------- view

var spinner = []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}

func (m *model) View() tea.View {
	m.hits = m.hits[:0]
	var s string
	if m.w < 30 || m.h < 10 {
		s = "Make the popup bigger (at least 30×10)."
	} else {
		m.clamp()
		s = m.render()
	}
	v := tea.NewView(s)
	// Inline, mouse rows would be relative to the terminal, not to the view.
	if !m.inline {
		v.AltScreen = true
		v.MouseMode = tea.MouseModeCellMotion
	}
	return v
}

func (m *model) render() string {
	t := m.th
	H := m.h - 2 // the header and the footer
	wide := m.w >= 72
	lw := m.w
	if wide {
		lw = max(34, min(46, m.w*2/5))
	}
	sh := max(4, (H*11+19)/20)
	ah := H - sh
	left := m.listPanel(listSessions, "Sessions", 0, 1, lw, sh)
	left = append(left, m.listPanel(listAgents, "Agents", 0, 1+sh, lw, ah)...)
	body := left
	if wide {
		right := m.previewPanel(m.w-lw, H)
		for i := range body {
			body[i] += right[i]
		}
	}
	_ = t
	return strings.Join(append(append([]string{m.header()}, body...), m.footer()), "\n")
}

func (m *model) header() string {
	t := m.th
	pill := lipgloss.NewStyle().Background(t.iris).Foreground(t.base).Bold(true).Render(" ◇ dashboard ")
	where := lipgloss.NewStyle().Foreground(t.subtle).Render("  " + m.c().Label)
	var order []string
	for _, g := range m.c().Groups {
		order = append(order, lipgloss.NewStyle().Foreground(t.mux(g)).Render(g))
	}
	sep := lipgloss.NewStyle().Foreground(t.muted).Render(" › ")
	nS, nA := len(selectable(m.rows(listSessions))), len(selectable(m.rows(listAgents)))
	right := lipgloss.NewStyle().Foreground(t.muted).Render(fmt.Sprintf("%s · %s ", plural(nS, "session"), plural(nA, "agent")))
	left := pill + where + lipgloss.NewStyle().Foreground(t.muted).Render("  ·  ") + strings.Join(order, sep)
	return lr(left, right, m.w, plain)
}

// panel draws a rounded box with a title in the top border and an optional
// note in the bottom border.
func (m *model) panel(title, note string, body []string, w, h int, focused bool) []string {
	t := m.th
	bc := t.hlHigh
	ts := lipgloss.NewStyle().Foreground(t.subtle)
	if focused {
		bc, ts = t.iris, lipgloss.NewStyle().Foreground(t.text).Bold(true)
	}
	b := lipgloss.NewStyle().Foreground(bc)
	inner := w - 2
	top := b.Render("╭─") + ts.Render(" "+title+" ")
	top += b.Render(strings.Repeat("─", max(0, w-lipgloss.Width(top)-1)) + "╮")
	lines := []string{fit(top, w, plain)}
	for i := 0; i < h-2; i++ {
		l := ""
		if i < len(body) {
			l = body[i]
		}
		lines = append(lines, b.Render("│")+fit(l, inner, plain)+b.Render("│"))
	}
	bottom := b.Render("╰")
	if note != "" {
		n := lipgloss.NewStyle().Foreground(t.muted).Render(" " + note + " ")
		bottom += b.Render(strings.Repeat("─", max(0, inner-lipgloss.Width(n)-1))) + n + b.Render("─╯")
	} else {
		bottom += b.Render(strings.Repeat("─", inner) + "╯")
	}
	return append(lines, fit(bottom, w, plain))
}

func (m *model) listPanel(list int, title string, x, y, w, h int) []string {
	t := m.th
	focused := m.focus == list
	rows := m.rows(list)
	items := selectable(rows)
	inner, ih := w-2, h-2
	cur := m.cur[list]

	// Scroll so the cursor row stays visible, with its group header if
	// possible.
	selRow := 0
	for i, r := range rows {
		if r.kind != rowGroup && len(items) > cur && r == items[cur] {
			selRow = i
		}
	}
	start := 0
	if len(rows) > ih {
		start = max(0, min(selRow-ih/2, len(rows)-ih))
	}
	var body []string
	idx := 0
	for i, r := range rows {
		if r.kind != rowGroup {
			idx++
		}
		if i < start || i >= start+ih {
			continue
		}
		switch r.kind {
		case rowGroup:
			body = append(body, m.groupRow(r, inner))
		case rowSession, rowAgent:
			sel := idx-1 == cur
			if r.kind == rowSession {
				body = append(body, m.sessionRow(r, inner, sel, focused))
			} else {
				body = append(body, m.agentRow(r, inner, sel, focused))
			}
			m.hits = append(m.hits, hit{y: y + 1 + len(body) - 1, x0: x + 1, x1: x + 1 + inner, list: list, idx: idx - 1})
		}
	}
	if len(rows) == 0 {
		msg := "  nothing here"
		if m.filter != "" {
			msg = fmt.Sprintf("  no match for “%s”", m.filter)
		}
		body = append(body, lipgloss.NewStyle().Foreground(t.muted).Italic(true).Render(msg))
	}
	note := ""
	if len(items) > 0 {
		note = fmt.Sprintf("%d/%d", cur+1, len(items))
	}
	return m.panel(title, note, body, w, h, focused)
}

func (m *model) groupRow(r row, w int) string {
	t := m.th
	name := lipgloss.NewStyle().Foreground(t.mux(r.mux)).Bold(true).Render(" " + r.mux + " ")
	count := lipgloss.NewStyle().Foreground(t.muted).Render(fmt.Sprintf(" %d ", r.count))
	rule := lipgloss.NewStyle().Foreground(t.hlMed).Render(strings.Repeat("─", max(0, w-lipgloss.Width(name)-lipgloss.Width(count))))
	return fit(name+rule+count, w, plain)
}

func (m *model) selPainter(sel, focused bool) (painter, string) {
	t := m.th
	switch {
	case sel && focused:
		return painter{bg: t.hlMed}, lipgloss.NewStyle().Foreground(t.iris).Background(t.hlMed).Render("▌")
	case sel:
		return painter{bg: t.hlLow}, lipgloss.NewStyle().Background(t.hlLow).Render(" ")
	}
	return painter{}, " "
}

func (m *model) sessionRow(r row, w int, sel, focused bool) string {
	t := m.th
	p, accent := m.selPainter(sel, focused)
	s := r.s
	cur := m.isCurrent(r.mux, s.Name)
	mark := p.r(plain, "  ")
	if cur {
		mark = p.r(lipgloss.NewStyle().Foreground(t.love), "● ")
	}
	nameSt := lipgloss.NewStyle().Foreground(t.text)
	switch {
	case s.Exited:
		nameSt = lipgloss.NewStyle().Foreground(t.muted).Italic(true)
	case cur || sel:
		nameSt = nameSt.Bold(true)
	}
	left := accent + p.r(plain, " ") + mark + p.r(nameSt, s.Name)
	if s.Attached && !cur && w >= 40 {
		left += p.r(lipgloss.NewStyle().Foreground(t.muted), " attached")
	}
	var right string
	if s.Exited {
		right = p.r(lipgloss.NewStyle().Foreground(t.muted).Italic(true), "exited "+s.Age+" ")
	} else {
		if n := len(m.agentsOf(r.mux, s.Name)); n > 0 {
			right += p.r(lipgloss.NewStyle().Foreground(t.gold), fmt.Sprintf("◆%d ", n))
		}
		if w >= 34 {
			unit := "tab"
			if r.mux == "tmux" {
				unit = "win"
			}
			right += p.r(lipgloss.NewStyle().Foreground(t.muted), fmt.Sprintf("%-6s ", plural(len(s.Tabs), unit)))
		}
	}
	return lr(left, right, w, p.st(plain))
}

func (m *model) status(a *agent, p painter, wide bool) string {
	t := m.th
	glyph, st := "", plain
	switch a.Status {
	case "working":
		glyph, st = spinner[m.frame%len(spinner)], lipgloss.NewStyle().Foreground(t.gold)
	case "idle":
		glyph, st = "○", lipgloss.NewStyle().Foreground(t.foam)
	case "blocked":
		glyph, st = "●", lipgloss.NewStyle().Foreground(t.love).Bold(true)
	case "done":
		glyph, st = "✓", lipgloss.NewStyle().Foreground(t.pine)
	default:
		return ""
	}
	if wide {
		return p.r(st, glyph+" "+a.Status+" ")
	}
	return p.r(st, glyph+" ")
}

func (m *model) agentRow(r row, w int, sel, focused bool) string {
	t := m.th
	p, accent := m.selPainter(sel, focused)
	a := r.a
	gold := lipgloss.NewStyle().Foreground(t.gold)
	left := accent + p.r(plain, " ") + p.r(gold, "◆ ") + p.r(gold.Bold(sel), fmt.Sprintf("%-9s", a.Name)) +
		p.r(lipgloss.NewStyle().Foreground(t.text), a.Session) +
		p.r(lipgloss.NewStyle().Foreground(t.muted), " › "+a.Tab)
	return lr(left, m.status(a, p, w >= 40), w, p.st(plain))
}

// ---------------------------------------------------------------- preview

func (m *model) previewPanel(w, h int) []string {
	t := m.th
	r, ok := m.selected()
	title, note := "Preview", ""
	var lines []string
	if ok {
		path := lipgloss.NewStyle().Foreground(t.muted)
		if r.kind == rowAgent {
			a := r.a
			title = "Preview " + path.Render("· "+a.Mux+" › "+a.Session+" › "+a.Tab)
			note = "pane " + a.Pane
			lines = agentScreen(a)
		} else {
			s := r.s
			if s.Exited {
				title = "Preview " + path.Render("· "+r.mux+" › "+s.Name)
				dim := lipgloss.NewStyle().Foreground(t.subtle)
				lines = []string{"", dim.Render("This session exited " + s.Age + " ago."), dim.Render("Enter resurrects it; x deletes it.")}
			} else {
				title = "Preview " + path.Render("· "+r.mux+" › "+s.Name+" › "+s.Tabs[0])
				note = s.Cwd
				lines = shellScreen(s)
				for _, a := range m.agentsOf(r.mux, s.Name) {
					if a.Tab == s.Tabs[0] {
						lines = agentScreen(a)
					}
				}
			}
		}
	}
	body := make([]string, len(lines))
	for i, l := range lines {
		body[i] = " " + l
	}
	return m.panel(title, note, body, w, h, false)
}

// The mock screens use the terminal's 16 ANSI colors, as a capture-pane -e
// of a real pane would.
func ansiFg(n string) lipgloss.Style { return lipgloss.NewStyle().Foreground(lipgloss.Color(n)) }

func shellScreen(s *session) []string {
	dir, git := ansiFg("4").Bold(true), ansiFg("5")
	ps := func(cmd string) []string {
		return []string{dir.Render(s.Cwd) + git.Render("  main"), ansiFg("2").Render("❯ ") + cmd}
	}
	var out []string
	out = append(out, ps("git status -sb")...)
	out = append(out, ansiFg("2").Render("## main...origin/main"), ansiFg("1").Render(" M ")+"README.md", ansiFg("1").Render("?? ")+"notes.md", "")
	out = append(out, ps("git log --oneline -3")...)
	out = append(out, ansiFg("3").Render("a1b2c3d ")+"Describe the session order",
		ansiFg("3").Render("9f8e7d6 ")+"Add the herdr workspace label", ansiFg("3").Render("5a4b3c2 ")+"Initial commit", "")
	out = append(out, ps(lipgloss.NewStyle().Reverse(true).Render(" "))...)
	return out
}

func agentScreen(a *agent) []string {
	b := lipgloss.NewStyle().Bold(true)
	dim := lipgloss.NewStyle().Faint(true)
	switch a.Name {
	case "claude":
		return []string{
			ansiFg("5").Render("╭────────────────────────────────────────╮"),
			ansiFg("5").Render("│") + " ✻ Claude Code   " + dim.Render("~/"+a.Session) + strings.Repeat(" ", max(0, 21-len(a.Session))) + ansiFg("5").Render("│"),
			ansiFg("5").Render("╰────────────────────────────────────────╯"),
			"",
			b.Render("> ") + "add a preview pane to the dashboard",
			"",
			ansiFg("2").Render("● ") + b.Render("Read") + "(dashboard.go)",
			dim.Render("  ⎿  Read 412 lines"),
			ansiFg("2").Render("● ") + b.Render("Update") + "(dashboard.go)",
			dim.Render("  ⎿  Updated with ") + ansiFg("2").Render("18 additions") + dim.Render(" and ") + ansiFg("1").Render("4 removals"),
			ansiFg("2").Render("    + ") + ansiFg("2").Render("preview := m.previewPanel(w-lw, h)"),
			ansiFg("1").Render("    - ") + ansiFg("1").Render("preview := \"\""),
			"",
			ansiFg("3").Render("✻ Thinking… ") + dim.Render("(esc to interrupt)"),
		}
	case "codex":
		return []string{
			b.Render(">_ OpenAI Codex") + dim.Render("  model: gpt-5.5   directory: ~/"+a.Session),
			"",
			ansiFg("6").Render("› ") + "explain the popup placement code",
			"",
			ansiFg("2").Render("• ") + b.Render("Explored"),
			dim.Render("  └ Read popup.sh, ui.rs"),
			"",
			"The popup sits below the cursor when it fits, else above it,",
			"and falls back to the pane's bottom left without a cursor.",
		}
	case "opencode":
		return []string{"", b.Render("  opencode") + dim.Render("  build · claude-opus-5-5"), "", dim.Render("  Waiting for input.")}
	case "pi":
		return []string{b.Render("pi") + dim.Render("  ~/"+a.Session), "", ansiFg("1").Bold(true).Render("Allow bash: rm -rf target/ ?") + "  [y/N]"}
	}
	return []string{ansiFg("4").Render("✦ ") + b.Render("Summarize the open PRs"), "", "3 PRs are open; #41 is ready to merge."}
}

// ---------------------------------------------------------------- footer

func (m *model) footer() string {
	t := m.th
	prompt := lipgloss.NewStyle().Foreground(t.gold).Bold(true)
	caret := lipgloss.NewStyle().Reverse(true).Render(" ")
	muted := lipgloss.NewStyle().Foreground(t.muted)
	key := lipgloss.NewStyle().Foreground(t.iris).Bold(true)
	switch m.mode {
	case "filter":
		return fit(prompt.Render(" / ")+m.input+caret+muted.Render("   enter keep · esc clear"), m.w, plain)
	case "rename":
		return fit(prompt.Render(fmt.Sprintf(" Rename %s session “%s”: ", m.target.mux, m.target.s.Name))+m.input+caret, m.w, plain)
	case "new":
		return fit(prompt.Render(fmt.Sprintf(" New %s session ", m.newMux))+muted.Render("(empty: name from directory) ")+m.input+caret, m.w, plain)
	case "kill":
		verb, extra := "Kill", ""
		if m.target.s.Exited {
			verb = "Delete exited"
		}
		if m.isCurrent(m.target.mux, m.target.s.Name) {
			extra = " (the current session)"
		}
		warn := lipgloss.NewStyle().Foreground(t.love).Bold(true)
		return fit(warn.Render(fmt.Sprintf(" %s %s session “%s”%s? ", verb, m.target.mux, m.target.s.Name, extra))+key.Render("y")+muted.Render("/N"), m.w, plain)
	}
	if m.toast != "" {
		c := t.pine
		if m.toastWarn {
			c = t.love
		}
		return fit(lipgloss.NewStyle().Foreground(c).Render(" "+m.toast), m.w, plain)
	}
	var left string
	for _, kv := range [][2]string{{"↵", "switch"}, {"⇥", "focus"}, {"/", "filter"}, {"n", "new"}, {"r", "rename"}, {"x", "kill"}, {"q", "quit"}} {
		piece := key.Render(" "+kv[0]) + muted.Render(" "+kv[1]+" ")
		if lipgloss.Width(left)+lipgloss.Width(piece) > m.w-26 {
			break
		}
		left += piece
	}
	right := ""
	if m.filter != "" {
		right = prompt.Render("/"+m.filter+" ") + " "
	}
	right += lipgloss.NewStyle().Foreground(t.hlHigh).Render("proto: C context · T theme ")
	return lr(left, right, m.w, plain)
}

// ---------------------------------------------------------------- main

func main() {
	ctxFlag := flag.String("context", "outside", "outside, tmux, zellij, herdr or nested")
	themeFlag := flag.String("theme", "auto", "auto, light or dark")
	inline := flag.Bool("inline", false, "draw 22 rows below the prompt instead of fullscreen")
	flag.Parse()

	data, agents := mockData()
	m := &model{data: data, agents: agents, dark: true, inline: *inline}
	for i, c := range contexts {
		if c.Key == *ctxFlag {
			m.ctx = i
		}
	}
	switch *themeFlag {
	case "light":
		m.dark, m.themeLock = false, true
	case "dark":
		m.themeLock = true
	}
	m.th = newTheme(m.dark)

	final, err := tea.NewProgram(m).Run()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if fm := final.(*model); len(fm.log) > 0 {
		fmt.Println("Commands the dashboard would have run:")
		for _, e := range fm.log {
			fmt.Println()
			fmt.Println(e)
		}
	}
}
