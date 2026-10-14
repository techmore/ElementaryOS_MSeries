#!/usr/bin/env python3
"""Replace only the m1n1 binary at the front of an m1n1 boot.bin; DTB run and gzip U-Boot tail stay byte-identical.
  swap-m1n1.py --in boot.bin --m1n1 m1n1.bin --out boot.bin.new
"""
import argparse, importlib.util, pathlib
here = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("swapdtb", here / "swap-dtb.py")
sd = importlib.util.module_from_spec(spec); spec.loader.exec_module(sd)
ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--m1n1", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()
b = open(a.inp, "rb").read(); new = open(a.m1n1, "rb").read()
assert new[:4] == b[:4], "m1n1 binary does not start like the current one (not a raw m1n1.bin?)"
start, run, end = sd.split(b)
out = new + b[start:]
s2, run2, e2 = sd.split(out)
assert s2 == len(new) and len(run2) == len(run) and out[s2:] == b[start:], "re-parse disagrees"
open(a.out, "wb").write(out)
print(f"m1n1 {start} -> {len(new)} bytes; {len(run)} DTBs + tail unchanged; total {len(out)}")
