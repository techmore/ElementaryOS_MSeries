# Rapid-MLX feasibility — 2026-10-27

## Loopback Qwen smoke

In a separate `~/.cache/mseries-metal2vk/rapid-python` target, installed a
minimal set of Python dependencies (FastAPI 0.162.0, uvicorn 0.54.0,
tiktoken 0.13.0, jsonschema 4.26.0, python-multipart 0.0.32 and their
dependencies). No package was installed into the MLX venv. With this target
and the pinned Rapid source on `PYTHONPATH`, `rapid_mlx.server` imported;
`llguidance` was absent, so guided generation was explicitly disabled.

Under the shared worker lock, a 4.5 GiB allowance and six-GiB reserve, a
loopback-only Rapid server loaded the Qwen3.5-2B checkpoint identified in
[`receipts/2026-10-27-tensorfold-vulkan.md`](receipts/2026-10-27-tensorfold-vulkan.md)
using the private Vulkan ICD. A short OpenAI-compatible request returned HTTP
200 and `19` to the same arithmetic prompt, then the server was terminated and
shut down. The owner authorized exceeding the 3500 RPM noise cap; temperature
and memory guards remained. This is one request, not a tool-calling test,
metal2vk route test, correctness suite or performance comparison.

The initial request used the wrong model identifier and returned 404; the
successful request used the local model path. Telemetry was disabled and
isolated XDG paths were set; Rapid nevertheless wrote a prefix cache under
`~/.cache/rapid-mlx` (approximately 113 MB), which remains on disk. No service
or persistent runtime configuration was installed.

## LFM3 8-bit loopback smoke

With the same isolated server setup, the LFM3 model and mlx-lm PR model module
identified in the [TensorFold receipt](receipts/2026-10-27-tensorfold-vulkan.md)
were loaded on the Mac. The first 24-token request returned HTTP 200 but spent
its token budget on thinking text without an answer; it is retained as a failed
bounded answer check. A second request explicitly set
`chat_template_kwargs.enable_thinking=false` and returned `19` with HTTP 200,
two completion tokens and 24 cached prompt tokens. The latter reported 181 ms
to first token and 50 ms mean inter-token latency; cached input, one request
and differing output lengths make this unsuitable for speed comparison. Both
servers were stopped. Guided tool generation and broader correctness remain
untested, and the unmerged LFM3 support is not installed into the live runtime.

[Rapid-MLX](https://github.com/raullenchai/Rapid-MLX) source was inspected at
`1d09cdb684bbf58fac130f5804b08ee2e1f56558`. It offers an MLX server, request
scheduling, tool parsers and batching that could complement our stack. Its
advertised model speed measurements are on macOS Apple Silicon; they are not
evidence of gains on our Linux M1 Pro.

Initial read-only source imports in the existing private MLX venv: `rapid_mlx` and
`rapid_mlx.scheduler` import successfully with that source on `PYTHONPATH`.
`rapid_mlx.server` fails immediately because FastAPI is absent; uvicorn,
tiktoken, orjson and tomli_w were also absent. The later isolated dependency
and server smoke is described above; orjson was not required for that smoke.

Its `pyproject.toml` requires upstream `mlx>=0.32.1,<0.33` and
`mlx-lm>=0.31.3,<0.32`; our fork has mlx-lm 0.31.3 but does not expose an
`mlx` distribution metadata package. Replacing the working Linux MLX runtime
with upstream MLX to satisfy a resolver would not establish Vulkan support.
The installed fork reports `mx.metal.is_available() == False` under our private
Vulkan ICD, and Rapid-MLX has several Metal-gated optimizations; whether any
specific one is usable on this backend must be checked, not assumed. A search
of its runtime and tests at this revision found no LFM3-specific support.

Next: lock and review the full dependency set for a separate environment and
check custom-kernel routes and reproducible teardown. Compare matched
workloads and correctness against our current runtime. Investigate LFM3 separately
with its unmerged mlx-lm model support; do not claim its support or Rapid's
macOS performance numbers on this host before qualification.
