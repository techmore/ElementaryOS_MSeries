# Machine Lab roadmap

Tracked as GitHub issues in `techmore/ElementaryOS_MSeries`. Status as of 2026-10-19.

| Area | Issue | Status |
| --- | --- | --- |
| Display tab (frames, mouse, keyboard) | merged (#258, #259) | done; Wayland keyboard path unverified |
| Full screen with clear exit controls | this PR | done: F11, Ctrl+Alt+F (works while the keyboard is captured), floating Exit Full Screen / Release Keyboard bar |
| Bidirectional clipboard (text) | [#263](https://github.com/techmore/ElementaryOS_MSeries/issues/263) | guest to host works (verified); host to guest not working yet, see `experiments/clipboard/README.md` |
| Object copy/paste, drag-and-drop, file transfer | [#264](https://github.com/techmore/ElementaryOS_MSeries/issues/264) | blocked upstream: QEMU's D-Bus clipboard only carries text; needs a file-transfer channel or shared folder |
| Windows: virtio-win drivers, unattended install | [#265](https://github.com/techmore/ElementaryOS_MSeries/issues/265) | answer-file generator (driver paths per arch, local account, opt-in disk wipe), checksum-verified virtio-win download and attach flow, unit tested; not yet exercised in a real Windows install (needs a VM boot) |
| Display: resize to window, cursor, audio, faster stream, WebRTC | [#266](https://github.com/techmore/ElementaryOS_MSeries/issues/266) | not started |
| Ready-made images (import/export) | this PR | logic tested with real qemu-img; file chooser flow not exercised headless; no hosted image catalog yet |
| Snapshots (restore points) | this PR | take/restore/delete verified in the UI and with real qemu-img; offline only, no memory state |
| Incus containers and VMs panel | this PR | listing, lifecycle, terminal, log and create verified; no Display tab for Incus VMs yet |
| x86-64 emulated machines | this PR | built and labelled; boot not tested (needs qemu-system-x86 + ovmf on the host) |
| macOS (experimental) | [#267](https://github.com/techmore/ElementaryOS_MSeries/issues/267) | read-only readiness page and current ARM/KVM research recorded on codex/messaging-macos-lab; M1 Pro boot, iMessage and dock save/restore unqualified |

## Windows network driver: what the investigation found

In the Windows 11 ARM64 test VM the OOBE page "Let's connect you to a network" reports "No network drivers found" even after
the NetKVM driver is installed from `D:\NetKVM\w11\ARM64` through its **Install driver** button. The driver does load:

- `pnputil /add-driver D:\NetKVM\w11\ARM64\*.inf /install` reports `netkvm.inf` "already exists in the system" and
  "up-to-date on device PCI\VEN_1AF4&DEV_1000" (the virtio NIC).
- `ipconfig` shows `10.0.2.15` with gateway `10.0.2.2` (QEMU user-mode NAT), and `ping 10.0.2.2` answers.
- Pressing **Next** continues OOBE to "Checking for updates", so the network is usable; the page text is stale.

So the "network driver" problem is a stale OOBE page plus a manual driver step, not a missing driver. The virtio-win ISO also
has `viogpu`, `vioinput`, `Balloon` and the guest agent for ARM64, which are not installed yet (see #265).

## macOS: current research lane (2026-10-20)

See [the VMApple experiment](experiments/vmapple/README.md) for pinned external
ARM/Linux graphical-boot evidence, our historical dummy-firmware run, native
macOS artifact collection, and the M1 Pro qualification sequence. The readiness
page no longer treats the absence of Apple's host framework as proof that a
Linux/KVM guest is impossible. No guest boot or kernel deployment occurred.

The undocked requirement is full VM state saved to disk and QEMU stopped;
existing pause/resume and offline disk snapshots do not meet it.
