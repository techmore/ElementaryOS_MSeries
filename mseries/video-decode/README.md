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

## `brave-youtube` — YouTube-only Brave, contained by bubblewrap (EXPERIMENTAL, 2026-10-18)

[`brave-youtube`](brave-youtube) starts Brave with its own profile (`~/.config/brave-youtube`), in app mode on
YouTube, inside `bwrap`. Chromium's own sandbox is off (`--no-sandbox`), so the container is the wall:
only `/dev/dri`, `/dev/media*`, `/dev/video*`, the Wayland/PipeWire/Pulse sockets, read-only `/usr` `/etc`
`/opt` `/sys`, an empty tmpfs `$HOME` and that one profile directory are visible. Your normal Brave and
profile are untouched. The enhancement payload installs a system-wide menu entry with a YouTube logo;
its application ID and `StartupWMClass` also identify the running window in the dock.

Verified (`brave-youtube --probe`, 2026-10-18): the container starts under this system's AppArmor rules;
`$HOME` inside holds only `.config`; `~/.ssh` and other profiles are not visible; `vainfo` inside lists
H.264 High, HEVC Main10 and VP9 Profile0 with driver `v4l2-request`.

**NOT verified: that Brave actually uses hardware decode.** `brave-youtube --test` (headless, local 1080p VP9
clip in the profile's `test/` dir) produced no result page, and Chromium logged
`vaapi_wrapper.cc: GetHandle(): Either VADisplayStateSingleton::PreSandboxInitialization() hasn't been called
or that method failed to find a suitable render node`. With the sandbox off the VA-API handle may never be
initialised, so this approach may need a different flag set (or the render node selection patched upstream)
before it helps. Headless mode also does not exercise the real GPU path. A visible-window test on YouTube
(with `chrome://media-internals` / `chrome://gpu`) is the next step and needs the owner's screen.

### Passkeys in `brave-youtube` (2026-10-18)
Chromium shows the "use your phone via QR code" option only when it can talk to Bluetooth through BlueZ
(the phone proves it is nearby by BLE). Inside the container there was no system bus, so only the
"physical security key" prompt appeared. Fix: the launcher now runs `xdg-dbus-proxy --filter --talk=org.bluez`
and bind-mounts that filtered socket as the container's system bus, so the browser can reach BlueZ and
nothing else (verified: `busctl --system tree org.bluez` works inside, other bus names are not listed).
Passkeys created on an iPhone live in iCloud Keychain and are used through that QR flow, so signing in
this way needs the phone nearby with Bluetooth on. Browser-stored passwords/passkeys are not synced from iCloud;
see `../BUG-FIX-ROADMAP.md` (iCloud passwords evaluation) for the unofficial options.

**Owner-verified 2026-10-18:** after the BlueZ proxy fix, the passkey QR-code flow worked in `brave-youtube` and
the owner signed in (iPhone approving the sign-in). Hardware decode inside the container is still unconfirmed.

## Hardware decode confirmed in `brave-youtube`; first playback report — 2026-10-18 05:51

- **Brave uses the Apple Video Decoder.** While the owner played YouTube in the contained instance, the
  browser's `--type=gpu-process` held `/dev/video0` and `/dev/media0` open (the AVD v4l2-request nodes) plus
  `/dev/dri` fds; the other Brave processes held none. This is the first direct evidence that browser
  hardware decode works with the sandbox off inside the container.
- **VP9 decode is correct on a test clip.** `ffmpeg -hwaccel vaapi` (libva v4l2-request, "decoding vp9 via
  /dev/video0 [avd]") vs software on a 1080p30 VP9 clip: 120/120 frames bit-identical. (Synthetic `testsrc2`
  pattern, 4 s, so it proves the decode path, not every real-world stream.)
- **Owner report:** at first a stutter that "comes and goes", brief odd artifacts, a feeling of buffering;
  a few minutes later "smooth, really good" and the picture "looks better". No kernel messages about
  AVD/DCP/vblank/allocation failures in the window (`journalctl -k`, 05:46-05:52). Free high-order memory was
  low (buddyinfo: order-10 count 2, order-11 count 1, 747 MB MemFree with 17 GB available as cache); the AVD
  needs a large contiguous allocation per job (see `90-mseries-avd.conf`), so early stutter after a long
  uptime or while memory is fragmented is a plausible cause, **not proven**.
- System power while playing 1080p YouTube with the dock TV lit: median 25.1 W over 10 s (single sample, many
  other things running; not comparable to the idle numbers in `../POWER-ROADMAP.md`).
- Still to do: a software-decode control (normal Brave, same video) for CPU/power and smoothness, and look at
  `brave://media-internals`/`chrome://gpu` in the contained window to confirm the exact decoder per stream.

## DRM movies in `brave-youtube` — 2026-10-18
YouTube Movies (for example *Edge of Tomorrow*) said "your browser can't play this video" because the contained
profile had no Widevine. The launcher now copies the normal profile's Widevine CDM into its profile and opts in,
before Brave starts (skipped while the window is open). See `../BRAVE-WIDEVINE.md`. Not yet verified with a
movie playing in the container.

## YouTube launcher icon — 2026-10-18

The default enhancement payload installs these files for every user:

- `/usr/share/applications/mseries-brave-youtube.desktop`
- `/usr/share/icons/hicolor/scalable/apps/mseries-youtube.svg`
- `/usr/share/elementary-mac/mseries/video-decode/brave-youtube`

The SVG is a red YouTube play-button logo drawn here, with no external artwork
dependency. The launcher uses the installed executable rather than an owner's
checkout. `Icon=mseries-youtube` and
`StartupWMClass=brave-www.youtube.com__-Default` let the menu, pinned dock item and
running YouTube window share the same icon. Each user still gets a separate profile.
The Widevine helper is included alongside the launcher in the immutable payload.

`enhance.sh --only payload` stages the files during transformed installs and the
Apple Silicon factory overlay build. Both ARM64 liveiso and sysupdate consumers
install bubblewrap, xdg-dbus-proxy and the desktop/icon cache tools. Their final
post-install hooks validate the desktop entry and refresh application and icon
caches after merging the overlay. The transform's existing first-boot Brave module
also installs the container dependencies. Factory images now include the pinned
Brave runtime described below. Fresh installed ARM64 VM playback and dock identity now pass; see the
[qualification receipt](receipts/factory-2026-10-18/README.md). Physical Apple
hardware qualification remains separate.

For an existing shortcut, keep its working `Exec` path and change only its `Icon`
line to `Icon=mseries-youtube`. Install the icon from the repository root:

```sh
install -Dm644 mseries/video-decode/mseries-youtube.svg \
  "$HOME/.local/share/icons/hicolor/scalable/apps/mseries-youtube.svg"
gtk-update-icon-cache --force --ignore-theme-index "$HOME/.local/share/icons/hicolor"
update-desktop-database "$HOME/.local/share/applications"
```

The dock caches application icons; restart it or sign in again after changing an
existing shortcut. Playback and decode settings are unchanged.

## Factory Brave runtime — 2026-10-18

Both ARM64 factory images include Brave 1.97.59 (Chromium 155.0.8059.85) before
first boot. `mkosi.images/apple-silicon/build-brave` stages the official ARM64
[release package](https://github.com/brave/brave-browser/releases/tag/v1.97.59),
checking SHA256 `5efdd2356671eade31d3d0a59b2338931147f65f0db44863b6c23adea74ba1d2`
and its package/version/architecture metadata. The runtime is relocated to
`/usr/lib/mseries-brave` so sysupdate's `/usr` artifact includes it. No apt repo,
first-login browser download, vendor maintainer script, or `/opt` payload is
needed for the factory YouTube launcher. This is the contained launcher's private
runtime, not an apt-managed general browser installation.

The launcher prefers that runtime and retains the native `/opt`/apt fallback on
transformed desktops. Its separate per-user profile, container flags and dock
identity stay the same. Widevine provisioning remains the separate existing
per-profile helper; this browser package does not remove DRM limits or qualify
hardware decode on an untested factory kernel.

`brave-factory.json` records the exact version, official URL, SHA256 and Ubuntu
runtime dependencies. All three overlay/consumer configs declare those libraries.
The build retains the full vendor resources and LICENSE, writes provenance and
per-file hashes to `/usr/share/doc/mseries-brave`, and keeps them through factory
pruning. Both final consumer hooks require the runtime verifier and reject missing
or changed resources, a non-ARM64 binary, or unresolved shared libraries.

Updates ship through rebuilt images: review the official release, update the pin
and SHA256, audit its dependency metadata against Ubuntu package names, and rerun:

```sh
python3 mseries/video-decode/test-brave-factory.py
python3 mseries/test-image-wiring.py
# Optional local package cache; still checked against the committed SHA256:
MSERIES_BRAVE_DEB=/path/to/brave-browser_1.97.59_arm64.deb \
  SRCDIR="$PWD" DESTDIR=/path/to/empty-stage \
  bash mkosi.images/apple-silicon/build-brave
```

Verified with the real pinned package: staging and post-finalize hashes, ELF,
licenses and host shared-library resolution; a local page rendered in an empty
profile under Xvfb. Ubuntu Resolute ARM64 container dependency installation and
binary version/library checks also passed. A headless DOM dump timed out in the
minimal container, so it is not counted as a rendering pass. The subsequent
[new ISO and fresh-install VM qualification](receipts/factory-2026-10-18/README.md)
passed factory packaging, dock identity and anonymous YouTube playback at 480p
and selected 1080p. It does not qualify physical Apple boot, hardware decode or DRM.
