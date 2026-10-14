# ARM64 VM installer smoke test

Verified 2026-10-13 on the owner's M1 Pro using QEMU 10.2.1/KVM.

## Result and limits

The locally built ISO at source 89e959d, SHA-256
`ca707f3e959809d27686b2e535c9b165b843694ff86b5a48dd065cf118e02041`,
booted through AAVMF UEFI to the graphical elementary installer language
selection screen. Serial output also reached the elementary OS 9 login
prompt and showed LightDM starting. No installer selections or installation
were performed. Screenshot: `docs/images/os9-arm64-vm-installer.png`.

This verifies generic ARM64 UEFI/kernel/initramfs/live-environment startup
for that ISO. It does not verify a full Pantheon user session, installation,
Apple m1n1/U-Boot, GPU, speakers, suspend, or other Mac hardware behavior.
The first tested ISO predates the liveiso overlay-selection fix. The corrected
CI artifact was independently verified and tested separately below.

## Isolation

- 4 virtual CPUs, 4 GiB RAM; /dev/kvm accessible to the desktop user.
- Networking disabled.
- Only the ISO attached as read-only SCSI CD-ROM; no host disk or writable
  guest system disk attached.
- UEFI code read-only; private copied firmware variables file.
- No host boot/kernel/audio settings changed.

## Command used

Create a private output directory and copy AAVMF_VARS.fd there first.
Replace the two directory paths below when reproducing; preserve the
read-only disk and disabled network settings.

```bash
qemu-system-aarch64 \
  -machine virt,accel=kvm -cpu host -smp 4 -m 4096 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/AAVMF/AAVMF_CODE.no-secboot.fd \
  -drive if=pflash,format=raw,file=/home/admin/Documents/os9-vm-smoke-20261013/vars.fd \
  -device virtio-gpu-pci -device qemu-xhci -device usb-kbd -device usb-tablet \
  -device virtio-scsi-pci \
  -drive if=none,id=cdrom,format=raw,media=cdrom,readonly=on,file=/home/admin/Documents/os9-local-build-20261013/mkosi.output/elementaryos-9.0-daily-arm64.20261013134230.iso \
  -device scsi-cd,drive=cdrom,bootindex=1 -nic none -display none \
  -serial file:/home/admin/Documents/os9-vm-smoke-20261013/serial.log \
  -qmp unix:/home/admin/Documents/os9-vm-smoke-20261013/qmp.sock,server=on,wait=off
```

The actual test ran in transient user service
`elementary-os9-vm-smoke-20261013.service`. Its framebuffer was captured with
QMP screendump after UEFI boot. The VM was then stopped; the serial log,
firmware variables, and screenshot remain in the private test directory.

## Corrected CI image — verified October 13

Source `32877a7b8a07d2a16d6bef978e5071a983953b8a`, run 38410538372.
Downloaded ISO `elementaryos-9.0-daily-arm64.20261013140741.iso` passed
`sha256sum -c INSTALLER-SHA256SUMS` independently on this Mac:
`066147b211909347e3499463419a39ba66326aa0fbd277985c7957b6fcfc59ab`.
The CI actual-payload test passed before upload.

Repeated the same isolated QEMU/KVM command above, replacing ISO path with
`/home/admin/Documents/os9-corrected-38410538372/elementaryos-9.0-daily-arm64.20261013140741.iso`
and output directory with `/home/admin/Documents/os9-corrected-vm-20261013`.
Reached the graphical installer language screen and serial login prompt.
Screenshot: `docs/images/os9-arm64-corrected-vm-installer.png`.
No installer selections or installation were performed. User service
`elementary-os9-corrected-vm-20261013.service` was stopped after capture.

This corrected generic-kernel image now has checksum, payload and VM startup
evidence. It does not test the separately compiling enhanced Fairydust
Debian kernel or Apple hardware boot, firmware, GPU, speakers or suspend.

## Opt-in Fairydust image — verified October 13

Source `4c0cdb92663c01900f9eac719b829f2c5ca540c4`, run
[38432118320](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38432118320)
completed successfully. The ARM64 CI job built the pinned Fairydust + USB4
Debian kernel package after installing the required Rust source component;
the image job verified all package hashes, built the Fairydust profile,
passed `test-image-wiring.py`, and uploaded the ISO.

Downloaded installer `elementaryos-9.0-daily-arm64.20261013170336.iso`
(size 7,481,829,376 bytes) passed the artifact build-record checksum:
`14184dfc351b23e7db3f7712d5c0bad5b62bb9abd75cbfd25fcb4337d8b21c1e`.
The ISO's live filesystem package database lists
`linux-image-7.1.13-elementary-fairydust-usb4`, `m1n1`, and `u-boot-asahi`
as installed. The CI build log also confirms a 79.7 MB Fairydust UKI and
module initrd were generated.

Booted the ISO in QEMU/KVM with 4 virtual CPUs and 4 GiB RAM, networking
disabled, read-only ISO media, and no writable guest system disk. It reached
the elementary live login prompt. The GRUB live entry starts `/casper/vmlinuz`
and `/casper/initrd`, so this smoke test booted the generic live kernel; it
did not boot the Fairydust UKI. The Fairydust kernel is bundled in the image
for installed-system testing, but its actual boot has not yet been qualified.
The m1n1/U-Boot packages and generated UKI do not mean that the required
Apple m1n1 ESP payload is assembled. No Mac hardware, USB4, GPU, audio, or
suspend behavior is qualified by this test.

## Direct Fairydust kernel smoke test — October 13

Rebuilt the locally packaged Fairydust kernel with built-in ARM PL011 console
support, then ran
`mseries/fairydust/debian/vm-kernel-smoke-test.sh` against the package
`linux-image-7.1.13-elementary-fairydust-usb4_7.1.13+elementary.usb4.3_arm64.deb`.
Package SHA-256:
`6047f67c33c78fd4c614adadb619aa612919e151497d3941fe8949ae08e084f3`.

QEMU/KVM ran with two vCPUs and 1 GiB RAM, attached only the kernel and a
temporary BusyBox initramfs, with no disk or network. Serial output confirmed
kernel `7.1.13-elementary-fairydust-usb4` startup on QEMU's `linux,dummy-virt`
device tree, execution of `/init`, the
`FAIRYDUST_KERNEL_USERSPACE_HANDOFF_OK` marker, and orderly poweroff. The test
script has a 45-second bound plus a 5-second forced-stop limit.

This directly boots the compiled kernel and verifies generic ARM64 kernel
startup through userspace handoff. It does not test the installed-system
initramfs or bootloader, any Apple DTB or m1n1/ESP payload, Mac hardware, GPU,
USB4, audio, suspend or a full desktop session. Keep the distinction between
this direct-kernel test and the separate generic live-ISO boot above.

## Latest CI artifact boot — October 13

Downloaded artifact from [CI run 38479577898](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38479577898).
The ISO `elementaryos-9.0-daily-arm64.20261013230825.iso` is 7,482,648,576
bytes; its SHA-256 `89c74fa25ac72dd8f20f7eb42e456c929ed828f791f77af3edb6f5ce1b7b259d`
matched the artifact's `INSTALLER-SHA256SUMS` after download.

QEMU 10.2.1/KVM (4 vCPUs, 6 GiB RAM, AAVMF) booted the ISO to the graphical
installer language screen. Serial output reached the elementary OS 9 login
prompt. Only a read-only SCSI CD-ROM was attached; no writable guest or host
disk was attached. Screenshot:
[`os9-ci-38479577898-installer.png`](../docs/images/os9-ci-38479577898-installer.png).

The ISO's live entry uses `/casper/vmlinuz` and `/casper/initrd`; this verifies
the generic live-kernel installer path, not the Fairydust kernel packaged for
an installed system. The separate direct-kernel test above verifies only
generic ARM64 startup through a BusyBox initramfs. Neither test verifies the
installed-system initramfs, Apple DTB selection, m1n1 boot on hardware, GPU,
USB4, audio, suspend, or a full desktop installation. No host ESP or boot
configuration was changed. The temporary artifact ZIP and signed download URL
were removed; the verified ISO and screenshot remain in the local test
directory and repository evidence folder, respectively.
