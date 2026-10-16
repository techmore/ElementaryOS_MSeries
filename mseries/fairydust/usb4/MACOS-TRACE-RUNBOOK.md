# macOS / m1n1 trace: prerequisites and capture sequence

Updated 2026-10-16. Start with the complete
[cutover checklist](MACOS-CUTOVER-CHECKLIST.md), including cable planning,
ordinary macOS collection, acceptance gates and publication rules.

**Current blocker:** only the target Mac is available. The Python recorder
must run on another computer while this Mac runs macOS under m1n1. A normal
macOS boot can collect the baseline, but cannot record its own MMIO trace.

## Corrections to older recipes

- The guest payload is matching XNU's extracted **kernelcache.macho**,
  not iBoot, build/m1n1.macho, or Asahi's /boot/m1n1/boot.bin bundle.
- Run one guest with multiple hooks, not two competing primary proxy clients.
- trace_dptx.py omits atcN-dpin0/1 and the crossbar. Use trace-dpin.py.
- An existing Linux m1n1 install does not prove a correct macOS guest boot
  context. The OS volume, firmware and kernel must match.
- The Linux ADT read already failed under the owner's sudo with EPERM.
  Use the macOS IODeviceTree export or proxy ADT; don't weaken /dev/mem.

## Prepare the second host first

Use a Linux/macOS recorder independent of the dock's keyboard, network and
storage. Prepare Python, construct and pyserial, plus a matching m1n1
binary/client source tree and its recorded revision. Our dependency helper
vendors Python modules without installing them system-wide:

~~~bash
git clone --recursive https://github.com/AsahiLinux/m1n1.git
# Build using that tree's README for the host architecture/toolchain.
git -C m1n1 rev-parse HEAD
M1N1="$PWD/m1n1" bash /path/to/usb4/m1n1-trace-deps.sh
~~~

Save the printed PYTHONPATH. Dependencies on the target are not automatically
present on the recorder. Transfer the reviewed tools too: inspect-dpin-adt.py,
trace-dpin.py, trace-dcp-raw.py and collect-macos-dock.sh. Record hashes of
the hooks and m1n1 build outputs. The extracted local source tree without
Git history is not a provenance substitute for a recorded upstream commit.

The [official hypervisor guide](https://asahilinux.org/docs/sw/m1n1-hypervisor/)
currently names macOS 13.5 (M1/M2) and 14.8.3 (M1–M3) as supported targets.
It recommends a separate test macOS installation and describes the
Recovery/boot-policy changes. Review exact volume UUIDs and a recovery plan
with the owner before any change. The willingness to switch OSes does not
identify the volume to modify. This runbook installs or modifies nothing.

Copy the active test install's confirmed Preboot kernelcache to the recorder
(selection and copy steps are in the cutover checklist). Extract it there:

~~~bash
img4tool -ep out.im4p /path/to/PRIVATE/kernelcache
img4tool -eo kernelcache.macho out.im4p
~~~

Record build/hash and extraction output locally. Keep Apple's kernelcache
and firmware off public GitHub. A KDK is optional for this initial trace.
Recheck supported versions when actually preparing the guest.

## Cable and proxy setup

Keep the existing USB4 dock and HDMI connected. Connect the recorder directly
to a **different** target Thunderbolt port with a USB data cable. Use
independent power if required. The selected proxy port is removed from the
guest ADT; using the dock port defeats the capture.

The [proxy guide](https://asahilinux.org/docs/sw/m1n1-user-guide/) describes
the two serial interfaces and M1N1DEVICE. Save the secondary interface's guest
console to a separate logfile. Reserve the primary interface for one proxy
client at a time. Verify recorder serial permissions before the guest boot;
don't assume a ttyACM number or macOS device suffix.

On the recorder:

~~~bash
umask 077
TRACE_DIR="$PWD/wd22tb4-trace-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$TRACE_DIR/PRIVATE" "$TRACE_DIR/REVIEW"
export M1N1DEVICE=/CONFIRMED/PRIMARY/PROXY/DEVICE
~~~

Once the approved proxy boot route is ready, chainload the matching tree's
m1n1 build to synchronize its ABI with the Python client:

~~~bash
python3 /path/to/m1n1/proxyclient/tools/chainload.py -r \
  /path/to/m1n1/build/m1n1.bin
~~~

This is a future command on the recorder, not the live Linux target.
Follow the guide's boot-context preparation first. Save errors rather than
overwriting the working Asahi boot bundle.

## Save original ADT and resolve targets

Run proxyclient/tools/shell.py on the recorder. At its Python prompt:

~~~python
from pathlib import Path
Path('/ABSOLUTE/TRACE_DIR/PRIVATE/original-adt.bin').write_bytes(u.get_adt())
~~~

Substitute the actual capture path. This reads ADT metadata through the
proxy, not guessed DP-IN MMIO. Exit the primary proxy shell before running
another primary client. In an ordinary recorder terminal:

~~~bash
python3 /path/to/usb4/inspect-dpin-adt.py \
  --from-file "$TRACE_DIR/PRIVATE/original-adt.bin" \
  > "$TRACE_DIR/REVIEW/original-dpin-metadata.json"
~~~

Confirm the target ATC by translated registers and parent links.
Linux's xbar is 0xb0304c000; proposed DP-IN addresses 0xb01e50000 and
0xb01e58000 remain candidates until the original metadata confirms them.
Resolve both DP-IN nodes, ACIO/PHY/xbar parents, interrupts, clocks and gates.

Resolve DCP's alias/node against controller MMIO 0x28cc00000; don't assume
dcpext1 has that meaning on every firmware. The context section of the
metadata JSON includes selected DCP/DART/ACIO/PHY node ranges. Confirm the
DCP and display DART aliases required by the upstream tracer too.

Plan external power/clock coverage using the actual ADT. Our DP-IN hook
traces only DP-IN0/1 and xbar, not all PMGR/ACIO/ATC registers. Select any
required dependency ranges explicitly before guest start. Stock trace_pmgr.py
and trace_atc.py contain fixed addresses/ports; don't load them blindly.
If this remains unresolved, label the capture partial.

## Launch one guest, initially stopped

After selectors, guest cache and boot context are confirmed:

~~~bash
# Example selectors matching Linux: validate them against the original ADT.
export TRACE_DCP=dcpext1
export TRACE_DPIN_XBAR=0xb0304c000
set -o pipefail
python3 -u /path/to/m1n1/proxyclient/tools/run_guest.py \
  -S -l "$TRACE_DIR/PRIVATE/hypervisor.log" \
  -m /path/to/usb4/trace-dpin.py \
  -m /path/to/m1n1/proxyclient/hv/trace_dcp.py \
  -m /path/to/usb4/trace-dcp-raw.py \
  /path/to/kernelcache.macho \
  -- 'debug=0x14e serial=3 apcie=0xfffffffe -enable-kprintf-spam wdt=-1 clpc=0' \
  2>&1 | tee "$TRACE_DIR/PRIVATE/console.log"
~~~

-S stops at the hypervisor shell before starting the guest. Hook order matters:
raw DPTX logging wraps classes created by trace_dcp.py. The inspected upstream
validateConnection decoder prints fields without a raw hex dump; our hook
preserves those bytes and other DPTX service payloads before decoding.

At the stopped shell, save the guest ADT after proxy-port removal:

~~~python
from pathlib import Path
Path('/ABSOLUTE/TRACE_DIR/PRIVATE/guest-adt.bin').write_bytes(hv.adt.build())
~~~

Before starting, require:

- DPIN_TRACE entries for the intended xbar and **both** DP-IN nodes.
- Correct external DCP/DART paths, without internal-display substitution.
- DPTX_RAW_READY, with timestamps enabled.
- No traceback, missing node, hook failure or unsupported firmware.

On failure, **do not press Ctrl-D**: run_guest.py offers a fallback shell and
can otherwise launch the guest with incomplete instrumentation. Leave the
guest unstarted and fix the failed precondition. When checks pass, Ctrl-D
starts it. Preserve initial boot logs; hotplug alone may miss power/reset.

## Working guest and acceptance

1. Require a visible Amazon Basics picture through WD22TB4 HDMI.
   Keep the built-in display available. A failed guest is distinct from a
   successful native macOS baseline.
2. Run collect-macos-dock.sh inside the guest with state guest-attached,
   saving its output separately from the native macOS data.
3. Record mode, input, physical topology and event times on the recorder.
4. If boot already captured a complete working transition, leave cables alone.
   Otherwise use one monitor power cycle or one HDMI detach/reattach at the
   monitor end. Keep USB4 connected.
5. Check for actual DP-IN MMIO events, raw DPTX command/reply bytes and
   correlated HPD/AUX/link traffic. Registering tracers is not enough.
6. Check overflow, decode errors and loss. Copy both logs, both ADTs, provenance
   and guest baseline to a second location before shutdown.

Use sections F/G of the cutover checklist for the full acceptance gate and
publication review. Keep raw ADT, full registry, kernelcache and firmware
local. Publish reviewed engineering evidence and hashes. Later Linux changes
follow CI and the owner-approved side-by-side kernel process.

## Validation and primary references

Offline fixtures pass; no macOS guest or trace is hardware-qualified here.
The [provenance record](evidence/2026-10-16-tool-provenance.json) identifies
the inspected local files independently of the upstream main revision.
Sources checked 2026-10-16:

- [Asahi hypervisor setup](https://asahilinux.org/docs/sw/m1n1-hypervisor/).
- [Proxy guide](https://asahilinux.org/docs/sw/m1n1-user-guide/).
- [Loader source](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/tools/run_guest.py)
  for payload loading, multiple hooks, -S and fallback behavior.
- [Hypervisor source](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/m1n1/hv/__init__.py)
  for proxy-port removal and tracing APIs.
- [DCP tracer](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/hv/trace_dcp.py)
  for aliases, DART setup and raw/decoded payload coverage.
