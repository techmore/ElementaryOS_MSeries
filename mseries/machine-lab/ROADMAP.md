# Machine Lab roadmap

Tracked as GitHub issues in `techmore/ElementaryOS_MSeries`. Status as of 2026-10-19.

| Area | Issue | Status |
| --- | --- | --- |
| Display tab (frames, mouse, keyboard) | merged (#258, #259) | done; Wayland keyboard path unverified |
| Full screen with clear exit controls | this PR | done: F11, Ctrl+Alt+F (works while the keyboard is captured), floating Exit Full Screen / Release Keyboard bar |
| Bidirectional clipboard (text) | [#263](https://github.com/techmore/ElementaryOS_MSeries/issues/263) | not started: vdagent channel + guest agent |
| Object copy/paste, drag-and-drop, file transfer | [#264](https://github.com/techmore/ElementaryOS_MSeries/issues/264) | not started: needs #263 |
| Windows: virtio-win drivers, unattended install | [#265](https://github.com/techmore/ElementaryOS_MSeries/issues/265) | manual procedure documented; network driver investigated |
| Display: resize to window, cursor, audio, faster stream, WebRTC | [#266](https://github.com/techmore/ElementaryOS_MSeries/issues/266) | not started |
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
