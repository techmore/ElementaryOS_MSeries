# J314S dock HDMI dark after replug: stale DRM connector, unhandled link-status, unmatched profile — 2026-10-21

Diagnosis by Claude Code on the owner's J314S (MacBook Pro 14-inch, M1 Pro),
elementary OS 9 / Ubuntu 26.04.1, kernel `7.1.12-elementary-aurora20-enh1`
(`linux-image-elementary-aurora-enhancements`), session `pantheon-rust-wayland`
(`/usr/bin/pantheon-compositor --backend native`, package `pantheon-rust-compositor`
built 2026-10-20 14:20). Owner report: monitor on the dock's HDMI shows nothing.
The diagnosis changed nothing on the host. The fix described under "Fix" is source-only: it is
built and unit tested but **not deployed**, so the running compositor is still the old one.
Journal times below are seconds after kernel start (boot 11:00:10Z, 07:00 America/New_York).

## Attached hardware

| Item | Evidence |
| --- | --- |
| Sink | AOC `24E2QA`, product `0x2402`, serial `0x4dd3`, week 50 / 2025, 256-byte EDID with one CEA extension, modes up to 1920x1080@74.973. Parsed from `/sys/class/drm/card2-DP-1/edid`. |
| Path | Thunderbolt DP tunnel from the WD22TB4 dock (`display routed to Thunderbolt DP tunnel dpin0`, `tunnel=1 route=borrowed`). The Mac's own HDMI connector `card2-HDMI-A-1` stays `disconnected` (`DP2HDMI HPD connected:0`). |
| Controllers | `38bc00000.dcp` panel (eDP-1, crtc-0); `289c00000.dcp` dcpext (crtc-1); `28cc00000.dcp` dcpext (crtc-2). Connectors DP-1 (id 74), DP-2 (id 77), DP-3 (id 80) each list `possible_crtcs=0x6`. |

## Timeline

| Time | Kernel (`apple-dcp`) | Compositor (`pantheon-compositor`) |
| --- | --- | --- |
| 15.3 s | `289c00000`: `allocated Type-C DPTX PHY 1`, `atc=1`, link rate 0x1e, 4 lanes, `dcp_hotplug() connected:1 valid_mode:0 nr_modes:26`, then `set_digital_out_mode 1920x1080@60`, finished 16.10 s | 15.86 s creates output **DP-2** on crtc-1 (connector 77), `mapped newly connected DRM output name=DP-2` |
| 39–40 s | `289c00000`: `SET_LINK_RATE 0x0`, `INACTIVE_SINK_DETECTED`, `dcp_dptx_disconnect`, `DEACTIVATE` | libinput removes `event6..8` (dock USB devices); no connector change for DP-2 |
| 45.5 s | `289c00000`: retries on `PHY 0`, `atc=0`, `connected:1 valid_mode:0`, then `INACTIVE_SINK_DETECTED`, `DEACTIVATE` at 46.13 s | 46.11 s creates output **DP-1** on crtc-2 (connector 74) |
| 46.1–46.7 s | `28cc00000`: `allocated Type-C DPTX PHY 0`, link rate 0x1e, 4 lanes (`unexpected lane count:4 phy: 0` warning), `connected:1 valid_mode:0`, `set_digital_out_mode 1920x1080@60` finished 46.68 s, `connected:1 valid_mode:1` | 46.68 s `Creating new wl_output output="DP-1"`; one `Page flip commit failed ... Device or resource busy` (EBUSY) during the pending modeset, then normal rendering |
| after 47 s | no further display messages this boot (only the known missing `rtl_nic/rtl8153b-2.fw`) | redraw stats continue: `vblanks == frames_queued` every 30 s |

The dock moved from Type-C PHY 1 to PHY 0 across the replug. No `dcp_hotplug() connected:0`
was ever logged for connector DP-2 after controller `289c00000` deactivated.

## Resulting state

- `/sys/class/drm/card2-DP-1` and `card2-DP-2` both report `status=connected`, `enabled=enabled`,
  **byte-identical EDIDs** (`md5 f55796ff630e8fc3abaef138806d7e7b`) and identical 26-mode lists.
- DRM atomic state (`/sys/kernel/debug/dri/2/state`): crtc-0 eDP-1 3024x1964@120, crtc-1 DP-2
  1920x1080@60 fb 90, crtc-2 DP-1 1920x1080@60 fb 96; all three CRTCs `active=1` with AR30
  framebuffers allocated by `pantheon-compos`.
- libdrm connector properties: DP-1 `link-status = Bad`, DP-2 `link-status = Bad`, eDP-1 `Good`.
- `org.gnome.Mutter.DisplayConfig GetCurrentState` (serial 7): three logical monitors, eDP-1 at
  x=0 scale 1.25 primary, **DP-2 at x=2420**, **DP-1 at x=4340**, every monitor reported as
  vendor `Apple`, product = connector name, serial `Unknown`.
- `~/.config/monitors.xml` and `~/.config/mseries/display-profiles.json` only know the Insignia
  TV `INS:NS65DF710NA21:0x01010101` on DP-2 (profile `desk-4k`) and `laptop-only`.
- `~/.cache/mseries-display-profiles.log`: `07:00:26 card2-DP-2 connected`,
  `no profile for the displays attached: ['Apple:DP-2:Unknown']`, `07:00:56 card2-DP-1 connected`,
  then only `MonitorsChanged`. No profile was applied.

## Findings

1. **Stale kernel connector (upstream appledrm).** After the tunnel moved controllers, connector
   DP-2 kept `connected` with the old EDID. The Rust compositor trusts connector state and keeps a
   phantom 1920x1080 output mapped at x=2420 between the panel and the real monitor. Windows and
   the pointer can land on a monitor that does not exist. Not fixable in this repository's kernel
   packaging lane (owner rule: do not change the running kernel); mitigate in userspace.
2. **`link-status Bad` is never handled.** In upstream `drivers/gpu/drm/apple/iomfb.c`
   (`dcp_hotplug`, revision `c46d7dcdb8712ea9aeb0ce47b439ffae76371e55`) the driver sets
   `DRM_MODE_LINK_STATUS_BAD` when the DCP has no valid mode and comments that "userspace needs to
   trigger a flush, or the CRTC gets no signal". The compositor (`rust/pantheon-compositor/src/native.rs`)
   never reads or resets the property. For DP-1 the compositor's own first modeset did train the link
   this time (`valid_mode:1`), so the property is stale there; on a route interruption that leaves the
   CRTC active, the compositor will keep doing plane-only flips and the monitor stays at "no signal".
3. **Monitor identity is hardcoded.** `native.rs` fills `PhysicalProperties`/`OutputSnapshot` with
   make `Apple`, model = connector name, serial `Unknown` instead of parsing the EDID. The
   display-profiles watcher matches by `vendor:product:serial`, so no saved profile can match under
   the Rust session, and its documented hotplug "1080p then saved mode" kick (the retrain workaround,
   see `mseries/display-profiles/README.md`) never runs. This is the "wrong dock profile" symptom.
4. **Not established:** whether the AOC currently shows DP-1's (empty) desktop region or "no signal".
   Kernel and compositor both believe DP-1 is scanning out 1920x1080@60. This session could not see
   the screen. If it is dark with the kernel in this state, the fault is downstream of the DCP
   (dock HDMI conversion or monitor input), or a link that needs the retrain in finding 2.

## Repro / check commands (read-only)

```bash
for c in /sys/class/drm/card2-*; do echo "$c $(cat $c/status) $(md5sum < $c/edid | cut -c1-8)"; done
journalctl -k -b -o short-monotonic | grep -E '289c00000.dcp|28cc00000.dcp' | grep -vE 'RTKit|DCP property|read_edt'
journalctl --user -b -o short-monotonic -u pantheon-rust-compositor@wayland.service | grep -E 'DP-|render failed|Device changed'
busctl --user call org.gnome.Mutter.DisplayConfig /org/gnome/Mutter/DisplayConfig org.gnome.Mutter.DisplayConfig GetCurrentState
tail -20 ~/.cache/mseries-display-profiles.log
```

`bash mseries/check-display-paths.sh` now prints the EDID checksum and `link-status` per connected
connector and flags identical EDIDs. `pantheon-drm-probe` prints parsed identity as well.

## Fix (branch `claude/dock-replug-display-fix`, not deployed)

| Change | Where | Effect |
| --- | --- | --- |
| EDID identity | `rust/pantheon-compositor/src/edid.rs`, `kms_props.rs`, `native.rs` | Every external output now publishes the EDID vendor, model name and serial (`AOC:24E2QA:RJLRCHA019923`) to Wayland `PhysicalProperties` and to `org.gnome.Mutter.DisplayConfig`. The eDP panel keeps the old `Apple`/connector/`Unknown` identity because it exposes no EDID. |
| Stale duplicate connector | `edid::stale_duplicates`, `NativeKmsDevice::refresh_connectors`, `open_output_device` | Connected connectors with byte-identical EDIDs that carry a unit-unique serial are one monitor. The connector with the newest EDID blob id is kept; the rest are treated as disconnected, so no phantom output is mapped. Monitors with serial 0, `0x01010101` or `0xffffffff` and no serial descriptor are never merged. |
| Bad link recovery | `link_status.rs`, `NativeKmsDevice::reset_bad_link_status` | On each connector reconcile (udev event plus follow-up plus 30 s poll) a mapped connector whose `link-status` is Bad gets `Good` written back, which the atomic core turns into a full modeset. At most 3 attempts per bad episode, 5 s apart. |
| Diagnostics | `mseries/check-display-paths.sh`, `pantheon-drm-probe` | Both print per-connector `link-status`; the script flags identical EDIDs as `[STALE]`; the probe prints parsed identity, blob ids and the stale verdict. The script also no longer reports dock video as dead when a DP tunnel is connected. |
| Work Mode guard | `mseries/work-mode/test_work_mode.py`, `README.md` | A test fails if the helper ever reads display or dock hardware. No behavior change (see below). |

### Verification

- `cargo test` passes 55 tests with `--features native-drm` (14 new in `edid.rs` and `link_status.rs`) and 34 without;
  `cargo clippy --all-targets` and `cargo fmt --check` are clean; release build succeeds with the native feature.
- **Live, read-only:** the rebuilt `pantheon-drm-probe` ran against the real KMS device and printed:

```
DP-1: Connected   EDID blob 94: AOC:24E2QA:RJLRCHA019923 (unique serial: true)   link-status: Bad
DP-2: Connected   EDID blob 88: AOC:24E2QA:RJLRCHA019923 (unique serial: true)   link-status: Bad
stale duplicate connectors (same monitor EDID, older blob): DP-2
```

  This confirms the EDID read, parse, blob-recency choice and property reads on the actual hardware, and
  that the choice matches the finding (DP-1 live, DP-2 stale).
- Display-profiles tests (`test_display_profiles.py`, 6) and Work Mode tests (10) pass.

### Not verified

- Writing `link-status = Good` and the resulting modeset on the dock link. It needs DRM master, which only
  the running compositor holds, so it can only be exercised by deploying the new compositor and starting a
  new session. Success shows as the log line `link-status was Bad; reset to Good to retrain the link`
  followed by a normal vblank cadence, and the AOC showing the desktop.
- Whether the AOC currently shows a picture (nobody looked at the screen during diagnosis).
- Blob-recency as the live-connector signal assumes the driver publishes a fresh EDID blob on every
  reconnect. It held in this incident (94 vs 88). If the dock returns to the other controller, the
  newer blob should flip the choice; that flip has not been observed.
- Two genuinely identical monitors with byte-identical EDIDs (same serial) would be merged; units of one
  model normally differ in serial, so this is not expected.

### Work Mode

The desktop being in Work Mode is not caused by the dock. `io.elementary.mseries.work-mode enabled` is
`true` with `scheduled false` and `network-trigger false`, so the manual switch alone keeps it applied and
`mseries-work-mode --status` reports "Active". `evaluate()` in the helper reads only the switch, the
schedule and the public IP. Turning it off (System Settings, Windows Work Mode, or
`gsettings set io.elementary.mseries.work-mode enabled false`) restores the normal wallpaper, icon theme and
dock on the next one-minute tick. This session did not change the setting.

## Owner directions recorded this session

- Work/home ("Work Mode") must **not** be inferred from which dock or display is attached.
  Acceptable signals: public IP, a manual toggle, a schedule.
- The owner believes the dev kernel is more stable than assumed; wants a cleanup pass, new
  upstream features ported in, and a polling-based performance comparison of the Rust compositor
  against native Gala. Both are separate tasks, not started.
