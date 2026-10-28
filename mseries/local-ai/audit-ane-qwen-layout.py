#!/usr/bin/env python3
"""Offline preflight for the experimental staged Qwen ANE layout plan.

This reports incompatibilities; passing is not proof that an ANE submission is safe.
"""
import argparse
import json
import math
import struct
from pathlib import Path


def audit(plan, programs_dir):
    report = {"programs": len(plan["programs"]), "surfaces": 0,
              "unreferenced_surfaces": [], "packing_mismatches": [],
              "extended_descriptors": [], "duplicate_channels": []}
    for i, program in enumerate(plan["programs"]):
        path = programs_dir / f"prog_{i:03d}.anec"
        with path.open("rb") as stream:
            header = stream.read(16)
        if len(header) != 16:
            raise ValueError(f"short ANEC header: {path}")
        _, td_size, _ = struct.unpack("<QII", header)
        if td_size > 0x1f8:
            report["extended_descriptors"].append({"program": i, "td_size": td_size})
        seen = set()
        for surface in program["surfaces"]:
            report["surfaces"] += 1
            channel = surface["anec_channel"]
            if channel in seen:
                report["duplicate_channels"].append({"program": i, "channel": channel})
            seen.add(channel)
            if not surface["named_in_stream"]:
                report["unreferenced_surfaces"].append({"program": i, "port": surface["port"]})
            shape = surface["shape"]
            if len(shape) != 4 or any(not isinstance(x, int) or x <= 0 for x in shape):
                raise ValueError(f"invalid surface shape: program {i}, {surface['port']}")
            runtime_bytes = math.prod(shape[:-1]) * max(shape[-1] * 2, 64)
            if runtime_bytes != surface["packed_bytes"]:
                report["packing_mismatches"].append({
                    "program": i, "port": surface["port"], "shape": shape,
                    "compiled_bytes": surface["packed_bytes"], "runtime_bytes": runtime_bytes,
                    "compiled_strides": surface["strides"],
                })
    report["submission_allowed"] = False  # Offline evidence alone cannot establish device safety.
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("programs", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.plan.read_text()), args.programs), indent=2))


if __name__ == "__main__":
    main()
