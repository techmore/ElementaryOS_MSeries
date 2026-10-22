# Performance

Measured 2026-10-21 on elementary OS (Pantheon, Wayland, 2x HiDPI) on the Apple Silicon
j314s (10 cores, aarch64). CPU is the average over a 20 s window from `/proc/<pid>/stat`
deltas (`utime + stime`), RSS from `/proc/<pid>/status`, sampled once a second
(`bench.sh <pid> 20`, the same method as `mseries/claude-pantheon-native/docs/PERFORMANCE.md`).
Every run had the real Incus (deb-test, orchard-test, rupert-dev running), the real rootless
Podman (two containers) and the three mseries-vm guests under `~/vms` (all stopped) on screen in
the sidebar, the first machine's Overview page open, nothing else open, the window behind
another app.

## Idle, window open

| App | Launch | CPU % avg over 20 s | RSS avg (MB) |
|---|---|---|---|
| Machine Lab 0.11.0 (`~/.local/bin/machine-lab`, before the merge) | binary | **37.6** | 281 |
| Orchard for Incus (`com.github.techmore.orchard-incus`, Podman page) | binary, running since the morning | 0.9 | 262 |
| Orchard 1.0.0, first merged build (animation gone, cairo, outline, steady cursor, per-page timers) | `gio launch` on the desktop file | 0.6 | 82 |
| Orchard 1.0.0, final (hidden pages defer widget updates, sidebar text static, no re-sort per poll) | `gio launch` on the desktop file | **0.3** | **82** |

Breakdown of the final build by switching inputs off (15 s windows, `./build/orchard`):
real Incus and machines 0.2 %; Incus socket missing (error path) 0.3 %; no machines 0.1 %;
neither 0.0 %. What remains is the 3 s instance listing over the Unix socket (libsoup request,
JSON of three instances) and the 2 s machine state poll (pid file and `/proc` reads).

## What the 37.6 % was

Measured rather than guessed, in order of effect:

1. **The pulsing status dot.** `style.css` animated `.ml-dot.running` with an infinite CSS
   keyframe (`ml-pulse`, 1.6 s). A CSS animation keeps GTK's frame clock running for as long as
   the widget is mapped, so every running row in the sidebar (three Incus containers) made the
   whole window repaint at the display rate, forever. With no QEMU guest running and the display
   stream off, this alone explains the "idle" load. The dot is now a steady green ring.
2. **The GL renderer.** With the session's default `GSK_RENDERER=gl` Mesa on Asahi loads LLVM
   and allocates ~180 MB of heap for shaders: 281 MB RSS. `entry.vala` forces `cairo`
   (`ORCHARD_RENDERER=gl|ngl|vulkan` overrides); the same window is 82 MB.
3. **The blurred CSD shadow.** GTK's default client-side decoration is a blurred `box-shadow`
   that the cairo renderer re-blurs over the whole window on every frame (~52 ms per repaint at
   2x, measured on the Claude client). `style.css` replaces it with a 1 px outline for every
   window of the app.
4. **Cursor blink.** GTK fades the text cursor with a frame-clock tick for ten seconds after
   each keystroke, which keeps the window repainting with an entry focused.
   `gtk-cursor-blink = false` in `startup ()`.
5. **Timers while hidden.** Every machine page ran a 1 s uptime tick whether or not it was on
   screen; the Incus and machine polls ran after the window was closed. Ticks now start on
   `map` and stop on `unmap`; the window's polls do the same; the Podman page already polled only
   while visible and the instance Statistics tab samples only while shown.
6. **Relayout per poll.** Each 3 s listing re-sorted the sidebar, rebuilt every section header
   label, and wrote fresh memory figures into every hidden instance page, the dashboard's labels
   and table, which queued a relayout and a full cairo repaint of the window every poll (0.6 %).
   Hidden pages now remember the newest state and apply it on `map`; the sidebar re-sorts only
   when a row appears or disappears; row text carries no per-poll figure; the content stack is
   not vertically homogeneous, so hidden pages are not measured.

## Targets

| Target | Result |
|---|---|
| ~0 % CPU at idle with the window open | 0.3 % (0.0 % with nothing to poll) |
| Under 120 MB RSS | 82 MB |
