# QEMU vmapple on Linux/KVM (experiment, 2026-10-19)

Question: can a Linux Mac present Apple's virtual Mac platform with QEMU's upstream `vmapple` machine, so macOS can be a guest?

`linux-vmapple.patch` applies to QEMU master at `288b6c9e78913401fac4880b3281ce431540b8df` (11.1.50) and makes `vmapple` build and initialise on Linux:

1. `hw/vmapple/Kconfig`: drop `depends on HVF` and `select MAC_PVG_MMIO` (Apple's paravirtual GPU, macOS-only).
2. `configs/devices/aarch64-softmmu/default.mak`: remove `CONFIG_VMAPPLE=n`.
3. `hw/vmapple/aes.c`: constant expression for `MAX_LEN` (gcc rejects the initialised VLA).
4. `hw/vmapple/vmapple.c`: skip the `apple-gfx-mmio` device when its type is missing (the guest then has no GPU).

```sh
git clone --depth 1 https://gitlab.com/qemu-project/qemu.git qemu-vmapple && cd qemu-vmapple
git checkout 288b6c9e78913401fac4880b3281ce431540b8df 2>/dev/null; git apply /path/to/linux-vmapple.patch
mkdir build && cd build && ../configure --target-list=aarch64-softmmu --enable-kvm --disable-docs
ninja qemu-system-aarch64
```

## What happened (this Mac, Asahi-style Linux 7.1, 16 KiB pages, QEMU built from the patched tree)

| Attempt | Result |
| --- | --- |
| stock QEMU 10.2.1 | no `vmapple` machine type |
| patched build, `-M vmapple` | `Parameter 'uuid' expects integer` (the docs derive it from the VM's UUID) |
| `uuid=1`, no pflash | `No AUX device. Please specify one as pflash drive.` |
| blank aux/root pflash, before item 4 | `unknown type 'apple-gfx-mmio'` |
| after item 4, `-accel kvm`, dummy firmware | `apple-gfx-mmio is not available` warning, then **`error: kvm run failed Invalid argument` at `PC=0000000000100000`** with all registers zero: KVM refuses the very first `KVM_RUN` |
| same, `-accel tcg -cpu max` | runs silently (executes the zero-filled "firmware"), no output |

The real firmware (`AVPBooter.vmapple2.bin`) and a macOS 12 VM's aux/root images were not used (they come from a Mac and Apple's servers),
so this shows how far the **machine model** gets, not a macOS boot. Open questions: why KVM returns EINVAL on the first run (likely vCPU or
GIC setup that `vmapple` expects HVF to provide), and what to do about graphics (none on Linux).
