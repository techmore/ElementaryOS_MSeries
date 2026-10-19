# Clipboard sharing: what was verified (2026-10-19)

Machine Lab shares the clipboard through QEMU's D-Bus display (`org.qemu.Display1.Clipboard`), not by speaking the SPICE
agent protocol itself: QEMU runs `-display dbus,p2p=on` plus a `qemu-vdagent` chardev on a virtio-serial port named
`com.redhat.spice.0`, and Machine Lab is a D-Bus peer (a socketpair handed over with QMP `getfd` + `add_client "@dbus-display"`).

Tested against the elementary OS 9 ARM64 guest from the CI image (it already ships `spice-vdagent` 0.23, Wayland session):

| Direction | Result |
| --- | --- |
| guest to host, text | **works**: copy in the guest Terminal, Machine Lab logs `guest grab` then `fetched 96 bytes of text/plain;charset=utf-8` |
| host to guest, text | **not working yet**: Machine Lab sends the grab (`host clipboard changed`), QEMU accepts it, but the guest never asks for the data (`xclip -o` in the guest just waits; no `Request` reaches Machine Lab) |
| images, files | **not possible through this channel today**: QEMU's D-Bus clipboard only handles `text/plain;charset=utf-8` (`dbus_clipboard_qemu_request` returns early for any other type) |

Findings worth keeping:

- QEMU's `-display dbus,p2p=on` serves **one client at a time**: each `add_client` takes over the exported objects, so a second
  connection (even a debugging probe) silently breaks the first one (`Object does not exist at path`). Machine Lab starts exactly one
  bridge per machine.
- `Register` must be called asynchronously: QEMU calls back into the client while handling it (it resets the session and calls the
  peer's `Register` and `Release`), so a blocking call from the main loop deadlocks until the 25 s timeout.
- The QMP socket serves one client at a time as well; a debugging tool that keeps it open blocks `mseries-vm` and the app.
- The guest journal shows `spice-vdagentd: read: invalid message size: 0 for message type: 9` followed by `lost spice client connection,
  reconnecting` whenever QEMU sends a clipboard RELEASE with no selection field. That resets the agent link each time Machine Lab
  registers; it is a QEMU/agent mismatch for this agent version. Likely related to the host-to-guest failure, not proven.
- Wayland: `spice-vdagent` is an X11 agent (`spice-vdagent -x`); clipboard hand-off between Xwayland and Wayland apps is up to the
  compositor. Try an X11 session in the guest to separate the two causes.

`clipboard-peer.py QMP_SOCK TEXT SECONDS` is a stand-in host peer used to see the raw D-Bus traffic (it needs `python3-gi`).
