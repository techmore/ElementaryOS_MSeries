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

The three findings (cairo renderer forced in `Application.main` with `CLAUDE_PANTHEON_RENDERER` to
override, a 1 px outline instead of the blurred CSD shadow, `gtk-cursor-blink = false`) and the
ones the Rust twin added later are kept in one place for every GTK app here:
[`mseries/GTK-PERFORMANCE-ASAHI.md`](../../GTK-PERFORMANCE-ASAHI.md). Specific to this client:
parsing off the main thread, turns rendered in idle batches of 40, tool-result widgets created only
when a row is expanded, and sidebar titles indexed from the head and tail of each file with a cache
in `~/.cache/claude-pantheon`.
