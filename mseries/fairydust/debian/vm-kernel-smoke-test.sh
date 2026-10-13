#!/usr/bin/env bash
# Boot the packaged Fairydust kernel to a tiny initramfs in an isolated ARM64 VM.
# This checks kernel decompression, built-in console support and userspace handoff;
# it does not emulate Apple hardware or qualify the m1n1/ESP boot path.
set -euo pipefail

usage() {
    echo "Usage: $0 /path/to/linux-image-*_arm64.deb" >&2
    exit 2
}
[[ $# == 1 && -f $1 ]] || usage
package=$(realpath "$1")
[[ $(uname -m) == aarch64 ]] || { echo 'Run on native ARM64 for KVM acceleration.' >&2; exit 2; }
for command in dpkg-deb qemu-system-aarch64 busybox cpio file timeout; do
    command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 2; }
done
busybox_bin=$(realpath "$(command -v busybox)")
file "$busybox_bin" | grep -q 'statically linked' || {
    echo "BusyBox must be statically linked: $busybox_bin" >&2
    exit 2
}

work=$(mktemp -d "${TMPDIR:-/tmp}/fairydust-vm-smoke.XXXXXXXX")
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
mkdir -p "$work/root/bin" "$work/root/dev" "$work/root/proc" "$work/root/sys"
dpkg-deb -x "$package" "$work/package"
kernel=$(find "$work/package/boot" -maxdepth 1 -type f -name 'vmlinuz-*' -print -quit)
[[ -n $kernel ]] || { echo 'Kernel image missing from Debian package.' >&2; exit 1; }
gzip -dc "$kernel" > "$work/Image"
install -m 0755 "$busybox_bin" "$work/root/bin/busybox"
ln -s busybox "$work/root/bin/sh"
cat > "$work/root/init" <<'INIT'
#!/bin/sh
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true
echo FAIRYDUST_KERNEL_USERSPACE_HANDOFF_OK
/bin/busybox poweroff -f
while :; do /bin/busybox sleep 1; done
INIT
chmod 0755 "$work/root/init"
(cd "$work/root" && find . -print0 | cpio --null -o --format=newc 2>/dev/null | gzip -1) > "$work/initramfs.cpio.gz"

cpus=${VM_CPUS:-2}
[[ $cpus =~ ^[1-9][0-9]*$ ]] || { echo 'VM_CPUS must be a positive integer.' >&2; exit 2; }
echo "Booting $(basename "$kernel") with $cpus KVM vCPUs; no disks or network are attached."
set +e
timeout --signal=TERM --kill-after=5s 45s qemu-system-aarch64 \
    -machine virt,accel=kvm -cpu host -smp "$cpus" -m 1024 \
    -kernel "$work/Image" -initrd "$work/initramfs.cpio.gz" \
    -append 'earlycon=pl011,mmio32,0x09000000 console=ttyAMA0 rdinit=/init loglevel=7 ignore_loglevel panic=-1' \
    -display none -monitor none -serial stdio -no-reboot \
    2>&1 | tee "$work/serial.log"
qemu_status=${PIPESTATUS[0]}
set -e
if (( qemu_status != 0 )); then
    echo "QEMU exited with status $qemu_status." >&2
    exit "$qemu_status"
fi
grep -q 'FAIRYDUST_KERNEL_USERSPACE_HANDOFF_OK' "$work/serial.log" || {
    echo 'Kernel did not reach initramfs userspace.' >&2
    exit 1
}
echo 'PASS: Fairydust kernel reached initramfs userspace in isolated QEMU/KVM.'
