# ARM64 QEMU/KVM VM spike

This is the first backend spike for the elementary-native VM app idea. It creates one persistent ARM64 VM from a local installer ISO using QEMU/KVM, AAVMF UEFI, virtio storage/network/graphics, and user-mode NAT.

The host inspected for this spike is elementary OS 9 Early Access on an M1 Pro. QEMU/KVM, qemu-img, and AAVMF are present. No installer image has been downloaded and this launcher has not been run yet.

## Usage

    ./run-vm.sh /path/to/arm64-installer.iso [vm-directory]

The default VM directory is `./omarchy-arm64-vm`, relative to the current directory. It stores a sparse 64 GiB qcow2 disk and a writable UEFI variable store. Removing that directory removes the VM, so keep it somewhere intentional once it contains data.

The guest sees a virtio Ethernet device connected through QEMU user networking. It does not receive the host's Wi-Fi adapter. TCP from host `127.0.0.1:2222` is forwarded to guest port 22 for later SSH access if the guest enables SSH.

## Current limits

- This is a launch harness, not the app or a VM manager.
- It accepts any ARM64 installer ISO; it does not yet validate the image architecture or automate installation.
- It assumes AAVMF firmware at `/usr/share/AAVMF/` and access to `/dev/kvm`.
- It currently uses 4 vCPUs, 6 GiB RAM, 2D virtio graphics, and a 64 GiB disk.
- It has not yet been boot-verified. The first real guest artifact should be Omarchy ARM64 from its documented edge/image-building path.
- The host currently has about 19 GiB free, below the Try Omarchy guest-builder's stated ~20 GiB build allowance, so that full build should wait until space is available or use a smaller disposable ARM64 installer image for the initial engine check.
