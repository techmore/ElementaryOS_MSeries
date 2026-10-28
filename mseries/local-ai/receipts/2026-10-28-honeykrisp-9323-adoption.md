# Honeykrisp 9323171c12 and 120k submit budget — adoption, 2026-10-28

M1 Pro 32 GB (G13S C0), kernel `7.2.11-elementary-aurora72-wip4`, omarchy-mlx v0.7.33
(`33630f9c`, mlx-lm 0.31.3). Adopted in #664 and installed on this machine. The live table
is in [`ENGINE-SCOREBOARD.md`](../ENGINE-SCOREBOARD.md); triage history is in issue #659.

## Why we looked

[coreglass](https://github.com/joshuaswarren/coreglass)'s daily ledger runs our exact MLX
build on a plain M1 at 40.8 tok/s (Qwen 2B, mlx-lm) with Honeykrisp `e7631595df`, and faster
again on its `9323171c12` "main" stack. Our M1 Pro has 2x the GPU cores of an M1 but decoded
at 36.0, on an older driver (`7faf04c065`, 2026-09-20) and with the 5,000 work-group submit
budget that omarchy-mlx uses for a board with no calibration row (G13S has none).

## What changed

| | before | after |
| --- | --- | --- |
| Private Honeykrisp ICD | `7faf04c065` | `9323171c12` (joshuaswarren/mesa-1, 2026-10-25) |
| MLX submit budget, `model-worker.py` MLX workers | unset → 5000 fallback | `MLX_OMARCHY_BATCH_WORK=120000` (environment wins) |
| MLX submit budget, `mseries-assistd.service` | 20000 | 120000 |

Built with `honeykrisp-candidate.sh` (install.sh's exact Mesa flags) and installed into
`~/.local/share/mlx-omarchy/vulkan/`. The old driver is kept at
`~/.local/share/mlx-omarchy/vulkan-7faf04c065`.

## Evidence

**Correctness** (`mlx-gate.py`, CPU float32 reference over the same weights, 6 prompts,
32 greedy tokens, rules fixed before measuring): all 9 scheduling configs pass on both
drivers; pooled RMSE is identical (0.03647); the `SDPA_BF16_FAST` negative control fails on
both (R3: 0.04041 > 1.05 × 0.03647). Receipts: `2026-10-28-mlx-gate-sweep.json`,
`2026-10-28-mlx-gate-sweep-hk9323171c12.json`.

**Speed** (`engine-compare.py`, 32 tokens, greedy, three rotated rounds, fresh process per run,
6 GiB reserve and 80 °C guard), median decode tok/s:

| Model | old, default | old, 120k | new, default | new, 120k |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.5 2B 4-bit | 36.0 | 47.2 | 48.9 | **56.4** |
| Qwen3.5 4B 4-bit | 18.6 | 24.8 | 23.1 | **27.0** |
| LFM3 1.7B 8-bit | 15.3 | 16.9 | 22.6 | **27.5** |

Generated text was byte-identical between drivers for every model and budget. llama.cpp
(LFM2.5 1.2B Q4_K_M, `llama-server`, 3 requests) on the same driver swap: decode 56.6 → 61.0,
prompt 76 → 82 tok/s, identical text. After installation, the default path (no override)
decoded Qwen 2B at 53–54 tok/s with the same text.

## Known risk and limits

- Since `ff013781c00` the driver segfaults in `agx_ra` on software f16 cooperative matrices
  when `AGX_SIMDMAT=1` (see `2026-10-19-honeykrisp-v3-candidate/`). That variable is opt-in
  and unset in our stack; none of the gated paths reach it.
- Not measured: dictation speech workers (budget unchanged), long desktop sessions at 120k
  beyond the short 2026-10-27 frame probes, contexts beyond the short prompts.

## Rollback

```bash
mv ~/.local/share/mlx-omarchy/vulkan ~/.local/share/mlx-omarchy/vulkan-9323171c12
mv ~/.local/share/mlx-omarchy/vulkan-7faf04c065 ~/.local/share/mlx-omarchy/vulkan
systemctl --user restart mseries-assistd
```

and revert the `install.sh` pin in #664.

## Server layer (after adoption, same driver and budget)

The everyday model is served by `mlx-omarchy-serve` (mlx-lm backend, launched by
`model-worker.py`). On the new driver it loses much of the gain. Decode tok/s (for several
requests at once: total over all of them), three rotated rounds, identical text per request:

| | Rapid-MLX 1d09cdb | mlx-omarchy-serve (mlx-lm 0.31.3) |
| --- | ---: | ---: |
| Qwen 2B, 1 request | 50.6 (TTFT 0.18 s) | 33.1 (TTFT 0.63 s) |
| Qwen 2B, 4 at once | 43.5 total | 19.9 total (TTFT ~4.2 s) |
| Qwen 2B, 8 at once | 48.1 total | 19.8 total (TTFT ~8.1 s) |
| Qwen 4B, 1 request | 25.7 | 19.1 |

In-process MLX decodes Qwen 2B at 56.4. Upstream's mlx-lm 0.32 line carries a
`server-skip-logprob-read` patch that targets this server path; we stay on 0.31.3 until
omarchy-mlx moves its default. Moving the everyday model to Rapid-MLX is a separate decision.
Receipts: `2026-10-28-engine-compare-qwen{2b,4b}-short-hk9323171c12[-c4|-c8]-rapid-120k+serve-120k.json`.
