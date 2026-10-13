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
- Old OS retirement raised free space to **69.4 GiB**; the local build
  capacity/tool check now passes. See STORAGE-PLAN.md for approvals, retained
  private backups, and verification. Full image-build status is recorded
  separately by the worker, not inferred from this preflight.

The 60 GiB guard is a conservative capacity policy, not a measured peak
requirement. The successful CI installer is about 6.6 GiB, but a full build
also keeps unpacked roots, raw images, tool/container layers, and caches.
The remaining APFS partition is not Linux free space. Authorized cache,
build-tree, and snapshot cleanup recovered about 12.2 GiB; see STORAGE-PLAN.md.
No partition, bootloader, kernel, or audio changes were made.

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

## First native run — started 2026-10-13 at 09:42 EDT

- Source checkout: `/home/admin/Documents/os9-local-build-20261013`.
- Committed source: `89e959db11768ec1e24cbae74d5f466c7e8ace8e`.
- User service: `elementary-os9-local-build-20261013.service`.
- Worker: `mseries/local-build-worker.sh`, running with Nice=10, no CPU cap.
- Records: `local-build-records/status.json`, `build.log`, and checksum after
  completion, inside that isolated checkout.
- Local live monitor: http://127.0.0.1:8767/ (only on this Mac), served by
  `elementary-os9-local-monitor-20261013.service`. It exposes only the build
  records directory and refreshes every five seconds. No external bind.
- Progress was verified at image-build stage with advancing log writes.
  This does not yet establish build success or boot support.

Check without starting a duplicate:

```bash
systemctl --user status elementary-os9-local-build-20261013
journalctl --user -u elementary-os9-local-build-20261013 -n 30 --no-pager
cat /home/admin/Documents/os9-local-build-20261013/local-build-records/status.json
```

Transient services run beyond the Codex turn, but a shutdown/logout can
interrupt them. They are not recurring automations or automatic AI takeover.
The local monitor is separate from the public GitHub dashboard. Filesystem
free space was 69.4 GiB before starting; it will fall as build products grow.
