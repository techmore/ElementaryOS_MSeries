# omarchy-mlx Qwen3.5-4B A/B readiness — 2026-10-19 (M1 Pro, G13S C0)

No model inference ran. The candidate diagnostics wheel and exact model files are prepared; admission currently refuses the model load.

## Diagnostics route proof

- Candidate: omarchy-mlx `61495cb`, diagnostics wheel `mlx_omarchy-0.32.4.dev202610191224+diag.61495cb-cp314-cp314-linux_aarch64.whl`.
- Final wheel SHA-256 after worker-pin stamping: `f9e469265b770acfaba8ab62d2e1785c886c497fc7f5c6930b2aebf9c92c8047`.
- GPU profiler literal and `mlx/bin/mlx-omarchy-info` were present; runtime assets and wheel worker pin were verified. The diagnostics wheel is in a separate cache-local venv from the non-diagnostics candidate.
- With the private Honeykrisp ICD, `mx.sum(mx.ones((1,8192), dtype=mx.float32))` returned `8192.0`. The GPU profile identified `Apple M1 Pro (G13S C0)` and one `ReduceRowF32` dispatch (79.8 μs). This verifies a synthetic route only; Qwen3.5-4B route reachability is still unknown.

## Pinned model files

Downloaded `mlx-community/Qwen3.5-4B-MLX-4bit`, revision `32f3e8ecf65426fc3306969496342d504bfa13f3`, to the normal Hugging Face cache (unauthenticated download). Catalog verification passed:

| File | Bytes | SHA-256 |
|---|---:|---|
| `config.json` | 3,366 | `f3efc81b2ea8d96a45301037d3ccccbcccdef44a961845c87f286aaddbc6eaaa` |
| `model.safetensors` | 3,034,300,695 | `5fb9acd0246866381cf8c5c354c6db1019f6498eec4ccb4f5edcc71ffeacb2db` |

## Admission and service state

Latest read-only sample: 12.26 GiB available, fan telemetry present (0 RPM reported), max temperature 51.2 C. The 4B profile's 6.5 GiB admission plus 6 GiB desktop reserve requires at least 12.5 GiB available, so `machine.violations` correctly refused admission. The everyday service remains failed from its earlier offline/missing-weights attempt; it has not been restarted. No user services were stopped or changed, and no LLM model was loaded.

Next gate: wait until the normal reserve policy allows admission; then confirm the installed baseline service can load these exact files before running the 4B A/B in the quiet-window plan.
