#!/usr/bin/env python3
"""Inspect or patch the installed Apple device tree inside an m1n1 boot.bin.

`boot.bin` is a run of concatenated DTBs followed by gzip(U-Boot). Because m1n1
and U-Boot consume it before GRUB, that tree is shared by *every* GRUB entry, so
changing it here is how the dock-video experiment is armed and disarmed. This
tool finds the DTB whose `compatible` matches (default `apple,j314s`), walks its
structure block, and reports or rewrites the few properties the experiment
depends on.

    boot-dt.py --in /boot/m1n1/boot.bin                 # report the armed state
    boot-dt.py --in boot.bin --mux-arg 0 --out new.bin  # crossbar back to dpphy
    boot-dt.py --in boot.bin --ablate-dp-tunnel --out new.bin
    boot-dt.py --in boot.bin --restore-dp-tunnel --out new.bin

Every edit is a length-preserving byte patch, so m1n1, the other DTBs and the
gzip tail stay byte-identical and nothing has to be rebuilt or recompressed.
The two ablations let one install answer two different questions without another
CI round trip:

  * `--mux-arg 0|1|2` selects the display crossbar input for `&dcpext1`
    (0 = dpphy, the Type-C DP PHY; 1 = dpin0; 2 = dpin1). Restoring 0 undoes
    experiment 1's routing.
  * `--ablate-dp-tunnel` renames the `apple,dp-tunnel` property (same length, so
    no structure changes) so the DCP no longer takes experiment 2's path and
    attaches the ATC PHY as it always did. `--restore-dp-tunnel` puts the real
    name back.

Both are safe to run on the working (non-experimental) kernel as well; the only
effect there is which crossbar input `dispext1` is routed to.
"""
import argparse
import hashlib
import struct
import sys
from pathlib import Path

MAGIC = b"\xd0\x0d\xfe\xed"
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9

TUNNEL_PROP = b"apple,dp-tunnel"
TUNNEL_ALIAS = b"apple,dp-tunneX"          # same length, matches nothing
assert len(TUNNEL_PROP) == len(TUNNEL_ALIAS)

# Node path -> the properties that matter for this experiment.
INTERESTING = {
    "dcp@28cc00000": ("tunelled connector / dpin0 route (experiment 1+2)"),
    "dcp@289c00000": ("HDMI connector (control; must never change)"),
}


def find_run(b):
    """Return (run_start, [(offset, size)...], tail_start) for the DTB run."""
    best = None
    i = b.find(MAGIC)
    while i != -1:
        j, run = i, []
        while b[j:j + 4] == MAGIC:
            n = struct.unpack(">I", b[j + 4:j + 8])[0]
            if not 40 <= n <= len(b) - j:
                break
            run.append((j, n))
            j += n
        if len(run) >= 8 and (best is None or len(run) > len(best[1])):
            best = (i, run, j)
        i = b.find(MAGIC, max(j, i + 4))
    if not best:
        raise SystemExit("no run of device trees found; is this an m1n1 boot.bin?")
    return best


def parse_tree(buf, base, size):
    """Walk one FDT in `buf` starting at file offset `base` (`size` bytes long).

    Yields (path, name, offset_in_file, value_bytes) for every property.
    """
    totalsize, off_struct, off_strings, off_rsvmap, version, lastcomp, cpid, size_strings, size_struct = \
        struct.unpack(">9I", buf[base + 4:base + 40])
    if totalsize != size:
        raise SystemExit(f"DTB totalsize {totalsize} != run entry size {size}")
    sbase = base + off_struct
    pos = sbase
    strings = buf[base + off_strings:base + off_strings + size_strings]
    stack = []
    while True:
        (tok,) = struct.unpack(">I", buf[pos:pos + 4])
        pos += 4
        if tok == FDT_BEGIN_NODE:
            end = buf.index(b"\0", pos)
            name = buf[pos:end].decode()
            pos = sbase + ((pos + len(name) + 1 - sbase + 3) & ~3)
            stack.append(name)
        elif tok == FDT_END_NODE:
            stack.pop()
        elif tok == FDT_PROP:
            length, nameoff = struct.unpack(">II", buf[pos:pos + 8])
            pos += 8
            name = strings[nameoff:strings.index(b"\0", nameoff)].decode()
            val = buf[pos:pos + length]
            path = "/" + "/".join(n for n in stack if n and n != "")
            yield path, name, pos, val
            pos = sbase + ((pos + length - sbase + 3) & ~3)
        elif tok == FDT_NOP:
            pass
        elif tok == FDT_END:
            break
        else:
            raise SystemExit(f"unknown FDT token {tok} at {pos - 4}")
    return


def u32s(v):
    return " ".join(f"{x:08x}" for x in struct.unpack(f">{len(v) // 4}I", v)) if v else "(empty)"


def show(buf, base, size, dtb_path):
    print(f"device tree: {dtb_path}  ({size} bytes)")
    print(f"  sha256: {hashlib.sha256(buf[base:base + size]).hexdigest()}")
    props = {}
    for path, name, off, val in parse_tree(buf, base, size):
        props.setdefault(path, {})[name] = (off, val)
    for key, why in INTERESTING.items():
        suffix = [p for p in props if p.endswith("/" + key)]
        if not suffix:
            print(f"\n  !! node {key} not found")
            continue
        p = suffix[0]
        node = props[p]
        print(f"\n  {p}   [{why}]")
        st = node.get("status")
        print(f"    status               : {st[1].rstrip(b'\0').decode() if st else '(absent = okay)'}")
        for prop in ("apple,connector-type", "apple,dptx-phy", "mux-index"):
            if prop in node:
                val = node[prop][1]
                shown = (str(struct.unpack(">I", val)[0]) if len(val) == 4
                         else val.rstrip(b"\0").decode())
                print(f"    {prop:<20}: {shown}")
        if "mux-controls" in node:
            off, val = node["mux-controls"]
            words = struct.unpack(f">{len(val) // 4}I", val)
            arg = words[1] if len(words) > 1 else None
            names = {0: "dpphy (Type-C DP PHY, experiment OFF)", 1: "dpin0 (ACIO DP IN 0)",
                     2: "dpin1 (ACIO DP IN 1)"}
            print(f"    mux-controls         : phandle {words[0]} arg {arg}"
                  f"  -> {names.get(arg, '?')}")
            print(f"    (file offset of arg) : {off + 4}")
        tun = node.get(TUNNEL_PROP.decode())
        if tun:
            print(f"    apple,dp-tunnel      : present, value {tun[1].hex()} ({len(tun[1])} bytes)")
        else:
            alias = node.get(TUNNEL_ALIAS.decode())
            if alias:
                print("    apple,dp-tunnel      : ABLATED (renamed to "
                      f"{TUNNEL_ALIAS.decode()}) -> DCP attaches the ATC PHY as before")
            else:
                print("    apple,dp-tunnel      : absent")


def patch(buf, base, size, args):
    out = bytearray(buf)
    changed = []
    props = {}
    for path, name, off, val in parse_tree(buf, base, size):
        props.setdefault(path, {})[name] = (off, val)

    if args.mux_arg is not None:
        key = "dcp@28cc00000"
        p = [q for q in props if q.endswith("/" + key)]
        if not p:
            raise SystemExit(f"node {key} not found")
        off, val = props[p[0]]["mux-controls"]
        if len(val) != 8:
            raise SystemExit(f"unexpected mux-controls length {len(val)}")
        old = struct.unpack(">I", val[4:8])[0]
        if old != args.mux_arg:
            out[off + 4:off + 8] = struct.pack(">I", args.mux_arg)
            changed.append(f"mux-controls arg {old} -> {args.mux_arg}")

    if args.ablate_dp_tunnel or args.restore_dp_tunnel:
        want = TUNNEL_ALIAS if args.ablate_dp_tunnel else TUNNEL_PROP
        src = TUNNEL_PROP if args.ablate_dp_tunnel else TUNNEL_ALIAS
        hits = []
        start = 0
        while True:
            i = bytes(out).find(src + b"\0", start)
            if i == -1:
                break
            hits.append(i)
            start = i + 1
        if len(hits) != 1:
            raise SystemExit(f"expected exactly one {src.decode()!r} string, found {len(hits)}")
        out[hits[0]:hits[0] + len(src)] = want
        changed.append(f"{src.decode()} -> {want.decode()} (property-name rename, "
                       f"length preserved)")

    if not changed:
        print("nothing to change (already in the requested state)")
    for c in changed:
        print("change:", c)

    if args.out:
        out = bytes(out)
        start, run, end = find_run(out)
        assert out[end:] == buf[find_run(buf)[2]:], "tail (gzip U-Boot) changed"
        if out == buf:
            print("output identical to input; not writing")
        else:
            args.out.write_bytes(out)
            print(f"wrote {args.out}  sha256 {hashlib.sha256(out).hexdigest()} "
                  f"({len(out)} bytes; input {hashlib.sha256(buf).hexdigest()})")
    elif changed:
        print("(dry run: no --out given, nothing written)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", type=Path, required=True,
                    help="boot.bin to read (e.g. /boot/m1n1/boot.bin)")
    ap.add_argument("--match", default="apple,j314s",
                    help="compatible string identifying the DTB (default apple,j314s)")
    ap.add_argument("--mux-arg", type=int, choices=(0, 1, 2),
                    help="set the &dcpext1 crossbar input: 0=dpphy 1=dpin0 2=dpin1")
    ap.add_argument("--ablate-dp-tunnel", action="store_true",
                    help="rename apple,dp-tunnel so the DCP ignores it (experiment 2 off)")
    ap.add_argument("--restore-dp-tunnel", action="store_true",
                    help="restore the real apple,dp-tunnel name")
    ap.add_argument("--out", type=Path, help="write the patched boot.bin here")
    a = ap.parse_args()

    if a.ablate_dp_tunnel and a.restore_dp_tunnel:
        ap.error("--ablate-dp-tunnel and --restore-dp-tunnel are mutually exclusive")
    if not a.src.is_file():
        ap.error(f"{a.src} not found (boot.bin is root-only readable on some systems; use sudo)")

    buf = a.src.read_bytes()
    start, run, end = find_run(buf)
    key = a.match.encode()
    hits = [(k, o, n) for k, (o, n) in enumerate(run) if key + b"\0" in buf[o:o + n]]
    if len(hits) != 1:
        raise SystemExit(f"expected exactly one DTB matching {a.match}, found {len(hits)}")
    k, base, size = hits[0]
    print(f"{len(run)} DTBs from offset {start} to {end}; match #{k}")

    if a.mux_arg is None and not a.ablate_dp_tunnel and not a.restore_dp_tunnel:
        show(buf, base, size, f"#{k}")
        return
    patch(buf, base, size, a)
    print()
    show(bytes(a.out.read_bytes()) if a.out and a.out.is_file() else buf, base, size,
         f"#{k} (after)")


if __name__ == "__main__":
    main()
