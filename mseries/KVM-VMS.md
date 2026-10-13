# Running ARM64 Linux VMs with KVM on the M1 Pro

Checked 2026-10-13 on the owner's MacBook Pro 14" (M1 Pro), QEMU 10.2.1, Linux 7.1.13 fairydust kernel.
Hardware virtualisation works: `/dev/kvm` exists and your user is in the `kvm` group. Guests must be
**ARM64**; x86 guests would be emulated and slow, and are not covered here.

## What was verified

A 2 CPU / 2 GiB guest booted the locally built elementary OS 9 ARM64 live ISO under KVM with a 16 GiB
virtio disk and user-mode networking attached, and reached LightDM start-up in about 25 seconds
(serial console, no display). Nothing was installed into the guest.

## What was not verified

- A graphical window (`-display gtk`) and 3D acceleration (`virtio-gpu-gl`); the test ran with `-display none`.
- That the guest actually received an address on user-mode networking (the serial log shows its network
  services starting, not an IP).
- `virt-manager`; it is not installed here, and nothing below depends on it.
- Performance overhead: that needs an installed guest, and was not measured. The suite in
  [`benchmarks/`](benchmarks/README.md) can be run inside a guest and compared with the host columns.

## Prerequisites (already met on this Mac)

```bash
ls -l /dev/kvm            # crw-rw----+ root kvm
id -nG | tr ' ' '\n' | grep -x kvm
command -v qemu-system-aarch64 qemu-img
ls /usr/share/AAVMF/      # UEFI firmware (AAVMF_CODE.no-secboot.fd, AAVMF_VARS.fd)
```

## Create a guest

Keep each VM in its own folder, with its own copy of the UEFI variables file, and give the disk plenty of
room: qcow2 files only use space as the guest writes.

```bash
vm=~/vms/test; mkdir -p "$vm"
cp /usr/share/AAVMF/AAVMF_VARS.fd "$vm/vars.fd"
qemu-img create -f qcow2 "$vm/disk.qcow2" 32G
```

## Boot an installer ISO

```bash
iso=/path/to/arm64-installer.iso
qemu-system-aarch64 \
  -machine virt,accel=kvm -cpu host -smp 4 -m 4096 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/AAVMF/AAVMF_CODE.no-secboot.fd \
  -drive if=pflash,format=raw,file="$vm/vars.fd" \
  -device virtio-gpu-pci -device qemu-xhci -device usb-kbd -device usb-tablet \
  -drive file="$vm/disk.qcow2",if=virtio,format=qcow2 \
  -device virtio-scsi-pci \
  -drive if=none,id=cdrom,format=raw,media=cdrom,readonly=on,file="$iso" \
  -device scsi-cd,drive=cdrom,bootindex=1 \
  -nic user,model=virtio-net-pci \
  -serial file:"$vm/serial.log" -display gtk
```

Use `-display none` instead of `-display gtk` for a headless run, then read `serial.log`. After installing,
drop the `cdrom` drive and the `scsi-cd` device and boot from the disk.

## Keeping the host safe

- `-nic user` gives the guest outbound NAT only; nothing on your network can reach it. Use `-nic none` for a
  fully offline guest, as the [smoke test](VM-SMOKE-TEST.md) does.
- Attach installer media read-only (`readonly=on`), and never attach a host disk or partition.
- Size the guest to leave the host headroom: on 32 GB, 4 GiB and 4 CPUs is comfortable.
- Stop a guest with its window's close button, or `kill` the `qemu-system-aarch64` process; its disk is
  crash-safe but unsaved work inside the guest is lost.
