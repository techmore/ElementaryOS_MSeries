# Apple Silicon Wi-Fi firmware — design (v1: detect + report, copy ready)

## The problem

`brcmfmac` drivers for BCM4378/BCM4387 are upstream (since 6.3), but Apple
firmware blobs are proprietary and NOT in `linux-firmware`. Without them
there is no Wi-Fi at all — and without Wi-Fi there is no install-time
package fetch on a wireless-only MacBook. Asahi's answer: the installer
extracts firmware from the running macOS into a manifest on the EFI
partition, and the distro makes it available under `/lib/firmware` at boot
(see the `[v2] brcmfmac: Support Apple T2 and M1 platforms` cover notes).

This project must do the same, and must NEVER redistribute the blobs
(git history would carry them forever). So: a first-boot provisioning unit
that copies from installer-provided source locations, plus loud logging
when there is nothing to copy from.

## Files each chip needs (from brcmfmac `MODULE_FIRMWARE` names)

- BCM4378 (PCI `14e4:4425`, M1 family): `brcmfmac4378b1-pcie.bin`,
  `brcmfmac4378b1-pcie.clm_blob`, `brcmfmac4378b1-pcie.txcap_blob`, plus an
  NVRAM `.txt` (name varies by module/antenna — any
  `brcmfmac4378b1-pcie*.txt` counts as present).
- BCM4387 (PCI `14e4:4433`, M1 Pro/Max and later): `brcmfmac4387c2-pcie.*`
  in the same pattern.

Destination: `/lib/firmware/brcm/`.

## v1 behavior (shipped in the apple-silicon image)

- `mseries-wifi-firmware.service`: `ConditionArchitecture=arm64`, runs
  before NetworkManager, `Type=oneshot RemainAfterExit=yes`.
- `/usr/sbin/mseries-wifi-firmware`:
  1. Gates on aarch64 + Apple device-tree (same gate as everything else).
  2. Detects the chip from `lspci -nn` (4425 → 4378, 4433 → 4387).
  3. If all blobs are already in `/lib/firmware/brcm/` → log + exit 0.
  4. Else, looks in the installer handoff locations
     (`/boot/efi/mseries-firmware`, `/run/mseries/firmware`) and copies
     what matches. (Nothing populates these yet — see step 5 of the plan.)
  5. Else, logs the exact missing filenames and how to provide them, and
     exits 0. Wi-Fi stays down; everything else works. Never fails the boot.

## Plan to full provisioning

1. ~~Detect + report~~ (this commit).
2. Define the installer handoff: live-ISO session (or a tiny macOS-side
   helper) extracts the blobs from macOS and drops them at
   `/boot/efi/mseries-firmware` (FAT, visible to both OSes). Copy paths
   inside macOS to be confirmed on hardware.
3. Re-test on M1 + M2-Pro hardware: clean boot without firmware (expect the
   log message), populate handoff, reboot (expect Wi-Fi).
4. Revisit whether the copy should move into the installer (elementary's
   `elementary-install`) instead of first boot, once the installer path on
   Apple hardware is defined.

## Verification TODO (needs hardware)

- Exact blob set per chip (extra `.clm_blob`/`.txcap_blob` revisions).
- NVRAM `.txt` selection rule on Apple (module/antenna-specific names).
- Whether `CONFIG_BRCMFMAC_*` in the Asahi kernel needs non-default options.
