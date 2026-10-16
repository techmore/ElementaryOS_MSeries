# DP-IN adapter: enable protocol recovered from Apple's own driver

**Date:** 2026-10-16
**Status:** static RE **done** for the DP-IN control path. This is the sequence
`STATE-OF-PLAY.md` called "the unknown". It is no longer unknown.
**Method:** Apple's kernelcache (already local) → decompressed Mach-O fileset →
ARM64 disassembly of `com.apple.driver.AppleDisplayCrossbar`.
**Tool:** `tools/kc-slice.py` (in this repo, no Ghidra needed).

---

## 1. The block, its address, and its owners

Base addresses come from the shipped board ADT for this machine (`j314sap`),
already captured by the other agent in
`evidence/2026-10-16-j314sap-dpin-derived.json`:

| ADT node | base | size | compatible |
|---|---|---|---|
| `/arm-io/atc1-dpin0` | `0xb01e50000` | `0x4000` | `atc-dpin,t600x` |
| `/arm-io/atc1-dpin1` | `0xb01e58000` | `0x4000` | `atc-dpin,t600x` |
| `/arm-io/atc1-dpxbar` | `0xb0304c000` | `0x4000` | `atc-dpxbar,t600x` |
| `/arm-io/acio1` | parent (phandle 95) | — | — |
| `/arm-io/atc-phy1` | phandle 212 | — | `atc-phy` |

Per-node wiring that matters:

```
atc1-dpin0 : acio-parent=acio1, atc-phy=atc-phy1, dpxbar-parent=atc1-dpxbar,
             dp-switch-parent=display-crossbar0, dp-switch-dfp-port=1,
             transport-type=5, transport-tunneled=1, interrupts=[1354]
atc1-dpin1 : same, dp-switch-dfp-port=2, interrupts=[1355]
```

`transport-tunneled=1` is the decisive metadata: these are **the host-side
adapters for tunneled DisplayPort** — exactly the dock path. Two of them
(`dpin0`, `dpin1`) is why the Linux mux driver has `MUX_DPIN0`/`MUX_DPIN1`.

**The Linux DT does not contain these nodes.** Asahi's converted DT has the ATC
PHY (`phy@b03000000`, windows `0xb0300000+0x4c000`, `0xb0305000`, `0xb0000000`,
`0xb02a9000`, `0xb02a8400`) and the crossbar `mux@b0304c000`, but **nothing at
`0xb01e5xxxx`**. So no Linux driver can currently even ioremap the block.

## 2. The register protocol (recovered)

`AppleATCDPINAdapterPortBase` implements a tiny MMIO API over its own block:

```
readReg(u32 off)                       -> ldr w, [base + off]      ; off is a BYTE offset
writeReg(u32 off, u32 val)             -> str w, [base + off]
andReg(u32 off, u32 mask)              = writeReg(off, readReg(off) & mask)
orReg(u32 off, u32 bits)               = writeReg(off, readReg(off) | bits)
setBitsInReg(off, shift, width, val)   = writeReg(off, (read(off) & ~(width<<shift)) | (val<<shift))
```

(`setBitsInReg(off, s, w, v)`: disassembly at `0xfffffe0009384920` shows
`bic w8, w0, w20; lsl w9, w19, w21; orr w2, w8, w9` — i.e. `(old & ~mask) | (v << shift)`.)

**Every single call site of those primitives in the whole slice:**

| # | primitive | call site | context |
|---|---|---|---|
| 1 | `writeReg(0x04, v)` | `0xfffffe000938a03c` | on the `handleStart` path: **polls `readReg(0x04)` until it equals the target, then writes it** (a handshake/ack register) |
| 2 | `writeReg(0x00, v)` | `0xfffffe000938a0d8` | `handleStart` path, register 0 |
| 3 | `orReg(0x08, 0x3)` | `0xfffffe000938a9b8` | **`incrementTunnelUse()`** — tunnel became active |
| 4 | `andReg(0x08, ~0x3)` | `0xfffffe000938ae5c` | **`decrementTunnelUse()`** — tunnel went inactive |
| 5 | `setBitsInReg(0x0c, 0, 1, active)` | `0xfffffe000938c2dc` | **`makeDPINAdapterPortActive(bool)`** |

That is the whole register-level interface of the DP-IN adapter:

| reg | meaning |
|---|---|
| `0x00` | control, written during start |
| `0x04` | handshake/status, polled then acked |
| `0x08` | bits `[1:0]` = tunnel/lane use (`0b11` while a tunnel is up, cleared on down) |
| `0x0c` | bit `0` = **"DP-IN adapter port active"** |

## 3. The control flow (who calls what, and in what order)

`AppleATCDPINAdapterPort` holds **two** IOService interfaces, and the missing
Linux glue is precisely these calls:

* `_cioInterface` — the **ACIO/CIO** (parent `acio1`):
  `isTunnelInUse()`, **`startUsingTunnel()`**, **`stopUsingTunnel()`**
* `_phyInterface` — the **atc-phy**:
  **`open()`** (*"asking for %u lanes"*), `closeTunnel()`, **`openTunnel()`**,
  **`setActiveLaneCount()`**, `getActiveLaneCount()`

Observed chain, reconstructed from the strings and the symbol graph:

```
IOTBTTunnelClientInterface  (the Thunderbolt tunnel!)  --state change-->
  AppleATCDPINAdapterPort::tunnelStateChangeNotification
      -> tunnelStateChangeThreadCallFunc
      -> handleTunnelStateChange
          -> handleTunnelActive        -> incrementTunnelUse  -> orReg(0x08,3)
                                                              -> _cioInterface->startUsingTunnel()
          -> handleTunnelInactive      -> decrementTunnelUse  -> andReg(0x08,~3)
                                                              -> _cioInterface->stopUsingTunnel()
  bringConnectionUp()                  -> _phyInterface->open()  (asks for N lanes)
                                       -> _phyInterface->openTunnel()
                                       -> _phyInterface->setActiveLaneCount()
                                       -> makeDPINAdapterPortActive(true)
                                             -> setBitsInReg(0x0c, 0,1, true)
  interruptOccurred / forceHotPlugDetect  -> HPD handling (_hpdAsserted)
  setDriveSettings(IODPDriveSettings*, N)
```

State it tracks: `_dpinIndex`, `_tunnelUseCount`, `_dpTunnelActive`,
`_dpinAdapterPortActive`, `_hpdAsserted`, `allocated`, `activated`,
`interruptsEnabled`. Full method inventory is in the symbol dump
(`tools/kc-slice.py ... syms ... 'ATCDPINAdapterPort'`).

**This is the answer to "what does macOS do that Linux doesn't":** on Linux the
Thunderbolt driver allocates the DP tunnel and stops. Nothing listens for the
tunnel state on the DP-IN adapter, nothing calls ACIO `startUsingTunnel()`,
nothing maps or programs `0xb01e50000`, nothing activates lane count, and
nothing lights `reg 0x0c bit 0`. The crossbar mux select (the only thing we ever
tried) is the *last, smallest* step, not the enable.

## 4. Reproduce (all local, ~5 minutes, no hardware)

```bash
# 1. kernelcache -> raw Mach-O fileset (already extracted to /tmp/krnl.macho)
#    see evidence/2026-10-16-apple-display-binaries-extracted-locally.md
# 2. requires: python3 + capstone (apt install python3-capstone) and c++filt
python3 tools/kc-slice.py /tmp/krnl.macho segs com.apple.driver.AppleDisplayCrossbar
python3 tools/kc-slice.py /tmp/krnl.macho syms com.apple.driver.AppleDisplayCrossbar 'ATCDPINAdapterPort'
python3 tools/kc-slice.py /tmp/krnl.macho xref com.apple.driver.AppleDisplayCrossbar \
        'ATCDPINAdapterPortBase::(writeReg|orReg|andReg|setBitsInReg)\(unsigned int' 10
```

Notes that cost time to learn:
* a fileset entry's segments are at **absolute** offsets in the collection file
  and are *not* contiguous — carving the header alone gives
  `truncated or malformed object`. `kc-slice.py` maps `vmaddr -> file offset`
  through the entry's own segments.
* Mach-O prepends one extra `_`; strip exactly one before `c++filt`, or
  demangling silently returns the mangled name and every regex misses.
* GNU `objdump` cannot read Mach-O here; `llvm-objdump` reads the fileset header
  but not the per-entry symbols. capstone + the symbol table is the reliable route.
* filter symbols to `__TEXT_EXEC` when disassembling: the `*_os_log_fmt` statics
  live in `__TEXT` as string data and match the same regex.

## 5. Next steps

1. **DT:** add the two `atc-dpin` nodes (or at least the MMIO windows) so a
   driver can ioremap `0xb01e50000` / `0xb01e58000`. Addresses are now sourced.
2. **Driver:** model the adapter. Minimum viable sequence to try:
   `reg 0x0c bit0 = 0`, program `reg 0x00`, handshake `reg 0x04`,
   then `reg 0x08 |= 0b11` and `reg 0x0c bit0 = 1` when the tunnel comes up.
   The ACIO `startUsingTunnel()` and PHY `open/openTunnel/setActiveLaneCount()`
   are IOService calls into two *other* drivers — their register effects still
   need recovery (next RE target: `AppleATCDPXBAR`, `AppleT6000TypeCPhy`,
   and the ACIO service).
3. **Then** the crossbar select (what we always tried) and DCP bring-up.
4. Hardware: still needs **M0** — a live sink on the dock.

**Regression guard:** do *not* re-try "crossbar selection alone" as if it were
the enable. It is step 3 of 4, and steps 1-2 have never been executed on Linux.
