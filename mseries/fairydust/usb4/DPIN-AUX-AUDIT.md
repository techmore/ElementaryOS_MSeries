# DP-IN / AUX audit — 2026-10-16

**New static evidence:** [REA DP-IN findings](REA-DPIN-FINDINGS.md) supersedes
the address-candidate and unknown-sequence state below. The exact shipped
j314sap/13.5 ADT confirms DP-IN windows `0xb01e50000` and `0xb01e58000`,
size `0x4000` each, alongside the known `0xb0304c000` crossbar. Actual
AppleDisplayCrossbar analysis identifies inactive/ack/HPD byte offsets and
tunnel/PHY/interrupt lifecycle. These are shipped metadata and static
derivations, not a live MMIO trace or working display. No reboot or cable
change is authorized; current work continues offline and in public notes.

Execution handoff: [complete macOS cutover checklist](MACOS-CUTOVER-CHECKLIST.md).
The [MacBook Neo recorder](NEO-RECORDER-SETUP.md) is now available over SSH.
The native macOS collector can obtain a
working baseline and IODeviceTree metadata without moving cables. The
full m1n1 MMIO trace still requires its USB handshake and a qualified guest. The guest payload
is matching XNU's extracted kernelcache, correcting the earlier iBoot claim.

Target: M1 Pro / MacBookPro18,3, WD22TB4, dock HDMI to an Amazon Basics
monitor. The owner confirmed that the monitor is powered on and HDMI is
selected. No kernel, boot image, audio, or device register was changed by this
audit. The owner ran the existing `force_link` disconnect/connect probe.

## Findings that change the investigation

### 1. Identify the missing MMIO block by its Apple device-tree node

The public IORegistry dump for **this Mac model**, macOS 13.1, names
`atc0-dpin0`, `atc0-dpin1`, `atc1-dpin0`, `atc1-dpin1`,
`atc2-dpin0`, and `atc2-dpin1`. Their unit addresses are `1E50000` and
`1E58000`. That dump does not include full `reg` properties, so these are
**not sufficient to establish physical addresses on this machine**.

An older, original M1 device-tree dump has separate `atc-dpin,t8103` nodes
with 16 KiB register windows, `acio-parent`, `atc-phy`, `dpxbar-parent`,
`dp-switch-parent`, `dp-switch-dfp-endpoint`, and `dp-switch-dfp-port`.
DPIN0 has DFP port 1; DPIN1 has port 2; DPPHY has port 0. These are useful
relationship names, not a license to copy M1 addresses onto M1 Pro.

For the live Linux port, the confirmed crossbar is `0xb0304c000`, ACIO RC is
`0xb01ac0000`, and NHI is `0xb01f00000` (`t600x-dieX.dtsi`). Applying the
public unit offsets to that address group suggests **candidates**
`0xb01e50000` and `0xb01e58000`. Do not read or write those candidates until
the original ADT confirms them. The original Apple ATC index also needs to
be resolved by address; it must not be assumed to equal Linux's PHY index.

The preserved original ADT is available as a labelled reserved-RAM region:
`/sys/firmware/devicetree/base/reserved-memory/flash@10005960000`, label
`adt`, size `0x70000` at the time of inspection. m1n1 creates that region in
`src/kboot.c:dt_setup_mtd_phram`. It is RAM metadata, not DP-IN MMIO.
Only NVRAM is currently exposed through `/proc/mtd`; do not load a module
or alter the kernel merely to inspect it.

`inspect-dpin-adt.py` reads the labelled ADT RAM region (or a supplied ADT
file), resolves bus ranges and phandle relationships, and prints only
DP-IN/crossbar/DP-PHY metadata. It does not print unrelated identity
properties or retain the entire ADT. It includes IRQ/clock/power-gate IDs,
parent references and a property-size inventory to reveal any tunable tables
without dumping arbitrary property contents. Live use may require root and may
still be refused by `/dev/mem` policy. This chat runner's `NoNewPrivs=1`
prevents sudo; the owner's regular Terminal can attempt the read:

```bash
sudo python3 /home/sdolbec/wt-dockvideo/mseries/fairydust/usb4/inspect-dpin-adt.py \
  > /home/sdolbec/dptunnel-logs/dpin-adt.json
```

The owner attempted this command from their regular Terminal on Asahi and
reported `errno 1: Operation not permitted`. The output file is empty. The
running kernel configuration confirms `CONFIG_STRICT_DEVMEM=y` and
`# CONFIG_MTD_PHRAM is not set`; the inspected kernel's `read_mem()` returns
`EPERM` when `devmem_is_allowed()` rejects a RAM page. This is consistent
with the refusal even under real sudo, independently of the chat runner's
`NoNewPrivs=1` restriction. No successful live ADT read has occurred.

Do not retry with broader sudo or weaken memory protections. Obtain a macOS
IODeviceTree archive using `collect-macos-dock.sh` and parse it with
`inspect-dpin-adt.py --from-ioreg FILE`, or obtain the original ADT through
the proxy when a separate recorder is available. Neither import has yet
been qualified against this Mac's real original metadata; fixtures pass.

### 2. AUX path activation proves routing configuration, not AUX traffic

`drivers/thunderbolt/path.c:tb_path_activate()` programs HopID routing,
credits, and enable bits through `tb_port_write()`. It then prints
`AUX ... path activation complete`. There is no downstream DPCD request /
response check in that success path.

Therefore the measured activation logs demonstrate that the connection
manager configured the tunnel paths. They do **not** establish the entire
host-side DP-IN/AUX path, and they cannot exclude an uninitialised host
DP-IN block. The handoff's phrase "host side works end to end" is too strong.

`tunnel.c:tb_dp_wait_dprx()` polls the host DP-IN adapter's
`DP_COMMON_CAP_DPRX_DONE`. With the experimental bypass it returns success
without that bit. `tb.c:tb_dp_tunnel_active()` prints "DPRX capabilities
read completed" when the tunnel is marked active. This is not proof of a
real sink read under bypass. Require an unbypassed, tuple-correlated event.

### 3. The forced DCP attempt is real, but does not establish its AUX route

Latest owner-run probe in `dptunnel-logs/live-monitor.txt`:

| Boot monotonic time | Observed event |
|---|---|
| 39501.368 s | `dcp_dptx_disconnect(port=0)` |
| 39502.370 s | `dcp_dptx_connect(port=0)` and DCP "powering nub" |
| 39509.431 s | APCALL 22 and 24: device not responding / not started |

`card2-DP-1` remained disconnected. Bypass was subsequently read as `Y`.
This proves that the existing software trigger executes. It does not prove
that a valid DCP DP-IN endpoint or a functioning tunneled AUX channel was
selected. Consequently, the DCP and router failures are consistent with H2,
but are not independent proof that both readers used the same AUX route.

The experiment-2 patch avoids assigning the ATC PHY to the tunneled
connector, but keeps this call unchanged:

```c
dptxport_connect(service, 0, dcp->dptx_phy, dcp->dptx_die);
```

The endpoint/role selection is still a trace question. **Do not change the
core argument to 1 merely because m1n1 defines `DPIN0 = 1`.** The older
`dcpav.py` helper uses a different command and target layout (connected bit
8), while this kernel uses connected bit 15 and command 11. A public macOS
DCP log explicitly connects `dispext0::core0` to `atc2::dpin0`; core 0 is
therefore compatible with a DP-IN destination. The role and endpoint
selection must be learned from the correct firmware version's raw request
and corresponding Apple transport metadata.

`atc.c`'s USB4 mode deliberately has `enable_dp_aux = false`. This is the
external Type-C DP-altmode AUX path, not evidence that setting it true
would initialize the internal DP-IN/AUX bridge. Do not force DP-altmode
PHY programming while its lanes carry USB4.

### 4. The previous macOS trace recipe would miss the principal target

The local and public `proxyclient/hv/trace_dptx.py` enumerate only
`dptx-phy`, `lpdptx-phy0`, and `lpdptx-phy1`. They do not enumerate
`atcN-dpin0`, `atcN-dpin1`, or `atcN-dpxbar`.

Also, `trace_dcp.py` defaults `TRACE_DCP` to `dcp0` (usually the internal
display), and `run_guest.py` already accepts multiple `-m` arguments.
Launch one guest with both trace hooks; do not start two competing proxy
clients in separate shells.

The new `trace-dpin.py` hook selects the crossbar by its **confirmed physical
address**, resolves the original Apple ATC prefix, validates both DP-IN
nodes, and traces all register ranges of those three nodes. It aborts before
installing a partial trace if the target is absent or the ranges are
unexpected. It has only been tested with synthetic objects, not hardware.

The hypervisor removes the proxy port's ACIO/ATC/DP-IN nodes from the guest
ADT. The proxy and dock must be on different physical ports. A missing
target node is a failed capture precondition, not proof that the silicon
has no DP-IN block. The DCP trace must target the controller at
`0x28cc00000`, resolved against the original ADT/aliases.

## What is still missing before an implementation is justified

1. This machine's translated DP-IN register ranges and relationship graph.
   The live Linux ADT export above was refused. Obtain the IODeviceTree
   archive during the normal macOS visit, or the original ADT through the
   m1n1 proxy when a second computer is available.
2. The macOS writes/readbacks to those DP-IN blocks: power/clock/reset,
   endpoint selection, interrupt handling, and AUX/HPD enable ordering.
   The existing sources do not provide trustworthy register offsets/values
   for a driver implementation. **This capture requires a second computer,
   a matching extracted XNU kernelcache and validated macOS boot context,
   and rebooting the target into the hypervisor.**
3. Correlate DP-IN0/1, host router adapters 0:5/0:6, DCP remote target/role,
   and the dock's adapter used by its actual HDMI path. Do not assume a
   one-to-one physical HDMI/DP mapping from adapter numbers alone.
4. Demonstrate a genuine DPCD response with bypass off before working on
   EDID, mode setting, or test colors. Keep bypass on between scoped probes.

The owner's HDMI topology is confirmed, but the watchdog had no new HDMI
hotplug event after its recorded starting line 2488. The subsequent manual
force-link probe armed bypass. That watchdog output cannot close H1 or
qualify any future "ANSWERED" result without checking the bypass epoch and
matching adapter. Do not repeat force-link to manufacture new evidence.

Live-state update during publication: the HDMI watchdog was restarted at
08:00:50, with a new start line 2795, and bypass was read as `N`. There was
still no new DP hotplug/DPRX result in the inspected log. This audit did not
restart the watchdog or change the parameter. The earlier `Y` reading is a
point-in-time observation, not a claim about the current state.

An additional confirmed collector defect: `test-dp-tunnel.sh` counts all
connected DRM connectors, including eDP. Combined with any earlier path
activation it can claim display success while `card2-DP-1` is disconnected.
Interpret its raw per-connector state; fix that verdict before relying on
an automated go/no-go decision. The collector was not changed in this batch.

## Validation and provenance

- `python3 mseries/fairydust/usb4/test-inspect-dpin-adt.py`: 6 tests passed
  (range translation / relationship resolution, privacy filtering,
  truncation, invalid input, IORegistry import and ambiguous roots).
- `python3 mseries/fairydust/usb4/test-trace-dpin.py`: 3 tests passed
  (all three blocks included, wrong/removed target, missing DP-IN fails
  before partial capture).
- `python3 mseries/fairydust/usb4/test-trace-dcp-raw.py`: 3 tests passed
  (all service directions, raw preservation before decode failure, repeat install).
- The native macOS collector passes shell syntax and Linux refusal checks.
  Its registry/profiler/log commands were validated on the Neo recorder;
  denied Preboot search is retained as a failure. The importer now accepts
  the Neo's actual dictionary-root plist, blank ADT names with registry-name
  fallback and anonymous non-ADT leaves. Target collection remains pending.
- Live kernel, DT, drivers, audio, and probe parameters were not modified
  by this batch. No real macOS trace or video qualification was performed.
- Kernel reference: Fairydust `ce9f2eba72c061a50b2d790450e90af3439d8c24`
  plus experiment-2 patch SHA-256
  `c962eff07c54b2d3e6d066dd85c5a969a5130e0d61c7f55daaccd999589da6ac`.
- Local m1n1 source is an extracted tree rather than a Git checkout. The
  inspected `trace_dptx.py` SHA-256 is
  `4a0d30433ec656ed3e7c07026684a59ade58680111315c2064c2e9cc658175e0`;
  `run_guest.py` SHA-256 is
  `2c11188c237a9f427dd46fd4430090cf9e82f66bdbdd342f45627630f0751346`.
  The public main version also accepts repeated `-m` and omits DP-IN from
  `trace_dptx.py`. No third-party firmware or source was imported.
- The public `AsahiLinux/linux` `tbt-reset-wip` branch was also checked at
  `c404e6e4892526896bd2a44146c7b7c985beb48e`: its `drivers/phy/apple`
  directory lists `atc.c` and no separate DP-IN PHY driver. This is a scoped
  source check, not a claim that every public or private development branch
  was searched.

Primary evidence / original hardware data:

- [Same-model IORegistry dump](https://github.com/robre/ioreg-archive/blob/master/ioreg-MacBookPro18%2C3-A2442-13.1.txt)
  (downloaded file SHA-256
  `6333642d93378e98799afe27c5c4d9c8bbd110c2aad463d8ffbae64cca0eb382`).
- [Original M1 ADT comparison](https://gist.github.com/zhuowei/67bb835f86cb9f42c1168f6449b42031).
- [Original macOS DCP log](https://github.com/waydabber/BetterDisplay/discussions/3110)
  (a different machine/firmware; transport-semantic evidence, not our raw IPC).
- [Sven Peter's description of the two required MMIO blocks](https://lkml.rescloud.iu.edu/2608.2/03169.html).
- [Public m1n1 DPTX trace scope](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/hv/trace_dptx.py),
  [guest runner](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/tools/run_guest.py),
  [older DCPAV protocol helper](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/m1n1/fw/dcp/dcpav.py).

The audit narrows the missing integration. It does not claim to have
discovered or validated the DP-IN register programming sequence.
