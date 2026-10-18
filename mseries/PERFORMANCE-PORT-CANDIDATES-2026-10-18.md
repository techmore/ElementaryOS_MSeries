# High-performance codebases to port or adopt — pass of 2026-10-18

Scope: things that would improve what we actually run into on the M1 Pro (stutter, power, fragmentation, decode
paths, responsiveness), not a generic app list. Nothing here was installed or built. Existing coverage: upstream
watchers and the Rust-port plan (`EDGE-AND-RUST-PLAN.md`), local AI/oMLX review (`JOSHUA-REPOSITORY-REVIEW.md`,
`OMARCHY-AUDIT-2026-10.md`), dictation (`dictation/`), iPhone bridge (`TETHER-CONTINUITY.md`).
Kernel work belongs to DeepSeek/Aurora: items marked **kernel** are requests to file upstream, not changes made here.

## What this Mac runs today (checked live, Aurora `.20`, 2026-10-18)

| Fact | Value |
|---|---|
| CPU layout | 2 E-cores (Icestorm) + 8 P-cores (Firestorm), 1 thread each |
| Page size / preempt / HZ | 16 KiB pages, `PREEMPT` dynamic, HZ=1000 |
| `sched_ext` | **not built** (`CONFIG_SCHED_CLASS_EXT` unset; BPF JIT, BTF and BPF syscall are on) |
| MGLRU / THP | **not built** (`lru_gen` and `transparent_hugepage` sysfs absent) |
| Swap | 8 GiB zram, prio 100; `vm.swappiness` 60; `compaction_proactiveness` 100 |
| CMA | 64 MiB total, 57 MiB free |
| CPU pressure (PSI) | `some` avg10 ~10-17% while Claude/ChatGPT/Brave ran |
| GPU / Vulkan | Honeykrisp 1.4.335 on "Apple M1 Pro (G13S C0)" |
| FFmpeg | 8.0.1 (Ubuntu): `vaapi`, `vulkan`, libdav1d, libplacebo; **no `v4l2request` hwaccel**; only `*_v4l2m2m` wrappers |
| Video decode | AVD via libva v4l2-request: H.264, HEVC Main/Main10, VP9 P0 (brave-youtube confirmed it, `video-decode/README.md`) |

## Ranked candidates

| # | Candidate | Fit to a real gap | License / activity | Risk | Next step |
|---|---|---|---|---|---|
| 1 | **sched_ext + `scx_lavd` / `scx_bpfland`** ([sched-ext/scx](https://github.com/sched-ext/scx)) | Latency-critical scheduler written for interactive use; `lavd` is latency- and power-aware on asymmetric CPUs, i.e. 2E+8P. Directly aimed at "stutter that comes and goes". | GPL-2.0; v1.1.4 (2026-10-15), pushed 2026-10-17 | **kernel**: needs `CONFIG_SCHED_CLASS_EXT=y` in the Aurora/Asahi config, not set today; unproven on arm64 Apple SoCs | File an Aurora issue asking for the option; test in a lab build only |
| 2 | **MGLRU + CMA-backed decoder buffers** (kernel config) | AVD needs a large contiguous allocation per job and free high-order memory was nearly gone (buddyinfo during the stutter). MGLRU is absent; CMA exists (64 MiB, 57 free) but the decoder's order-10 allocation does not obviously use it. | in-tree | **kernel**; measured only as a plausible cause, not proven | Reproduce stutter vs `buddyinfo`, then ask upstream whether AVD can allocate from CMA or `dma-heap` |
| 3 | **FFmpeg native `v4l2request` hwaccel** (upstream FFmpeg) | Would let mpv/ffmpeg use the AVD without the libva shim and Chromium's sandbox problem. Ubuntu's 8.0.1 build has none. | LGPL | Unknown whether the upstream hwaccel covers VP9/HEVC on `avd` nodes; needs a custom FFmpeg build | Build FFmpeg with `--enable-v4l2-request`, test with the same VP9 clip (`framemd5` vs software), compare power |
| 4 | **mpv + libplacebo (Vulkan, gpu-next)** ([mpv-player/mpv](https://github.com/mpv-player/mpv)) | Already installed; best path to 4K and correct colour/range on the dock TV; `mpv-youtube.conf` exists | GPL/LGPL; pushed 2026-10-18 | Low | Try `video-decode/mpv-youtube.conf` once on the dock TV; compare against the contained Brave |
| 5 | **llama.cpp (Vulkan) / whisper.cpp** ([ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp), [whisper.cpp](https://github.com/ggml-org/whisper.cpp)) | Honeykrisp Vulkan 1.4 is present, so GPU inference on the M1 Pro is plausible; ties into local assistants and dictation | MIT; both pushed this month | Medium: Honeykrisp compute performance vs CPU unmeasured here | Run each on a fixed model/audio, 3 runs, median tokens/s and watts; existing dictation bench is `dictation/stream-bench.py` |
| 6 | **Ghostty / Alacritty** terminals ([ghostty](https://github.com/ghostty-org/ghostty), [alacritty](https://github.com/alacritty/alacritty)) | GPU-rendered terminals for responsiveness over long agent sessions | MIT / Apache-2.0; pushed this week | Low, optional apps; Wayland scaling on this setup untested | Install one beside the stock Terminal, measure input latency subjectively and idle watts |
| 7 | **uutils coreutils, ripgrep, fd** ([uutils/coreutils](https://github.com/uutils/coreutils)) | Memory-safe/faster userland; matches the Rust plan in `EDGE-AND-RUST-PLAN.md`; little measurable benefit for the stutter or power problems | MIT / Unlicense / Apache | Low | Only as part of the Rust-port plan, not for performance |
| 8 | **Zed, Helix** | High-performance editors; not needed by any known gap | Zed license field is "NOASSERTION" (mixed licenses, check before redistributing) | Low | Skip unless wanted |

## Not recommended
- Anything that needs SSPL source (`rustpush`) in the image; disabling the browser sandbox globally (see `video-decode/README.md`).
- Auto-applied tuning daemons (`ananicy`, `auto-cpufreq`): they would fight `mseries-power` and the PMP now running under the Aurora boot payload.

## Decisions for the owner
1. Whether to ask Aurora/DeepSeek for `sched_ext`, MGLRU and a CMA path for the AVD (the top two, kernel-side).
2. Whether to try a custom FFmpeg with `v4l2request` (safe: user-space only, side by side).
3. Whether to benchmark local AI on Honeykrisp (needs a dedicated session; it loads the GPU).
