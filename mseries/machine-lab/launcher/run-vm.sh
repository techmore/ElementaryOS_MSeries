#!/usr/bin/env bash
# Boot a Linux ARM64 guest under QEMU/KVM with user-mode NAT.
#   run-vm.sh ISO [VM_DIR] [CIDATA_ISO]   boot an installer (ISO "-" = none)
#   run-vm.sh --disk-only VM_DIR          boot the installed disk
# Hardware comes from the environment: MACHINE_CPUS, MACHINE_MEM_GIB,
# MACHINE_DISK_GIB, MACHINE_SSH_PORT, MACHINE_NAME, MACHINE_DISPLAY (gtk|none). Two QMP sockets in
# VM_DIR: qmp.sock (control: pause, resume, mseries-vm) and qmp-view.sock (the
# Machine Lab display) so a viewer never blocks control commands.
set -euo pipefail

CPUS=${MACHINE_CPUS:-4}
MEM_GIB=${MACHINE_MEM_GIB:-6}
DISK_GIB=${MACHINE_DISK_GIB:-64}
SSH_PORT=${MACHINE_SSH_PORT:-2222}
VM_NAME=${MACHINE_NAME:-Omarchy-ARM64}

if [ "${1:-}" = "--disk-only" ]; then
    if [ "$#" -ne 2 ]; then
        echo "Usage: $0 --disk-only VM_DIRECTORY" >&2
        exit 2
    fi
    ISO_PATH=""
    CIDATA_PATH=""
    VM_DIR=$2
else
    if [ "$#" -lt 1 ]; then
        echo "Usage: $0 ARM64_INSTALL_ISO [VM_DIRECTORY] [CIDATA_ISO]" >&2
        exit 2
    fi
    ISO_PATH=$1
    [ "$ISO_PATH" = "-" ] && ISO_PATH=""
    VM_DIR=${2:-./omarchy-arm64-vm}
    CIDATA_PATH=${3:-}
fi

QEMU=$(command -v qemu-system-aarch64 || true)
QEMU_IMG=$(command -v qemu-img || true)
FW_CODE=/usr/share/AAVMF/AAVMF_CODE.fd
FW_VARS=/usr/share/AAVMF/AAVMF_VARS.fd

if [ -z "$QEMU" ] || [ -z "$QEMU_IMG" ]; then
    echo "Install qemu-system-arm and qemu-utils first." >&2
    exit 1
fi
if [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ]; then
    echo "KVM is unavailable to this user. Check /dev/kvm permissions." >&2
    exit 1
fi
if [ -n "$ISO_PATH" ] && [ ! -r "$ISO_PATH" ]; then
    echo "Cannot read installer image: $ISO_PATH" >&2
    exit 1
fi
if [ -n "$CIDATA_PATH" ] && [ ! -r "$CIDATA_PATH" ]; then
    echo "Cannot read unattended-install seed: $CIDATA_PATH" >&2
    exit 1
fi
if [ ! -r "$FW_CODE" ] || [ ! -r "$FW_VARS" ]; then
    echo "AAVMF UEFI firmware was not found under /usr/share/AAVMF." >&2
    exit 1
fi

mkdir -p "$VM_DIR"
if [ ! -e "$VM_DIR/efi-vars.fd" ]; then
    cp --reflink=auto "$FW_VARS" "$VM_DIR/efi-vars.fd"
fi
if [ ! -e "$VM_DIR/disk.qcow2" ]; then
    "$QEMU_IMG" create -f qcow2 "$VM_DIR/disk.qcow2" "${DISK_GIB}G"
fi
rm -f "$VM_DIR/qmp.sock" "$VM_DIR/qmp-view.sock"

DISPLAY_ARGS=(-display gtk,gl=off)
[ "${MACHINE_DISPLAY:-gtk}" = none ] && DISPLAY_ARGS=(-display none)

QEMU_ARGS=(
    -name "$VM_NAME"
    -machine virt,gic-version=3,msi=gicv2m,acpi=off
    -accel kvm
    -cpu host
    -smp "$CPUS"
    -m "${MEM_GIB}G"
    -drive if=pflash,format=raw,readonly=on,file="$FW_CODE"
    -drive if=pflash,format=raw,file="$VM_DIR/efi-vars.fd"
    -drive if=none,id=system,format=qcow2,file="$VM_DIR/disk.qcow2"
    -device virtio-blk-pci,drive=system,bootindex=1
)

if [ -n "$ISO_PATH" ] || [ -n "$CIDATA_PATH" ]; then
    QEMU_ARGS+=(-device virtio-scsi-pci,id=scsi)
fi
if [ -n "$ISO_PATH" ]; then
    QEMU_ARGS+=(
        -drive if=none,id=installer,format=raw,media=cdrom,readonly=on,file="$ISO_PATH"
        -device scsi-cd,drive=installer,bus=scsi.0,bootindex=2
    )
fi
if [ -n "$CIDATA_PATH" ]; then
    QEMU_ARGS+=(
        -drive if=none,id=cidata,format=raw,media=cdrom,readonly=on,file="$CIDATA_PATH"
        -device scsi-cd,drive=cidata,bus=scsi.0,bootindex=3
    )
fi

QEMU_ARGS+=(
    -netdev user,id=net0,hostfwd=tcp:127.0.0.1:"$SSH_PORT"-:22
    -device virtio-net-pci,netdev=net0
    -device qemu-xhci
    -device usb-kbd
    -device usb-tablet
    -device virtio-gpu-pci
    -device virtio-rng-pci
    -qmp unix:"$VM_DIR/qmp.sock",server=on,wait=off
    -qmp unix:"$VM_DIR/qmp-view.sock",server=on,wait=off
    "${DISPLAY_ARGS[@]}"
    -boot menu=on
)

exec "$QEMU" "${QEMU_ARGS[@]}"
