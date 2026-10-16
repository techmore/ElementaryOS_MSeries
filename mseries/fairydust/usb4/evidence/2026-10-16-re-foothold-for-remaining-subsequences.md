# RE foothold: the exact Apple functions for the remaining sub-sequences


> Follow-up: [REA-DPIN-FINDINGS](../REA-DPIN-FINDINGS.md) now resolves the
> T6000 inherited clock dispatch and records matching T600x DCP firmware
> already acquired locally. [Implementation handoff](../DPIN-IMPLEMENTATION.md)
> contains the draft source and remaining activation-order question. Preserve
> this address map; do not repeat acquisition based on the older absence claim.

**Date:** 2026-10-16
**Status:** addresses and symbol names verified by disassembly. This is a
*foothold map*, not a completed recovery. No Apple binaries or bulk
disassembly are published here — only names, addresses and derived facts.
Every address below was re-checked against the symbol table on 2026-10-16
(two earlier rows were wrong and are corrected).

## Why this note exists

`STATE-OF-PLAY.md` lists the unrecovered sub-sequences as:

1. ACIO `startUsingTunnel()` / `stopUsingTunnel()`
2. ATC-PHY `open()` / `openTunnel()` / `setActiveLaneCount()`

Both now have **named functions with addresses**. Do not start from strings or
from the class list again.

## How to reproduce (all local, no macOS)

```sh
K=/tmp/opencode/krnl.macho      # 96 MB, sha256 3569563909b1d416c7407e4959df1621b2db5ae9789eaf87aa9a0280538878a3
cd mseries/fairydust/usb4
python3 tools/kc-slice.py "$K" syms com.apple.driver.AppleT8103TypeCPhy 'Tunnel|Lane|ACIO'
python3 tools/kc-slice.py "$K" dis  com.apple.driver.AppleT8103TypeCPhy 'configureACIOPhyLaneMode'
```

If the kernelcache is gone, rebuild it with
`evidence/2026-10-16-apple-display-binaries-extracted-locally.md` (IM4P -> LZFSE
-> Mach-O fileset).

### Gotcha that cost time — filter `_os_log_fmt`

Every method has a **`::_os_log_fmt` twin in `__TEXT` containing the format
string data**. `dis <entry> <regex>` prints whichever symbol matches first, and
the format-string copy often wins, producing disassembly of *data*. Filter
`_os_log_fmt` out, and take the symbol whose address is in `__TEXT_EXEC`
(the `0xfffffe0009xxxxxx` range for these kexts; the `0xfffffe0007xxxxxx`
range is `__TEXT`). `sed -n '/^;; ===== .*  @0xfffffe0009/p'` finds the code.

## The ACIO/PHY side — `com.apple.driver.AppleT8103TypeCPhy`

(The T6000 kext is a subclass; `AppleT6000TypeCPhy` imports these base-class
methods. `_ZN34AppleTypeCPhyDisplayPortInterface...` etc. are the interfaces the
crossbar calls.)

| Address | Symbol |
|---|---|
| `0xfffffe0009d34c24` | `AppleT8103TypeCPhy::configureACIOPhyLaneMode(unsigned int, tACIOPhyLaneMode)` |
| `0xfffffe0009d60088` | `AppleT8103TypeCPhy::configureDPTunnelMode(unsigned long long, unsigned int)` |
| `0xfffffe0009d63a00` | `AppleT8103TypeCPhy::configureDPTunnelModePLLFrequency(unsigned long long, unsigned int)` |
| `0xfffffe0009d63ed8` | `AppleT8103TypeCPhy::unconfigureDPTunnelMode(unsigned int)` |
| `0xfffffe0009d5fae4` | `AppleT8103TypeCPhy::applyACIOPHYTunables(unsigned int, AppleTypeCPhyTransportType)` |
| `0xfffffe0009d2e388` | `AppleT8103TypeCPhy::configureLanes(unsigned int, AppleTypeCPhyTransportType, AppleTypeCPhyPowerLevel, unsigned int)` |
| `0xfffffe0009d33804` | `AppleT8103TypeCPhy::setACIOPhyPowerLevel(AppleTypeCPhyPowerLevel)` |
| `0xfffffe0009d6cf88` | `AppleT8103TypeCPhy::setACIOPhySleepBSmlBig()` |
| `0xfffffe0009d6dc4c` | `AppleT8103TypeCPhy::clearACIOPhySleepBSmlBig()` |
| `0xfffffe0009d34818` | `AppleT8103TypeCPhy::resetACIOPhy(bool)` |
| `0xfffffe0009d87808` | `AppleT8103TypeCPhy::adjustLinkRateOwnerDPTunnelMode(unsigned int)` |
| `0xfffffe0009d697f8` | `AppleT8103TypeCPhy::displayPortTunnelLinkRateChange(...)` |

`com.apple.driver.AppleTypeCPhy` (the generic base):

| Address | Symbol |
|---|---|
| `0xfffffe0009d20790` | `AppleTypeCPhyDisplayPortInterface::openTunnel(AppleTypeCPhyTunnelOption)` |
| `0xfffffe0009d20894` | `AppleTypeCPhyDisplayPortInterface::closeTunnel()` |
| `0xfffffe0009d1ace4` | `AppleTypeCPhy::openDisplayPortTunnel(AppleTypeCPhyDisplayPortInterface*, AppleTypeCPhyTunnel&)` |
| `0xfffffe0009d1baa8` | `AppleTypeCPhy::closeDisplayPortTunnel(AppleTypeCPhyDisplayPortInterface*)` |
| `0xfffffe0009d1f92c/34/3c` | `AppleTypeCPhy::initDPTunnel() / updateDPTunnel() / shutdownDPTunnel()` |
| `0xfffffe0009d19154` | `AppleTypeCPhy::configureLanes(...)` |
| `0xfffffe0009d1f8ec` | `AppleTypeCPhy::initACIO(AppleTypeCPhy::tACIOPhyMode, unsigned int)` |
| `0xfffffe0009d1c250` | `AppleTypeCPhy::displayPortTunnelLinkRateChange(...)` |
| `0xfffffe0009d17f88` | `AppleTypeCPhy::getLaneConfigurationFromDock(AppleTypeCPhyLane)` |

### First concrete finding from `configureACIOPhyLaneMode` @ `0xfffffe0009d34c24`

The function is mostly `os_log` traffic, but the register access is clean and
identical for both lanes:

```asm
ldr  x8, [x20, #0x160]      ; register-block base pointer (per-phy object member)
ldr  w9, [x8, #0x48]        ; read  block+0x48
and  w25, w19, #7           ; save the incoming 3-bit mode (arg2 = tACIOPhyLaneMode)
bfxil w9, w19, #0, #3       ; reg[2:0] = mode            (lane A)
str  w9, [x8, #0x48]
...
bfi  w9, w25, #3, #3        ; reg[5:3] = saved mode      (lane B)
str  w9, [x8, #0x48]
```

So: **the ACIO PHY lane mode is a 3-bit field per lane, at offset `0x48` of the
PHY register block**, bits `[2:0]` for one lane and `[5:3]` for the other. Arg1
bit 0 selects the pass. The register block is reached through the object member
at `+0x160` — resolve that from the class's `start`/`initACIO` path (see
`initACIO`, `resetACIOPhy`) to get from an address to a phys base.

## The crossbar side — `com.apple.driver.AppleDisplayCrossbar`

| Address | Symbol |
|---|---|
| `0xfffffe000937ef24` | `___ZN19AppleT602XATCDPXBAR7connectE17IODPTXPortAddressS0__block_invoke` |
| `0xfffffe000937f29c` | `___ZN19AppleT602XATCDPXBAR17bringConnectionUpE17IODPTXPortAddressS0__block_invoke` |
| `0xfffffe0009381f20` | `___ZN19AppleT8103ATCDPXBAR7connectE17IODPTXPortAddressS0__block_invoke` |
| `0xfffffe0009382298` | `___ZN19AppleT8103ATCDPXBAR17bringConnectionUpE17IODPTXPortAddressS0__block_invoke` |
| `0xfffffe000938c154` | `___ZN23AppleATCDPINAdapterPort25makeDPINAdapterPortActiveEb_block_invoke` |
| `0xfffffe000938fa64` | `___ZN24AppleATCDPOUTAdapterPort26makeDPOUTAdapterPortActiveEb_block_invoke` |
| `0xfffffe0009384afc` | `IODPTXPHYInterface::getActiveLaneCount() const` |
| `0xfffffe0009384b0c` | `IODPTXPHYInterface::setActiveLaneCount(unsigned int)` |
| `0xfffffe0009376ac0` | `IODPTXPHYInterface::getSupportsLaneMapping() const` |
| `0xfffffe0009376acc` | `IODPTXPHYInterface::setLaneMap(IODPLaneMap)` |
| `0xfffffe000937fc1c` | `___ZN19AppleT602XATCDPXBAR18takeConnectionDownE17IODPTXPortAddressS0__block_invoke` |
| `0xfffffe00093766d0` | `AppleATCDPNativePort::setActiveLaneCount(unsigned int)` |
| `0xfffffe0009399bf0` | `AppleDPTXPort::setActiveLaneCount(unsigned int)` |
| `0xfffffe0009375320` | `AppleATCDPNativePort::handleActivate()` |
| `0xfffffe0009375d28` | `AppleATCDPNativePort::handleDeactivate()` |
| `0xfffffe00093749c8` | `AppleATCDPNativePort::checkInitialHPDState()` |
| `0xfffffe00093747d0` | `AppleATCDPNativePort::handlePortMessage(AppleATCDPNativePort::PortMessage)` |
| `0xfffffe0009374108` | `AppleATCDPNativePort::enqueuePortMessage(AppleATCDPNativePort::PortMessage)` |
| `0xfffffe00093737c8` | `AppleATCDPNativePort::handleStop(IOService*)` |

(`IODPTXPHYInterface` rows are the ones the crossbar itself calls
`_phyInterface->open()/openTunnel()/setActiveLaneCount()` against — that is why
they appear inside the crossbar kext.)

Note the naming: for T6000 the crossbar class is **`AppleT602XATCDPXBAR`**
(there is no `T6000` variant) — the same T602X/T6000 naming quirk as elsewhere
in Apple's tree.

## Important negative result — `startUsingTunnel` is NOT in this kernelcache

`grep -abo 'startUsingTunnel' krnl.macho` hits **only** two places:
`com.apple.driver.AppleDisplayCrossbar` (0x328f11..0x32fd2e) and
`com.apple.iokit.IODisplayPortFamily` (0x7053d5). Both are *interface/vtable
declarations* (the format-string/interface-name region), **not** an
implementation: no kext in this fileset defines a `*startUsingTunnel*` symbol.

The interface calls are PAC-authenticated virtual calls through a vtable, e.g. at
`0xfffffe000938a9a8`:

```asm
ldr  x8, [x16]              ; vtable slot
movk x17, #0x9b16, lsl #48  ; PAC discriminator
blraa x8, x17
```

(The discriminator does **not** identify the method — the vtable slot does. Do not
assume this particular site is `startUsingTunnel`.)

So the CIO-side implementation of `startUsingTunnel()` lives in another binary —
most likely an **auxiliary kernel collection** (Apple Silicon splits kexts
between the boot kernelcache and the auxiliary KCs), not in
`kernelcache.release.mac13j`. `AppleConvergedPCI` ("Converged PCI" = Apple's
name for this) has **no** `startUsingTunnel`/`openTunnel`/`setActiveLaneCount`
symbols either — do not spend time there.

Finding the CIO service: look for an aux KC on the macOS volume / Recovery
(`/System/Volumes/Preboot/*/boot/*/KernelCollections/*.kc` or
`/System/Library/KernelCollections/`), or take it from the IPSW. Record it here
if found.

## Suggested order of attack

1. `AppleT8103TypeCPhy::configureDPTunnelMode` @ `0xfffffe0009d60088` — this is
   the function named after exactly the thing we are missing ("DP tunnel mode"),
   and it takes a `unsigned long long` (likely a phys address / lane map).
2. `configureDPTunnelModePLLFrequency` and `applyACIOPHYTunables` — they carry
   the tunable values the bootloader would otherwise copy from Apple's ADT;
   compare against `apple,dp-tunnel` / the `apple,tunable-*` properties.
3. `AppleTypeCPhy::openDisplayPortTunnel` @ `0xfffffe0009d1ace4` — the top of
   the PHY-side sequence the crossbar calls.
4. Only then the ACIO `startUsingTunnel` binary hunt (aux KC).

## Local (non-published) artifacts from this session

`~/dp-tunnel-artifacts/re/` :

* `phy-configureACIOPhyLaneMode.txt` (1930 lines)
* `phy-openTunnel.txt` (772 lines)
* `phy-openDisplayPortTunnel.txt` (2316 lines)

These contain Apple disassembly. Keep local.
