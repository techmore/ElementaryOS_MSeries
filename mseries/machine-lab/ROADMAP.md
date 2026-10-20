# Machine Lab roadmap

Tracked as GitHub issues in `techmore/ElementaryOS_MSeries`. Status as of 2026-10-19.

| Area | Issue | Status |
| --- | --- | --- |
| Display tab (frames, mouse, keyboard) | merged (#258, #259) | done; Wayland keyboard path unverified |
| Full screen with clear exit controls | this PR | done: F11, Ctrl+Alt+F (works while the keyboard is captured), floating Exit Full Screen / Release Keyboard bar |
| Bidirectional clipboard (text) | [#263](https://github.com/techmore/ElementaryOS_MSeries/issues/263) | guest to host works (verified); host to guest not working yet, see `experiments/clipboard/README.md` |
| Object copy/paste, drag-and-drop, file transfer | [#264](https://github.com/techmore/ElementaryOS_MSeries/issues/264) | blocked upstream: QEMU's D-Bus clipboard only carries text; needs a file-transfer channel or shared folder |
| Windows: virtio-win drivers, unattended install | [#265](https://github.com/techmore/ElementaryOS_MSeries/issues/265) | manual procedure documented; network driver investigated |
| Display: resize to window, cursor, audio, faster stream, WebRTC | [#266](https://github.com/techmore/ElementaryOS_MSeries/issues/266) | not started |
| Ready-made images (import/export) | this PR | logic tested with real qemu-img; file chooser flow not exercised headless; no hosted image catalog yet |
| Snapshots (restore points) | this PR | take/restore/delete verified in the UI and with real qemu-img; offline only, no memory state |
| Incus containers and VMs panel | this PR | listing, lifecycle, terminal, log and create verified; no Display tab for Incus VMs yet |
| x86-64 emulated machines | this PR | built and labelled; boot not tested (needs qemu-system-x86 + ovmf on the host) |
| macOS (experimental) | [#267](https://github.com/techmore/ElementaryOS_MSeries/issues/267) | attempt page done and shows how it fails; emulation route not attempted |

## Windows network driver: what the investigation found

In the Windows 11 ARM64 test VM the OOBE page "Let's connect you to a network" reports "No network drivers found" even after
the NetKVM driver is installed from `D:\NetKVM\w11\ARM64` through its **Install driver** button. The driver does load:

- `pnputil /add-driver D:\NetKVM\w11\ARM64\*.inf /install` reports `netkvm.inf` "already exists in the system" and
  "up-to-date on device PCI\VEN_1AF4&DEV_1000" (the virtio NIC).
- `ipconfig` shows `10.0.2.15` with gateway `10.0.2.2` (QEMU user-mode NAT), and `ping 10.0.2.2` answers.
- Pressing **Next** continues OOBE to "Checking for updates", so the network is usable; the page text is stale.

So the "network driver" problem is a stale OOBE page plus a manual driver step, not a missing driver. The virtio-win ISO also
has `viogpu`, `vioinput`, `Balloon` and the guest agent for ARM64, which are not installed yet (see #265).

## macOS: what the experiment shows

The macOS (experimental) page in the app runs real commands and records the output (this Mac, 2026-10-19):

1. `ls /System/Library/Frameworks/Virtualization.framework`: no such file or directory (macOS hosts only).
2. `qemu-system-aarch64 -machine apple-silicon-vm`: `unsupported machine type: "apple-silicon-vm"`.
3. `qemu-system-aarch64 -machine virt,accel=kvm -cpu Haswell`: `unable to find CPU model 'Haswell'`.
4. `qemu-system-x86_64`: not installed (and it could only emulate, never use KVM, on an ARM host).
5. Emulating an Intel Mac in software: not attempted (Apple recovery image, OpenCore, tens of times slower).

## macOS: QEMU `vmapple` on this Linux Mac (2026-10-19)

Built QEMU master (11.1.50) in `~/src/qemu-vmapple` with two local patches and ran its `vmapple` machine under KVM:

1. `hw/vmapple/Kconfig` required HVF and selected the macOS-only graphics device, and `configs/devices/aarch64-softmmu/default.mak`
   set `CONFIG_VMAPPLE=n`. Removing those three lines makes `vmapple` appear in `-machine help` on Linux.
2. `hw/vmapple/aes.c` does not compile with gcc (`char hex[MAX_LEN * 2 + 1] = ""` with `static const size_t MAX_LEN`); an
   `enum` constant fixes it (worth sending upstream).

Then, with `-accel kvm`:

- `-M vmapple,uuid=1` alone: `Parameter 'uuid' expects integer` (the docs derive it from the VM's UUID with `contrib/vmapple/uuid.sh`).
- With `uuid=1`: `No AUX device. Please specify one as pflash drive.` (needs the aux storage of a real macOS VM).
- With blank aux and root pflash plus a dummy `-bios`: `unknown type 'apple-gfx-mmio'`. `vmapple.c` creates Apple's
  paravirtual GPU unconditionally; that device is built from `ParavirtualizedGraphics.framework`, which exists only on macOS.
  This is the first hard Linux blocker. Stubbing it out (skip the device when the type is missing) is the obvious next patch,
  but it was not applied or built: the sandbox declined further edits to this externally sourced code, so the attempt stops here.

What a real boot still needs: Apple's `AVPBooter.vmapple2.bin` copied from a macOS install, aux and root images from a macOS 12 VM
made with Virtualization.framework (`macosvm`), and an answer for graphics (none exists on Linux; the guest would be headless over
serial, ssh or screen sharing). Unknowns: whether the guest tolerates running on KVM with Apple's cores instead of HVF.

Update: with the GPU device skipped (`experiments/vmapple/linux-vmapple.patch`), the machine initialises and KVM then fails on the
first run: `error: kvm run failed Invalid argument` at `PC=0x100000`. TCG runs silently on dummy firmware. See
`experiments/vmapple/README.md` for the table and how to reproduce.

Update 2: the KVM `Invalid argument` is the PMU: `-cpu host` turns it on and `vmapple` never sets the PMU interrupt. With
`-cpu host,pmu=off` the vCPU runs under KVM (silently, on dummy firmware). First real blocker left: Apple's firmware and macOS images.
