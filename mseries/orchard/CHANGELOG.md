# Changelog

## 1.0.0 (2026-10-21): Orchard
- Machine Lab and Orchard for Incus are one app, Orchard (`com.github.techmore.orchard`, Orchard's icon and `orchard://` links), built on Machine Lab's window: one sidebar with the sections YOUR MACHINES / NEW — NOT INSTALLED (unchanged), INCUS (a home row with dashboard, statistics and tools, then one row per container or VM) and PODMAN (one row, the page lists containers, images and volumes). Incus pages follow the Machines design: hero, status pill, spec cards, action buttons, tabs Overview / Statistics / Configuration / Logs / Snapshots, the More menu with Clone, Export Backup, Mount Folder, Publish Port, Attach Network and Connect Local Model. Orchard's REST client (ETag-checked configuration, snapshots, restore, clone, backup export, journals, statistics history, image pull, device editor, resource browser, model endpoints, sandboxes, command palette) and its Podman client, page and details window are kept; Machine Lab's CLI-based Incus panel is gone.
- Idle CPU: 37.6 % of a core and 281 MB RSS for the installed Machine Lab, 0.3 % and 82 MB for Orchard launched from its desktop file (`docs/PERFORMANCE.md`). The pulsing running-dot animation kept the frame clock running for every running row; the GL renderer, blurred CSD shadow and cursor blink are replaced as in the Claude client; per-page timers run only while the page is on screen; hidden pages defer their widget updates.
- `mseries/install-orchard.sh` installs under `~/.local`, removes the Machine Lab and Orchard for Incus entries and launchers, moves the dock pin, and restarts the dock so the icon is right.
- Not carried over: the instance list's search, type filter, sort order, group-by-label and bulk actions (the command palette searches instances). Preferences and metric history keep their `orchard-incus` paths; machines keep their `machine-lab` paths.

## 0.11.0 (2026-10-21)
- Display, resize: the guest's screen follows the Display tab. Machine Lab asks QEMU's D-Bus display (`org.qemu.Display1.Console.SetUIInfo`) for the window's size, which QEMU puts into the virtual monitor's EDID (virtio-gpu / virtio-vga), and the guest picks it up as a monitor change. Sizes are rounded to a multiple of 8, kept between 640x480 and 7680x4320, sent only after the window has been still for 0.4 s, at most once a second, and not when within 16 px of what the guest already has (so a window drag does not redo the guest's desktop layout dozens of times). The toolbar button next to full screen turns it off. Display devices that cannot resize (ramfb for Windows setup) are detected and left alone.
- Display, stream: with the D-Bus display the screen is pushed by QEMU (`Scanout` for the whole screen, `Update` for the changed rectangle) instead of polled with `screendump` at 30 fps, so an idle guest costs nothing and a changing one is shown as it changes (painting is capped at about 60 per second). Pixel formats from QEMU (x8r8g8b8, a8r8g8b8, the byte-swapped 32 bit ones, 24 bit and 16 bit) are converted to one opaque BGRA picture; malformed or oversized data is rejected, not trusted. If the D-Bus display is not there (the machine started without it, or QEMU is still starting) the old `screendump` polling stays as the fallback.
- Display, cursor: the guest's hardware cursor shape (`CursorDefine`, which never appears in a screendump) is used as the pointer over the screen, so the pointer looks right and does not wait for the guest to draw it.
- Machines now start with `-display dbus,p2p=on` whether or not clipboard sharing is on (`MACHINE_DBUS=on` for the native launcher, `MSERIES_VM_DBUS_DISPLAY=on` for `mseries-vm`; nothing changes for other users of the launchers). The clipboard and the display share the machine's single D-Bus control connection, because QEMU serves one control client at a time.
- Tests: the real `DisplayBridge` against a fake QEMU on socketpairs (console discovery, `RegisterListener` with fd passing, Scanout, Update, Disable, cursor, `SetUIInfo`, unsupported display, loss and reattach), the pixel conversion for every supported format with stride, clipping and truncated data, and the resize planner (31 cases). Also run once against a real QEMU 10.2.1 started paused (`-S`, no guest code): console found, listener registered, the 640x480 placeholder screen arrived as a Scanout, `SetUIInfo` was accepted, and the clipboard registered on the same connection.
- Not done: audio (virtio-sound is attached but nothing plays it), WebRTC / remote viewing, shared-memory and DMABUF scanouts, Wayland keyboard verification.

## 0.10.0 (2026-10-21)
- Clipboard, host to guest (text): the machine can now paste what you copied here. Cause found in QEMU's and spice-vdagent's sources: QEMU forwards the D-Bus grab serial unchanged to the guest agent, which accepts a client grab only when the serial equals its own counter (0 on a fresh agent connection), and silently drops anything else. Machine Lab used `1` for its first grab, so every first host copy was dropped and the guest never asked for the data. The serial counter now follows the protocol: it restarts at 0 whenever QEMU calls Register (QEMU does that each time the guest agent connects), advances with every grab from either side, and a tie goes to the host.
- After a session reset (guest agent reconnect, login) and when sharing starts, the current host text is offered again, so a copy made earlier is not lost.
- Loop prevention: text the guest just gave us is not sent back (recognised by content as well as by the write itself), and a guest clipboard manager re-owning text it just pasted does not rewrite the host clipboard. A newer host copy cancels a slower guest fetch. One copy reported several times by the toolkit makes one grab.
- Text over 1 MiB is not transferred in either direction (a status toast says so). QEMU waits for the host while the guest pastes, so a host clipboard owner that does not answer within 3 s is given up on.
- Settings: "Paste from this computer into the machine" and "Copy from the machine to this computer" switches (app-wide, live, in `~/.config/machine-lab/settings.ini`, both on by default once sharing is enabled).
- Images were advertised but QEMU only ever carries text, so the image path is gone.
- Tests: the real bridge talks D-Bus over a socketpair to a fake QEMU that models `ui/dbus-clipboard.c` and spice-vdagentd's serial rules (23 cases, `meson test`). Not yet verified against a live guest.
## 0.9.0 (2026-10-21)
- Windows guests: a Settings card downloads the pinned virtio-win 0.1.302 ISO on request (HTTPS only, SHA-256 and size checked, failed or corrupt downloads are deleted) and attaches it with a generated `autounattend.xml` disc. The answer file loads `viostor`, `vioscsi`, `NetKVM` and `vioinput` in the windowsPE pass and stages the full driver set in specialize (DriverPaths plus a pnputil fallback), with an optional local account and an opt-in, confirmed disk wipe. Only machines that are not installed and not running are changed. Unit tests cover the generator (XML validity, ARM64/amd64 driver paths, escaping, defaults), the media list and the download failure states (#265).

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
