# Benchmarks

Numbers for elementary OS 9 on a MacBook Pro 14" (M1 Pro, 10 cores, 32 GB) running Asahi's `fairydust` kernel with
our USB4 patches. Reproduce on your own Mac:

```bash
sudo apt install sysbench fio glmark2-es2-wayland p7zip-full
python3 mseries/benchmarks/run.py        # ~10 minutes; plug in the charger, leave the Mac idle
python3 mseries/benchmarks/render.py     # refresh the table below from results/*.json
```

Raw results (with kernel, Mesa, governor, power profile, temperatures) are in [`results/`](results/). Add a new file
after a kernel or Mesa update and the table gets a new column.

## Results

<!-- results:start -->
| Benchmark | 2026-10-13 · 7.1.13-1-2-fairydust-usb4-ARCH |
|---|---|
| CPU single-thread, sysbench primes (events/s) | 3804.74 |
| CPU all 10 cores, sysbench primes (events/s) | 27096.17 |
| 7-Zip built-in benchmark, total MIPS | 50,536 |
| SHA-256, 1 thread (MB/s) | 2310.1 |
| Memory read, 1 thread (MiB/s) | 47432.74 |
| Memory read, 10 threads (MiB/s) | 292400.92 |
| Memory write, 1 thread (MiB/s) | 34444.56 |
| Memory write, 10 threads (MiB/s) | 53427.37 |
| Disk sequential read 1 MiB (MB/s) | 6393.6 |
| Disk sequential write 1 MiB (MB/s) | 896.2 |
| Disk random read 4 KiB QD32 (IOPS) | 145,537 |
| Disk random write 4 KiB QD32 (IOPS) | 12,759 |
| Sustained all-core throughput drop over 60 s (%) | 6.6 |
| GPU glmark2-es2 off-screen 1024x768 (score) | 2,026 |
| Firefox headless start, warm (s) | 0.53 |
| Chromium (snap) headless start, warm (s) | 0.55 |
<!-- results:end -->

## Method and caveats

- **One run each** on AC power, balanced profile, `schedutil` governor. Treat differences under ~5% as noise.
- **CPU**: sysbench prime test (`--cpu-max-prime=20000`, 10 s), 7-Zip's built-in benchmark, OpenSSL SHA-256 on 16 KiB
  blocks. The OpenSSL AES-256-GCM figure did not parse and is omitted; this is a harness gap, not a result.
- **Memory**: sysbench, 1 MiB blocks, 24 GiB total. The 10-thread read figure (292 GB/s) is above what the M1 Pro's
  memory can deliver (~200 GB/s), so sysbench is partly hitting caches: use the memory rows to compare runs of this
  suite against each other, not as true DRAM bandwidth.
- **Disk**: fio against `~/.cache` on the encrypted btrfs root (zstd:1 compression, `ssd,discard=async`), O_DIRECT,
  incompressible data, 2 GiB file, 15 s per job. Includes the filesystem and encryption overhead; it is not raw NVMe
  speed. Random-write is low because btrfs copy-on-write plus direct I/O.
- **Sustained**: all cores for 60 s, throughput per 10 s window; the drop is best window versus worst window. Temperature
  rose from 55 to 59 °C. A 6.6% spread with no sharp drop suggests mild frequency variation, not heavy throttling;
  one run cannot separate throttling from noise.
- **GPU**: glmark2 (OpenGL ES 2, Wayland, **off-screen**, 1024x768) on Mesa's Asahi (Honeykrisp) stack, renderer
  `Apple M1 Pro (G13S C0)`. Off-screen avoids the vsync cap, so the score is not comparable to windowed runs.
- **Startup**: median of three warm headless launches. The first launch of the snap Chromium is much slower (~2.6 s)
  because snaps set up their sandbox on first run, which is why Firefox now comes from Mozilla's apt repository.
- **Boot**: `systemd-analyze` includes the time spent typing the NVMe passphrase, so use the userspace figure only.
  What our fixes changed is tracked in `mseries/ROADMAP.md` (login stall 119.7 s → 0.82 s).
- No comparison machines are shown: numbers from other systems would need the same tools, kernel and settings.

## Not measured yet

Battery life, video playback, WebGL/JavaScript browser suites (Speedometer), compile times, Wi-Fi throughput.

## Installer speed: serial vs parallel (synthetic) (#47)

`installer-speed.py` compares running the first-boot modules one at a time with the opt-in parallel runner
(`mseries/modrun.py`, graph in `mseries/enhance-modules.json`). **Every module is a fake that only sleeps.** It runs no
apt, download, build or install script and touches nothing outside a temporary directory, so it can run anywhere and
in CI. It measures the scheduler and the lock graph, not install speed.

```bash
python3 mseries/benchmarks/installer-speed.py --what-if --repeat 5 --out mseries/benchmarks/installer-speed-synthetic.json
```

Module durations are the issue's measured first-boot values for brave (49 s), video (21 s) and files (53 s) and round
guesses for the others (marked `assumed` in the JSON), scaled by 0.02 so a run takes seconds. Median of 5, one machine:

| Scenario (synthetic) | Wall time (scaled) | Speedup |
|---|---|---|
| Serial (what runs today) | 6.50 s | 1.00x |
| Parallel, 5 jobs, apt and Wingpanel-plugin locks | 2.61 s | 2.49x |
| What-if: same without the Wingpanel-plugin lock | 1.74 s | 3.74x |

What this does and does not say:

- The locked graph's floor is its longest lock chain (the five Wingpanel plugin modules, 121 of 302 modelled seconds,
  2.42 s scaled), so the 2.49x is close to the most the current locks allow. Relaxing the Wingpanel lock is the only
  large lever, and it is a what-if row, not a recommendation: it needs real per-module timings first.
- Sleeping modules never compete for CPU, disk or network. Real builds do, so real speedups will be lower. The
  real-install before/after numbers the issue asks for (first-boot wall time and CPU use on the Mac) are **not yet
  measured**; run `sudo elementary-mac-enhance --run --parallel` against the default run and compare
  `/var/lib/elementary-mac/enhance/timing-summary.json`.
- `ccache` (`mseries/lib-build.sh`) is used when installed. It helps a second build of the same pinned source, not the
  first one on a fresh machine, so it does not appear in this table at all.

Every first-boot run now records per-module timing: `elementary-mac-enhance --timing` prints the table (slowest first,
wall and CPU seconds) and the one-line summary, and the JSON is in `timing-summary.json` next to the state files.
`post-install.sh` records the same per stage under `~/.local/state/mseries-post-install/`.
