#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise reviewed M1/M2 source logic; no hardware operations or promotion."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile

from candidate import tree_digest
from qualification import digest, write_new

CLOCK_CASES = ["m1-admission", "m1max-admission", "m2-admission", "single-stop",
               "stop-first", "stop-second", "rate-change", "force-stop",
               "first-poll-failure", "lock-failure", "first-command-failure",
               "second-command-failure", "busy-pll", "busy-mode"]


def check(source, output):
    source = source.resolve()
    if output.resolve().is_relative_to(source):
        raise ValueError("output must be outside the tested source tree")
    if output.exists():
        raise ValueError("receipt exists; choose a new output")
    util = source / "drivers/gpu/drm/asahi/util.rs"
    queue = (source / "drivers/gpu/drm/asahi/queue/mod.rs").read_text()
    if "fn read_supported" not in util.read_text() or queue.count(".read_supported(") < 2:
        raise ValueError("reviewed M1/M2 command admission missing; this suite targets the reviewed .20 lane")
    # Includes all production files and original fixture code. No source edits.
    source_hash = tree_digest(source)
    results = {}
    with tempfile.TemporaryDirectory(prefix="aurora-review-host-") as temporary:
        root = Path(temporary)
        for name, arguments in (("tunnel-route", []), ("tunnel-clock", CLOCK_CASES), ("bcm4377-resume", [])):
            script = source / "tools/asahi" / f"{name}-tests.py"
            directory = root / name
            subprocess.run(["python3", str(script), "--out", str(directory), *arguments], check=True,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            results[name] = {"harness_sha256": digest(script), "receipt": json.loads((directory / "receipt.json").read_text())}
        shim = root / "gpu-reader.rs"
        shim.write_text('''// SPDX-License-Identifier: GPL-2.0-only OR MIT
#![allow(dead_code)]
extern crate self as kernel;
pub mod prelude {
    pub type Result<T> = core::result::Result<T, i32>;
    pub const EINVAL: i32 = 22;
}
#[path = ''' + json.dumps(str(util)) + ''']
mod production;
''')
        binary = root / "gpu-reader"
        compiler = ["rustc", "+1.93.1"]
        subprocess.run([*compiler, "--edition=2021", "--test", "-D", "warnings", str(shim), "-o", str(binary)], check=True)
        run = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
        if "7 passed; 0 failed" not in run.stdout:
            raise ValueError("expected seven original GPU-reader tests")
        results["gpu-reader"] = {"production_sha256": digest(util), "tests_passed": 7, "stdout": run.stdout,
                                  "fixture_boundary": "Kernel Result/EINVAL types only; unmodified production util.rs and its original tests"}
    if tree_digest(source) != source_hash:
        raise ValueError("source changed during tests")
    result = {"schema": 1, "kind": "source-host-controls", "captured_at": datetime.now(timezone.utc).isoformat(),
              "source_tree_sha256": source_hash,
              "tools": {"rustc": subprocess.check_output(["rustc", "+1.93.1", "--version"], text=True).strip(),
                        "cc": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]},
              "results": results, "hardware_qualification": False,
              "limits": "Production source with controlled core/PCI/firmware services; no kernel boot, real radio/dock/suspend execution, or energy claim."}
    write_new(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="reviewed .20 source or prepared .20 enhancement source")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.source, args.output)
