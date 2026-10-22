# GTK4 apps on Asahi: what keeps them small and idle

The findings every GTK4/Granite app in this repository builds on, measured on the j314s (Apple
Silicon, elementary OS, Pantheon on Wayland, 2x HiDPI) while the two Claude clients were brought
under their targets (under 120 MB RSS, ~0 % CPU idle with a window open, under 300 ms to the first
frame). Both clients hit them: the Vala twin at 74 MB / 0.0 % / ~130 ms, the Rust twin at 58 – 70 MB
/ 0.0 % / ~200 ms. The per-app numbers stay in each app's `PERFORMANCE.md`; this page is the shared
reasoning so the next app does not rediscover it.

## The three findings that matter most

1. **Renderer: force cairo.** With the session's default `GSK_RENDERER=gl` (or `ngl`, `vulkan`)
   Mesa on Asahi loads LLVM and allocates about 180 MB of heap for shaders before a single widget
   is drawn: 240 – 290 MB RSS for an empty window. The cairo renderer draws the same window in
   ~70 MB. Set `GSK_RENDERER=cairo` in `main()` before GTK initialises unless the environment
   already names a renderer, and keep an override (`<APP>_RENDERER=gl|ngl|vulkan`). GL paints a
   full window in ~3 ms against cairo's ~6 ms; for a chat or settings window that difference is
   invisible, the memory is not.
2. **Window shadow: a 1 px outline, not a blurred `box-shadow`.** GTK's default client-side
   decoration is a blurred shadow that the cairo renderer re-blurs over the whole window on every
   frame: ~52 ms per repaint at 2x. Replacing it in the app's CSS with a 1 px outline brings a
   full repaint to ~6 ms.
3. **Cursor blink off.** GTK fades the text cursor with a frame-clock tick for ten seconds after
   every keystroke; a focused text view keeps the window repainting at 14 – 19 % of a core while
   "idle". `gtk-cursor-blink = false` in the application's startup handler; the cursor is steady and
   idle CPU is 0.0 %.

## Findings from the later work (Rust client, October 2026)

4. **CSS animations run while unmapped.** A `@keyframes` pulse on skeleton rows parked in a hidden
   stack page cost 2.6 % of a core at idle. Add the animating class on `map` and remove it on
   `unmap` (`gtk::Widget::connect_map` / `connect_unmap`); gated, the same animation costs
   nothing while hidden.
5. **No synchronous D-Bus at start-up.** Asking Granite's style manager for
   `prefers-color-scheme` at start-up is a synchronous portal round trip (hundreds of ms under
   load); Granite already follows the portal on its own. The same goes for `secret-tool`: on a
   bus without a secret service it waits 25 s, so wrap keyring calls in `timeout 3` and fall back
   to a 0600 file.
6. **Heavy libraries are cheap until used.** Linking libwebkitgtk-6.0, libvte and
   GtkSourceView adds ~3 MB RSS in total; a WebKit web process or a PTY only exists once the
   owner asks for that pane, so create those widgets lazily and destroy them with the pane.
7. **Keep the main loop single.** The whole T3 protocol (WebSocket, HTTP) sits on
   `gio::SocketClient` futures on the GLib loop: no tokio, no worker threads, nothing to wake up
   at idle. Parsing goes to `gio::spawn_blocking` / a worker thread; widgets are created only for
   the visible tail of a transcript and in idle batches; the sidebar is rebuilt once per burst of
   events, not per event.
8. **Bench the same way every time.** `bench.sh <name> 20` averages CPU from `/proc/<pid>/stat`
   deltas and RSS from `/proc/<pid>/status` over 20 s with a chat open and the window settled
   (30 s after launch); `--quit-after-frame` prints the time from `main()` to the first frame.
   Under Xvfb with `dbus-run-session`, `GSETTINGS_BACKEND=memory` and a private
   `XDG_CONFIG_HOME` the numbers match the desktop. Check `pgrep -fc` shows exactly one
   instance: a stray earlier build holding the bus name doubles every figure. Note the machine's
   load average beside start-up samples; at load 80+ from other jobs a 200 ms start-up reads as
   500 – 900 ms.

## The GTK apps here and what applies to each

| App | Language | Renderer forced to cairo | 1 px CSD outline | Cursor blink off | Numbers |
|---|---|---|---|---|---|
| [`rust/claude-pantheon-rs`](../rust/claude-pantheon-rs/) | Rust, gtk4-rs + granite-rs | yes (`CLAUDE_PANTHEON_RENDERER` override) | yes | yes | [`docs/PERFORMANCE.md`](../rust/claude-pantheon-rs/docs/PERFORMANCE.md) |
| [`mseries/claude-pantheon-native`](claude-pantheon-native/) | Vala, GTK4 + Granite 7 | yes (`CLAUDE_PANTHEON_RENDERER` override) | yes | yes | [`docs/PERFORMANCE.md`](claude-pantheon-native/docs/PERFORMANCE.md) |
| [`rust/mseries-updates`](../rust/mseries-updates/) | Rust, gtk4-rs + granite-rs | no (short-lived settings pane) | default | default | – |
| [`rust/mseries-diskspace`](../rust/mseries-diskspace/) | Rust, gtk4-rs + granite-rs | no (short-lived settings pane) | default | default | – |
| [`rust/granite-smoke`](../rust/granite-smoke/) | Rust, gtk4-rs + granite-rs | no (smoke test) | default | default | – |
| [`mseries/orchard`](orchard/) | Vala, GTK4 | no | default | default | – |
| [`mseries/dock-switcher`](dock-switcher/) | Vala, GTK4 | no | default | default | – |
| [`mseries/codexbar-wingpanel`](codexbar-wingpanel/) | Vala, Wingpanel (GTK4 popover) | runs inside Wingpanel | n/a | n/a | [CODEXBAR-PERFORMANCE-AUDIT-2026-10-18.md](CODEXBAR-PERFORMANCE-AUDIT-2026-10-18.md) |
| [`mseries/dock-taskbar`](dock-taskbar/), [`mseries/quick-settings`](quick-settings/), [`mseries/calendar`](calendar/), [`mseries/display-space`](display-space/), `mseries/clockright`, `mseries/panel-ui-probes` | Vala / Python, inside the dock, Wingpanel or System Settings | host process decides | n/a | n/a | – |

A long-lived window (a client, a monitor) should take all three of the first findings; a pane that
opens for seconds inside System Settings or a panel runs in its host's process and renderer, so
only the animation and D-Bus rules apply there.

## Related

- [CODEXBAR-PERFORMANCE-AUDIT-2026-10-18.md](CODEXBAR-PERFORMANCE-AUDIT-2026-10-18.md): the
  Wingpanel module's own measurements.
- [PERFORMANCE-PORT-CANDIDATES-2026-10-18.md](PERFORMANCE-PORT-CANDIDATES-2026-10-18.md): what else
  on this Mac is worth porting for speed.
- [RUST-UPSTREAM-MAINTENANCE.md](RUST-UPSTREAM-MAINTENANCE.md): the gtk4-rs / granite-rs pins the
  Rust apps share.
