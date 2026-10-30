# QMV batch candidate on the J314S — 2026-10-30

Built upstream omarchy-mlx merge `42b30a2de2f8b42e673cc50eaca9f7b145f04ac6` in a private checkout using `scripts/build-wheel.sh`, three build jobs and the existing pinned whole-encoder bundle. Wheel SHA-256 `b4a0094507d82b400c7bbfd1f9270a739f8eef2ba1d61f3dd649cd3ac3cc7c97`; installed only into a copy of the live virtual environment. The baseline is the installed v0.7.34 source `5e40ecf953e8b907dcae1ce6caadce6ad62b0e0f`; the candidate contains other intervening source changes as well as #303. Both use private Honeykrisp Mesa `9323171c12`, kernel `7.2.11-elementary-aurora72-wip5`, and the same locally cached Qwen3.5-2B MLX 4-bit model.

The existing `mlx-gate.py sweep --configs work120k` passed its baseline and work120k configurations for both runtimes. The reference and margins are those of the project's Qwen 2B gate; raw reports are alongside this file. This checks single-stream correctness, not the batching optimization.

For a batch smoke, ran upstream's `receipts/2026-10-29-qmv-batch-hoist/bg_decode_ab.py` with batch sizes 2, 3 and 4, 32 greedy tokens, one warmup and one measured generation in each fresh process. Three alternating baseline/candidate pairs were run at each size, in the order in the two JSON receipts. The harness held the project worker lock, required 4.5 GiB model allowance plus 6 GiB free reserve before each process, monitored the reserve and 80°C limit during each, and stopped on failure. All 18 processes completed; the generated token-ID hashes matched across runtimes for each batch size.

| Batch | Live median ms/step | Candidate median ms/step | Median paired reduction |
|---|---:|---:|---:|
| 2 | 34.586 | 32.392 | 8.7% |
| 3 | 44.741 | 46.106 | -3.1% (slower) |
| 4 | 51.423 | 47.327 | 8.0% |

The candidate's separately traced batch-4 model run contained 3,366 dispatches of kernel ID 547, including warmup and measurement. A real-device [probe](dispatch-probe.py) toggled `MLX_OMARCHY_QMV_BATCH` on the same wheel: its single quantized matmul dispatch changed from ID 410 to ID 547, consistent with the source's batch-kernel selection. The [probe log](dispatch-probe.log) preserves the markers and dispatches. Full model trace remains locally at `~/.cache/mseries-mlx-qmv-20261030/trace-4-candidate.log`, SHA-256 `4d4ffff02e8702d472c3806bb56ab4e05030fed51a9b24f5d1f6f73fad1b5b43`. The installed baseline was also probed: the same toggle selected ID 410 versus 547, and its separately traced batch-4 model run also contained 3,366 ID 547 dispatches. The baseline probe log is retained beside this file; its full model trace is local at `~/.cache/mseries-mlx-qmv-20261030/trace-4-live.log`, SHA-256 `985c9f5d7199bafd49f768e29d266cb7fb53e765296b940b09205ada16291b08`. Both runtimes use the batch route in these traces; the timings also include other source changes.

This is a short loaded-desktop smoke, not a stable serving or numerical-fidelity qualification. Only one short prompt set and one model were tested; step timings exclude prefill, and matching hashes do not prove logits match. No installed runtime, desktop driver, or default changed. The mixed batch-3 result and unqualified serving fidelity argue against promotion now.
