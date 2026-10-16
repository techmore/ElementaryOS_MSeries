# WD22TB4 dock video — state of play (READ THIS FIRST)

Updated 2026-10-16 (day 9 of the attempt). Purpose: **stop re-deriving, stop
regressions.** If this file disagrees with any other note, this file wins until
it is deliberately updated here.

## Objective

Get the **dock's own** video output (its DP or HDMI socket) onto a monitor from
the M1 Pro (`MacBookPro18,3` / j314s) under Linux, via USB4 DisplayPort
tunnelling. Explicitly *not* the Mac's built-in HDMI, and *not* a direct
USB-C DP-Alt-Mode adapter — both were ruled out by the owner.

## One-line state

The dock enumerates and USB4 DP tunnels activate, but **the host never feeds the
tunnel**, so the sink never answers and there is no picture. The cause is
localised to exactly one missing block (see "The unknown").

## MILESTONES — measured in pixels, not knowledge

Learning does **not** count as progress here. Each milestone has a binary,
observable pass criterion. Current position: **before M0.**

| # | Milestone | Pass = observable evidence | Status |
|---|---|---|---|
| **M0** | A sink exists on the dock | Monitor on the dock's DP **or** HDMI, powered, correct input selected; `1:13`/`1:14` appear under the TB tree; a hot-plug event in dmesg | **NOT MET** — on day 9 the dock reported *zero* sinks |
| **M1** | The host feeds the tunnel | `DPRX capabilities read completed` with `dprx_bypass` **OFF** and **no** `DPRX read timeout` | **NOT MET** — 7x timeout in ~460 ms |
| **M2** | DCP links to the sink | `card2-DP-1` = `connected`, a valid mode logged, no `DEVICE_NOT_RESPONDING` | **NOT MET** |
| **M3** | **The monitor lights up through the dock** | Visible picture on the dock output, mode matches, dock HDMI socket confirmed | **NOT MET** ← the one that matters |
| **M4** | Stable / repeatable | Survives monitor re-plug and a reboot; reproducible without hand-holding | **NOT MET** |

M1 is the true frontier milestone: it is the first point where the host proves it
can drive the tunnelled link. Everything after it is "normal" display bring-up.
**M1 is blocked by exactly one thing: the DP-IN enable sequence (see "The
unknown").** No amount of Linux-side crossbar/tunnel work reaches it.

## The chain, as measured on this machine

```
fb -> dispext0/1 (dcp@289c00000, dcp@28cc00000, both "apple,dcpext")
   -> display crossbar (mux@b0304c000, "apple,t6000-display-crossbar")
   -> one of { dpphy | dpin0 | dpin1 }
   -> ACIO DP IN adapter (USB4 host router adapter 0:5)
   -> USB4 tunnel -> dock (1:13 = DP, 1:14 = HDMI) -> monitor
```

## PROVEN (do not re-derive)

1. The dock enumerates: `0-1` = `WD22TB4 Thunderbolt Dock`, Dell, USB4 gen 4.
   USB tunnelling fully works through it (Realtek hubs, RTL8153 GbE, Logitech
   H390 audio, mouse).
2. A DP tunnel **does** form when a sink is present: `0:5 <-> 1:13`, state
   `activating`, AUX TX/RX activation complete, `22500 Mb/s` — yet
   `card2-DP-1: disconnected`.
3. With the DPRX bypass **off**, a real read times out: 7 x `DPRX read timeout`
   in ~460 ms -> `RESULT=SILENT`.
4. DCP's own connect path reaches the firmware, then fails: APCALL 20
   `INACTIVE_SINK_DETECTED`, 22 `DEVICE_NOT_RESPONDING`, 24
   `DEVICE_NOT_STARTED`; the connector stays `disconnected`.
5. Two independent readers fail (router DPRX; DCP AUX) -> the wall is
   **host-side**, not the cable (caveat H1 below).
6. `DPRX capabilities read completed` is printed *after* the (bypassed) wait. It
   is **not** evidence the sink answered.
7. The mainline display crossbar already implements three muxes —
   `dpphy` (0), `dpin0` (1), `dpin1` (2) — and `MUX_DPIN0/DPIN1` program
   `CROSSBAR_MUX_CTRL_DPIN{0,1}_SELECT{0,1}` plus the `ATC_DPIN0/DPIN1` enable
   bits (`drivers/mux/apple-display-crossbar.c`). Routing to the DP-IN inputs is
   **already implemented and was exercised** by experiment 1 (`--mux-arg 1`).
8. The DP-IN blocks (candidates `0xb01e50000`, `0xb01e58000`) are referenced by
   **no source we hold** — not the Asahi kernel, not m1n1 `src/`, not the m1n1
   `proxyclient/`. `drivers/thunderbolt/apple.c` mentions "DP IN" only in a
   comment diagram.
9. **The macOS kernelcache is already on this machine's ESP** and does *not*
   need a macOS boot to obtain:
   `/boot/asahi/kernelcache.release.mac13j` (25,847,891 bytes, IM4P,
   `KernelManagement_host-354.14.0.3`), plus
   `/boot/asahi/BuildManifest.plist`, `SystemVersion.plist`,
   `RestoreVersion.plist`. The Asahi installer left them there. The
   `all_firmware.tar.gz` / `vendorfw` bundles hold only wifi/Bluetooth/input
   firmware — **not** the display firmware.

## The unknown — this is the entire problem

Nothing enables or programs the **ACIO DP-IN adapter and its DP-IN block**. So
the crossbar's `dpin0`/`dpin1` output is a dead end, and DCP's DPTX never
reaches the sink over AUX. The sequence that does this exists only in Apple's
display driver / firmware (macOS). It is not in any open-source tree.

We **do** now hold Apple's kernelcache locally (PROVEN 9), so the static route
can start immediately. The DCP **firmware** blob is still missing and is the
harder half.

## RULED OUT (do not retry)

- Cable/adapter as the root cause (except H1).
- **Crossbar selection alone** — already tried as experiment 1 (`--mux-arg 1`,
  `dpin0`). `DP-TUNNEL-RE.md` explicitly supersedes the "crossbar selection is
  the fix" inference.
- `dprx_bypass=1` as a fix: it fakes the read and cannot produce a picture.
- The Neo as a Thunderbolt reference: it has **no TB controller**
  (`SPThunderboltDataType` -> "No hardware was found"); its dock link is
  DP-Alt-Mode, a different path.
- `/dev/mem` ADT read: `EPERM` (`STRICT_DEVMEM=y`). Not retried.
- Stock `trace_atc.py` / `trace_pmgr.py`: contain hardcoded addresses/ports.

## H1 caveat (still open)

We have **never** confirmed a picture on the dock from any OS in this session.
If the dock's video output is itself dead, everything above is moot. Closing H1
costs 60 seconds and requires a sink actually present on the dock.

## Regression guards (each one has already bitten us)

- **Boot entry:** the working kernel is `linux-asahi-fairydust-usb4-dptunnel`.
  Its entry lives in `/boot/grub/custom.cfg` (id `elementary-usb4-dptunnel`);
  `GRUB_DEFAULT=0` stays untouched. One-shot boot:
  `sudo grub-reboot elementary-usb4-dptunnel && sudo reboot`.
- **`dprx_bypass` resets to N on every boot.** Re-arm before any dock unplug:
  `echo 1 | sudo tee /sys/module/thunderbolt/parameters/dprx_bypass`.
- **Never unplug the dock with the bypass OFF** — a DPRX read in flight
  deadlocks the port.
- The USB4 NHI can disappear from the bus (`b01f00000.nhi` missing). ACIO
  `unbind`/`bind` does **not** restore it; only a reboot does.
- The dock exposes DP adapters **only** when a live sink is present. Zero sink
  means there is nothing to measure (this wasted a session on day 9).
- Run session scripts from the `wt-dockvideo` worktree; the shared checkout is
  stale and edited by another agent.

## NEXT (cheapest first)

0. **[no hardware] Disassemble Apple's `AppleDisplayCrossbar`** — specifically
   `AppleATCDPINAdapterPort` / `AppleT600xDisplayCrossbar::bringConnectionUp` —
   and recover the DP-IN adapter enable sequence. The binary is already
   extracted: see
   `evidence/2026-10-16-apple-display-binaries-extracted-locally.md`.
   Cross-check the recovered offsets against
   `drivers/mux/apple-display-crossbar.c`. **This is the current frontier task
   and it needs no hardware and no macOS boot.**
1. (hardware) Put a sink on the dock; confirm `1:13`/`1:14` exist. Nothing is
   measurable without this — milestone M0.
2. Smallest driver change -> CI build -> one hardware test.
3. A macOS visit is now needed **only** for the DCP *firmware* blob and the
   dynamic trace — do not schedule it until step 0 is exhausted.

## Honest assessment

No open-source Apple Silicon project has working USB4 DP tunnelling. This is
frontier work. Success is **not** guaranteed and may be unreachable without
Apple's display firmware as a reference.

## Evidence index

- `~/dptunnel-logs/` — `dp-sink-test-*.log`, `collector-*.txt`, `live-monitor.txt`
- `~/dp-tunnel-artifacts/exp2/` — reinstallable exp-2 kernel `.deb` + checksums
- RE map: `DP-TUNNEL-RE.md`; audit: `DPIN-AUX-AUDIT.md`; decision: `DOCK-VIDEO-DECISION.md`
- macOS baseline helper: `run-macos-baseline.sh`
- This file is the entry point.
