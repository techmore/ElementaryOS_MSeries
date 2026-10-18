# Audio/video out of sync on the external (dock) monitor

Reported by the owner on 2026-10-18 while the WD22TB4 dock monitor (Insignia NS-65DF710NA21, 1080p60 via
Aurora `.20` + upstream-matched `boot.bin`) was showing the desktop. Status: **open, not measured,
cause unknown**. Not known to be a documented upstream limitation.

## What is known about the audio path (checked live 2026-10-18)

- Default PipeWire sink is `audio_effect.j314-convolver` ("MacBook Pro J314 Speakers"): playback
  goes to the Mac's own speakers through the Asahi DSP chain, not to the monitor.
- The monitor's own speakers are **not** a kernel audio device: `appledrm.hdmi_audio=N` (described as
  "Enable unstable HDMI audio support"; upstream `.20` notes say HDMI audio changes only apply with
  `appledrm.hdmi_audio=1`, off by default on M1-M3) and only ALSA card `AppleJ314` exists. Upstream
  issue omacom/linux-aurora#48 (qualify HDMI/DP audio) is open.
- PipeWire also exposes network (AirPlay/RAOP) outputs via `~/.config/pipewire/pipewire.conf.d/50-raop.conf`,
  including one named `zTV-Living Room`. RAOP sinks add their own latency (log: `sess.latency.msec
  250.000000 should be an integer multiple of rtp.ptime 7.981859`).

## Candidate causes (none confirmed)

1. **Audio on the Mac speakers, video on the external monitor:** the external video path
   (DCP -> DP tunnel -> dock -> HDMI -> TV) adds display latency; many TVs add 50-150 ms more in
   non-game mode. Players sync to the audio device they know about, not to the remote display.
2. **Audio sent to an AirPlay/RAOP sink:** RAOP delay (hundreds of ms to ~2 s) is not compensated
   unless the player reads the sink's reported latency.
3. **Display refresh/modeset effects:** 1080p60 on the TV vs 120 Hz built-in; Gala compositing both.

## How to measure (no reboot)

1. Note which sink is the default: `wpctl status`.
2. Play a flash/beep sync test (e.g. a clip with a visible flash and an audible click) fullscreen on
   the external monitor, record the monitor and the speaker with a phone at 60+ fps (or 240 fps slow
   motion) and count frames between flash and click.
3. Repeat with audio on (a) Mac speakers, (b) the AirPlay sink, (c) after the TV's "game"/low-latency
   picture mode.
4. For a mitigation, a fixed offset can be applied per sink in PipeWire/WirePlumber
   (`node.latency`/`audio.position` offsets) once the delay is known.

## Next

Which sink was active when the lag was seen, and the TV's picture mode, decide between causes 1
and 2; HDMI audio (`appledrm.hdmi_audio=1`, reboot) is the cleaner long-term route but is unstable
upstream. Record results here.

## `appledrm.hdmi_audio` ("unstable HDMI audio") — investigation 2026-10-18

Source (omacom/linux-aurora `.20`, `drivers/gpu/drm/apple/dcp.c`): `module_param(hdmi_audio, bool, 0644)`,
"Enable unstable HDMI audio support". Only when set (and the kernel has `CONFIG_DRM_APPLE_AUDIO`) does the
DCP driver start the AV endpoint (`avep_init`) and call `av_service_connect/disconnect` as displays plug,
power off (DPMS) and resume. Without it no display audio ALSA card exists (our live state: parameter `N`,
only card `AppleJ314`). Our installed UCM package `alsa-ucm-conf-asahi 8-3` has no `apple_dcp` profile.

Only upstream field report (omacom/linux-aurora#48, P3, "needs-retest"; J314S + Dell U2715H on the
**built-in HDMI port**, Aurora `.15`, `hdmi_audio=1`, plus the unmerged `apple_dcp` UCM profile from
AsahiLinux/alsa-ucm-conf-asahi#9 — without it the card offers only `off`/`pro-audio`):

| Test | Result |
|---|---|
| Playback / device selection | clean |
| Monitor plugged into a running session | no HDMI sink until WirePlumber is restarted |
| First playback after boot with monitor attached | sink exists, PCM `RUNNING`, but `hw_ptr` stuck at 0 and the client hangs until WirePlumber restart (kernel started the audio service twice, 150 ms apart) |
| Unplug/replug | sink returns, clean |
| DPMS during playback | `dcp_poweroff` -> `av_service_disconnect`, sink disappears, audio falls back to the laptop speakers while the screen is off, returns afterwards |
| s2idle then playback | clean |
| **Thunderbolt/USB-C display audio** | **not tested** |

Consequences for us: our external monitor is on the **dock (DP-over-USB4 via `dcpext0`)**, which is the
untested case, and the TV's idle blanking would move audio to the Mac speakers. Needs: reboot with
`appledrm.hdmi_audio=1` on the Aurora `.20` entry, the `apple_dcp` UCM profile, then retest playback,
hotplug, DPMS and suspend on the dock monitor. A/V sync (above) should be re-measured on that sink, since the DCP
audio path has its own latency. Not enabled today (no reboot, and upstream rates it unstable).

## Sync-test page and the "add a slight audio delay" mitigation (2026-10-18)

[`mseries/tools/av-sync-test.html`](tools/av-sync-test.html) is a self-contained page (no network): a
full-screen flash once a second with a 1 kHz click, and a slider (also left/right arrow keys) that
delays the click by 0-600 ms. Open it in a browser **on the external monitor**, press Start, play the
click through the speakers normally used, and raise the slider until flash and click land together;
the number is the delay the audio path needs relative to the dock monitor (it includes the browser's own
output latency, shown on the page). Result is remembered in the page's local storage.

Applying it for real (only after the number is known): a PipeWire filter-chain `delay` node placed in front
of the speaker sink, enabled only while the external monitor is attached so the built-in panel stays in sync.
That restarts the user audio graph, so it is not done blind. Owner measurement: _pending_.
