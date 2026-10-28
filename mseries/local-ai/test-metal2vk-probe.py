#!/usr/bin/env python3
"""Check the shipped oMLX sigmoid probe in separate translator and m2v processes.

Run with the installed MLX Python. This is a bounded GPU test, not a model or
performance test. Source contract: jundot/omlx qwen35_gdn_verify_fused.py,
commit e2396c765d274785ce23abb764dc7eaf6b13db11 (Apache-2.0).
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import numpy as np

SOURCE = """
                uint i = thread_position_in_grid.x;
                float g = gates[i];
                float sy = 1 / (1 + metal::precise::exp(metal::abs(g)));
                out[i] = g * (g < 0 ? sy : 1 - sy);
            """


def worker(output):
    import mlx.core as mx

    x = np.linspace(-8, 8, 131072, dtype=np.float32)
    kernel = mx.fast.metal_kernel(name="omlx_gdn_sigmoid_probe", input_names=["gates"],
                                  output_names=["out"], source=SOURCE)
    y = kernel(inputs=[mx.array(x)], grid=(x.size, 1, 1), threadgroup=(256, 1, 1),
               output_shapes=[x.shape], output_dtypes=[mx.float32])[0]
    mx.eval(y)
    np.save(output, np.array(y))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(sys.argv[2])
        return
    icd = Path.home() / ".local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json"
    if not icd.is_file():
        raise SystemExit(f"Private ICD not found: {icd}")
    with tempfile.TemporaryDirectory(prefix="mseries-metal2vk-") as temp:
        results = {}
        for mode, expected in (("translator", (0, 1, 0, 0)), ("auto", (1, 0, 0, 0))):
            output = Path(temp) / f"{mode}.npy"
            env = os.environ.copy()
            for key in list(env):
                if key.startswith("MLX_OMARCHY_M2V_") or key == "MLX_OMARCHY_METAL_KERNEL_BACKEND":
                    del env[key]
            env.update(VK_DRIVER_FILES=str(icd), MLX_OMARCHY_METAL_KERNEL_BACKEND=mode,
                       MLX_OMARCHY_M2V_SUMMARY="1")
            run = subprocess.run([sys.executable, __file__, "--worker", str(output)],
                                 env=env, capture_output=True, text=True, timeout=30)
            print(run.stdout + run.stderr, end="")
            if run.returncode:
                raise SystemExit(f"{mode} worker failed: {run.returncode}")
            match = re.search(r"metal_kernel route summary: m2v=(\d+) translator=(\d+) fallbacks=(\d+) refusals=(\d+)", run.stderr)
            if not match or tuple(map(int, match.groups())) != expected:
                raise SystemExit(f"{mode} route did not match {expected}")
            results[mode] = np.load(output, allow_pickle=False)
        x = np.linspace(-8, 8, 131072, dtype=np.float32).astype(np.float64)
        reference = x / (1 + np.exp(-x))
        for mode, values in results.items():
            if values.shape != x.shape or not np.isfinite(values).all() or not np.allclose(values, reference, rtol=1e-5, atol=1e-5):
                raise SystemExit(f"{mode} numerical check failed")
            print(f"{mode}: max absolute reference error {np.max(np.abs(values - reference)):.9g}")
        print(f"maximum route difference {np.max(np.abs(results['auto'] - results['translator'])):.9g}")
        print("PASS: metal2vk dispatched without fallback; both routes matched the reference")


if __name__ == "__main__":
    main()
