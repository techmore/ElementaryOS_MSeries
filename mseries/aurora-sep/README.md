# Aurora SEP kernel lane (Touch ID)

Optional second kernel for M-series Macs that enables Touch ID on Linux. It
installs the community **Aurora** kernel (`omacom/linux-aurora`) beside the
stock kernel. It is not the default: one extra GRUB entry, marked for clean
removal.

## Current kernel lane — Aurora 20

The maintained kernel candidate is now release `aurora-2026.10.17.20`,
source `c46d7dcdb8712ea9aeb0ce47b439ffae76371e55`, entry **`elementary-aurora20`**.
Use [the Aurora port guide](../aurora/README.md) for the pinned Debian payload,
matched m1n1/J314S device-tree staging, installer options and qualification gaps.
The existing `.19` entry is retained. Shared Touch ID userspace is installed
only with `--with-touchid`; its upstream versions have not changed.

This is source/package integration, not a new hardware qualification. The
shared `boot.bin` must be reviewed separately before a new kernel test.

## Why this exists

Asahi Linux does not support Touch ID (listed TBA on every M-series page). The
fingerprint sensor is factory-paired to the Secure Enclave (SEP); matching
happens inside the enclave, so a normal fingerprint reader driver cannot work.
The Aurora kernel carries `apple-sep`, a driver that talks to the SEP directly,
plus a patched `libfprint` so `fprintd` sees the sensor as a normal device.

Upstream is community work moving quickly (October 2026): the Touch ID driver
series `aurora-silicon/linux#69` ("Touch ID after reboot on M2 Max, M1 Pro and
M1") merged 2026-10-08, and releases ship from `omacom/linux-aurora`.

## What it can and cannot do

- **Can:** unlock `sudo`, polkit prompts and the login greeter through PAM
  (`pam_fprintd`, already in the archive). `aurora-touchid-setup` enrols a
  finger, verifies it, then writes the PAM lines. Password always still works.
- **Cannot:** unlock the LUKS root at boot. The SEP is asleep that early and
  Apple Silicon has no TPM. The disk passphrase is unchanged.
- **Lock screen:** untested as of 2026-10-17. Gala's lock screen does not link
  PAM directly; the PAM service it uses is still being determined. `sudo` and
  polkit are the confirmed surfaces.
- **Suspend/resume:** community reports partial; not verified here.

## Install

```sh
mseries/aurora-sep/install-aurora-sep.sh            # dry run, changes nothing
sudo mseries/aurora-sep/install-aurora-sep.sh --apply
# Boot-chain staging/review is separate; see ../aurora/README.md before booting.
```

Detach the Thunderbolt dock for the first boot: the community j314s reports
recorded boot retries with a display attached (two of four boots recovered).

## Verify after boot

```sh
uname -r                                        # 7.1.12-2-20261017.20-sep-ARCH
systemctl status apple-sep.path apple-sep.service
ls -la /dev/sep-bio                             # enclave device
fprintd-list "$USER"                            # fprintd sees the SEP
sudo aurora-touchid-setup                       # enrol + wire PAM
fprintd-verify "$USER"                          # a good finger unlocks
```

## Remove

```sh
sudo mseries/aurora-sep/install-aurora-sep.sh --uninstall --apply
```

Removes the .20 GRUB entry, image, initramfs and manually installed modules.
Debian-managed modules and existing shared Touch ID userspace are retained.
Add `--with-touchid` only to explicitly remove/restore the shared userspace. Enrolled
fingerprints stay in `/var/lib/fprintd`; clear with `fprintd-delete "$USER"`.

## Pins (record per AGENTS.md)

| What | Pin |
|---|---|
| Release | `omacom/linux-aurora` `aurora-2026.10.17.20` |
| Kernel | `7.1.12-2-20261017.20-sep-ARCH`, commit `c46d7dcdb8712ea9aeb0ce47b439ffae76371e55` |
| Driver series | `aurora-silicon/linux#69` (merged 2026-10-08), on `aurora-wip` |
| Userspace | `aurora-touchid-20261003-2`, `libfprint-1.94.100-1.1` |
| sha256 | kernel `49efa0ec…`, touchid `84243a96…`, libfprint `bc7d9762…` (full values in the installer) |

Licences: kernel GPL-2.0, m1n1/aurora components as upstream. No sponsor-only
content is imported.

## Files

- `install-aurora-sep.sh` — the kernel lane installer (dry-run by default)
- `install-touchid-gui.sh` — installs the settings app for the current user
- `mseries-touchid-settings` — the GTK3 settings app (enroll / verify / remove)
- `touchid_core.py` — pure logic behind the app (messages, PAM state, findings)
- `test_touchid_core.py` — 9 unit tests, no session needed
- `mseries-aurora-touchid-apply-pam` — root helper the app calls via pkexec
- `mseries-touchid-settings.desktop` — applications menu entry
- this README

## GUI enrollment

`aurora-touchid-setup` (terminal) enrolls one finger and wires PAM. The
settings app does the same without a terminal, the way GNOME's Users panel
does for USB readers:

```sh
bash mseries/aurora-sep/install-touchid-gui.sh
```

Then "Touch ID (M-series)" appears in the applications menu: sensor status
with plain-language findings, enrolled fingers with per-finger removal,
enroll and verify dialogs driven by fprintd's D-Bus signals, and a PAM
section that adds (or removes) `pam_fprintd` for sudo and polkit via pkexec.

Verified without a session: 9 unit tests and `py_compile`. Not yet exercised
against the real sensor (the kernel is not booted here yet) — the fprintd
D-Bus Device interface members should be re-checked against the live device
after the first boot.

## Related

- `mseries/fairydust/usb4/install-ci-kernel.sh` — the same side-by-side kernel
  pattern for the fairydust lane
- `mseries/BUG-FIX-ROADMAP.md` — Touch ID row and test order
- `mseries/local-ai/touchid-watch.py` — upstream signal watcher
