# T3 ecosystem tools and their native Pantheon integration (2026-10-21)

Surveyed: pingdotgg (10 repos), t3-oss (8), t3dotgg personal (50+). T3 Chat has no public repo.
Everything that matters for an agent client lives inside `pingdotgg/t3code`. The rest of the
ecosystem is unrelated products (uploadthing: file-upload SaaS; lawn: video review; create-t3-app,
t3-env, create-t3-turbo: Next.js scaffolders; ts-rust: tsc port; quickpic, markerthing,
webhookthing, slotslop: one-off tools). None of those are integrated.

Sparse source for everything below: `~/claude-work/repos/t3code`.

## Already decided (milestones 2 and 3)
| T3 piece | Native Pantheon integration |
|---|---|
| Server RPC (`/ws`, JSON Effect-RPC, protocol v2) | Rust client module `src/t3/` |
| Providers: Claude Code, Codex, OpenCode, Grok, Cursor, Antigravity, Pi | provider + model picker, permission prompts, streamed turns |
| Usage (`docs/user/usage.md`) | Usage page, CodexBar style |

## Milestone 4: native tools that replace T3's platform helpers
| T3 piece (what it is) | Pantheon-native build |
|---|---|
| `native/resource-monitor` (Rust, `sysinfo`, child-process protocol; samples only while a diagnostics subscriber is live, `docs/internals/resource-telemetry.md`) | Diagnostics page: subscribe to the server's diagnostics RPC, show per-provider process groups CPU/RSS as sparklines. Do not run our own sampler. |
| `native/hyprland-snap-shot`, `native/kde-snap-shot` (Rust Wayland window capture with PID/title/frame; `docs/internals/linux-snap-shot.md`: one backend per session from `XDG_CURRENT_DESKTOP`, never fall back; portal capture carries no window identity) | **SnapShot for Pantheon**: a `t3-pantheon-snap-shot` Rust helper in `native/` of our repo using Gala's screenshot D-Bus (`org.gnome.Shell.Screenshot` as Gala exposes it, `ScreenshotWindow`) for the active window with PID/title/frame, falling back only by explicit choice to `org.freedesktop.portal.Screenshot`. AT-SPI window text per the doc's matching rules (PID + title + size). Shortcut registered through Pantheon's keyboard settings (`io.elementary.settings-daemon` custom shortcut) or the GlobalShortcuts portal. Attaches to the composer draft through the server's attachment RPC. This is the one piece the T3 desktop app cannot do on Pantheon today. |
| `native/libghostty-vt` + `docs/internals/terminal-runtime.md` (server owns PTYs; client attaches over the connection; 5,000-line / 8 MiB server history, 512 KiB client buffer) | Terminal pane with **vte4** (`vte-2.91-gtk4`), fed from the terminal output stream RPC, input sent back over RPC. No local PTY. Respect the client buffer cap. |
| `native/browser-secret` (C keychain for the headless browser) | Not needed; the server owns it. Credentials for our own session go to libsecret. |
| Visual replies / MCP apps (`docs/user/html-renders.md`, sandboxed HTML pages) | Render in a **WebKitGTK 6** view only when a turn contains one, created lazily and destroyed on close so idle RSS stays flat. Theme CSS injected from the Granite palette. |
| Source control (`packages/source-control-*`, `docs/user/source-control.md`) | Changes pane: turn diff and branch comparison from the RPCs, PR link/create/review-guide actions, open in `gh`-authenticated browser. |
| Remote (`packages/ssh`, `packages/tailscale`, `docs/internals/remote.md`, `t3-connect.md`) | Environments switcher in the sidebar: direct, Tailscale and SSH environments, each with its own connection state; T3 Connect pairing via the relay flow. Tailscale status read from `tailscale status --json` when present. |
| Devices (`docs/internals/devices.md`, expo-device-hub streams) | Out of scope for now (iOS/Android simulators). Show the panel entry only when the server advertises device hosts. |
| Voice input (`docs/internals/voice-input.md`, draft-only, iOS-local today) | Optional: whisper.cpp local transcription into the composer draft, never auto-submit. Last priority. |
| Keybindings, theme (`keybindings.ts`, `environmentTheme.ts`) | Honor the server's keybinding config; map theme defaults onto Granite light/dark. |
| Wingpanel | Optional legacy indicator like CodexBar: running threads, pending permission prompts (click to answer), today's usage. Separate `wingpanel-indicator` crate or Vala shim, like `orchard-incus-native`. |

## Order
Milestone 2 (client) → 3 (usage) → 4a SnapShot → 4b terminal (vte4) → 4c changes/source control →
4d environments → 4e Wingpanel indicator → 4f visual replies → 4g diagnostics → voice last.
Each step: commit, screenshot in `docs/`, PERFORMANCE.md re-run so idle RSS is tracked per feature.

## Status 2026-10-21 (Rust client)

| Step | State |
|---|---|
| 2 client, 3 usage | Done: `src/app.rs`, `src/usage.rs`; plan windows as gauges with the rotation decision (`pick_provider`). |
| 4a SnapShot | Not built. The compositor is `pantheon-compositor` (mseries Rust), not Gala: no `org.gnome.Shell.Screenshot` and no screencopy global. The portal backend `org.freedesktop.impl.portal.desktop.pantheon` serves `org.freedesktop.portal.Screenshot` v2 (`Screenshot(parent_window, options)`), so the helper will call the portal (interactive=false), accept that portal captures carry no window identity (`docs/internals/linux-snap-shot.md`), and take the focused window's title and PID from AT-SPI's active-window event, matching on title only. A compositor-side `ScreenshotWindow` D-Bus method (PID/title/frame) is a follow-up in the compositor repo. Attachment upload goes through `attachments.createUploadUrl`. |
| 4b terminal (vte4) | Done: `src/terminal.rs`, a VTE pane under the chat (Ctrl+Shift+T) attached over `terminal.attach` (history replay, live output), keystrokes through `terminal.write`, size through `terminal.resize`, 512 KiB client cap, elementary Terminal palette; no local PTY. |
| 4c changes | Partial: Changes page from `orchestration.getFullThreadDiff`, one collapsed diff per file. Branch comparison and PR actions (`pullRequests.*`) not built. |
| 4d environments | Not built; one direct environment (loopback) only. |
| 4e Wingpanel indicator | Optional legacy surface: `wingpanel-indicator/` (Vala, Wingpanel 9 API) reads the client's `status.json` feed with a FileMonitor (live prompts as the badge, selected-provider usage gauges, and thread actions). Disconnect and normal client shutdown preserve an explicitly stale last-known snapshot; offline activity is labeled and disabled. Live and stale headless probes cover both states. The app-only Debian package omits it by default. |
| 4f visual replies (WebKitGTK 6) | Not built: `webkit6` crate not in the offline cache. |
| 4g diagnostics | Done: `src/diagnostics.rs`, `subscribeResourceTelemetry` only while the page is open. |
| 5 workflow | Done except the webhook task (needs a reachable webhook endpoint through T3 Connect or Tailscale) and automatic per-run rotation (the server has no per-run hook; the client re-picks the provider when the runner is re-installed). |

## Native provider onboarding — 2026-10-22

`src/provider_setup.rs` adds a GTK/Granite provider manager under Settings. It reports the server's
configured instances and supports T3 Code's browser, device-code, terminal and credentials sign-in
interactions, sign-in method/account selection, plus sign-out. The featured entries are Claude Code,
ChatGPT via Codex, OpenCode and Grok Build; the T3 server remains the credential owner. New provider
instances for built-in drivers still need to be installed and enabled on the server. The Rust release
target compiles; a live sign-in flow and an interactive Pantheon session have not yet been qualified.

## Dock quick surface and ACP agents — 2026-10-22

Default Dock launch now opens `src/quick.rs`; **Open full chat** shows the complete `App` window and all its integrations.
Quick actions route to that same app instance. The surface shows the paired T3 environment and usage only for the
provider selected in full chat, plus active work and pending approvals. It listens to the atomic, versioned `status.json`
cache without a second connection or polling, and labels retained data stale after disconnect. Unpair and environment
switches clear it.

Settings can search T3's ACP Registry or add a local ACP command for execution on the paired server. This gives users a
supported way to register DeepSeek Harness, for example `dsh --profile default acp`, when the paired server has the CLI.
DeepSeek's prefix cache is server-side; retain stable prefixes and report cache-hit data only when T3 returns it.

Settled thread views now use a separate environment/thread-scoped cache record containing the bounded projection,
history marker and T3 `snapshotSequence`. The record is versioned, atomically replaced, mode `0600`, capped at 8 MiB
per thread and 64 MiB / 32 entries per environment. Active turns remain in memory until they settle; reopening renders
the cached view and resumes with `afterSequence`, ignores duplicate events, and blocks live actions until the server's
completion marker. Corrupt or mismatched records are discarded and explicit environment removal/unpair clears them.

The cache write-regression research remains relevant: this client avoids full serialization on each streamed update,
but it has not yet been profiled against a very large live conversation or verified on a poor network. Tracked in
[issue #523](https://github.com/techmore/ElementaryOS_MSeries/issues/523), with T3 Code cache-runtime, ACP Registry,
DeepSeek API cache and Harness prompt-prefix research. Live ACP setup, real reconnect qualification and a visual
Pantheon session remain open. See `mseries/OS9-HANDOFF.md` for validation results and deployment limits.
