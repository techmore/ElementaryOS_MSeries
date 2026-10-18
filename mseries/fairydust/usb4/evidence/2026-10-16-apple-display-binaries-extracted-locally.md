# Apple's display binaries are on this machine — extracted locally, 2026-10-16

**Status:** factual, reproduced. No hardware needed, no macOS boot needed.
**Audience:** both agents (OpenCode + Codex/ChatGPT). Read `STATE-OF-PLAY.md`
first for the milestone ladder and the definition of the blocker.

## Why this matters

`STATE-OF-PLAY.md` says the blocker is: *nothing programs the ACIO DP-IN
adapter, and that sequence exists only in Apple's driver/firmware.* That was
written assuming we had to boot macOS to obtain Apple's binary. **We don't.**
The Asahi installer left the matching macOS kernelcache on the ESP:

```
/boot/asahi/kernelcache.release.mac13j   25,847,891 bytes
```

sha256 `5b251a816ed2725d4529660a810b09ba099b71c7b25de1e411dce97138a7b28f`

It is `IM4P('krnl','KernelManagement_host-354.140.3')` whose payload is
**BVX2/LZFSE**; decompressed it is a 96 MB Mach-O arm64e **fileset**
(filetype 12) with **357 kext entries**.

## Exact reproduction (all on this Linux box)

`img4tool` is absent; a pure-Python IM4P parse plus the reference LZFSE
decoder is enough.

```bash
# 1. split the IM4P (DER) and keep the payload
python3 - <<'PY'
def tlv(b,o):
    t=b[o]; o+=1; l=b[o]; o+=1
    if l&0x80: n=l&0x7f; l=int.from_bytes(b[o:o+n],'big'); o+=n
    return t,b[o:o+l],o+l
d=open('/boot/asahi/kernelcache.release.mac13j','rb').read()
t,seq,_=tlv(d,0); o=0
while o<len(seq):
    t,v,o=tlv(seq,o)
    if t==0x04: open('/tmp/krnl.bvx2','wb').write(v); break
PY

# 2. build the reference LZFSE decoder and decompress
git clone --depth 1 https://github.com/lzfse/lzfse.git /tmp/lzfse
make -C /tmp/lzfse
/tmp/lzfse/build/bin/lzfse -decode -i /tmp/krnl.bvx2 -o /tmp/krnl.macho
```

`/tmp/krnl.macho` sha256
`3569563909b1d416c7407e4959df1621b2db5ae9789eaf87aa9a0280538878a3`

Kext slices are extracted by walking `LC_FILESET_ENTRY` (0x80000035) — note
`entry_id` is an **offset from the command start**, not an inline string
(getting this wrong silently yields zero matches).

## Extracted slices (kept local)

`~/dp-tunnel-artifacts/apple/` — **Apple content, do not publish:**

| Slice | Size | Owns |
|---|---|---|
| `com.apple.driver.AppleDisplayCrossbar.macho` | 42,656 | the crossbar incl. **the DP-IN port class** |
| `com.apple.driver.AppleDPTX.macho` | 50,800 | DPTX, crossbar UFP, HPD dispatch |
| `com.apple.driver.AppleDCPDPTXProxy.macho` | 7,040 | DCP remote-port UFP proxy |
| `com.apple.driver.AppleDCP.macho` | 3,280 | stub |

Also present in the fileset if needed: `AppleT6000TypeCPhy`, `AppleTypeCPhy`,
`AppleT6000DART`, `AppleDPDisplayTCON`, `com.apple.iokit.IODisplayPortFamily`.

## The finding — macOS models the crossbar exactly as Linux does, plus a step

Strings recovered from the slices:

```
AppleDisplayCrossbar:  AppleATCDPINAdapterPort{,Base}.cpp
                       "DPIN Adapter Count (%u)"
                       "_dpinIndex(%u)"
                       "_xbar->connect(ufp, this) ret=0x%08x"
                       "_xbar->bringConnectionUp(*ufp, *this) ret=0x%08x"
                       "DPOUT_HPD_LEVEL_STATUS %s cleared"
                       "HPD event: hpd=%u (lvlchg=%s) plug=%s irqhpd=%s unplug=%s"
                       AppleT600xDisplayCrossbar / AppleT600XATCDPXBAR
AppleDPTX:             AppleDPTXCrossbarUFP ; "core%u dfp.address.port(%u) not DPIN"
                       dpin0 / dpin1 / dpphy
AppleDCPDPTXProxy:     AppleDCPDPTXRemotePortUFP ; "(%s -> %s (role=%u, supportsHPD=%u))"
                       dispext0..3 ; dpin0 / dpin1 / dpphy
```

Interpretation:

1. The crossbar is a UFP→DFP matrix: upstream ports `dpphy`, `dpin0`, `dpin1`;
   downstream targets `dispext0..N`. That is **the same model** as the mainline
   Linux driver (`drivers/mux/apple-display-crossbar.c`, `MUX_DPPHY/DPIN0/DPIN1`),
   confirmed independently by Apple's own naming.
2. macOS represents the DP-IN as a **first-class adapter port**
   (`AppleATCDPINAdapterPort`) with a `_dpinIndex`, and it does not merely
   select a mux state: it performs a **`connect(ufp, this)` + `bringConnectionUp()`**
   handshake, and it handles **HPD** on the DP-IN side
   (`DPOUT_HPD_LEVEL_STATUS`, `plug/unplug/irqhpd`).
3. Linux does only the mux select (one `mux_control_select` on `"dp-xbar"`).
   `bringConnectionUp` — enabling the DP-IN adapter — has no Linux counterpart.
   **That is the missing glue**, and it is now a readable function in a binary
   we hold.

## Next steps (whoever picks this up)

1. Disassemble `AppleT600xDisplayCrossbar` / `AppleATCDPINAdapterPort` in
   `AppleDisplayCrossbar.macho` and recover what `bringConnectionUp` writes
   (registers, ordering, delays). `aarch64-linux-gnu-objdump` is installed;
   `cc/make/cmake` are available. Ghidra would make this far faster.
2. Cross-check the recovered offsets against
   `drivers/mux/apple-display-crossbar.c`
   (`CROSSBAR_MUX_CTRL 0x060`, `DPIN0/1_SELECT*`, `CROSSBAR_ATC_EN 0x070`,
   `CROSSBAR_DISPEXT_EN 0x050`).
3. Trace which DCP endpoint owns a *tunnelled* connector
   (`AppleDCPDPTXProxy`) and when HPD is expected to arrive.
4. Then: smallest driver change → CI build → one hardware test (needs a sink —
   milestone M0).

## Still missing

The **DCP firmware** blob (the code that runs on the display coprocessor).
It is *not* in `all_firmware.tar.gz` (that is wifi/Bluetooth/input only) nor in
`vendorfw`. Recovering it may still require a macOS visit — but the kernelcache
finding above may make that unnecessary, so **do not schedule a macOS boot until
step 1 above is done.**

## Collaboration note

- Both agents read `STATE-OF-PLAY.md` before acting on dock video.
- Keep Apple binaries and the decompressed kernel **local**
  (`~/dp-tunnel-artifacts/apple/`). Publish only hashes, offsets and reasoning.
- The dock is currently detached/moved. No hardware work is possible until a
  sink is back on it (milestone M0).
- Do **not** re-litigate: crossbar selection alone (experiment 1), the Neo as a
  TB reference, or `/dev/mem` ADT reads. All are ruled out in `STATE-OF-PLAY.md`.
