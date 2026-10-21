# Changelog

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
