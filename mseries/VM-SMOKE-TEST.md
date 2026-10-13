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
The tested ISO predates the liveiso overlay-selection fix; the corrected
image must be rebuilt/content-checked and smoke-tested separately.

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
