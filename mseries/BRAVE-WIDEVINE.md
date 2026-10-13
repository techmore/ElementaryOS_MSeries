# Brave DRM video (Widevine) on the M-series port

Rented and purchased YouTube movies (and Netflix, Apple TV+, Spotify) are DRM-protected. They need the Widevine module.
Ordinary YouTube does not, and plays without it.

## Symptoms and causes found (2026-10-13)

| Symptom | Cause |
|---|---|
| Movie never starts, spinner forever | No Widevine module: Brave on arm64 Linux only fetches it after you opt in, and the profile's `WidevineCdm/` was empty |
| Still spinning after dropping in a ChromeOS-image library | glibc 2.43 refuses it: `DT_RELR without GLIBC_ABI_DT_RELR dependency` (journal: `content_main_runner_impl.cc`, `cdm_module.cc`). It needed Asahi's `widevine_fixup.py` |
| Playback works but is SD/720p, no HD | Software-level (L3) Widevine. Services cap L3; HD/4K needs L1 (hardware-protected video path), which this hardware and port do not have |
| Playback is heavy on the CPU | No hardware video decode on Asahi yet, so frames are decoded in software |

## Fix

Easiest: `brave://settings/extensions` -> turn on **Widevine**, restart Brave. Brave then downloads Google's arm64 build
by itself (`brave://components` shows "Widevine Content Decryption Module").

Scripted: with Brave fully quit,

```bash
bash mseries/install-brave-widevine.sh
```

It downloads Google's Linux arm64 component (pinned size and SHA-512), checks it loads, registers it in the profile and
sets `brave.widevine_opted_in`. `--uninstall` reverses it. Nothing is patched.

Check the log if it spins: `journalctl --since -10min | grep -iE 'cdm|widevine'`.

## Limits that are not bugs

- **L3 only.** Expect SD/720p on YouTube movies and similar. Nothing in Brave or this repo changes that.
- **Hardware decode** is not available on Asahi for the Apple video engine. The Omarchy M4 work documents hardware H.264/VP9
  decode on its own stack; that does not install Widevine and is not part of this port.
- Netflix may additionally want a ChromeOS user-agent string (Asahi widevine-installer notes).

## What Omarchy does

Omarchy on Asahi installs the `widevine` package from the asahi-alarm repo (built from a ChromeOS image and patched with
Asahi's fixup) and symlinks `/opt/WidevineCdm/chromium` into `/opt/brave-bin/WidevineCdm`. The Omarchy M4 reference tree
uses the same Google component as this script (`tools/setup-brave-widevine.py`). Same L3 ceiling either way.

## Sources

- Brave: <https://support.brave.app/hc/en-us/articles/23881756488717> (Widevine on Linux)
- Pinned component: <https://bugzilla.mozilla.org/show_bug.cgi?id=1612995#c17>
- Asahi fixup: <https://github.com/AsahiLinux/widevine-installer>
