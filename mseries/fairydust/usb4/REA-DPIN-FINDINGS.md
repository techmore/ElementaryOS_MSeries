# M1 Pro DP-IN static analysis with REA — 2026-10-16

## Current result and owner constraints

We have obtained the matching **T6000 macOS 13.5 / 22G74 ARM64e kernelcache**,
extracted the relevant drivers, and run real REA/Kuna function analysis.
This establishes concrete DP-IN operations absent from the inspected Linux
crossbar path. It does **not** establish a working dock display or authorize
applying register writes to the running machine.

The owner requires **no M1 Pro reboot, power cycle, cable unplug, kernel,
bootloader or audio change**. Keep SSH in delegated workers with hard timeouts
and the primary conversation responsive. Static analysis continues locally
if the Neo is unreachable. Do not force external DP-altmode AUX while USB4
occupies the lanes, or confuse crossbar offsets with separate DP-IN offsets.

Latest read-only target check: port2 is host, partner USB4, Dell dock remains
enumerated, experimental `dprx_bypass=Y`, eDP connected, external DP/HDMI
disconnected. Bypass success is not proof of a DPRX/DPCD response.
Owner confirmed the dock cable is in the left-front socket nearest trackpad;
the Neo has a separate direct USB-C connection. These statements supersede
older point-in-time reports of no target USB/TB devices.
The owner clarified that HDMI is connected but has **no picture**, and the
Neo port under discussion is occupied by the firmware connection. Preserve
that connection; no cable transfer is needed for the static work here.

## Correct input and reproducibility

The Neo's readable native boot/restore IMG4 containers were unpacked into
three ARM64e `MH_FILESET` images, approximately 115–118 MB, without sudo.
The standard `/System/Library/KernelCollections` files there are x86_64
compatibility images and are unsuitable for this target analysis. SSH later
changed from working to refused/timed out; bounded attempts stopped.
Neo macOS 26/A18 is also a different platform from the target T6000/13.5.

We therefore used the exact board identity in Apple's restore BuildManifest:
`DeviceClass=j314sap`, `ApChipID=0x6000`, `ApBoardID=0x08`. It selects
`kernelcache.release.mac13j` and `Firmware/dcp/t600xdcp.im4p`.
Only selected ZIP components were fetched by HTTP ranges, not the full IPSW.
ZIP CRCs were independently verified before decompression.

Official source:
[UniversalMac_13.5_22G74_Restore.ipsw](https://updates.cdn-apple.com/2023SummerFCS/fullrestores/032-69606/D3E05CDF-E105-434C-A4A1-4E3DC7668DD0/UniversalMac_13.5_22G74_Restore.ipsw).
The URL is also selected by [Asahi's installer](https://github.com/AsahiLinux/asahi-installer/blob/main/src/main.py).

| Artifact | SHA-256 |
|---|---|
| BuildManifest.plist | `09e3d094f126bbc8d530aa230159b8d3077f3e193520a8e2b3b273e799d63834` |
| Original kernel IM4P | `5b251a816ed2725d4529660a810b09ba099b71c7b25de1e411dce97138a7b28f` |
| Decompressed kernel Mach-O | `3569563909b1d416c7407e4959df1621b2db5ae9789eaf87aa9a0280538878a3` |
| Original DCP IM4P | `209fa06afc4139a1df153994997eee0f230b65daaa46490ae1ff579ff42b2bca` |
| Original board DeviceTree IM4P | `7a5351307bcb8b0b73141f78fb376399bd309e75cbccb4b88594eaea82b5bc72` |
| Decompressed board ADT | `9524a38c680238a434f951790a6a23f983a321e00f639bbd77d398cb99818cdf` |

Kernel ZIP component: 25,816,441 compressed bytes, 25,847,891 IM4P bytes,
96,763,904 decompressed bytes. DCP compressed component: 3,318,792 bytes.
The same manifest selects `Firmware/all_flash/DeviceTree.j314sap.im4p`:
50,777 IM4P bytes, decoded to a 295,972-byte board ADT. That selected ZIP
member also passed CRC verification.
LZFSE decoding used the [Apple reference implementation](https://github.com/lzfse/lzfse)
at `e634ca58b4821d9f3d560cdc6df5dec02ffc93fd`, built inside private scratch.

Fileset extraction used [ipsw](https://github.com/blacktop/ipsw), version
3.1.739, commit `1f8b657858d7510219f59bf9ba183bf4c0a59104`.
The Linux ARM64 release archive SHA-256 was verified:
`1df59830692c44d7fc956eeba7e94234791f663fd74c0b16780c82808e6b1c62`.

```sh
ipsw kernel extract kernelcache.release.mac13j.macho \
  com.apple.driver.AppleDisplayCrossbar --imports -o PRIVATE-KEXT-DIR
```

Repeat for `AppleDCPDPTXProxy`, `AppleTypeCPhy`, `AppleT6000TypeCPhy`,
`AppleT8103TypeCPhy`, `AppleThunderboltDPInAdapter`, and
`AppleThunderboltDPAdapterFamily`, using
their full `com.apple.driver.*` IDs. See the author's
[fileset extraction documentation](https://blacktop.github.io/ipsw/docs/cli/ipsw/kernel/extract/).
Each output's segment, section and symbol-table bounds were independently
checked. Export remaps file offsets; it does **not** establish resolution of
every chained/authenticated pointer or external import. Keep the parent image.

## REA execution and limitations

[REA](https://github.com/morluto/rea) source was pinned to
`180ba03bfddd5916251e81e97a500b1ede7a9eea`. The published npm 6.5.0 CLI lacks
the Kuna provider present in that source revision, despite the same version
label. The pinned source was run in an isolated workspace with Node 24.21.0
and a local TypeScript loader; no Codex MCP configuration or app restart.

[Kuna](https://github.com/Noelo-Lab/kuna) 1.878 Linux ARM64 and its processor
specifications were fetched from its official release with SHA-256 checks.
Executable SHA-256:
`67576df44238b25aaf98f97051c99bbe3d54386fe0777183a0c66254c1b01185`.
REA's explicit `doctor --provider kuna` check passed. REA documents verification
against Kuna 1.833, so 1.878 is explicitly recorded as an unverified release
layout. Actual target function analyses succeeded; that does not qualify
every provider feature.

Example intent, with the pinned source CLI substituting for `rea`:

```sh
REA_KUNA_COMMAND=/absolute/path/to/kuna \
REA_KUNA_CACHE_DIR=/absolute/path/to/private-cache \
rea function PRIVATE-KEXT-DIR/com.apple.driver.AppleDisplayCrossbar \
  0xfffffe000938c888 --provider kuna --json
```

REA evidence records target hashes, provider identity, original virtual
addresses, reconstructed pseudocode, assembly and limitations. Pseudocode is
a reconstruction, not original source. Indirect calls require vtable/fixup
validation; log strings can support a function interpretation but do not
resolve a call target by themselves. Raw Apple binaries and full decompiled
listings remain private and are not committed.

## Concrete DP-IN findings

The DP-IN adapter and T600X/T8103 ATC crossbar classes are in
**`com.apple.driver.AppleDisplayCrossbar`**, not the TypeC PHY bundle.
The remote DCP port proxy is in **`com.apple.driver.AppleDCPDPTXProxy`**.
Extracted DisplayCrossbar SHA-256:
`761b1360f9294291497aee2e76b668ead61a4eea30b81035de7d1c4eeadae782`.
Extracted DCPDPTXProxy SHA-256:
`9e014bb29f88658955edb0b045c2eb669806610d6c3f502b9607863cb31e288f`.

### Shipped board metadata resolves the previous address candidates

The existing `inspect-dpin-adt.py --from-file FILE` parser successfully read
the exact shipped j314sap ADT. These are **shipped macOS 13.5 board metadata**,
not a capture of the target's live, boot-patched ADT:

| Node | Physical register range | Apple ADT interrupt value | Transport index / DFP port |
|---|---|---|---|
| `atc1-dpin0` | `0xb01e50000`, size `0x4000` | 1354 | 0 / 1 |
| `atc1-dpin1` | `0xb01e58000`, size `0x4000` | 1355 | 1 / 2 |
| `atc1-dpxbar` | `0xb0304c000`, size `0x4000` | — | — |

Both DP-IN nodes refer to `acio1`, `atc-phy1`, `atc1-dpxbar` and
`display-crossbar0`; transport type 5, tunneled 1, DFP endpoint 1.
The crossbar address corroborates the existing Linux resource for the
owner-confirmed dock socket. The DP-IN physical bases are no longer merely
offset guesses. Correct live resource ownership, power state, interrupt
translation and adapter identity still require implementation validation;
this metadata is not authorization for a `/dev/mem` poke.
The small [derived wiring summary](evidence/2026-10-16-j314sap-dpin-derived.json)
contains only the selected board nodes and provenance, not a raw ADT.

| Routine, unslid 13.5 virtual address | Observed / derived behavior |
|---|---|
| DPIN base `handleStart`, `0xfffffe0009384034` | Maps provider register resource 0; saves its mapping at object offset `0x258` |
| DPIN base `readReg`, `0xfffffe0009384584` | 32-bit load with unscaled byte offset (`UXTW #0`) |
| DPIN base `writeReg`, `0xfffffe0009384704` | 32-bit store with unscaled byte offset (`UXTW #0`) |
| DPIN `incrementTunnelUse`, `0xfffffe000938a5e4` | On first use: tunnel-client start, PHY tunnel open (selector 1 or 2), bridge interrupt enable, then `orReg(0x8, 0x3)` |
| DPIN `handleActivate`, `0xfffffe000938c888` | Tunnel-use acquire, superclass activation, then DP-IN active transition; cleans up on failure |
| DPIN `bringConnectionUp`, `0xfffffe000938da18` | Superclass bring-up, then DP-IN active transition |
| DPIN `makeDPINAdapterPortActive`, `0xfffffe000938c0d4` | Dispatches its gated action block at `0xfffffe000938c154` |

The inner action block was analyzed with an explicitly supplied function
address through Kuna after REA's procedure inventory omitted it. Record this
distinction; it is not a REA-discovered function boundary.

The block's operations and diagnostic strings identify these **separate
DP-IN block byte offsets**, subject to mapping/resource confirmation:

| Offset | Bit | Derived meaning |
|---|---|---|
| `0x000` | 2 | HPD level status |
| `0x008` | 0–1 | OR mask `3` after bridge interrupts are enabled; full bit meanings unresolved |
| `0x00c` | 0 | DPTX inactive request |
| `0x010` | 0 | DPTX inactive acknowledgment |

Activation clears inactive and polls for a cleared acknowledgment;
deactivation sets inactive and polls for a set acknowledgment. The active
wait checks HPD and has a 1000 ms deadline. This is a discovered handshake,
not permission to write an unconfirmed live address.

Verification includes exact first-instruction agreement between original
kernel and extracted component, and independent GNU AArch64 decoding of all
455 instructions returned for `incrementTunnelUse`, with zero original-byte
mismatches. Its final branch resolves to the actual `orReg` symbol, with
arguments `w1=8`, `w2=3`. The PHY open and interrupt-object calls are indirect;
their interpretations also use Apple diagnostic strings.
Independent parent-image chained-pointer decoding additionally resolves
the PHY interface's `0x198` slot to `openTunnel` at `0xfffffe0009d20790`,
with the authentication diversity matching the callsite. This validates a
static vtable target, not the type of an object observed on running hardware.
The same method resolves the mapping-object getter to
`IOMemoryMap::getVirtualAddress` and the interrupt-object call to
`IOInterruptEventSource::enable`, including matching authentication diversity.
Do not infer extra memory barriers from reconstructed helper pseudocode:
the validated data accesses are bare 32-bit AArch64 loads/stores.

### PHY tunnel clocks are a separate missing integration path

REA analyzed `AppleT8103TypeCPhy::configureDPTunnelMode`
(`0xfffffe0009d60088`), its PLL-frequency routine (`0xfffffe0009d63a00`),
and unconfiguration (`0xfffffe0009d63ed8`). The reconstruction includes
per-tunnel PCLK1/PCLK2 enable and selection, shared first/last-use clock
handling, and AUSPLL lock polling. Original parent-image chained-fixup
validation confirms T6000's slot `0xa80` inherits this T8103 PLL routine and
slot `0xa78` inherits its unconfiguration. T6000's `initDPTunnel` slot `0x9f0`
instead targets its local implementation at `0xfffffe0009d27dc4`; preserve
that difference rather than substituting the T8103 initializer.
That T6000 initializer is **a no-op**: original and extracted bytes decode
to `BTI c; RET`. Reserving/opening a tunnel alone does not establish PLL or
PCLK configuration. The later link-rate path supplies the actual trigger:

1. `AppleATCDPPort::setLinkRate` at `0xfffffe0009395d3c` dispatches its
   gated block at `0xfffffe0009395dbc` to the PHY interface's slot `0x188`.
2. That slot resolves to `AppleTypeCPhyDisplayPortInterface::setLinkRate`
   at `0xfffffe0009d20308`. Its block at `0xfffffe0009d20604` uses the
   parent's slot `0x940` when a tunnel is open.
3. T6000 slot `0x940` resolves to inherited
   `displayPortTunnelLinkRateChange` at `0xfffffe0009d697f8`. Its block
   at `0xfffffe0009d69bd0` calls slot `0xa70`.
4. T6000 slot `0xa70` resolves to `configureDPTunnelMode` at
   `0xfffffe0009d60088`; first-PCLK setup calls the inherited PLL routine
   through slot `0xa80`.

All cited interface/T6000 slots were checked against their original format-8
authenticated pointer chains. This is stronger than matching imported names;
the runtime object's identity and selected connected port remain unmeasured.
The DP-IN `setActiveLaneCount` routine at `0xfffffe000938ddd8` only updates
software state/logging in the analyzed function; do not infer a lane-register
write from its name.

The T8103 routine uses `TX_DP_CTRL0` PCLK enables at bits 13/14 and selection
fields 4–6 / 7–9. Link-rate codes 6, 10, 20, 30 select 4, 3, 1, 0 respectively.
Linux `drivers/phy/apple/atc.c` defines those same fields, but its visible
selection writer is the physical DP AUX-enable path, with fixed selection 1.
USB4 deliberately keeps that path disabled. Its AUSPLL configuration/lock
poll is likewise reached through physical DP configuration, not the normal
USB4 host path after experiment 2 removes the tunneled connector's ATC PHY.
The Apple tunnel PLL routine uses a fixed descriptor with per-port clock
selection, whereas Linux's physical DP path retunes AUSPLL per link rate.
Reusing the latter directly is not yet justified. Apple polls AUSPLL lock for
up to 500 ms in this path; the inspected Linux physical DP path uses 10 ms.

Generic PHY power, reset, clamp, CIO PLL/tunables and ACIO power handling
**already exist** in Linux. The gap is the visible per-DP-IN tunnel clock
and lifetime integration, not a claim that USB4 has no clocks or power.
Opaque ACIO firmware effects have not been excluded. Do not fix this by
turning on the whole external DP-altmode AUX path in USB4 mode.

## Linux comparison and next work for Codex / DeepSeek

The inspected fairydust kernel source is pinned to
`ce9f2eba72c061a50b2d790450e90af3439d8c24` plus experiment 2.
`drivers/mux/apple-display-crossbar.c` maps its crossbar resource and
programs mux/clock/routing registers. It does not map the separate DP-IN
resource or implement the above inactive/ack/HPD transition. The crossbar's
T602x `0x00c` clock register is a different block, not an equivalent handshake.
USB4 AUX HopID path activation proves routing setup, not that handshake or
a successful monitor DPCD read.

There is also a concrete dispatch gap in `drivers/gpu/drm/apple/dptxep.c`:
`SET_LINK_RATE` (lines 375–444 in the inspected tree) calls `phy_configure`
only when `atcphy` exists. With experiment 2's null tunneled PHY, it updates
software rate fields and replies success without a DP-IN tunnel clock
replacement. `SET_ACTIVE_LANE_COUNT` (285–336) similarly skips PHY work when
absent and completes positive-count configuration. This is conditional source
behavior, not proof those callbacks arrived in the current boot. It identifies
where dedicated USB4-preserving tunnel operations need to be integrated;
restoring a physical DP-altmode PHY binding is not an equivalent fix.

The proxy's `connectTo` at `0xfffffe00092fed98` and `validateConnection` at
`0xfffffe00092ff2a8` were analyzed through REA. Original constant bytes confirm
commands **11** and **12**, consistent with current Linux. The connection
argument includes role and HPD-support attributes in the low word and the
target address in the high word. Linux currently sends zero in the connect
low word and `0x100` for validation. The DP-IN low word is now traced as `0x101`, as detailed below. Keep the
physical DP values unchanged.

Next work:

1. Preserve the verified shipped device-tree ranges above and design a
   separate DP-IN resource/IRQ provider; confirm live resource ownership and
   USB4 adapter correlation without guessing node/port indices.
2. Finish `AppleTypeCPhyDisplayPortInterface::openTunnel` and
   `AppleTypeCPhy::openDisplayPortTunnel` into T8103/T6000 tunnel clock/PLL
   configuration. Check actual equivalence with Linux ACIO/ATC operations,
   rather than assuming absence from a missing function name.
3. Resolve DP-IN interrupt handling, tunnel lifecycle and DCP attribute
   selection. Check original instruction bytes and relevant pointer fixups.
4. Design a resource-checked DP-IN implementation and meaningful offline
   validation before proposing a kernel change. Hardware validation remains
   outstanding and requires separate owner authorization for the concrete
   action. Do not reboot or unplug to collect these static inputs.

No display picture, live DP-IN write/read, unbypassed DPRX response, EDID or
hardware-qualified patch has been obtained in this analysis.

## Neo port distinction for future baseline collection

The owner raised Neo port selection. [Apple's port guide](https://support.apple.com/en-us/109523)
states that only its USB 3 port supports a display: the leftmost USB-C port
when facing the laptop's left side. The other port is USB 2. This is relevant
to a future owner-authorized Neo baseline, not evidence of USB4 DP tunneling
on the M1 Pro. Preserve the owner's occupied firmware connection; no move is
requested by this investigation.

## Implementation update and independently checked attributes — 2026-10-16

[DPIN-IMPLEMENTATION](DPIN-IMPLEMENTATION.md) supersedes the proposed next-work
list above with source patches 0004–0006, offline validation and the explicit
router/DCP activation-ordering gap. No new live hardware result is claimed.

`IODPTXPort::getAttributes` at `0xfffffe000a4dc4b4` loads the value at object
`+0x1a6` (BTI, add, load, return). DP-IN `handleStart` at
`0xfffffe0009389264` initializes role byte `+0x1a6` to 1 and ORs flag byte
`+0x1a7` with 1. `getSupportsHPD` at `0xfffffe000938df94` extracts attribute
bit 8. Original instructions therefore establish low word **0x101** for this
DP-IN port: role 1 plus HPD support. This supports changing tunneled
connect/validate attributes, not guessing another core or transport index.

The fixed tunnel descriptor maps to Linux DESC_A `0x1e0e021c`, DESC_B zero
within its defined field mask, DESC_C `0x00654a00` within bits 22:0. PCLK
selection for 1620/2700/5400/8100 Mb/s is 4/3/1/0. Tunnel APB sequence is
0, lock poll up to 500ms, 0x2000; final shutdown command is 3. Physical DP's
per-rate descriptor and 0x2800 command are not substituted for this path.

An actual [Ghidra headless second pass](evidence/2026-10-16-ghidra-dpin-crosscheck.md)
completed on the same matching extracted drivers. It corroborates the
inactive/ACK/HPD semantics, exact status/HPD/status IRQ capture and selected
clock functions. Indirect-call reconstruction remains checked against
original instructions/authenticated pointer chains. This corroboration is
static, not evidence the proposed Linux callback order works on hardware.
