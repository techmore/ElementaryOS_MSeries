# Clipboard sharing: what was verified (2026-10-19)

Machine Lab shares the clipboard through QEMU's D-Bus display (`org.qemu.Display1.Clipboard`), not by speaking the SPICE
agent protocol itself: QEMU runs `-display dbus,p2p=on` plus a `qemu-vdagent` chardev on a virtio-serial port named
`com.redhat.spice.0`, and Machine Lab is a D-Bus peer (a socketpair handed over with QMP `getfd` + `add_client "@dbus-display"`).

Tested against the elementary OS 9 ARM64 guest from the CI image (it already ships `spice-vdagent` 0.23, Wayland session):

| Direction | Result |
| --- | --- |
| guest to host, text | **works**: copy in the guest Terminal, Machine Lab logs `guest grab` then `fetched 96 bytes of text/plain;charset=utf-8` |
| host to guest, text | **was not working; cause found (see "The host-to-guest bug" below), fix tested only against a fake QEMU, not yet re-run on a live guest** |
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

## The host-to-guest bug (found 2026-10-21 from the QEMU and spice-vdagent sources)

Symptom above: the host grab is accepted by QEMU, the guest never requests the data. The cause is the grab **serial**.

- QEMU (`ui/dbus-clipboard.c`) takes our `Grab(selection, serial, mimes)`, checks `serial >= current serial`, and hands the info to the
  vdagent chardev (`ui/vdagent.c`, `vdagent_send_clipboard_grab`), which writes `info->serial` **unchanged** into `VD_AGENT_CLIPBOARD_GRAB`.
- The guest's `spice-vdagentd` (`src/vdagentd/vdagentd.c`, `do_client_clipboard`) keeps a counter `N` per selection. It accepts a client
  grab only if `serial == N` (then `N++`) or `serial == N - 1` (the client wins a tie). Anything else is dropped with only a debug line,
  `grab discard, serial %u != session serial %u`, so the agent never claims the X selection and never sends `VD_AGENT_CLIPBOARD_REQUEST`.
- `N` is 0 whenever a client connects (`do_client_capabilities` zeroes it). QEMU resets its side in `vdagent_chr_recv_caps`
  (`qemu_clipboard_reset_serial`), which calls our `Register` (the D-Bus `Register` doc: "The server can reinitialize the session as well
  (to reset the counter)").
- Machine Lab used `max(own, guest) + 1` starting from 0, so its first grab was `1` while the guest expected `0`: dropped. A copy in the
  guest first would move the counters into step (guest grabs `0`, then our `1` equals `N`), which fits the observation that only the
  host-first test failed. This is derived from the sources, not yet observed on a live guest.
- Fix (src/clipsync.vala, class `ClipboardSync`): the counter restarts at 0 in our `Register` handler, our grab uses the counter value and
  increments it, a guest grab sets it to `guest serial + 1`, a guest grab with our own latest serial is a tie that we win, lower ones are
  stale. The bridge also re-offers the current host text after every session reset.
- The size-0 `RELEASE` that the guest journal rejects (`invalid message size: 0 for message type: 9`) is, most likely, QEMU sending a release while
  its `caps` are cleared during that reset; it is noise from the reset, not the cause (unconfirmed).

To confirm on a live guest (not done in this change, which did not boot a VM): start a machine with Share clipboard on, copy text on the
host as the very first action, then paste in the guest; `journalctl -u spice-vdagentd` with `-d` should no longer show `grab discard`.
`clipboard-peer.py` now sends serial 0 for its single grab (a fresh agent connection counts from 0).
