# macOS trace runbook — the last unknown for dock DP tunneling

Updated 2026-10-16 after the [DP-IN/AUX audit](DPIN-AUX-AUDIT.md).
**Preparing this capture is safe on Linux; executing it requires a second
computer and a reboot into macOS under m1n1.** No such boot has been performed
for this audit. Do not execute the capture without the owner's approval.

Goal: learn three things that no amount of Linux-side source reading can give us,
by tracing macOS driving the WD22TB4 on this exact machine.

1. **How the DCP is told to drive a tunnelled DP endpoint.** Today Linux calls
   `dptxport_connect(service, core=0, atc=<dptx-phy>, die=<dptx-die>)` only for
   Type-C DP Alt Mode (`apple_connector_oob_hotplug` -> `dcp_dptx_connect_oob`).
   For a USB4 tunnel the DCP must be started some other way, and the remote-port
   encoding may differ.
2. **How HPD/AUX flows.** In a tunnel the sink's HPD and the AUX channel come
   back through the USB4 path, not the ATC PHY's AUX. We need to see what macOS
   does with them.
3. **The crossbar programming for `dpin0`/`dpin1`.** Which registers/order, and
   which DP IN adapter index a given tunnel uses.

## Prerequisites

| Need | Status here |
|---|---|
| m1n1 with the proxy (the Mac already boots it) | present — `/boot/m1n1/boot.bin`, m1n1 tree at `~/m1n1-build/m1n1` |
| proxyclient Python deps (`construct`, `pyserial`) | **done** — `bash mseries/fairydust/usb4/m1n1-trace-deps.sh` (vendored off-system) |
| DCP / DP-IN tracers | `proxyclient/hv/trace_dcp.py` plus this directory's `trace-dpin.py`; offline fixture tests pass, actual capture unverified |
| Exact DP-IN addresses / Apple ATC index | Obtain `inspect-dpin-adt.py` output; resolve the target by physical crossbar address rather than guessing the Apple ATC index |
| A **second computer** on the USB proxy port | not attached; required — the Mac cannot drive its own m1n1 proxy |
| The **macOS iBoot payload** for `run_guest.py` | not on the ESP (`/boot/asahi/all_firmware.tar.gz` is the installer's factory/camera set, not macOS) |

The second host, payload and address mapping are capture prerequisites. The
original `trace_dptx.py` only traces standalone `dptx-phy`/`lpdptx-phy*` nodes;
it does not capture the missing ATC DP-IN blocks. `trace_dcp.py` defaults to
`dcp0`, so select the external controller explicitly.

## Confirm the address mapping without rebooting

From the regular host Terminal (this chat runner cannot elevate with sudo):

```bash
sudo python3 /home/sdolbec/wt-dockvideo/mseries/fairydust/usb4/inspect-dpin-adt.py \
  > /home/sdolbec/dptunnel-logs/dpin-adt.json
```

This only reads preserved ADT RAM and outputs filtered device metadata. It
does not read guessed DP-IN MMIO. If `/dev/mem` policy refuses the read, save
the error and obtain the ADT from the m1n1 proxy during the approved capture;
do not change kernel security settings or load modules to work around it.

## Procedure (shape; confirm the two flagged items first)

On the **second computer**:

```
git clone --depth 1 https://github.com/AsahiLinux/m1n1        # or reuse this Mac's
bash mseries/fairydust/usb4/m1n1-trace-deps.sh                # vendors construct+pyserial
export PYTHONPATH=$HOME/.local/share/m1n1-proxyclient/site:$PWD/proxyclient
python3 proxyclient/tools/run_guest.py --help                 # sanity check
```

1. Boot the Mac into m1n1 (the normal Linux boot path already does this) with the
   dock and its monitor attached.
2. Connect the second computer to the Mac's USB proxy port.
   **[confirm]** which port the t6000 m1n1 proxy uses on this 14" M1 Pro.
   Use a different physical port from the dock: m1n1 removes the proxy port's
   ACIO/ATC/DP-IN nodes from the guest ADT. Stop if the target nodes are missing.
3. Obtain the macOS iBoot Mach-O. **[confirm]** the current Asahi method for
   pulling it out of the macOS Boot volume (the installer does this behind the
   scenes; `/boot/asahi` here only holds the restore/factory set).
4. Copy this directory's `trace-dpin.py` to the second host. Confirm the
   guest's external DCP node/alias resolves to physical `0x28cc00000`, and
   confirm the dock crossbar's address from the ADT (Linux uses
   `0xb0304c000`). Run **one guest with both hooks**, not two proxy clients:

```
# Example only after confirming these two target selectors against the ADT:
TRACE_DCP=dcpext1 TRACE_DPIN_XBAR=0xb0304c000 \
python3 proxyclient/tools/run_guest.py \
  -l dpin-capture.log \
  -m /path/to/trace-dpin.py \
  -m proxyclient/hv/trace_dcp.py \
  <macOS-iBoot>.macho 2>&1 | tee dpin-capture-console.log
```

   The guest runner supports repeated `-m`. Verify the console lists
   `DPIN_TRACE` ranges for the selected crossbar **and both** DP-IN nodes.
   If a hook reports an error, abort the capture rather than continuing from
   the fallback shell with missing instrumentation. The hook validates its
   complete target set before registering a partial trace.

5. Once macOS is up and the dock's display is live, unplug/replug the monitor so
   a clean attach/detach sequence is in the log. Save the whole log.

## What to send back

- The full `trace_dcp.py` log around the dock's DP sink appearing/disappearing
  (the AFK/ASC frames, not a summary).
- The `trace-dpin.py` MMIO records around the same window, including the
  `DPIN_TRACE` node/address/range inventory from the console.
- `dcpext1`'s DT node from macOS's perspective if it is easy to dump.
- The target DP-IN nodes' `reg`, parent relationships, interrupt properties
  and transport indices; the actual dock adapter used by HDMI; the raw
  DCP `connectTo` / `validateConnection` requests and replies.

From that we can identify the DP-IN enable/reset/AUX sequence and correlate
its ordering with the DCP transport request and router DPRX completion.
Do not infer a firmware IPC selector from the older `dcpav.py` constants:
that helper uses a different target layout. See the audit for the limits of
the public `core0 -> dpin0` observation.

## What has already been ruled out (so nobody re-does it)

- **Static firmware analysis on the Linux side:** the DCP/dcpext firmware is not
  in the Linux vendor firmware. `/boot/vendorfw/firmware.tar` (337 entries) holds
  Broadcom Wi-Fi, ISP `.dat` and HW-config files only; `/boot/asahi/all_firmware.tar.gz`
  is the installer's factory/camera set. The DCP firmware is loaded from the
  macOS volume at boot, so a static dump needs macOS (or APFS access to its
  volume) too.
- **Forcing DP Alt Mode on the dock:** the CD321x firmware picks USB4 and Linux
  has no mode control (see `README.md`).
- **The built-in HDMI and a direct USB-C adapter:** supported but explicitly out
  of scope for this work.

## Meanwhile

Everything that does not need this trace is tracked in `DP-TUNNEL-RE.md`
section 6 (experiments 1-5): the crossbar route is already buildable, and the
trigger can be exercised by hand through the debugfs `force_link` attribute, so
experiment 1 can be judged without the trace.
