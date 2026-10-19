# Sound on the dock TV, and why YouTube Movies stop at 480p (investigated 2026-10-18)

Owner report: YouTube Movies (after the Widevine fix) play at most 480p, and there is still no sound from the TV on
the WD22TB4 dock (Insignia NS-65DF710NA21 on the dock's HDMI, Aurora `.20`).

## 1. No TV sound: the kernel has no sound card for the display

Checked on the running system (read-only):

| Check | Result |
|---|---|
| Kernel | `7.1.12-2-20261017.20-sep-ARCH`, `CONFIG_DRM_APPLE_AUDIO=y` (display audio is built in) |
| `/sys/module/appledrm/parameters/hdmi_audio` | `N`; the boot command line does not set it |
| ALSA cards | only `AppleJ314` (speakers/headphones) and `AppleJ314HPAI`; **no `apple_dcp` card** |
| Device tree | `dcp@289c00000` and `dcp@28cc00000` are the two external display controllers (`apple,t6000-dcpext`); each has an enabled `apple,dpaudio` controller (`audio-controller@39b504000` and `@39b508000`) linked to it by OF graph, both bound by `dcp-dp-audio` |
| Which controller drives the TV | `dcp@289c00000` (dcpext0): `SET_LINK_RATE 0x1e`, `1920x1080@60` over the USB4 tunnel; DRM connector `card2-DP-2` connected |
| UCM | `alsa-ucm-conf-asahi 8-3` has no `apple_dcp` profile |

So the hardware path to the TV's speakers exists and is wired in the device tree. Two things block it:

1. **Kernel switch off.** In Aurora `.20` (`drivers/gpu/drm/apple/dcp.c`, `audio.c`) the parameter
   `appledrm.hdmi_audio` ("Enable unstable HDMI audio support") gates both `avep_init()` (the DCP's AV endpoint,
   started in `dcp_start`) and `dcpaud_init_snd_card()` (called when the display subsystem binds at boot). The
   parameter is writable at runtime, but setting it afterwards does nothing until both run again, and rebinding the
   display subsystem would black out every screen. `appledrm` loads from the initramfs, so a `modprobe.d` file
   would also need an initramfs rebuild. **It has to be on the kernel command line at boot.**
2. **No UCM profile.** With the card present but no profile, WirePlumber offers only `off`/`pro-audio`. The
   profile is AsahiLinux/alsa-ucm-conf-asahi#9 (open, not merged). **Installed here 2026-10-18** from
   [`ucm/apple_dcp/`](ucm/apple_dcp/SOURCE.md) by [`install-dcp-display-audio.sh`](install-dcp-display-audio.sh);
   it does nothing until the card exists (sinks unchanged after install, checked with `wpctl status`).

### What upstream knows (omacom/linux-aurora#48, open, P3, "needs-retest")

The only report is a J314S like ours on Aurora `.15` with `hdmi_audio=1` and the same UCM profile, but on the
**built-in HDMI port**, not a dock. Results: playback clean; a display plugged in after login shows no sink until
WirePlumber restarts; **the first playback after a boot can stall** (`hw_ptr` stuck at 0) until WirePlumber
restarts; unplug/replug and s2idle are fine; **when the screen blanks (DPMS) the sink disappears and audio moves to
the laptop speakers** until the screen wakes. **Thunderbolt/USB4 dock audio has never been tested upstream.**
That makes our dock the first test of this path.

### To try it (needs the owner: a boot-entry change and a reboot)

Add a separate, non-default GRUB entry: a copy of `elementary-aurora20` with ` appledrm.hdmi_audio=1` appended to
the `linux` line. Boot it once from the menu. Leave the default and the armed `.20-enh1` one-shot trial alone,
because that trial records "no audio changes". Then:

1. `cat /proc/asound/cards` should list `Apple DisplayPort`; `wpctl status` should show a `HiFi__HDMI1__sink`.
2. If the TV was attached at boot and playback hangs: `systemctl --user restart wireplumber` (upstream workaround).
3. Test playback, dock replug, the TV blanking, s2idle; then re-measure A/V sync with `../tools/av-sync-test.html`,
   since the DCP audio path has its own latency.
4. Record results here and on omacom/linux-aurora#48 (first Thunderbolt/dock data point).

Rollback: boot any other entry. Removing the UCM profile: `install-dcp-display-audio.sh --uninstall`.

### Ways to get TV sound now, without a kernel change

- Bluetooth or wired speakers or headphones on the Mac (headphone jack works).
- The TV's own apps. The NS-65DF710NA21 is a Fire TV model: its YouTube app plays Movies in HD with TV sound, which
  no Linux browser can (section 2).
- An AirPlay output, if the TV or a box on it receives AirPlay. PipeWire lists `zTV-Living Room` (RAOP), but its
  device type could not be identified from here. RAOP adds hundreds of ms of delay.

## 2. YouTube Movies at 480p: YouTube's rule for browsers, not a port bug

Google's YouTube system-requirements page says Movies & TV HD playback is unavailable when streaming in a browser,
Safari excepted (<https://support.google.com/youtube/answer/78358>). Linux users report the same 480p cap on
free-with-ads and rented films in Chromium-based browsers. Our Widevine is the software level (L3), as on every
Linux desktop. No flag, user agent or package on this machine changes that. It is not the hardware decoder or the
container: ordinary YouTube videos still play up to 4K. For HD films use a supported device (the TV's own YouTube app).

Correction: `../BRAVE-WIDEVINE.md` and the earlier handoff said "SD/720p" for YouTube Movies. For YouTube in
a browser the ceiling is 480p.

## Boot entry added (owner-approved, 2026-10-18 06:28)

`/boot/grub/custom.cfg` now has a block `# BEGIN mseries display-audio test` with entry id
`elementary-aurora20-hdmiaudio`: an exact copy of `elementary-aurora20` plus ` appledrm.hdmi_audio=1`. It is not the
default and does not touch `next_entry` (still `elementary-aurora20-enh1`). `grub-script-check` passes. Backup:
`/boot/grub/custom.cfg.before-hdmiaudio-20261018`. Pick it from the boot menu. Remove it by deleting that block.
Not booted yet; nothing is verified on hardware.

Noted at the same time: another agent rewrote `custom.cfg` concurrently. It removed the old fairydust test entries
and appended `mseries-full-height` (`appledrm.show_notch=1`), which sets the normal-boot default to that entry. That
change is not part of this work.

## Safari comparison

There is no Safari for Linux and no port effort. Apple ships Safari only on its own OSes. WebKitGTK (GNOME Web) shares
the engine but has neither FairPlay (the DRM that gives Safari HD films) nor Widevine, so it would not play YouTube Movies
at all. macOS cannot run in a VM on Linux on Apple Silicon, and Darling does not run Safari. **macOS is still on this disk**
(717 GB APFS container, `nvme0n1p2`), so the real A/B is: hold the power button at boot, choose macOS, and play the same
film in Safari on the same hardware and TV.
