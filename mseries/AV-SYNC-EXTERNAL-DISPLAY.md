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
