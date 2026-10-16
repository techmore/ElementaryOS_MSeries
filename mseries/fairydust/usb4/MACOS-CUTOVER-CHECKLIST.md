# WD22TB4 video: complete cutover and evidence checklist

Updated 2026-10-16. Target: MacBookPro18,3 / M1 Pro / j314s, Dell WD22TB4,
dock HDMI → HDMI cable → powered Amazon Basics monitor. Repository:
[techmore/ElementaryOS_MSeries](https://github.com/techmore/ElementaryOS_MSeries).
Working branch: `docs/dock-video-decision`.

## Current authorization: NO reboot or power cycle

The owner explicitly forbids rebooting or power-cycling the M1 Pro. **Do not
execute the shutdown, startup-picker, macOS cutover or guest-boot steps below.**
This checklist is retained as future reference only; the earlier cutover plan
is no longer authorized for the current session.

Next work is read-only live enumeration and recovery diagnosis, preserving the
running system. The Neo can support bounded diagnostics and offline analysis;
it cannot instrument the already-running M1 Pro with a boot-time m1n1
hypervisor. Full MMIO capture requires a target boot and is therefore outside
the current authorization. Remote checks belong to delegated workers with
hard timeouts; the primary chat must never wait on SSH. Report active progress
every 30 seconds. Revisit boot-dependent collection only after fresh owner
authorization.

## Read this before switching operating systems

The owner has now supplied a **MacBook Neo recorder**, successfully reached
over SSH; see [recorder setup and verified checks](NEO-RECORDER-SETUP.md).
The earlier single-computer blocker is resolved. A normal macOS boot can
collect the missing device-tree metadata and prove whether this exact HDMI
chain works. It cannot record macOS register accesses through the Python
m1n1 hypervisor client: that client must run on another computer while this
Mac runs the guest. The Neo's macOS 26.6.2 is its recorder OS, not the
hypervisor guest version that must be confirmed on this M1 Pro.

**Future baseline procedure:** an ordinary macOS visit with the dock and HDMI left
attached, using `collect-macos-dock.sh` below. No security downgrade or boot
modification is needed for that visit. Native macOS tools are sufficient.

**Future trace prerequisites:** recorder tools have passed smoke checks, but
the target's installed macOS build is unconfirmed, and no matching XNU kernelcache has
been selected or extracted. A successful capture may expose more than one
missing operation; we cannot promise an immediate working Linux driver.

The older recipe incorrectly requested an **iBoot payload** and, in one
place, passed m1n1's own Mach-O as the guest. Those instructions are
superseded. `run_guest.py` loads **XNU's extracted `kernelcache.macho`**.
The normal Asahi `boot.bin` is not that file. The original DPTX tracer also
omits the separate `atcN-dpin0/1` blocks. Follow this checklist and the
corrected [trace runbook](MACOS-TRACE-RUNBOOK.md).

## What we know, and what each new artifact must answer

| Question | Current evidence | Required collection / decision |
|---|---|---|
| Does this exact dock HDMI chain work on macOS? | Owner confirms monitor power/input; Linux has no picture | Visible macOS picture, selected input, resolution/refresh and registry state; do not substitute built-in HDMI |
| Where are DP-IN0/1, and which Apple ATC owns the current dock port? | Linux crossbar is `0xb0304c000`; public same-model names exist | Full IODeviceTree plist locally, filtered translated `reg`, parents, interrupts, clock/power IDs from this Mac |
| Which external DCP is used? | Linux controller at `0x28cc00000` | macOS DCP node ranges and related DART/transport metadata; confirm alias before tracing |
| How is DP-IN powered/reset and enabled? | No validated implementation sequence | Trace from guest boot, including crossbar and both DP-IN blocks; identify any operations outside those ranges |
| How does DCP select the tunneled endpoint? | Linux forced connect reaches DCP, then APCALL22/24 | Raw DPTX connect/validate command and reply bytes, service identity and firmware/build |
| Which host/dock adapters carry HDMI? | Host `0:5/0:6`, dock `1:13/1:14`; physical mapping unproven | Correlated USB4/IOService topology, DCP target and HPD events; do not assign HDMI to `1:14` by assumption |
| Is there a real AUX/DPCD response? | Linux tunnel activation logs are only route programming | Successful macOS link/capability evidence; later a fresh Linux read with bypass off and matching tuple |

The public [audit](DPIN-AUX-AUDIT.md) contains the source analysis, rejected
assumptions and exact Linux probe results. A picture on macOS establishes a
working reference, not that the current Linux DP-IN path works.

## Cable plan: keep the dock where it is

For the ordinary macOS visit:

1. Leave the Mac→WD22TB4 USB4 cable connected to its current Mac port.
2. Leave the dock→monitor HDMI cable connected at both ends.
3. Keep the monitor powered on with that HDMI input selected. Keep the Mac
   lid open so its built-in display remains available if the dock has no picture.
4. Do not change dock firmware, video sockets, monitor or cable during the baseline.
5. Record the physical Mac port in `observations.txt`: right side, left side
   nearest hinge, or left side nearest front. Software's ATC indices are not
   physical labels until correlated.

The first capture needs **zero cable changes**. If macOS produces a picture,
an optional monitor power-off/on pair can add HPD evidence without moving a
cable; some monitors retain HPD when off, so lack of a transition is not a
failure. If a clean HPD transition is still needed, plan **one** HDMI
disconnect/reconnect at the monitor end, while on macOS, recording times.
That is optional for the baseline; never repeatedly replug the USB4 dock.

For a later full trace, connect the recorder's USB data cable **directly to
a different Mac Thunderbolt port**, not through the dock. m1n1 exposes its
USB proxy on Thunderbolt ports; the selected proxy port is removed from the
guest device tree. Prefer a free port and retain the dock's current port.
If a port move becomes unavoidable, make it once while the target is fully
powered off, and take a new baseline for that topology. Do not lose the
working dock port by selecting it as the proxy port.

Apple's [DFU port diagram](https://support.apple.com/en-us/120694) is a
physical reference if needed. m1n1 proxy mode is a different mechanism from
DFU recovery; do not put the machine into DFU as part of evidence collection.
The [m1n1 user guide](https://asahilinux.org/docs/sw/m1n1-user-guide/)
documents the proxy interfaces and selecting `M1N1DEVICE`.

## A. Before leaving Linux

- Save open work. The Linux kernel is
  `7.1.13-elementary-fairydust-usb4-dptunnel`; retain its installed boot entry.
- Stop starting new sink probes. Another collector/watchdog may be active;
  coordinate its end before switching. Read its actual output rather than
  treating an old `ANSWERED` string as success.
- Immediately before shutdown, arm the existing bypass from the owner's
  regular Terminal. This chat runner cannot elevate because of `NoNewPrivs`:

```bash
sudo sh -eu -c 'echo 1 > /sys/module/thunderbolt/parameters/dprx_bypass; test "$(cat /sys/module/thunderbolt/parameters/dprx_bypass)" = Y; printf "DPRX bypass armed: Y\n"'
```

- Require the printed `Y`. If the command fails, leave the dock connected
  and resolve the failure first. Never unplug it during an active DPRX read.
- Shut down fully through the desktop, then select the normal macOS install
  with the startup picker. Do not suspend with the dock attached.
- Keep the collector accessible from GitHub or an existing shared storage
  location. Linux's `/home/sdolbec/...` paths are not macOS paths.

Do not retry the Linux ADT `/dev/mem` command. The owner already ran it under
sudo and got `EPERM`; the output was empty. The running configuration has
`CONFIG_STRICT_DEVMEM=y` and no `CONFIG_MTD_PHRAM`. We are not changing either.

## B. One ordinary macOS visit — exact collection commands

Use the built-in display and open Terminal. Download the reviewed script as
a file, then run it. This uses native `curl` and `bash`, avoiding a Git/Xcode
installation. To freeze the version, replace the branch in `BASE` with the
reviewed commit hash from the GitHub handoff before downloading.

```bash
CAPTURE="$HOME/Documents/wd22tb4-capture-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$CAPTURE/tools"
BASE="https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/docs/dock-video-decision/mseries/fairydust/usb4"
curl -fL --retry 2 "$BASE/collect-macos-dock.sh" -o "$CAPTURE/tools/collect-macos-dock.sh"
curl -fL --retry 2 "$BASE/inspect-dpin-adt.py" -o "$CAPTURE/tools/inspect-dpin-adt.py"
curl -fL --retry 2 "$BASE/MACOS-CUTOVER-CHECKLIST.md" -o "$CAPTURE/CHECKLIST.md"
bash "$CAPTURE/tools/collect-macos-dock.sh" "$CAPTURE/01-attached" attached
```

The collector only reads system state and writes to the new directory. It
does not request sudo, install software, run a probe, change a boot setting,
put the machine to sleep, manipulate cables, or upload anything. Each
command's stderr and exit status are retained, including denied Preboot
access. The profiler can take a little time; let it finish.

Record in `01-attached/REVIEW/observations.txt`:

- Does the Amazon Basics screen display the macOS desktop through the dock?
- Exact monitor model from its label/OSD, selected HDMI input and observed mode.
- Mac port used by the USB4 cable, dock video socket and any intervening adapter.
- Any standby/wake behavior, and whether the dock appears in System Information.
- If no picture: say so explicitly; collect first rather than trying another cable.

Open `01-attached/REVIEW/status.tsv`. `OK` means that a command ran, not that
DP-IN was found or video worked. `FAILED` or `INVALID_OR_EMPTY` needs inspection
while still on macOS. Retain successful files when another command fails.

If Python 3 is **already installed** on macOS, produce the filtered metadata:

```bash
python3 "$CAPTURE/tools/inspect-dpin-adt.py" \
  --from-ioreg "$CAPTURE/01-attached/PRIVATE/iodevicetree.plist" \
  > "$CAPTURE/01-attached/REVIEW/dpin-metadata.json"
```

If `python3` is absent or opens an Xcode installation prompt, cancel the
prompt. The essential archive is already captured. Run the same parser on
Linux or the future recorder later; no additional macOS boot is needed.
It preserves `reg`/`ranges` bytes, resolves phandles and exports only selected
hardware metadata. Real macOS validation is still required; fixtures pass.

### Optional on/off sequence without moving a cable

Only after the attached baseline finishes:

```bash
date -u '+monitor-power-off %Y-%m-%dT%H:%M:%SZ' >> "$CAPTURE/events.txt"
# Press the monitor's physical power button once; do not suspend the Mac.
bash "$CAPTURE/tools/collect-macos-dock.sh" "$CAPTURE/02-screen-off" screen-off
date -u '+monitor-power-on %Y-%m-%dT%H:%M:%SZ' >> "$CAPTURE/events.txt"
# Turn the monitor back on; wait for picture or its no-signal message.
bash "$CAPTURE/tools/collect-macos-dock.sh" "$CAPTURE/03-screen-on" screen-on
```

The comments describe manual actions; the commands do not press the button.
Record the actual action times and visible results. Skip this optional pair
if the owner wants the shortest visit. A blank desktop/wallpaper color can
be shown once macOS has a working picture, but is not an AUX test on Linux.

## C. Capture kernelcache prerequisites during the same visit

The collector saves `sw_vers`, root-volume/APFS metadata and every readable
Preboot `kernelcache` location. This avoids another visit just to discover
the build and path. The **active** macOS volume group/build must be matched;
do not select the first of several Preboot files or a Linux stub's cache.

If `kernelcache-paths.txt` has permission errors, the following is a
read-only directory search in the normal Terminal, not a boot change:

```bash
sudo find /System/Volumes/Preboot -type f -name kernelcache \
  > "$CAPTURE/01-attached/PRIVATE/kernelcache-paths-root.txt" \
  2> "$CAPTURE/01-attached/PRIVATE/kernelcache-paths-root.stderr"
```

After matching the active volume's UUID/build using the saved layout and
`diskutil info /`, set the exact existing path and copy it locally:

```bash
KERNELCACHE='/System/Volumes/Preboot/CONFIRMED-UUID/boot/CONFIRMED-HASH/System/Library/Caches/com.apple.kernelcaches/kernelcache'
sudo /usr/bin/ditto "$KERNELCACHE" "$CAPTURE/01-attached/PRIVATE/kernelcache"
shasum -a 256 "$CAPTURE/01-attached/PRIVATE/kernelcache" \
  > "$CAPTURE/01-attached/REVIEW/kernelcache-sha256.txt"
```

The placeholders are deliberate: never execute this with guessed UUIDs.
If matching is uncertain, keep the inventory and resolve it before copying
or returning to Linux. The local kernelcache is proprietary Apple content;
keep it off public GitHub. Publish its hash/build as provenance only.

The full trace uses an extracted Mach-O of this cache, not the original
IM4P container. Extraction and a compatible build can be prepared later on
the second host; see the trace runbook and the
[official hypervisor guide](https://asahilinux.org/docs/sw/m1n1-hypervisor/).
That guide currently names macOS 13.5 and 14.8.3 as supported targets. Record
the actual installed version before assuming it will run under m1n1.
Do not downgrade or update macOS merely to make this checklist pass.

## D. Before leaving macOS — baseline acceptance gate

All required baseline items must be checked, or explicitly marked missing:

- [ ] `REVIEW/platform.txt` contains macOS version/build and Mac model.
- [ ] `PRIVATE/iodevicetree.plist` and `PRIVATE/ioservice.plist` are nonempty
  and pass `plutil -lint` (the collector checks this).
- [ ] `PRIVATE/display-dock-usb.plist` is valid; inspect that the actual dock
  and external display appear, or record their absence.
- [ ] DP-IN0/1/xbar ranges are present in filtered JSON, **or** the original
  valid IODeviceTree plist is retained for later parsing.
- [ ] Written visible result, monitor/input/mode and physical port/cable facts.
- [ ] Kernelcache path access and active-volume matching are resolved, or the
  exact remaining problem is recorded. Prefer taking the verified cache now.
- [ ] Any optional power/HDMI changes have event times and before/after snapshots.
- [ ] A second copy of the capture exists on already-accessible storage or
  the future recorder, or a verified upload to storage the owner controls.
  Do not assume Linux can read macOS APFS or that `$CAPTURE` will survive a reset.

Leave the dock attached when returning to Linux. Re-arm and verify bypass
after the Linux boot before any future dock detach; module parameters do
not necessarily persist across boots. No new unbypassed probe is part of
this baseline handoff.

## E. Full trace readiness — recorder identified, guest still unqualified

| Requirement | Acceptance criterion | Current status |
|---|---|---|
| Separate recorder | Linux/macOS machine with Python, USB serial access, storage and data cable; usable without this dock | Neo reached by SSH; key login, runtime and imports verified; compiler/cable/handshake still to qualify |
| Physical topology | Dock retains one port; recorder uses another directly; original ADT confirms both | Physical port labels still to record |
| Working reference | Same dock HDMI chain produces a visible macOS picture | Not yet collected |
| macOS guest | Exact supported version/build, accessible matching volume and extracted XNU Mach-O | Version/cache not yet collected |
| Matching m1n1 | Source revision recorded; build and Python client from the same tree; ABI verified by chainload | Fresh source/build at c6a89b9 staged on Neo; no chainload yet |
| Boot route | Tested proxy entry and correct macOS boot context; recoverable existing boot entries | Not validated for a macOS guest |
| Target metadata | Confirmed xbar/DP-IN0/1 ranges, correct external DCP and DART aliases | Awaiting macOS baseline |
| Instrumentation | Both DP-IN blocks+xbar, correct DCP, raw DPTX payload hook, initial boot coverage | Offline hooks prepared; hardware untested |
| Extra dependency coverage | ADT power/clock/ACIO relationships resolved; any required PMGR/ACIO ranges explicitly selected | Unresolved until metadata is read |
| Owner-approved changes | Exact test volume, disk/UUID, security/boot changes and recovery plan reviewed | No such changes authorized/performed |

The established macOS guest setup may require a dedicated test macOS volume,
Recovery and boot-policy changes. The owner's willingness to switch OSes
does not identify a target volume or authorize overwriting the working boot
configuration. The existing Asahi boot path alone is not proof that an
arbitrary macOS cache can be launched safely from that stub. Prepare exact
commands against the real inventory before requesting approval for changes.

Do not run stock `trace_atc.py` or `trace_pmgr.py` blindly: the inspected
versions contain fixed ports/addresses. Do not use `trace_all.py` as a
substitute for an explicit plan. Before the trace boot, use the ADT to
select relevant per-port ACIO/PHY and power-state registers; preserve the
raw ADT locally so any metadata omitted from the filtered summary remains
available. If that selection is incomplete, label it a partial capture.

## F. One full trace session: mandatory evidence and stopping criteria

Detailed launch procedure is in [MACOS-TRACE-RUNBOOK.md](MACOS-TRACE-RUNBOOK.md).
Keep these together on the recorder, on storage independent of the dock:

1. Exact m1n1 revision/build hashes, guest cache hash, macOS build, tool revision,
   command line, proxy device and physical port map.
2. Original ADT before guest mutation, guest ADT after proxy-port removal,
   filtered metadata, confirmed DCP/DART identity, and trace range inventory.
3. Both console output and hypervisor logfile from **before guest start**.
   Initial boot may contain the power/reset sequence that hotplug alone misses.
4. `DPIN_TRACE` records for xbar, DP-IN0 and DP-IN1 and actual MMIO events
   from those ranges, including readbacks and ordering/timestamps.
5. Correct external DCP ASC/AFK/EPIC logs, raw connect/validate request/reply
   bytes, AUX/HPD/link events and any failures. Require `DPTX_RAW_READY`.
6. A visible dock HDMI picture and matching display/topology snapshot from
   the macOS guest. A working native boot and failed guest are separate results.
7. One optional HDMI detach/reattach at the monitor end, with event times,
   if needed to correlate HPD. Keep USB4 connected. An initial successful
   boot with complete logs is already valuable; do not force endless repeats.
8. Any known trace overflow, decode exception, dropped event, wrong target
   or missing register region. Preserve raw payloads even if a decoder fails.

**Do not call the capture complete** if only the internal display is traced,
only standalone DPTX PHY is traced, DP-IN nodes were removed with the proxy
port, the guest never drives the dock, or the logs contain only decoded
summaries. Check content and hashes while the guest and recorder are still
available, and make a second copy before shutdown. A failed precondition
means stop and fix that item, not repeated cable swaps.

## G. GitHub publication and implementation handoff

Publish the plan, tools, source provenance, validated hardware metadata,
reviewed relevant trace excerpts, timestamps/ordering and a clear observed
result. Add a dated directory under `evidence/` and link it from the audit,
handoff and roadmap. Keep a table of unknown offsets/bits and the evidence
supporting each interpretation. State whether data came from native macOS,
hypervisor macOS or Linux; do not combine them into a fictional successful run.

Full registry archives include serials/UUIDs and unrelated device state;
logs and EDID can contain identifiers too. The collector's `PRIVATE/` files
stay local. `REVIEW/` means **review before publication**, not automatic
sanitization. The metadata parser is an allowlist, not a general log scrubber.
Do not publish kernelcache/firmware, full ADT, account names or recovery data.
Nothing in the collector uploads files. Keep complete originals locally,
then publish inspected engineering evidence with original-file hashes.

After a usable trace, map each operation to its block and ordering, compare
against Linux's existing programming, then propose the smallest source change.
Build through CI and use the existing side-by-side kernel/boot process only
after the owner approves that specific change. A real unbypassed DPCD read
precedes EDID/modes/colors. A Linux picture through the dock, repeat attach
and clean recovery are required before declaring the objective solved.

## Tool validation and sources

- The macOS shell collector passes Linux refusal and shell syntax checks.
  On the Neo, native registry/profiler/log commands passed; the Preboot search
  correctly reported denied access. This is recorder validation, not target evidence.
- The ADT parser has six offline tests, including IORegistry address-range
  translation, phandle relationships and exclusion of unrelated identity data.
- The DP-IN trace hook has three offline target/atomicity tests.
- The raw DPTX hook has three offline tests, including preservation before a
  decoder raises. No real macOS trace is claimed.
- [Apple's ioreg manual source](https://github.com/apple-oss-distributions/IOKitTools/blob/main/ioreg.tproj/ioreg.8)
  defines the XML archive/plane/property flags used by the collector.
- [Asahi hypervisor setup](https://asahilinux.org/docs/sw/m1n1-hypervisor/),
  [proxy user guide](https://asahilinux.org/docs/sw/m1n1-user-guide/),
  [tethered boot](https://asahilinux.org/docs/sw/tethered-boot/).
- [Guest loader source](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/tools/run_guest.py),
  [DCP trace source](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/hv/trace_dcp.py),
  [hypervisor source](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/m1n1/hv/__init__.py).

The online guides were checked on 2026-10-16. Supported versions and setup
requirements must be checked again when preparing the actual trace host.
The [tool provenance record](evidence/2026-10-16-tool-provenance.json)
records the inspected local source hashes and upstream main at check time;
it does not claim that the extracted local tree equals that revision.
