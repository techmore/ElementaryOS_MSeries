# Fairydust kernel QEMU TCG smoke test

Verified 2026-10-13 on the native ARM64 host using QEMU software emulation.

The runner had no `/dev/kvm`, so the smoke-test script now accepts
`VM_ACCEL=tcg` as an explicit fallback. It uses QEMU's `max` CPU model in TCG
mode and retains KVM/`host` as the default. Invalid accelerator names fail
closed. Run it with:

```bash
VM_ACCEL=tcg VM_CPUS=2 \
  mseries/fairydust/debian/vm-kernel-smoke-test.sh \
  /path/to/linux-image-7.1.13-elementary-fairydust-usb4_arm64.deb
```

The tested package was
`linux-image-7.1.13-elementary-fairydust-usb4_7.1.13+elementary.usb4.3_arm64.deb`,
SHA-256 `6047f67c33c78fd4c614adadb619aa612919e151497d3941fe8949ae08e084f3`.
QEMU booted the kernel on `linux,dummy-virt`, started the temporary BusyBox
initramfs, printed `FAIRYDUST_KERNEL_USERSPACE_HANDOFF_OK`, and powered down.
The run used two emulated CPUs, 1 GiB RAM, no disk, and no network.

This confirms generic ARM64 kernel startup and userspace handoff under TCG.
It is not a performance measurement and does not validate Apple DTB selection,
the installed-system initramfs, m1n1/U-Boot, USB4, display, audio, suspend, or
boot on the Mac. The first local preflight found 22.4 GiB free. After clearing
the previously approved Hugging Face and mkosi caches and deleting the
completed kernel compiler-object tree (while preserving the tested `.deb`
packages, source tree, logs and configuration report), the current preflight
finds 37.6 GiB free. That remains 22.4 GiB below the conservative 60 GiB build
guard, so no full image build was started. Recheck with
`python3 mseries/local-build-preflight.py`.
