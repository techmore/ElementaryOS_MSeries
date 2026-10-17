# Neo recorder live status — 2026-10-16

Report recorded at **2026-10-16 12:45:43 UTC** (08:45:43 America/New_York).
The read-only observations below were supplied by the delegated live-check
worker immediately before publication; this is a point-in-time report.

| Check | Observed result | Limit |
|---|---|---|
| Recorder | MacBook Neo / Mac17,5 / A18 Pro; macOS 26.6.2 | Recorder identity, not the M1 Pro target |
| Sleep prevention | Tracked `caffeinate` still asserts indefinite `PreventSystemSleep`, `PreventUserIdleSystemSleep` and `PreventUserIdleDisplaySleep` | Keep the lid open; this does not qualify target boot or video |
| USB inventory | Dell dock/hubs, USB LAN and Logi USB Headset enumerate on Neo | Does not establish this is the same physical WD22TB4 targeted on the M1 Pro, or that the owner moved any cable |
| Proxy endpoint inventory | No `/dev/cu.usb*` endpoint | No proxy handshake was attempted; cable attachment alone does not establish a proxy session |
| Display inventory | `SPDisplaysDataType` reports A18 Pro GPU only, no display entries | External monitor picture remains unconfirmed |
| Target | M1 Pro remained in Linux at the latest check; `dprx_bypass` was `Y` | Point-in-time Linux state, not native macOS baseline or guest evidence |
| Target buses/displays | `lsusb -t` emitted no devices; `/sys/bus/thunderbolt/devices` had no entries; DRM DP/HDMI disconnected and eDP connected | No enumerated target USB/Thunderbolt dock was observed; this does not establish which physical cable moved |
| Recorder tools | Python/HV import, real AArch64 `ARMAsm` smoke and loader help previously passed | Tool readiness, not a successful hardware trace |

## Execution and publication rules

The primary chat must remain responsive and must never wait on SSH. Delegate
remote checks; apply hard command and connection timeouts. Launch any long
remote preparation as a tracked local job on the recorder, then return and
inspect its status with a bounded check. Provide progress updates every
30 seconds while active work is running, as requested by the owner.

This report publishes no credentials, account names, network addresses,
machine hostnames/serials, SSH keys or raw registry. The repository coordinator
is the sole Git writer; this report was published from the Linux worktree,
without installing Git or changing the recorder.

## Next required evidence

Resolve the physical cable/port topology without guessing from USB inventory.
The WD22TB4 host cable must connect to the M1 Pro for the target dock test;
the Neo uses a separate direct USB data cable to another target port.
Collect the M1 Pro's native macOS baseline and matching build/kernelcache with
the dock/HDMI retained. A separately approved and validated target guest boot
route, confirmed DP-IN/DCP/DART ranges and a proxy handshake remain necessary
before the combined MMIO/IPC trace. No reboot, boot modification, hardware
trace or dock-video success is claimed by these checks.

See [recorder setup](../NEO-RECORDER-SETUP.md) and
[cutover checklist](../MACOS-CUTOVER-CHECKLIST.md).
