# First successful OS 9 arm64 image build

Confirmed 2026-10-13. [GitHub run 38396499561](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38396499561)
succeeded at source commit `401dad7919a004b3ed0cc624cdab1d48d6cd5919`.
The build job ran from 08:19:58 to 08:45:47 America/New_York (25m 49s).

## Produced

- ISO: `elementaryos-9.0-daily-arm64.20261013122120.iso`.
- xorriso reports 3,456,159 sectors (7,078,213,632 bytes, about 6.59 GiB).
- Installer artifact: `os9-mseries-arm64-38396499561`, ID `11814507912`.
  The archive includes the ISO and `INSTALLER-SHA256SUMS`.
- Artifact archive SHA-256 reported by GitHub:
  `e5dbcb5cee097c3f663b7b9f592bf68f890c272bb5074b9dcfb651125aefe70e`.
  This is the **archive digest**, not the ISO checksum.
- Installer artifact expires 2026-10-20; records expire 2026-10-27.
  Download through the run's Artifacts section; GitHub may require sign-in.
- Installed image kernel from package logs: `7.0.0-38-generic`
  (`linux-image-generic` version `7.0.0-38.38`).

Build records were downloaded and inspected. The 7 GB installer archive was
not downloaded locally, so no independent ISO checksum verification or
filesystem inspection is claimed. Future builds copy the small checksum
manifest and installer size into the separate retained build records too.

## What passed

Image assembly, ISO creation, compression, checksum generation, artifact
upload, and the separate arm64 config/regression validation all succeeded.
The logs confirm the Apple hardware overlay was consumed and HID drivers
were selected for the initramfs.

## What remains

1. Independently download and verify the ISO checksum before use.
2. Inspect installer contents and perform an arm64 VM smoke boot where
   available. A VM boot cannot qualify Apple-specific drivers or boot firmware.
3. Qualify an Asahi kernel/m1n1/U-Boot path on test hardware. The generic
   Ubuntu kernel is not equivalent to this Mac's working Fairydust kernel.
4. Package the safe speaker DSP chain and matching PipeWire LV2 plugin.
5. Hardware boot and the complete POST-BOOT-CHECKS.md checklist remain pending.
   No stable installer release or working Mac factory-image boot is claimed.

## Residual log findings

The build contains nonfatal package/chroot diagnostics (NetworkManager could
not connect to its daemon; masked service preset failures; cryptsetup could
not determine the build root). These did not fail assembly. Separately,
`io.elementary.tasks` package setup attempted to reference a missing stable
Flatpak and remove a missing autostart file; investigate package postinst
behavior and first-login task functionality. Successful assembly alone does
not prove that those application behaviors work.
