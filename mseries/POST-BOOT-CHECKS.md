# Post-boot checks — first elementary boot on Apple Silicon

Run these inside the new elementary system, in order. Each check says what
to run, what to expect, and what counts as a failure. **Expected failures
are marked** — hitting one is data, not disaster. Report back with the
template at the end (gist or issue).

Conventions: `✔` expected pass, `⚠` expected fail/gap in v1, `?` unknown.

The owner's M1 Pro already boots the transformed elementary installation.
Use this checklist to validate a built factory image; that existing desktop
does not count as a factory-image boot because it uses a different boot and
kernel path.

## 0. Boot & session

| # | Check | Expect |
|---|---|---|
| 0.1 | Boot menu shows **elementary OS (M-series)** alongside Omarchy | ✔ menu entry present |
| 0.2 | Boots to a graphical login without manual intervention | ✔ greeter |
| 0.3 | Log in → Pantheon desktop loads (top bar, dock, wallpaper) | ✔ session |

If 0.2 drops to console: log in, run `systemctl status display-manager`,
paste the output. Reboot back into Omarchy — that system is untouched.

## 1. Display / GPU (`?` — biggest desktop unknown)

```bash
glxinfo -B 2>/dev/null | grep -iE "renderer|vendor|accelerated" || echo NO_GLXINFO
ls /dev/dri
```

| # | Check | Expect |
|---|---|---|
| 1.1 | `glxinfo` renderer mentions Asahi/AGX (not llvmpipe) | ? hardware accel |
| 1.2 | Windows drag smoothly; no tearing in overview | ? compositor fine |
| 1.3 | Full-height display incl. notch strip (bar usable at very top) | ⚠ needs `appledrm` (Asahi kernel: yes; check `sudo dmesg \| grep -i appledrm`) |

`llvmpipe` (software GL) still counts as "desktop works, GPU pending" —
report it exactly.

## 2. Network stack (`?` — must confirm end to end)

```bash
nmcli g; nmcli d status
journalctl -b -u mseries-wifi-firmware --no-pager | tail -5
journalctl -b -u NetworkManager --no-pager | grep -iE "error|warn" | head -5
```

| # | Check | Expect |
|---|---|---|
| 2.1 | `mseries-wifi-firmware` unit is active (exited) | ✔ provisioned, or exact missing-blob message |
| 2.2 | Wi-Fi scans + connects; `ping -c3 1.1.1.1` works | ? the real test |
| 2.3 | Suspend, resume, Wi-Fi returns within ~30s | ? resume unit covers wedge; report `journalctl -b -u omarchy-wifi-resume-fix` |
| 2.4 | AppCenter refreshes its catalogue (proves HTTPS + DNS app-side) | ? |

## 3. Input (trackpad race is intermittent — repetition matters)

| # | Check | Expect |
|---|---|---|
| 3.1 | Internal keyboard works at login + in session | ✔ |
| 3.2 | Trackpad moves/clicks/scrolls | ✔ (inherited host initramfs fix) |
| 3.3 | Reboot 3×, trackpad alive every time | ? race shows here if anywhere |
| 3.4 | Brightness/volume keys | ? report per-key |
| 3.5 | Open Wingpanel Quick Settings and check for **Keyboard Brightness** slider; move it and confirm the keys change | ? slider is implemented in transform and factory-image build paths; image boot/UI confirmation pending |

## 4. Audio (⚠ speakers expected muted in v1)

```bash
pactl info | grep -i "server name"; pactl list short sinks; pactl list short sources
systemctl --user status pipewire pipewire-pulse wireplumber --no-pager | grep -E "Active|PipeWire" | head -6
```

| # | Check | Expect |
|---|---|---|
| 4.1 | PulseAudio server answers (no "Connection refused") | ✔ pipewire-pulse installed by design |
| 4.2 | Headphones / HDMI output produce sound | ? |
| 4.3 | Internal speakers | ⚠ muted until `speakersafetyd` is packaged (known gap) |
| 4.4 | Internal mic records (`arecord -d 3 /tmp/mic.wav && aplay /tmp/mic.wav`) | ? |

## 5. Video decode (`?`)

```bash
mpv --hwdec=auto <any h264 file>   # watch CPU% in another terminal with top
```

| # | Check | Expect |
|---|---|---|
| 5.1 | Plays smoothly; note CPU% and whether `mpv` reports `vaapi`/`v4l2` hwdec | ? Factory-image AVD integration is not confirmed; transformed desktop H.264 720p/1080p/4K decode has passed |
| 5.2 | `bash mseries/check-video-decode.sh` (after a reboot, no memory compaction first) | 720p, 1080p and 4K hardware decode match software; needs the usb4.4 kernel |

## 6. Default apps (spot-check, not exhaustive)

Open each, note crash/missing: Files, Terminal, Text Editor, Videos,
Music, Photos, AppCenter, System Settings (every pane opens), Web browser.
Report exact failure text, plus `dpkg -l elementary-desktop` version.

## 7. M-series units

```bash
systemctl is-active mseries-wifi-firmware.service omarchy-wifi-resume-fix.service
systemctl status mseries-wifi-firmware.service --no-pager | tail -8
```

## Report-back template

```
Model: (e.g. MacBookPro18,3)
Chip/Wi-Fi: (lspci -nn | grep 14e4)
LUKS: yes/no   Kernel: (uname -r)
0.x: pass/fail + notes
1.x–7: same, with pasted outputs for failures
```

One gist with the template filled + `journalctl -b` attached answers every
open question in PORT-MAP.md, KERNEL-REPORT.md, and FIRMWARE-WIFI.md.
