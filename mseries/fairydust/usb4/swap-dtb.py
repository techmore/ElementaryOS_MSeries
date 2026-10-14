#!/usr/bin/env python3
"""Replace one Apple device tree inside an m1n1 boot.bin, leaving everything else byte-identical.

boot.bin layout (update-m1n1): m1n1 binary | run of concatenated DTBs | gzip(U-Boot) [| config lines].
Only the DTB whose compatible string matches --match is replaced; m1n1, the other DTBs and the gzip tail are
copied untouched, so no m1n1 rebuild and no recompression happen.

    swap-dtb.py --in /boot/m1n1/boot.bin --dtb t6000-j314s.dtb --match apple,j314s --out boot.bin.new
    swap-dtb.py ... --check     # only report what would change
"""
import argparse, hashlib, struct, sys
from pathlib import Path

MAGIC = b"\xd0\x0d\xfe\xed"


def split(b):
    """Return (prefix_end, [(offset, size)...], tail_start) for the contiguous DTB run."""
    best = None
    i = b.find(MAGIC)
    while i != -1:
        j, run = i, []
        while b[j:j + 4] == MAGIC:
            n = struct.unpack(">I", b[j + 4:j + 8])[0]
            if not 40 <= n <= len(b) - j:
                break
            run.append((j, n)); j += n
        if len(run) >= 8 and (best is None or len(run) > len(best[1])):
            best = (i, run, j)
        i = b.find(MAGIC, max(j, i + 4))
    if not best:
        raise SystemExit("no run of device trees found; is this an m1n1 boot.bin?")
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", type=Path, required=True)
    ap.add_argument("--dtb", type=Path, required=True)
    ap.add_argument("--match", required=True, help="compatible string identifying the DTB to replace, e.g. apple,j314s")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    b = a.src.read_bytes()
    new = a.dtb.read_bytes()
    if new[:4] != MAGIC or struct.unpack(">I", new[4:8])[0] != len(new):
        raise SystemExit(f"{a.dtb} is not a single flattened device tree")
    start, run, end = split(b)
    key = a.match.encode()
    hits = [k for k, (o, n) in enumerate(run) if key + b"\0" in b[o:o + n]]
    if len(hits) != 1:
        raise SystemExit(f"expected exactly one DTB matching {a.match}, found {len(hits)}")
    if key + b"\0" not in new:
        raise SystemExit(f"{a.dtb} does not contain compatible {a.match}")
    k = hits[0]; o, n = run[k]
    print(f"{len(run)} DTBs from offset {start} to {end}; replacing #{k} ({n} -> {len(new)} bytes)")
    out = b[:o] + new + b[o + n:]
    print("input  sha256", hashlib.sha256(b).hexdigest())
    print("output sha256", hashlib.sha256(out).hexdigest(), f"({len(out)} bytes)")
    s2, run2, e2 = split(out)
    assert len(run2) == len(run) and s2 == start, "re-parse of output disagrees"
    assert out[e2:] == b[end:], "tail (gzip U-Boot) changed"
    if out == b:
        print("identical to input")
    if a.out and not a.check:
        a.out.write_bytes(out); print("wrote", a.out)


if __name__ == "__main__":
    main()
