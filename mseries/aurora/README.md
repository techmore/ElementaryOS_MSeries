# Aurora 20 kernel port for elementary

This opt-in lane follows **omacom/linux-aurora release
`aurora-2026.10.17.20`**, kernel source
`c46d7dcdb8712ea9aeb0ce47b439ffae76371e55`. It brings the upstream display
fabric, USB4/Thunderbolt display routing, SEP/Touch ID, GPU and other Apple
drivers into this project's kernel packaging. The published kernel binaries,
modules and device trees are preserved unchanged. This is a packaging and
boot-integration port, not a rebuild of the kernel or a merge of kernel files
into the OS image repository.

`release.json` records the public source revisions, exact artifacts and hashes.
The release's Arch installer is **not** run: it assumes pacman, Omarchy and its
boot lifecycle. No Omarchy/Hyprland desktop or M3-specific Mesa package is
installed by this port. The current Fairydust and older Aurora lanes remain.

## Build the Debian payload

Requirements: Python 3.12+, `zstd`, `fdtget` (device-tree-compiler). This works
on macOS or Linux and does not need root or a kernel compiler.

```sh
python3 mseries/aurora/package-release.py \
  --cache /absolute/work/aurora-cache --output /absolute/work/aurora-packages
```

The tool verifies the kernel, original build recipe and corresponding source
against fixed hashes, checks J314S SEP/sensor/display wiring and module
dependencies, then creates
`linux-image-elementary-aurora20_7.1.12+aurora.20261017.20-1_arm64.deb`.
The upstream binary, build recipe, source archive, licenses, checksums and a
provenance receipt accompany it. `--offline` requires all inputs in the cache.
Keep the corresponding source and recipe with any distributed binary.

The .deb contains `/usr/lib/modules/7.1.12-2-20261017.20-sep-ARCH`, its DTBs and
the upstream phram blacklist. It has no maintainer scripts, `/boot` payload or
bootloader hooks. Installing it alone does not create a boot entry. This
avoids invoking the factory image's existing generic/Fairydust boot hooks.

[Aurora kernel port CI](https://github.com/techmore/ElementaryOS_MSeries/actions/workflows/aurora-kernel.yml)
builds and inspects the payload and retains its source and recipe together.
The factory ISO workflow still uses its existing kernel profiles; this port
does not qualify a new factory image.

## Stage the matched boot chain, without deploying

J314S needs the **matching device tree in m1n1's `boot.bin`**, not just the DTB
under `/usr/lib/modules`. This is what earlier kernel-only trials missed:
the older tree lacked the full sensor/display wiring. Stage from an explicit
copy of the current boot image:

```sh
python3 mseries/aurora/stage-boot.py --cache /absolute/work/aurora-cache \
  --existing-boot /absolute/work/current-boot.bin \
  --output /absolute/work/aurora20-boot-candidate
```

This verifies and uses `m1n1-aurora 1.6.1.aurora17-5` (source `d05ba17d…`)
and the release's `t6000-j314s.dtb`. It replaces the m1n1 prefix and **only**
the J314S tree in the copy; other board DTBs and the original gzip U-Boot/config
tail are byte-identical. The output includes a byte-exact rollback image and
a hash/component report. Nothing is mounted, installed or armed. The m1n1
package and its corresponding source are cached with fixed hashes.

**The installed `boot.bin` is shared by all kernel entries.** Retaining a
Fairydust/.19 GRUB entry does not prove it will work with Aurora's newer DTB.
Before deployment, review fallback-kernel compatibility, retain an accessible
copy of the original ESP payload, and account for the retained E4 experiment
and its one-shot boot selection. This port deliberately provides a staging
tool rather than an automatic global boot-image replacement.

## Install a non-default kernel candidate

`../aurora-sep/install-aurora-sep.sh` is the maintained entrypoint. It defaults
to a read-only preview; it downloads nothing in dry-run mode. Configure the
correct `ROOT_UUID`, `CRYPTDEVICE`, `ESP_UUID` and `ROOTFLAGS` in the existing
`/etc/default/aurora-sep-cmdline` or environment for the target installation.
The inherited defaults describe the owner's btrfs elementary subvolume;
they are not a generic disk layout.

```sh
bash mseries/aurora-sep/install-aurora-sep.sh
# After reviewing the preview on the target Linux installation:
sudo bash mseries/aurora-sep/install-aurora-sep.sh --apply
```

The new versioned entry is **`elementary-aurora20`**. The installer replaces
only its own managed block on repeat runs, preserves the legacy
`elementary-aurora-sep` (.19) block, and never changes the default or
`next_entry`. It supports both the transformed desktop's mkinitcpio and native
elementary's initramfs-tools; `INITRAMFS_TOOL=mkinitcpio` or `initramfs-tools`
selects one explicitly. It copies the system's known-good initramfs config,
adds the display/SEP/Thunderbolt modules and checks the resulting archive for
`appledrm`, `drm_dma_helper`, `dcp-fabric-core`, `apple-sep` and `thunderbolt`.
For encrypted installations the existing config must retain its unlock hooks
and firmware; module presence alone does not validate root unlock.

Existing .19 SEP/libfprint userspace is unchanged upstream and can be reused.
Only pass `--with-touchid` when deliberately installing those shared userspace
files on a new system. The opt-in retains the old libfprint backup behavior;
it excludes upstream's SDDM configuration and does not edit PAM. Enrollment
requires a physical finger and remains a separate action.

Removal previews by default; `--uninstall --apply` removes only the .20 kernel
lane. Debian-owned modules are retained for removal with apt. Shared Touch ID
userspace is retained unless `--with-touchid` is explicitly added. It never
restores or changes the shared `boot.bin`; use the staged rollback copy for a
separately deployed boot-chain experiment.

## Hardware qualification still required

Upstream `.20` has M1 Air + CalDigit TS4 display evidence using an identical
source tree and direct M3 Pro package testing. Earlier J314S reports show a
working Thunderbolt LG UltraFine 5K display. **None is this J314S + WD22TB4 HDMI
path.** The `.20` release explicitly lists M1 Pro/Max and Touch ID among its
untested hardware cases. Existing tests here are offline package/DT/boot-copy
checks, not an elementary hardware boot.

Keep experimental `user4k` off (do not add `user4k=on`). Its shared MM paths
remain compiled in even while the feature is off. The Neo has software-rendered
graphics in `.20` pending a matching Mesa build; M1/M2/M3 support does not imply
every model/feature is qualified. M4/M5/M6 are not advertised as supported by
this port. The recipe lacks QEMU PL011 serial-console options, so the existing
Fairydust serial smoke-test gate is not applicable without a new source build.

Next hardware batch: review/deploy the matched boot payload and kernel together,
boot only the explicit candidate, then verify root unlock and the internal
desktop, dock USB/Ethernet, DCP lane count/link rate, EDID/modes, a picture on
the dock's HDMI, and SEP/fingerprint enrollment/verification. Record the actual
highest gate in `../fairydust/usb4/STATE-OF-PLAY.md`. Suspend/resume, audio,
camera, GPU workloads and recovery boot need their own results before promotion.

Upstream evidence:
[release 20](https://github.com/omacom/linux-aurora/releases/tag/aurora-2026.10.17.20),
[J314S Thunderbolt display](https://github.com/omacom/linux-aurora/issues/38#issuecomment-6117263883),
[M2 Max dock report](https://github.com/omacom/linux-aurora/issues/132).
