# Machine Lab

Native elementary OS look (Vala + GTK 4 + Granite 7) for running other Linux ARM64 guests under
QEMU/KVM with NAT networking. Install for the current user and pin it to the dock with
`bash mseries/install-machine-lab.sh`.

**Design:** flat sidebar of machines ("YOUR MACHINES" vs "NEW — NOT INSTALLED"), preset gallery,
Overview / Console / Settings tabs, per-machine color, status pill with uptime, readiness and
free-space check, toasts, light/dark and accent following the system.

**Function:**
- Imports guests already managed by `mseries/vms/mseries-vm` (`~/vms/*/vm.conf`) and starts/stops them through it.
- Native machines saved in `~/.config/machine-lab/machines.ini`, with CPU, memory, disk and SSH port settings.
- **Omarchy, automatically** (merged from the Codex spike): `launcher/prepare-latest-omarchy.py` checks Omarchy's
  latest ARM64 nightly, downloads and SHA-256-verifies the ISO, builds unattended-install media, and boots
  QEMU. Sign-in details are shown in the app and saved with owner-only permissions.
- Own ISO path: drop or choose any ARM64 `.iso`; once the disk holds real data the installer detaches itself.
- **Pause / Resume** over QEMU's QMP socket (`qmp.sock` in the machine folder), plus Shut Down / Force Stop.
- **Display tab**: the machine's desktop inside the app (streamed from QEMU's D-Bus display: whole-screen `Scanout` and changed-rectangle `Update` messages, the guest's cursor shape, and a request to size the guest's screen to the tab; falls back to QEMU `screendump` frames as uncompressed PPM over QMP, about 30 fps while the screen changes; mouse and keyboard sent back over a dedicated `qmp-view.sock` so the viewer never blocks `mseries-vm` control commands; click the screen to capture, Ctrl+Alt+G to release; Ctrl+Alt+Del and screenshot buttons). Machines start headless so the screen lives in the app, not a separate QEMU window.
- **Ready-made images**: load a bootable disk instead of installing; save a disk as an image (`src/images.vala`).
- **Snapshots**: disk restore points per machine (`src/snapshots.vala`).
- **Windows drivers**: a pinned, checksum-verified virtio-win download and a generated `autounattend.xml` (DriverPaths for ARM64/amd64, optional local account, opt-in disk wipe) attached to not-yet-installed `mseries-vm` Windows guests (`src/unattend.vala`, `src/virtiowin.vala`, `src/windows-ui.vala`).
- **Incus**: containers and VMs managed by Incus listed in the sidebar with lifecycle actions, terminal, log and a create dialog (`src/incus-model.vala`, `src/incus-ui.vala`).
- Live console from the launcher output, or the guest serial log for imported machines.

```sh
meson setup build && meson compile -C build
./build/machine-lab        # finds ../launcher/run-vm.sh; MACHINE_LAB_LAUNCHER overrides
```

Guides: `docs/USER-GUIDE.md`, `ROADMAP.md`, `CHANGELOG.md`. Tests: `meson test -C build`. Package: `bash mseries/machine-lab/build-deb.sh`.

Layout: `src/machine.vala` (model, QMP, process control, discovery), `src/page.vala` (machine pane),
`src/main.vala` (window, sidebar, presets), `launcher/` (QEMU launcher and Omarchy updater).

**Not verified:** a full guest install and boot end to end (the Omarchy nightly is ~6 GiB and the host had
~19 GiB free). Pause/resume was verified against a headless QEMU through the app. The Display tab was verified in GTK Broadway against the installed elementary guest (frames, mouse, keyboard); the Wayland keyboard path uses evdev codes and is unverified. Visual checks used GTK Broadway.
Provenance: started as the Codex `native-vm-poc` spike; its launcher and Omarchy updater are merged here.
