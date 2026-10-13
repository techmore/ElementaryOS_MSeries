# Local OS 9 build readiness

Checked 2026-10-13 on the owner's M1 Pro running elementary OS 9.

## Current outcome

- Native aarch64 host, 10 online CPUs, about 32 GB physical RAM.
- Installed `just` 1.45.0-1 and `podman` 5.7.0+ds2-3build1 from the Ubuntu
  archive, with six runtime dependencies. No existing packages were upgraded
  or removed. `zstd` and `rsync` were already installed.
- The official elementary mkosi container runs and sees all **10 CPUs**.
  No container CPU cap was applied. Actual utilization depends on build stage;
  downloads/package setup cannot necessarily occupy every CPU.
- A **local read-only `mkosi summary` succeeded**. This parses configuration,
  not a full image build.
- Full local image build has **not started**: about 37.4 GiB free is below
  the conservative **60 GiB disk guard**. About 22.6 GiB more is needed to
  pass the current guard. The owner chose internal storage only if it passes.

The 60 GiB guard is a conservative capacity policy, not a measured peak
requirement. The successful CI installer is about 6.6 GiB, but a full build
also keeps unpacked roots, raw images, tool/container layers, and caches.
The remaining APFS partition is not Linux free space; no partition changes,
data cleanup, bootloader changes, kernel changes, or audio changes were made.

## Recheck without changing anything

```bash
python3 mseries/local-build-preflight.py
# Or check a future build directory's underlying filesystem:
python3 mseries/local-build-preflight.py --directory /path/to/build-directory
```

Exit 0 means the architecture, required tool executables, and disk guard
pass. Exit 2 means blocked; the JSON lists why. A pass does not validate
RAM availability, firmware, or hardware boot and is not a guarantee that
all future builds will fit. The check creates/deletes no files.

## Configuration check performed

```bash
sudo -n podman run --rm --network host \
  -v /home/admin/Documents/ElementaryOS_MSeries:/work:ro -w /work \
  ghcr.io/elementary/mkosi:tanit mkosi summary
```

The repository was mounted read-only, without a host `/dev` bind or a
privileged container. The summary is saved locally outside Git at
`/home/admin/Documents/elementary-os9-local-summary.txt`.
Container digest observed:
`sha256:a1fbe462ef7cd66445866ff068c9ec96b5ab1c1e0383e9313462675590da45a9`.

## When storage is ready

Recheck capacity and current available RAM, then use a separate checkout
for local `just genkey` and `just do-daily`. Preserve source revision,
container digest, full build log, elapsed time, checksum, and exit status.
The upstream full-build recipe uses privileged containers and binds host
`/dev`; review that separately from this read-only summary before launching.
Keep the running kernel, bootloader, and audio stack untouched. Do not delete
user data to make room automatically. Compare actual build duration with CI
instead of assuming a speedup from core count alone.
