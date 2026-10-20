# macOS on Linux/KVM: experimental lane (2026-10-20)

The older dummy-firmware experiment below is retained as historical evidence.
It does not establish a macOS boot. The new Machine Lab page runs read-only
readiness checks, not launch attempts against made-up machine or CPU names.

## Current external evidence

- [Steelbrain's Asahi experiment](https://github.com/steelbrain/experiment-macOS-arm64-on-asahi-linux-arm64/tree/657bb2423ec8d572b22a97dd33563dbba1680e6a), published 2026-08-18: Ventura 13.6 (22G120), M2 Pro,
  Fedora Asahi 42, custom 6.19.14-vmapple2 kernel, eight guest vCPUs and graphical
  Setup Assistant. Graphics used llvmpipe. This is an upstream report, not our reproduction.
- [Reims vGPU](https://github.com/steelbrain/reims-vgpu/tree/2ce320931917e8a07a00243f53656f8cd11306b2), inspected 2026-10-20: active graphics work, beta status.
  Its ordinary ARM/macOS-host and x86/Linux-host demonstrations do not prove ARM/Linux support here.
- Apple KVM APVMKEY, APCTL and KERNKEY context handling, QEMU's Apple hypercall and
  interrupt handling, and the Reims display patches are separate prerequisites.
  Our installed Aurora .20 has not been qualified for them. Do not install a
  replacement kernel or change boot defaults as part of application deployment.

## Prepare the host and the macOS visit

`python3 launcher/macos-check.py` reports ARM host, KVM access, QEMU VMApple,
firmware, guest files and qualification separately. Environment variables:
`QEMU_VMAPPLE` selects an experimental QEMU executable; `MACOS_DIR` selects the
bundle directory (default `~/vms/macos`). Both may also be passed as CLI options.
A successful file check never proves a boot or working iMessage.

Bring back `AVPBooter.vmapple2.bin`, `disk.img`, `aux.img` and `vm.json` from the
same provisioned VM; retain `aux.img.trimmed` if provisioning produced it.
The upstream proof uses `macosvm` on native macOS to provision the Ventura IPSW.
Use its pinned provisioning instructions and preserve sparse disks with
`rsync --sparse`. Merely copying the native macOS partition is not sufficient.
Firmware from a newer installed macOS may not match the Ventura restore chain.
Keep all Apple files, identities, hardware codes and account state outside Git.
The current Linux filesystem has about 19 GiB free; it is not ready for an
IPSW download plus guest provisioning and large VM-stack builds.

Bubbles activation is a separate native-Mac export, not an identity copied from
this VM. Mac Hardware Info must export a full OABS blob (Prevent sharing off).
Bubbles accepts that blob; its 517-byte raw-validation import path is stubbed in
this revision, and short MB codes are not resolved by its local-hardware UI.

## Qualification sequence and dock policy

1. Review/rebase the pinned upstream KVM patches against a separate Aurora source tree.
2. Build kernel/QEMU/Reims separately; retain the known working kernel and boot entry.
3. Boot a matching macOS bundle on this M1 Pro; record CPU, memory, rendering and power.
4. Verify Apple Account/iMessage, then BlueBubbles, without inferring activation from a GUI boot.
5. Qualify full memory/device save-to-disk, process exit, and restored network/Apple push connections.
6. Only then connect resume/start to dock attachment and save/exit to undocking,
   with a clean shutdown fallback. Dock detection must identify the actual WD22TB4,
   not assume that any charger or display means docked.

Machine Lab's existing Pause keeps RAM; its disk snapshots omit RAM. Neither
meets the requested undocked state with QEMU stopped and guest RAM released.
There is no published support date for this host. This branch provides preparation
and honest readiness reporting; it does not claim a working macOS launcher.

## Historical experiment, 2026-10-19

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
