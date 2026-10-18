# Omacom improvements audit and elementary implementation

Survey: October 17, 2026. Baseline: elementary main `f114d865`;
maintained packages `ffe5246c`. The [receipt](upstream-audits/omacom-2026-10-17.json)
inventories 69 public repositories and 1,482 branch heads. Source review is
targeted to hardware/power/desktop applicability, not a security review of all
branch implementations. The [import ledger](upstream-audits/imported-sources.json)
records source hashes; [provenance](power/UPSTREAM.md) retains the MIT license.

## Implemented ports

| Candidate | Elementary implementation | Qualification remaining |
| --- | --- | --- |
| `omarchy-mac-pkgs/feat/sleep-power-report` at `b5e10d3d` | `power/sleep_cost.py`, `power/power_report.py`, bounded system-sleep recorder, logind/notify-send user unit, Applications power-report launcher. Included by the diagnostics enhancement module in transforms and the factory layer. | Real suspend/resume, logind lock hints, notification timing, overnight battery measurements and image boot. |
| `port/498-bluetooth-resume-recovery` at `aa747a8c` | `hardware/bluetooth-resume-fix`, Apple/PCI/rfkill gates, suspend-cycle-specific timeout detection and bounded recovery. Shipped disabled; opt-in installer enables only future suspend events. Original race/failure fixtures ported. | Reproduce the matching timeout on this controller; healthy/radio-off and repeated-resume hardware regressions. |
| `touchid/fingerprint-readers` at `9b296ccb` | GUI distinguishes missing SEP, published-but-not-ready sensor, busy sensor, and fprintd-enumerated device. Fix first-refresh manager initialization, duplicate signal connections and the installer's duplicated source directory. | GUI appearance, real SEP readiness, enrollment/verify, password fallback. No additional activation service or PAM change. |
| `port/683-builtin-keyboard-keys` at `99fac5c5` | Optional hardware hwdb for built-in F4 screenshot and F5/F6 keyboard lighting, compiled in the selected root only. Unrelated boot-service dependency change excluded. | Owner's preferred key layout and actual input events after reboot/replug. Existing Gala bindings stay the default. |
| Current Mac-image acceptance harness | Existing `verify-m1n1-esp.py` and daily image pipeline already use mtools. Added a real GPT/FAT fixture that tests matching, mismatched and empty payloads without mounting. | Full image build and hardware boot remain separate. |

## Audit dispositions

| Reference | Disposition and reason |
| --- | --- |
| `omarchy/thunderbolt-event-driven` (`6d9ef180`) and `thunderbolt-idle-recheck` | No Omarchy Bolt authorization daemon/watch loop is installed by this repo. No polling workload exists here to replace. Do not introduce a new authorization stack to optimize it. These branches do not fix DCP tunnel link training. Existing display-profile hotplug handling uses desktop events. |
| Maintained package main `222f7a8` → `ffe5246` | Four commits change microphone tests and acceptance tooling only. No new production hardware behavior to import. |
| `fix/dtb-overlays-follow-config` | Tip is already an ancestor of current package main. No separate import. Preserve the existing elementary GRUB/initramfs contracts. |
| Audio platform hints | Pinned elementary sound source `8b7991c9` constructs devices from card ports in `Services/PulseAudioManager.vala` and omits monitor sources; it does not render Quickshell's general node/app list. The Omarchy hidden-node JSON is not a compatible drop-in. Do not change DSP routes or hide a port based only on a node-name match. Validate the actual sound UI before a separate patch. The deliberately omitted stereo-mic mapper remains unnecessary without a reproduced silent-mic case. |
| Backlight preference / DDC guard | `brightness/shell-bridge.py` already selects active eDP through Mutter. No ddcutil/SMBus-probing path was found in this repo. Display profiles use compositor events and monitor identity. No additional generic backlight selector or DDC poller is installed. |
| Notch panel data | Wingpanel lacks the upstream bar's cutout contract; retain the existing cropped-panel policy. Importing JSON would not make Wingpanel notch-aware. |
| DSP no-suspend (`f379cce3`) | Continuous graph processing is a click/stability workaround with a documented CPU cost, not a power improvement. Excluded; preserve the running protected audio stack and its existing watchdog. |
| m1n1 / video bridge | `integration/aurora` equals pinned `d05ba17d`. `avd-fixes` is one merge commit beyond `c653eaa` with no file differences. No payload update required. |
| Mesa | `main` vs `26.2` is a large divergent development history; API comparison hit the 300-file cap. No targeted M1 Pro win was established. Keep system Mesa and the separate local-AI ICD arrangement. |
| Aurora kernel work | Already covered by the [kernel branch audit](aurora/UPSTREAM-BRANCH-AUDIT-2026-10-17.md) and separate source-candidate PR #79. This userspace batch neither duplicates nor merges that work. |
| Native macOS installer / T2 firmware / archived Omakub / Hyprland plugins | Installer plan was declined; firmware reference is T2-specific; archived Ubuntu/GNOME and compositor-specific packages are not elementary Apple Silicon ports. Excluded. |

## Use and removal

Install the diagnostics from an installed elementary desktop:

```sh
bash mseries/install-hardware-support.sh
mseries-power-report --sample 10
```

The installer stages files and user enable links. It does not start/restart
services, rebind a controller or reload devices. Log out/in for the user service;
the system sleep hook applies on a subsequent suspend. Manual installation
installs missing runtime packages; offline `--root /absolute/root` never uses apt.
The factory and transform enhancement module uses that offline path. Existing
service masks and enable-link replacements take priority.

After confirming the matching Bluetooth timeout, explicitly opt in:

```sh
bash mseries/install-hardware-support.sh --enable-bluetooth
```

This stages the suspend enable link; a live systemd manager needs
`sudo systemctl daemon-reload` before the next suspend. It does not recover
the current connection during installation. To opt out, disable
`mseries-bluetooth-resume-fix.service`. Package restaging does not enable it.

Optional built-in-keyboard remaps:

```sh
bash mseries/install-hardware-support.sh --keyboard-keys
```

No udev trigger is issued. Reboot/replug is needed to apply the compiled hwdb;
no F-key changes are part of the normal diagnostics installation.

`--uninstall` removes these installed support files and enable links, keeping
historical energy records. Stop a running user unit and opt-in Bluetooth unit
before uninstalling; log out/in afterwards. After removing the optional hwdb,
run `sudo systemd-hwdb update` and reboot to restore the previous keymap.

## Measurement limits

Records retain only 200 intervals in `/var/lib/mseries/sleep-cost.log` and
reject missing/unknown charging state, changed boot IDs, invalid clock/energy
values and attempts with no observed suspended-clock interval. The energy
delta covers the entire pre/post interval, including transitions; it does not
establish low-power residency or detect an adapter connected only between
endpoint readings. Charging intervals are not discharge benchmarks.
Notifications wait for a known active, unlocked logind session and retry failed
delivery; runtime state prevents duplicate delivery after a watcher restart.
CPU activity is reported as activity, not per-process watts.

Offline regression fixtures validate algorithms, gating and packaging. The
real-FAT test requires fdisk/mtools and is mandatory in the dedicated CI job;
it skips on hosts without those tools. No live kernel, boot, audio, display,
Bluetooth or keyboard change was performed while preparing this port.
