# Brave DRM video (Widevine) on the M-series port

Some YouTube Movies titles, including free/ad-supported movies, and services
such as Netflix, Apple TV+ and Spotify use DRM and need Widevine. Ordinary
YouTube videos do not. If only selected movies fail with a spinner or DRM
playback error, enable Widevine in Brave; this repo's post-install flow now
installs the pinned ARM64 component and opts it in by default.

## Symptoms and causes found (2026-10-13)

| Symptom | Cause |
|---|---|
| Movie never starts, spinner forever | No Widevine module: Brave on arm64 Linux only fetches it after you opt in, and the profile's `WidevineCdm/` was empty |
| Still spinning after dropping in a ChromeOS-image library | glibc 2.43 refuses it: `DT_RELR without GLIBC_ABI_DT_RELR dependency` (journal: `content_main_runner_impl.cc`, `cdm_module.cc`). It needed Asahi's `widevine_fixup.py` |
| Playback works but is SD/720p, no HD | Software-level (L3) Widevine. Services cap L3; HD/4K needs L1 (hardware-protected video path), which this hardware and port do not have |
| Playback is heavy on the CPU | No hardware video decode on Asahi yet, so frames are decoded in software |

## Fix

To apply on an existing installation, fully quit Brave and run
`bash mseries/post-install.sh --only widevine`. The profile must have been
created by launching Brave once. You can also use
`brave://settings/extensions` -> turn on **Widevine**, then restart Brave;
`brave://components` should show "Widevine Content Decryption Module".

Scripted: with Brave fully quit,

```bash
bash mseries/install-brave-widevine.sh
```

It downloads Google's Linux arm64 component (pinned size and SHA-512), checks it loads, registers it in the profile and
sets `brave.widevine_opted_in`. `--uninstall` reverses it. Nothing is patched.

Check the log if it spins: `journalctl --since -10min | grep -iE 'cdm|widevine'`.

## The contained YouTube window (`video-decode/brave-youtube`)

It has its own profile (`~/.config/brave-youtube`), so the steps above do not reach it. Since 2026-10-18 the
launcher sets up Widevine in that profile each time it starts and finds it missing: it copies the normal profile's
CDM, or falls back to this installer with `BRAVE_PROFILE_DIR=~/.config/brave-youtube`. Close the YouTube window
and reopen it for the change to apply.

## Limits that are not bugs

- **L3 only.** Expect SD/720p on YouTube movies and similar. Nothing in Brave or this repo changes that.
- Widevine and hardware video decode are separate. If DRM playback still shows
  a green or blank picture while audio continues, the Omarchy Mac reports a
  Brave/AVD hardware-decode issue; test software decoding in `brave://flags`
  by disabling **Hardware-accelerated video decode**, then relaunch Brave. The
  modern command-line workaround documented upstream is
  `--disable-features=AcceleratedVideoDecoder`; it trades browser hardware
  decoding for software decoding and higher CPU use. See
  [Omarchy Mac issue #388](https://github.com/omacom/omarchy-mac/issues/388)
  and [workaround PR #418](https://github.com/omacom/omarchy-mac/pull/418).
- Netflix may additionally want a ChromeOS user-agent string (Asahi widevine-installer notes).

## What Omarchy does

Omarchy on Asahi installs the `widevine` package from the asahi-alarm repo (built from a ChromeOS image and patched with
Asahi's fixup) and symlinks `/opt/WidevineCdm/chromium` into `/opt/brave-bin/WidevineCdm`. The Omarchy M4 reference tree
uses the same Google component as this script (`tools/setup-brave-widevine.py`). Same L3 ceiling either way.

## Sources

- Brave: <https://support.brave.app/hc/en-us/articles/23881756488717> (Widevine on Linux)
- Pinned component: <https://bugzilla.mozilla.org/show_bug.cgi?id=1612995#c17>
- Asahi fixup: <https://github.com/AsahiLinux/widevine-installer>
