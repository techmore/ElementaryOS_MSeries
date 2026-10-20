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
| **`-accel kvm -cpu host,pmu=off`** | **the vCPU runs** (no KVM error; still alive after 15 s), silently executing the zero-filled "firmware" |

The real firmware (`AVPBooter.vmapple2.bin`) and a macOS 12 VM's aux/root images were not used (they come from a Mac and Apple's servers),
so this shows how far the **machine model** gets, not a macOS boot. 
## Why KVM said `Invalid argument` (found)

`strace -e ioctl` against the working `virt` machine shows three extra `KVM_SET_DEVICE_ATTR` calls on the vCPU fd that `vmapple` never makes:
`virt` sets the PMU interrupt and initialises the PMU (`kvm_arm_pmu_set_irq`, `kvm_arm_pmu_init`), and `-cpu host` enables the PMU
feature by default. With the PMU feature on and no PMU interrupt configured, the first `KVM_RUN` fails with `EINVAL`. Turning the
feature off fixes it without touching the code: **`-cpu host,pmu=off`** (a code fix would set the PMU IRQ as `virt.c` does).

Remaining open questions: whether a real AVPBooter and macOS 12 images get further under KVM (Apple cores instead of HVF), and what
to do about graphics (none on Linux).

## Where the Apple parts can and cannot come from (checked 2026-10-20)

Run `run-vmapple.sh` once these three files are in `~/vms/macos` (it refuses with a clear list until then).

- **This Mac's own macOS install: no.** The 717 GB APFS container (`nvme0n1p2`) and the 2.3 GB one (`p3`) cannot be opened from Linux:
  `apfs-fuse` (built from github.com/sgan81/apfs-fuse) fails with `Initialization of KeyManager failed`, because Apple Silicon
  volumes are encrypted with keys held by the Secure Enclave.
- **This Mac's Recovery volume: no.** `p6` mounts read-only, but its `arm64eBaseSystem.dmg` (readable with `7z`) has only Virtualization
  *plists*, no `AVPBooter` and no `Virtualization.framework`. Mounted read-only, nothing written, unmounted again.
- **A macOS IPSW from Apple: likely has the firmware, not usable alone.** The restore image's system disk should contain
  `Virtualization.framework/Resources/AVPBooter.vmapple2.bin` (not verified: ~15 GB download not done), but turning an IPSW into the
  aux and root images is `VZMacOSInstaller` / `macosvm`, which only exist on macOS.
- **Practical route:** on any Mac running macOS, `macosvm` creates `aux.img` and `root.img` from an IPSW and the framework carries
  `AVPBooter.vmapple2.bin`; copy the three files here. Nothing in this repository ships them.
