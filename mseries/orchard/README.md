# Orchard

Machines, containers and pods on this Mac, with the look and feel of an elementary OS app
(Vala + GTK 4 + Granite 7). One sidebar with three sections:

- **Machines**: ARM64 (and emulated x86-64) virtual machines under QEMU/KVM with NAT networking,
  a built-in Display tab, clipboard sharing, snapshots, ready-made images, Windows drivers and the
  Omarchy auto-installer. This is Machine Lab's code, unchanged in behaviour.
- **Incus**: containers and virtual machines over the local Unix socket: create, start, stop, pause,
  restart, delete, snapshots and restore, clone, backup export, configuration editing with ETag
  conflict protection (optional stop/apply/start), logs and journals, live statistics with 24 h of
  history, images/networks/profiles/projects browser, image downloads, mounts, port proxies, NICs,
  local AI model endpoints and model sandboxes, a Ctrl+K command palette and `orchard://` links.
  This is Orchard for Incus's code behind Machine Lab's pages.
- **Podman**: the user's rootless containers, images and volumes with start/stop/restart/remove,
  live counters and a details window.

Install for the current user and pin it to the dock with `bash mseries/install-orchard.sh`
(it also removes the Machine Lab and Orchard for Incus entries it replaces).

**Design:** flat sidebar with section headers ("YOUR MACHINES", "NEW — NOT INSTALLED", "INCUS",
"PODMAN"), preset gallery, Overview / Display / Console / Settings tabs for machines and
Overview / Statistics / Configuration / Logs / Snapshots for Incus instances, per-machine colour,
status pill with uptime, readiness and free-space check, toasts, light/dark and accent following
the system. Captures: `docs/screenshot-machines.png`, `docs/screenshot-incus.png`,
`docs/screenshot-incus-instance.png`, `docs/screenshot-podman.png`.

**Idle cost** (`docs/PERFORMANCE.md`): about 80 MB RSS and 0–1 % of a core with the window open,
against 281 MB and 38 % for the installed Machine Lab it replaces. The running-dot pulse animation
(which kept the frame clock running for every running row), the GL renderer's shader heap, the
blurred CSD shadow and the blinking cursor are gone; per-page timers only run while the page is on
screen.

## Build

```sh
meson setup build && ninja -C build       # or: meson compile -C build
meson test -C build                        # 12 tests: machines, QMP, clipboard, display, Incus client/model/restart, Podman, the whole window
./build/orchard                            # finds ../launcher/run-vm.sh; MACHINE_LAB_LAUNCHER overrides
```

Requires Vala, Meson/Ninja, GTK 4 (>= 4.12), Granite 7, libsoup 3, JSON-GLib, libsecret and GIO Unix
development packages. `-Dwingpanel=enabled` also builds the Wingpanel indicator (installs under
`/usr/lib`, so it needs a root install; `install-orchard.sh` disables it for `~/.local`).

Environment: `ORCHARD_RENDERER=gl|ngl|vulkan` overrides the cairo default; `INCUS_SOCKET` overrides
the saved socket preference; `ORCHARD_PODMAN` overrides the `podman` binary; `MSERIES_VM_DIR`
overrides `~/vms`; `ORCHARD_SCREENSHOT=<png>` with `ORCHARD_SCREENSHOT_PAGE=machines|incus|podman|<name>`
renders the window to a file (no screenshot tool exists on this Wayland desktop).

Data: machines in `~/.config/machine-lab/machines.ini` and `~/.local/share/machine-lab/`, guests
managed by `mseries/vms/mseries-vm` in `~/vms/*/vm.conf`; Incus preferences in
`~/.config/orchard-incus/preferences.ini`, metric history in `~/.local/state/orchard-incus/metrics`.
API keys use Secret Service. The paths are the ones the two apps used, so nothing is migrated.

## Layout

`src/main.vala` (application, window, sidebar, presets, `orchard://` navigation, command dispatch),
`src/sidebar.vala` (row types), `src/incus-page.vala` (Incus home page, instance page, create
dialog), `src/entry.vala` (entry point). Machines: `src/machine.vala`, `src/page.vala`,
`src/viewer.vala`, `src/display.vala`, `src/clipsync.vala`, `src/snapshots.vala`, `src/images.vala`,
`src/unattend.vala`, `src/virtiowin.vala`, `src/windows-ui.vala`, `src/macexp.vala`, `launcher/`.
Incus and Podman: `src/IncusClient.vala`, `src/Instance.vala`, `src/Dashboard.vala`,
`src/ResourceBrowser.vala`, `src/CommandPalette.vala`, `src/LogViewer.vala`, `src/MountsWindow.vala`,
`src/SystemWindow.vala`, `src/ImagePullWindow.vala`, `src/DeviceEditor.vala`, `src/ModelService.vala`,
`src/ModelBridge.vala`, `src/SandboxesWindow.vala`, `src/PodmanClient.vala`, `src/PodmanPage.vala`,
`src/PodmanDetails.vala`, `src/Indicator.vala` (Wingpanel). Guides: `docs/USER-GUIDE.md` (machines),
`docs/ORCHARD-FOR-INCUS-README.md` and `docs/UPSTREAM-PARITY.md` (Incus feature background),
`ROADMAP.md`, `CHANGELOG.md`. Package: `bash mseries/orchard/build-deb.sh`.

**Not carried over from Orchard for Incus:** the instance list's search, type filter, sort order,
group-by-label and bulk select/start/stop/delete. The sidebar lists instances by name; the command
palette (Ctrl+K) searches them. **Not verified in this merge:** a full guest install and boot end to
end, the Wayland keyboard path of the Display tab, and the Wingpanel indicator (built, not installed).
Provenance: Machine Lab (`mseries/machine-lab`, started as the Codex `native-vm-poc` spike) and
Orchard for Incus (`mseries/orchard-incus-native`, inspired by andrew-waters/orchard; see `NOTICE.md`).
