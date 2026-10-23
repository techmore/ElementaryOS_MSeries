# T3-R Pantheon

A native Pantheon client for AI coding agents: Claude Code, ChatGPT via Codex, OpenCode, Grok Build and ACP providers through the
[T3 Code](https://github.com/pingdotgg/t3code) server, with your local Claude Code transcripts
(`~/.claude/projects/*/*.jsonl`) as the offline view. gtk4-rs 0.11 + granite-rs 3.3, one process
and one T3 connection for both surfaces. The measured full-client baseline is in
[`docs/PERFORMANCE.md`](docs/PERFORMANCE.md); quick-panel memory has not yet been measured separately. Built to replace
the Electron desktop app (19 processes, 2.4 GB) on an Apple Silicon Mac running elementary OS; the shared GTK-on-Asahi
findings in [`mseries/GTK-PERFORMANCE-ASAHI.md`](../../mseries/GTK-PERFORMANCE-ASAHI.md). This directory is the source;
the standalone checkout at `~/Projects/claude-pantheon-rs` is a retired pointer.

![Milestone 2: a live thread](docs/screenshot-m2.png)

## Build and run

```sh
cargo build --release
./target/release/claude-pantheon-rs            # opens the full desktop chat
./target/release/claude-pantheon-rs --quick    # opens the compact status window
# or, with the shared target dir in ~/.cargo/config.toml:
~/.cache/cargo-target/release/claude-pantheon-rs
```

Toolchain: Rust 1.99, system GTK 4.22 and Granite 7.8 (`libgranite-7-dev`), plus `libgtksourceview-5-dev` (code blocks), `libvte-2.91-gtk4-dev` (terminal pane) and `libwebkitgtk-6.0-dev` (visual replies; the web process starts only when a page is shown).

Other entry points:

| Command | What |
|---|---|
| `claude-pantheon-rs` or `--full` | open the full desktop client |
| `claude-pantheon-rs --quick` | open the compact status window |
| `claude-pantheon-rs --new-thread`, `--usage`, `--thread ID` | open the full client at that destination |
| `claude-pantheon-rs --index` | list the offline sessions the sidebar shows, with timing |
| `claude-pantheon-rs --quit-after-frame` | draw one frame, print the start-up time, exit (benchmarks) |
| `claude-pantheon-rs --t3-dump DIR [TOKEN]` | record the server's answers as JSON (fixtures); pairs first when a token is given |
| `scripts/refresh-contracts.sh [--check] [--record]` | refresh the sparse t3code clone, regenerate `contracts/` (protocol version + RPC tags compiled in by `build.rs`), `--record` re-records `tests/fixtures`; `--check` only reports drift |
| `claude-pantheon-rs --t3-call TAG [JSON]` | one RPC call with the stored credential |
| `CLAUDE_PANTHEON_OPEN=<id>` | open that thread or session at start |
| `CLAUDE_PANTHEON_OFFLINE=1` | never connect; transcripts only |
| `CLAUDE_PANTHEON_RENDERER=gl` | use a GL renderer instead of cairo (see PERFORMANCE.md) |
| `CLAUDE_PANTHEON_DEBUG=1` | log RPC frames to stderr |

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+N | New thread |
| Ctrl+K | Command palette (the thread search until the palette lands) |
| Ctrl+F | Search threads |
| Enter | Send (Shift+Enter inserts a newline; Ctrl+Enter also sends) |
| Ctrl+W | Close the thread |
| Ctrl+Shift+U | Usage |
| Ctrl+, | Settings (appearance, defaults per project, server, notifications, renderer) |
| Ctrl+Shift+T | Terminal pane for the open thread (the server's PTY, no local shell) |
| Ctrl+Shift+S | SnapShot: screenshot through the portal, named after the focused window, attached to the draft |
| Ctrl+plus / Ctrl+minus / Ctrl+0 | Text zoom (80–200 %, remembered; also in Settings → Appearance) |
| Ctrl+Shift+V | Voice input: record, press again to stop; the words go into the draft, never sent |
| Ctrl+Q | Quit |
| Y / N | Allow once / deny the oldest waiting permission prompt (when not typing) |

The same actions sit in the app menu (header bar, right) with their accelerator labels, plus Repos
and Issues, Changes, Diagnostics, Import Sessions, Hand Off to Repo, Open Offline Twin, Reconnect,
Forget Pairing and About (version, server, providers ready).

## Dock popover, Wingpanel indicator, and quick window

In taskbar mode, the T3-R Dock launcher owns an attached native GTK popover: hover opens after 250 ms, the pointer can
cross to the popover during a 450 ms grace period, click pins or toggles it, and Escape or an outside click dismisses
it. The popover shows the selected provider and paired T3 server separately, usage for that provider, and live activity.
New chat, Usage, Settings, Open full chat, and live thread rows route to the matching destination in the full client.
When taskbar mode is off, the launcher opens the full client directly.

The optional native Wingpanel indicator (`wingpanel-indicator/`) is a separate system-panel surface with selected-provider
usage and activity. `--quick` opens a separate compact status window for explicit use; it is not attached to the Dock icon.
The Dock popover, Wingpanel indicator, and quick window read the local versioned `status.json` snapshot through file
monitors; they do not open another RPC socket or poll. Writes use an atomic rename and mode `0600`. On disconnect the feed
keeps the last successful snapshot as stale; normal application shutdown also marks it stale. The Wingpanel indicator
additionally watches the client session D-Bus name, so an unclean process exit marks cached activity stale even when the
client cannot write a shutdown snapshot. The Dock popover and quick window identify the selected provider separately
from the paired T3 server; when no provider is selected, they say so instead of showing the server as an account. The
Wingpanel summary scopes usage to the selected provider. Stale status is treated as offline even if feed flags disagree,
and stale activity cannot open a thread. Unpairing or switching environments clears the cache. The Wingpanel module is
included in the Debian package when built with `CLAUDE_PANTHEON_ENABLE_INDICATOR=1`;
install it with `bash mseries/install-claude-pantheon-indicator.sh` if only the app package is installed.

## Thread resume cache

Settled T3 thread views are cached under `~/.cache/claude-pantheon-rs/threads/`, scoped to the selected environment
and thread. Each atomic, mode-`0600` record keeps the bounded view, history marker and `snapshotSequence` together;
environment directories use mode `0700`. The client reopens from that view and asks T3 for `afterSequence`, ignores
duplicate replay events, and keeps send, stop and approval actions disabled until synchronization completes. Active
turns stay in memory and are persisted only after they settle, so token-by-token updates do not rewrite the cache.
If the thread stream ends while the main connection remains open, the last view is marked interrupted and live
actions stay disabled until the user retries synchronization.
Live item updates use a process-local identity index, rebuilt from the cached projection on demand, so replaying
large histories does not scan the full item list for every event. Version-3 cache records are still readable; the next
cache write upgrades them without dropping their history cursor.
Records are capped at 8 MiB each and 64 MiB / 32 entries per environment. Corrupt, wrong-scope and old-schema files
are discarded; forgetting or removing an environment clears its thread cache. A replay gap beyond the server's
retention window still falls back to T3's current snapshot.

## Reading older chat history

The full chat starts with T3's bounded thread window. Scrolling to the top loads the next older page from T3 using its
opaque history cursor; older messages are prepended without moving the part of the conversation already on screen.
Rows deduplicate by source thread and item identity, including inherited rows. A Load earlier / Retry control stays at
the top as a fallback. History pages can be fetched while connected; the offline cache retains all loaded items with
their next cursor up to the 8 MiB record limit. If a larger thread no longer fits, the previous valid cache stays in
place rather than advancing its cursor past unsaved history.

## Sidebar

Threads sit in project/repository groups ordered by recent activity, with pinned chats leading each
group. A chat row shows T3's repository identity and saved thread branch when those fields exist;
generic workspaces and chats without Git context remain visible without a made-up repository label.
The bell filters to unanswered prompts, unseen completed work and unseen failures, sorted by most
recent attention. Its badge shows the number of matching chats. The sidebar uses repository and
branch metadata already present in the T3 shell snapshot, avoiding a Git/status request for every row.
That keeps list rendering light; if an agent switches worktrees outside T3's tracked branch update,
the displayed branch may lag until T3 refreshes the thread metadata.

Rows also show the provider accent, a spinner while a turn runs, a "?" badge when a prompt waits and
a blue dot for activity since the last visit (the server's `lastVisitedAt`; opening a thread records a
visit). Right-click or long-press a thread for Pin, Rename, Hand Off to Repo, Copy Link (a
`claude-pantheon-rs --thread <id>` command) and Archive. Section headers collapse on click and project
headers can be dragged into the order you want; the filter and order persist in
`~/.config/claude-pantheon-rs/sidebar.json`.

## Repository issue workflow

Repos → Issues supports local issue briefs with problem, research/context, success criteria and
constraints, then explicit GitHub filing. When MSeries Assistant is ready on the paired server,
**Refine locally** opens an unsent first-pass chat with that local provider selected. You can switch
to another connected T3 provider in the same composer for research and refinement. The local prompt
is capped at 16,000 characters and asks for a compact brief; its underlying model is managed by the
paired server and checked when you send. Issue labels and
readiness control the repo workflow; provider selection remains a separate T3 decision. Draft fields
scroll within the window, and the action buttons wrap on narrow layouts. The issue list loads open and closed issues
in pages of up to 100, with Open, Resolved and All filters. **Load more issues** advances the selected state, or both
states in All. Chats grouped beneath an issue remain browsable after it closes; repo backlog and runner counts continue
to include open issues only.

## Composer

The composer keeps a **Next message · Provider · Model** summary above its controls. The thread header shows the
provider's friendly model name, T3 repository identity and saved branch, project path, and the local checkout branch
when that workspace is accessible. A differing checkout is shown alongside the saved T3 branch; the tooltip retains
the full context if the header line is shortened. The message box grows to eight lines and then scrolls. Paste or drop images and files to attach
them: each becomes a chip, uploaded through the server's `attachments.createUploadUrl` and sent with
the message (10 attachments, 10 MB per image, 50 MB per file). Typing `@` opens a fuzzy picker over the
thread's project (`projects.searchEntries`) and inserts `@path`. The draft is kept per thread in
`~/.cache/claude-pantheon-rs/drafts.json` and comes back when the thread is reopened, across restarts.

## Pairing with the server

The server is `t3 serve` (here: the user service `t3code.service` on `127.0.0.1:3773`). Run `t3 pair`,
paste the token or the pairing URL into the first-run page. The pairing token is exchanged once for a
bearer session (`/oauth/token`); the session goes to the keyring (`secret-tool`) or, without one, to
`~/.config/claude-pantheon-rs/credentials.json` (0600). Each connection mints a short-lived WebSocket
ticket and opens `/ws?orchestrationProtocol=2`; a server that wants a newer client answers 426 and
its message is shown on the pairing page.

On loopback the client also points the server's Claude provider at the Claude Code CLI bundled with
the desktop app (`~/.config/Claude/claude-code/<version>/<hash>/claude`) when the server cannot find
`claude` on PATH.

## Provider sign-in

Open **Settings → Providers → Manage providers…** to see server-reported status and sign in or out of
Claude Code, ChatGPT through Codex, OpenCode and Grok Build. The sign-in window handles browser and
device-code steps, terminal prompts and credential forms, and lets you choose among sign-in methods
and saved accounts advertised by the server. The T3 Code server owns provider credentials; the client
sends only the responses needed to complete the current sign-in flow. Providers must be installed and
enabled on the server before they can be connected here.

The same page can search the ACP Registry or add a local ACP command. The provider rows reflect only agents returned
by the paired server; the **DeepSeek Harness…** button is a setup form, not a claim that Harness is installed or
connected. It prefills `dsh --profile acp`; this requires `dsh` to already be installed and a DeepSeek API key configured
in Harness on the paired T3 server. Harness is experimental and not security-audited; review its [safety notice](https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md)
before enabling it. The server runs the agent against the workspace T3 exposes. DeepSeek API context caching is
automatic and server-side, so the client does not duplicate it with a disk cache. DeepSeek Harness ACP keeps KV reuse
append-only while the selected route and assembled prefix stay stable; keep provider, model and tool configuration
stable when possible.

**MSeries Assistant…** adds the paired server's existing local assistant as an
ACP provider. Install the bridge on that server with
`python3 mseries/local-ai/configure-assistants.py --install-acp`; this keeps the
current Newelle and model settings intact. It reuses the supervised local model
and the sixteen scoped MSeries tools, with T3 permission prompts for writes. It
does not start or switch a model service. The optional `--endpoint` argument
can select another already-running loopback profile. See
[`mseries/local-ai/README.md`](../../mseries/local-ai/README.md) for setup and
the Liquid/ANE candidate limits.

## Usage and status (CodexBar-style)

The chat client includes the CodexBar-style usage view, so provider usage lives beside the threads that
use it. **Usage** combines server-reported 5-hour, weekly and monthly plan windows with reset times and
the next-provider capacity decision, then shows 30-day tokens, output, API-equivalent cost, model breakdowns
and a 7-day activity chart for Claude, Codex, OpenCode and Grok. Cache reads, cache writes and savings appear only
when the corresponding fields are present in T3's usage summary; missing server metrics are not shown as zero. The
optional Wingpanel indicator shows the selected chat provider's quota and activity summary on hover; clicking it opens
quota gauges, running threads and permission prompts, with thread links that open in this client. Other provider
accounts remain in Settings. The app's `--quick` window is a separate compact status window. Both read the local status
feed without starting another connection.

## What is where

| Path | Role |
|---|---|
| `src/t3/ws.rs`, `http.rs` | RFC 6455 client and HTTP/1.1 on gio sockets, all on the GLib loop |
| `src/t3/rpc.rs` | Effect-RPC JSON envelopes: Request/Chunk/Exit/Ack/Interrupt/Ping |
| `src/t3/auth.rs` | pairing, tickets, credential storage |
| `src/t3/model.rs` | lenient serde views of providers, shell, thread projections, usage, plan windows, rotation rule |
| `src/transcript.rs`, `index.rs` | JSONL parser and the cached session index (`~/.cache/claude-pantheon-rs`) |
| `src/app.rs` | the window: sidebar, live thread, composer, pages |
| `src/chat.rs` | message, tool-row, diff and permission-prompt widgets |
| `src/render.rs` | Markdown (pulldown-cmark) as widgets; fenced code in GtkSourceView 5 with copy and wrap |
| `src/usage.rs` | Usage page (CodexBar style) and plan-window gauges |
| `src/workflow.rs`, `repos.rs` | pinned repos, issue backlog and filing via `gh api`, local issue briefs, issue-organized chats, "Start on this", the runner as T3 scheduled tasks |
| `src/handoff.rs` | "Hand Off to Repo": structured summary appended to the project's handoff doc, optional commit |
| `src/changes.rs` | Changes page: file tree, inline/side-by-side diff in GtkSourceView, per-hunk copy, restore to checkpoint |
| `src/diagnostics.rs` | server resource telemetry as sparklines and process-local thread-cache hit/miss and disk-time totals |
| `tests/render.rs` | drives the real window under Xvfb and writes the screenshots in `docs/` |
| `bench.sh` | RSS and CPU of a process tree over 20 s, as a Markdown row |

Design notes: [`docs/T3-SPIKE.md`](docs/T3-SPIKE.md) (why the server), [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md)
(native replacements for T3's platform helpers), [`docs/WORKFLOW.md`](docs/WORKFLOW.md) (issues, lanes, runner).

## Tests and screenshots

```sh
cargo test --release --lib
dbus-run-session -- env -u WAYLAND_DISPLAY GDK_BACKEND=x11 GSETTINGS_BACKEND=memory \
  CLAUDE_PANTHEON_SHOT=docs/screenshot-m1.png CLAUDE_PANTHEON_SHOT_M2=docs/screenshot-m2.png \
  CLAUDE_PANTHEON_SHOT_M3=docs/screenshot-m3.png \
  xvfb-run -a -s "-screen 0 1400x900x24" cargo test --release --test render
```

The render test needs the real transcripts and, for the live parts, a stored credential (under the
test's D-Bus session the keyring is not reachable: copy the credential JSON to
`$XDG_CONFIG_HOME/claude-pantheon-rs/credentials.json` for the run). `CLAUDE_PANTHEON_LIVE_SEND=1`
also starts a real thread and waits for its answer.

## Install

```sh
./install.sh                    # release build + install under ~/.local: binary, .desktop (New Thread and
                                # Usage actions, D-Bus activation), metainfo, hicolor icons 16…128 + symbolic
./install.sh --prefix /usr      # system-wide (sudo for the copy)
./install.sh --uninstall
bash mseries/install-claude-pantheon-rs.sh   # the same from the repo root, with the build requirements check
```

The script restarts `pantheon-dock` at the end: the dock keeps showing a placeholder icon for a newly
installed app until it is restarted. The D-Bus service file lets the desktop entry and
`gapplication launch io.github.techmore.ClaudePantheonRs` start the app; a second launch, the desktop
actions and `gapplication action io.github.techmore.ClaudePantheonRs new-thread` all reach the running
window.

## Visual replies

When an agent answers with a page (the `html_render` tool), the turn shows a card with the page title and a **Show page** button. The WebKitGTK view (and its web process) is created only when that button is pressed and freed with the card's close button, so an idle window has no web process. Links open in the browser; a Granite palette style sheet makes unstyled pages follow light and dark; full screen opens the page in its own window (Escape closes it). Signed asset URLs come from `assets.createUrl` on each open.

## Runner, webhook and rotation

The Repos page installs, per pinned repo, the five-minute runner task and (with **Webhook**) the task GitHub's
`issues.labeled` → `agent:ready` event triggers; the GitHub hook itself is created once the server reports a webhook
URL GitHub can reach (the Tailscale or T3 Connect environment). Every five minutes the client re-points both tasks at
the provider with the lowest session usage, so the next run uses it (details in `docs/WORKFLOW.md`).

## Environments

The sidebar footer switches between saved environments (`~/.config/claude-pantheon-rs/environments.json`), each with its
own credential (keyed by server URL in the keyring or `credentials-<server>.json`) and its own connection state:
**Direct** (a URL), **Tailscale** (a peer from `tailscale status --json`; the server there listens on its tailnet address),
**SSH** (`ssh -N -L` kept open while the environment is current; the client talks to the local port) and **T3 Connect**
(the relay environment a pairing URL names; the relay sign-in happens in the browser). Pasting a pairing URL for another
server on the pairing page creates its environment. Switching drops the current connection and tunnel and reconnects;
a dropped connection reconnects with the usual back-off. Retryable failures during the first connection or config read
use that same supervisor; rejected credentials and protocol-version mismatches stop for user action.

## Empty, loading and error states

No pane is ever blank: the thread list shows skeleton rows while sessions are indexed or the server connects and a
hint afterwards (no threads yet, nothing matches the search); a transcript or thread opens onto skeleton bubbles until
its items arrive; the Repos page shows a Granite placeholder with an Import Sessions button when no project has a GitHub
remote, and the issue list shows skeleton rows while `gh` answers, a placeholder when nothing matches the filters, and a
placeholder with Retry when GitHub fails. Transient errors (server unreachable, a chat that could not be read, a thread
stream that ended, usage or GitHub failures) are Granite toasts with a Retry action.

## Window state and accessibility

Size, maximised state and the sidebar width are remembered in `~/.config/claude-pantheon-rs/window.json` (clamped to
sane values on load). Text zoom scales every font through `gtk-xft-dpi` relative to the system's text scaling, so
HiDPI and the owner's font DPI are kept; the window was checked at `GDK_SCALE=2`. Every icon-only control, the pickers,
the search field, the thread list and each chat item carry accessible names (chat items read as "You: …",
"Assistant: …", "Tool call Bash: …", "Permission request: …"), and keyboard focus is outlined on list rows and flat
buttons.

## Voice input

The composer's mic button (or Ctrl+Shift+V) records through PipeWire (`pw-record`, 16 kHz mono) until pressed again,
transcribes locally with whisper.cpp (`sudo apt install whisper.cpp`; a `ggml-*.bin` model in
`~/.local/share/claude-pantheon-rs/models` or named in Settings → Advanced) and inserts the words at the draft's cursor.
It never sends: the owner reviews and presses Send. A transcript for a draft that changed hands meanwhile is dropped.
Without whisper or a model the status line says what to install.
