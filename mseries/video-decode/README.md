# Video decode and YouTube quality on the M1 Pro (checked 2026-10-18)

- **Hardware decode exists:** `vainfo` (driver `v4l2-request`, omarchy-m1-video 1.3.r11) lists H.264
  (Baseline/Main/High), HEVC Main and Main10, and VP9 Profile 0. No AV1 hardware decode on this M1 Pro.
- **Brave 155.1.97.59 does not use it.** Upstream (omacom/linux-aurora#44, "Browser AVD integration") says
  browser hardware decode only works with the media (RDD) sandbox disabled, because the sandbox denies
  `/dev/media*` to libva-v4l2-request; normal sandboxed playback falls back to software, and disabling the
  sandbox globally "is not the delivered solution". So YouTube in Brave is software-decoded (VP9/AV1,
  including Premium's enhanced-bitrate 1080p). Software decode is correct in quality; it costs CPU/power.
- **No browser flags are set** (`~/.config/brave-flags.conf` absent; desktop entry has none).
- **DRM:** Widevine here is L3 (software): Netflix-style DRM video is capped at SD/720p. Ordinary YouTube
  (including Premium bitrate) is not DRM and can be up to 4K. See `../BRAVE-WIDEVINE.md`.
- **Maximum-quality route today: mpv + yt-dlp** (both installed): `mpv-youtube.conf` here selects
  VP9/H.264 so the AVD does the decoding, up to 2160p.
- **On the dock TV** the output is 1080p60 only (TV EDID advertises 4K30 at most and 4K30 stays dark), so
  1080p is upscaled by the TV regardless of source bitrate; see `../AV-SYNC-EXTERNAL-DISPLAY.md`.
- Options not taken: running Brave with the media sandbox disabled to get VA-API (security trade-off,
  untested here); the Xwayland-native-scaling setting for X11 apps (display setting, owner approval).
