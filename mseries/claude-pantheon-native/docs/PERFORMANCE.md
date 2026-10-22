# Performance

Measured 2026-10-21 on elementary OS (Pantheon, Wayland, 2x HiDPI) on an Apple
Silicon Mac: 10 cores, 30 GB RAM, aarch64. The native client is a release build
from this repository; the Electron app is `/usr/lib/claude-desktop/claude-desktop`
idle with its Code tab open. Both were sampled with `./bench.sh <name> 20`, which
sums RSS over every process with that name and averages CPU from
`/proc/<pid>/stat` deltas over 20 s.

## Idle, with a chat open

| Process | Processes | RSS avg (MB) | RSS peak (MB) | CPU % avg over 20 s |
|---|---|---|---|---|
| claude-pantheon, 1.3 MB transcript open, composer focused | 1 | 74 | 74 | 0.0 |
| claude-pantheon, 5.5 MB transcript open (60 turns) | 1 | 83 | 111 | 0.0 |
| claude-desktop (Electron), `bench.sh` run | 19 | 2399 | 2431 | 133.9 |
| claude-desktop (Electron), from `BASELINE.md` | 19 | 2330 – 2390 | – | 108 |

The Electron figures in `BASELINE.md` were taken a few minutes earlier with
`ps` samples and a 10 s `/proc` delta; the `bench.sh` run above is the same
app a little later. Either way the native client uses about 1/30 of the memory
and no CPU at idle, against roughly a full core busy for Electron (its GPU
process alone sat at ~49 % of a core).

## Start-up

Time from `main()` to the window's `map` signal, `CLAUDE_PANTHEON_DEBUG=1`,
five cold-ish launches in a row: **132, 132, 152, 136, 135 ms**. The sidebar is
populated from a worker thread after the window is up (138 sessions, 213
transcript files scanned, title cache warm).

## Transcript parsing (worker thread)

| Transcript | Size | Turns shown | Parse time |
|---|---|---|---|
| Quick settings panel nativization | 1.3 MB | 13 | 24 ms |
| Unified release pipeline + Rust-native Software Updates | 5.5 MB | 60 | 94 ms |

Measured with `./build/transcript-dump <file>`. Widgets are then created in
idle batches of 40 turns so the window never blocks.

## Targets

| Target | Result |
|---|---|
| Under 120 MB RSS | 74 MB typical, 111 MB peak while a 5.5 MB transcript loads |
| ~0 % CPU at idle with a transcript open | 0.0 % |
| Start-up under 300 ms | about 130 ms to a mapped window |

## What it took

Three things stood between a plain GTK4 app and those numbers, all found by
measuring rather than guessing:

1. **Renderer.** With the session's default `GSK_RENDERER=gl` (or `ngl`,
   `vulkan`) Mesa on Asahi loads LLVM and allocates about 180 MB of heap for
   shaders before a single widget is drawn: 240 – 290 MB RSS. The cairo
   renderer draws the same window in 70 MB, so `Application.main` forces
   `GSK_RENDERER=cairo` (override with `CLAUDE_PANTHEON_RENDERER`).
2. **Window shadow.** GTK's default client-side decoration is a blurred
   `box-shadow`. The cairo renderer re-blurs it over the whole window on every
   frame, which made each repaint cost ~52 ms at 2x; replacing it with a 1 px
   outline in the app's CSS brought a full repaint down to ~6 ms. (GL paints in
   ~3 ms but costs the memory above.)
3. **Cursor blink.** GTK fades the text cursor with a frame-clock tick for ten
   seconds after each keystroke. With the composer focused that kept the window
   repainting continuously, 14 – 19 % of a core "idle". The app sets
   `gtk-cursor-blink = false`; the cursor is steady and idle CPU is 0.0 %.

Everything else is ordinary care: parsing off the main thread, rendering turns
in idle batches, creating tool-result widgets only when a row is expanded,
and indexing sidebar titles from the head and tail of each file with a cache in
`~/.cache/claude-pantheon`.
