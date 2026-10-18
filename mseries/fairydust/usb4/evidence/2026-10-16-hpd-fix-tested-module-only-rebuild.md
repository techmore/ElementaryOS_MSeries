# First live test of the DP-OUT/HPD fix — results, and the module-only rebuild unlock


> Interpretation update: retain the live measurements below. HPD proves sink
> presence, not a working pixel chain, and the remaining timeout does not
> prove DP-IN is the only possible failure. See [current ledger](../STATE-OF-PLAY.md).
> The new DP-IN patch series is offline only; the historical deployment
> recipe below is not authorized by the owner's current constraints.

**Date:** 2026-10-16
**Tested on:** the live M1 Pro (`j314s`), Dell WD22TB4 attached, monitor on the
dock's HDMI, kernel `7.1.13-elementary-fairydust-usb4-dptunnel`.

## What was changed

`0003-dp-out-prefer-adapter-with-hpd.patch` — `tb_find_dp_out()` in
`drivers/thunderbolt/tb.c` now prefers a DP OUT adapter that reports HPD, only
falling back to the old first-available scan when none does. Rationale and the
register evidence: `2026-10-16-dpout-hpd-selection-bug.md`.

## What was measured

Before the fix (every observation ever recorded on this machine):

```
0:5 <-> 1:13 (DP)     <- host DP IN -> the dock's EMPTY video socket
```

After the fix, same hardware, same boot, dock re-enumerated:

```
0:5 <-> 1:14 (DP)     <- host DP IN -> the dock's HPD adapter (the monitor)
0:5 <-> 1:14 (DP): DPRX read timeout     (x325 and climbing)
0:5 <-> 1:14 (DP): DPRX bypass enabled, pretending DPRX completed
0:5 <-> 1:14 (DP): consumed bandwidth 0/17280 Mb/s
```

**So the fix does exactly what it was written to do, and it is not the root
cause of the failure.** The tunnel is now aimed at the right socket, is fully
programmed, and still cannot complete a DPRX read:

| | host `0-0:5` (DP IN) | dock `0-1:14` (DP OUT) |
|---|---|---|
| `ADP_DP_CS_0` | `0xc0090400` VE=1 AE=1 video_hop=9 | `0xc009044f` VE=1 AE=1 video_hop=9 |
| `ADP_DP_CS_1` | `0x00004008` AUX_TX=8 AUX_RX=8 | `0x00004008` AUX_TX=8 AUX_RX=8 |
| `ADP_DP_CS_2` | `0x5a1021c2` HPD=1 | `0x000a0040` HPD=1 |

Video enable, audio enable, video hop and the AUX hops are programmed on both
ends of the tunnel, and HPD propagates to the host DP IN adapter. The router
still never sets `DPRX_DONE`. That is upstream's claim reproduced under
controlled conditions: **nothing drives the Apple host router's DP IN adapters**
(`drivers/thunderbolt/quirks.c`), i.e. the ACIO/DP-IN block in
`2026-10-16-dpin-adapter-enable-protocol-recovered.md` is the wall, and it is
now the *only* wall.

## H1 is closed (the monitor/cable/dock-HDMI chain is good)

The dock itself reports hot-plug on the monitor's adapter, read from its own
config space twice, either side of a full TB stack reload:

```
dock 0-1 port13  ADP_DP_CS_2 = 0x000fff00   HPD=0   (empty socket)
dock 0-1 port14  ADP_DP_CS_2 = 0x000a0040   HPD=1   (the monitor)
```

The dock sees the monitor. No cable move was needed to establish this. The
monitor is HDMI-only, so the "move it to the dock's DP socket" test is not
available.

## Unlock: a module-only rebuild (minutes, not 1-3 hours)

`debian/build.sh` builds the whole kernel (~1-3 h, needs rustc 1.93.1, pahole,
35 GiB). For iterating on `drivers/thunderbolt` that is not necessary:

* the kernel has `# CONFIG_MODVERSIONS is not set`, so module CRCs are not
  checked and `Module.symvers` is not needed to load
* the running kernel's config is available at `/proc/config.gz`; using it gives
  the exact same `vermagic`

Recipe (in a scratch dir **outside** the repo, from the pinned tarball):

```sh
tar xzf <pinned linux-fairydust.tar.gz>
patch -p1 < 0001-...patch ; patch -p1 < 0002-...patch ; patch -p1 < 0003-...patch
zcat /proc/config.gz > .config
./scripts/config --file .config --disable RUST --disable DEBUG_INFO_BTF_MODULES
make -j"$(nproc)" olddefconfig
make -j"$(nproc)" modules_prepare
make -j"$(nproc)" M=drivers/thunderbolt KBUILD_MODPOST_WARN=1 modules
```

Then `cp drivers/thunderbolt/*.ko /lib/modules/$(uname -r)/kernel/drivers/thunderbolt/`
and `sudo depmod -a`.

Notes and gotchas:

* `RUST` must be off (or rustup 1.93.1 installed); `DEBUG_INFO_BTF_MODULES=off`
  avoids needing `pahole`. Neither affects the module ABI.
* `KBUILD_MODPOST_WARN=1` is required because modpost wants `Module.symvers`
  that a module-only build does not produce. The unresolved-symbol noise is
  harmless — verify it by diffing `nm -u` of the new and the installed module:
  **0 new unresolved symbols** means the kernel already exports everything.
* Always `modinfo -F vermagic` the new module against the installed one.
* The unstripped `.ko` is ~8 MB vs 764 KB installed. Irrelevant.

## Unlock: no reboot needed to test the TB stack

`sudo modprobe -r thunderbolt_apple thunderbolt && sudo modprobe thunderbolt_apple`
tears the dock down and brings it back — dock USB re-enumerated within seconds,
NHI survived. **Arm the bypass first** (`echo 1 > .../dprx_bypass`) to leave the
safe state before unloading, exactly as the cable hazard rule requires.

`/sys/bus/thunderbolt/devices/domain0/rescan` does not exist and cannot be
written (permission denied) — do not look for it again.

## ACIO co-processor observations (new, unexplored)

Firmware syslog this boot, via the `thunderbolt-apple-acio ... RTKit: syslog`
channel:

* `lane_init.c:936: Timeout reading AT register` — **24 occurrences** the
  strongest candidate lead: the AIO/ACIO firmware itself times out on a register
  read. Not yet attributed to anything.
* `configuration_space_tx.c:57: TX path: src port=14 ... hopid=8` and
  `ration_space_null.c:140: RX path: null port=0, queue=1, target port=14,
  hopid=8`, plus the same for ports 13, 15, 16 — the ACIO firmware programs
  internal null-port paths for its own adapters at boot. The ACIO's internal
  port numbering (13/14/15/16) does **not** match the TB driver's host adapter
  numbers (3/4/5/6/7); establish the mapping before reading anything into this.
* `PPipeDCP_H13P.cpp:11122: IOMFB setup_video_limits called on secondary display
  with no timing set` — DCP firmware ran its display setup with no mode.

## State of the machine after this test

* New `thunderbolt.ko` + `thunderbolt_apple.ko` **installed** in
  `/lib/modules/7.1.13-elementary-fairydust-usb4-dptunnel/kernel/drivers/thunderbolt/`.
  Originals backed up in `~/dpout-fix-build/backup-modules/`.
  Installed sha256: `e81e812bed42b1acd80c4056d93113994b5bccdf0af6a7bc3bc58ca2543f1ac9`
* `dprx_bypass=1` (safe to unplug) — it resets to 0 on every module load/boot.
* Dynamic debug is enabled for `tb.c`, `tunnel.c`, `switch.c`.

## Next

1. Implement the DP-IN enable (`2026-10-16-dpin-adapter-enable-protocol-recovered.md`):
   the ACIO `startUsingTunnel()`/`stopUsingTunnel()` register effects and the
   ATC-PHY `open()`/`openTunnel()`/`setActiveLaneCount()` effects are still
   unrecovered sub-sequences.
2. Investigate `lane_init.c:936 "Timeout reading AT register"` — it may be the
   firmware-side symptom of the same missing link.
3. Keep the HPD preference in any upstream-bound series; it is correct
   behaviour independent of Apple.
