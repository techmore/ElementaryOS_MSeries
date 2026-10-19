#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 ARM64_INSTALL_ISO [VM_DIRECTORY]" >&2
    exit 2
fi

ISO_PATH=$1   # "-" boots the installed disk without an installer
CPUS=${MACHINE_CPUS:-4}
MEM_GIB=${MACHINE_MEM_GIB:-6}
DISK_GIB=${MACHINE_DISK_GIB:-64}
SSH_PORT=${MACHINE_SSH_PORT:-2222}
VM_NAME=${MACHINE_NAME:-Omarchy-ARM64}
if [ "$#" -ge 2 ]; then
    VM_DIR=$2
else
    VM_DIR=./omarchy-arm64-vm
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
if [ "$ISO_PATH" != "-" ] && [ ! -r "$ISO_PATH" ]; then
    echo "Cannot read installer image: $ISO_PATH" >&2
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

CD_ARGS=()
if [ "$ISO_PATH" != "-" ]; then
    CD_ARGS=(-drive if=none,id=installer,format=raw,media=cdrom,readonly=on,file="$ISO_PATH"
             -device scsi-cd,drive=installer,bus=scsi.0)
fi

exec "$QEMU" \
    -name "$VM_NAME" \
    -machine virt \
    -accel kvm \
    -cpu host \
    -smp "$CPUS" \
    -m "${MEM_GIB}G" \
    -drive if=pflash,format=raw,readonly=on,file="$FW_CODE" \
    -drive if=pflash,format=raw,file="$VM_DIR/efi-vars.fd" \
    -drive if=none,id=system,format=qcow2,file="$VM_DIR/disk.qcow2" \
    -device virtio-blk-pci,drive=system \
    -device virtio-scsi-pci,id=scsi \
    "${CD_ARGS[@]}" \
    -netdev user,id=net0,hostfwd=tcp:127.0.0.1:"$SSH_PORT"-:22 \
    -device virtio-net-pci,netdev=net0 \
    -device virtio-gpu-pci \
    -display gtk,gl=off \
    -boot menu=on
