# Rapid-MLX feasibility — 2026-10-27

[Rapid-MLX](https://github.com/raullenchai/Rapid-MLX) source was inspected at
`1d09cdb684bbf58fac130f5804b08ee2e1f56558`. It offers an MLX server, request
scheduling, tool parsers and batching that could complement our stack. Its
advertised model speed measurements are on macOS Apple Silicon; they are not
evidence of gains on our Linux M1 Pro.

Read-only source imports in the existing private MLX venv: `rapid_mlx` and
`rapid_mlx.scheduler` import successfully with that source on `PYTHONPATH`.
`rapid_mlx.server` fails immediately because FastAPI is absent; uvicorn,
tiktoken, orjson and tomli_w are also absent. Nothing was installed. This is
not a server or inference test.

Its `pyproject.toml` requires upstream `mlx>=0.32.1,<0.33` and
`mlx-lm>=0.31.3,<0.32`; our fork has mlx-lm 0.31.3 but does not expose an
`mlx` distribution metadata package. Replacing the working Linux MLX runtime
with upstream MLX to satisfy a resolver would not establish Vulkan support.
The installed fork reports `mx.metal.is_available() == False` under our private
Vulkan ICD, and Rapid-MLX has several Metal-gated optimizations; whether any
specific one is usable on this backend must be checked, not assumed. A search
of its runtime and tests at this revision found no LFM3-specific support.

Next: create a separate environment with reviewed, pinned Python dependencies
and the existing fork explicitly exposed without overwriting it. Test a
loopback-only server and deterministic Qwen request under the shared worker
lock and resource guard. Capture errors, actual backend, custom-kernel routes,
and exact dependencies. Compare matched workloads and correctness against our
current runtime only after the basic server works. Investigate LFM3 separately
with its unmerged mlx-lm model support; do not claim its support or Rapid's
macOS performance numbers on this host before qualification.
