# Changelog

## 0.8.0 (2026-10-19)
- Ready-made images: load a bootable disk (qcow2, raw, vmdk, vdi, compressed xz/zst/gz, or a UTM zip) instead of installing, and save any machine's disk as a compressed image. Images are format-checked and refused if they reference other files on the host. Tested with real `qemu-img` and `xz`.

## 0.7.0 (2026-10-19)
- Snapshots: save, restore and delete disk restore points per machine from the Settings tab (qcow2 internal snapshots through `qemu-img`; machine must be off). Tested against real `qemu-img`.
- Emulated x86-64 machines no longer say they need `/dev/kvm`.

## 0.6.0 (2026-10-19)
- Incus panel: containers and virtual machines managed by Incus appear in the sidebar with state, address, memory, image and snapshots; start, stop, restart, pause, delete, open a terminal, read the console log, and create new instances from a dialog. Uses the `incus` CLI (JSON); verified against a real Incus 6.0.5 daemon with a throwaway container.
- The content stack no longer widens the window for a hidden wide page.

## 0.5.0 (2026-10-19)
- x86-64 (amd64) machines under software emulation (QEMU TCG, q35, OVMF), clearly labelled "emulated" with a warning banner; per-architecture setup checks; presets for Ubuntu, Debian and a blank machine. Not boot-tested yet: qemu-system-x86 is not installed on the test Mac.

## 0.4.0 (2026-10-19)
- Clipboard sharing over QEMU's D-Bus display (Settings, off by default): guest-to-host text verified with the elementary OS guest; host-to-guest not working yet.
- Machines started with it use `-display dbus,p2p=on` and a `qemu-vdagent` channel (`MACHINE_CLIPBOARD`, vm.conf `CLIPBOARD=on`).

## 0.3.0 (2026-10-19)
- Display tab: guest screen, mouse, keyboard, full screen with exit controls, Ctrl+Alt+Del, screenshots.
- macOS (experimental) page that runs real probes and shows how each route fails.
- Pause/resume; Omarchy automatic install; import of mseries-vm guests; readiness and free-space checks.
- Credentials are masked until revealed; the status poll runs off the main thread; `--version`.
- Tests (`meson test`): persistence, discovery, install detection, credentials, QMP transport; AppStream metadata; `.deb` build script.

## 0.2.0
- Multiple machines, presets, colours, Console and Settings tabs, imported guests.

## 0.1.0
- Single-machine prototype (Codex spike), restyled for elementary OS.
