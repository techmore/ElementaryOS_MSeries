#!/usr/bin/env bash
# Boot a macOS guest on QEMU's vmapple machine under KVM (experimental, headless, no graphics on Linux).
#
# You must bring the Apple parts yourself (they are not redistributable and come from a Mac):
#   AVPBooter.vmapple2.bin   Apple's boot ROM, from macOS (Virtualization.framework resources)
#   aux.img, root.img        auxiliary storage and root disk of a macOS 12 VM made with macosvm on a Mac
# Put them in ~/vms/macos (or set MACOS_DIR). QEMU must be the patched build from linux-vmapple.patch
# (QEMU_VMAPPLE=/path/to/qemu-system-aarch64, default ~/src/qemu-vmapple/build/qemu-system-aarch64).
set -euo pipefail
DIR=${MACOS_DIR:-$HOME/vms/macos}
QEMU=${QEMU_VMAPPLE:-$HOME/src/qemu-vmapple/build/qemu-system-aarch64}
ROM=$DIR/AVPBooter.vmapple2.bin AUX=$DIR/aux.img ROOT=$DIR/root.img
missing=0
for f in "$QEMU" "$ROM" "$AUX" "$ROOT"; do
    if [ ! -r "$f" ]; then echo "Missing: $f" >&2; missing=1; fi
done
[ "$missing" = 0 ] || { echo "See experiments/vmapple/README.md for where each file comes from." >&2; exit 2; }
if ! "$QEMU" -machine help | grep -q '^vmapple'; then
    echo "$QEMU has no vmapple machine: build it with linux-vmapple.patch." >&2; exit 2
fi
[ -r /dev/kvm ] && [ -w /dev/kvm ] || { echo "No access to /dev/kvm." >&2; exit 2; }
# pmu=off: vmapple never initialises the PMU interrupt, so KVM_RUN fails with EINVAL if the PMU is on.
exec "$QEMU" -accel kvm -cpu host,pmu=off -M vmapple,uuid="${MACOS_UUID:-1}" \
    -m "${MACOS_MEM:-4G}" -smp "${MACOS_CPUS:-4}" -display none -serial stdio \
    -bios "$ROM" \
    -drive file="$AUX",if=pflash,format=raw \
    -drive file="$ROOT",if=pflash,format=raw \
    -netdev user,id=net0 -device virtio-net-pci,netdev=net0 \
    "$@"
