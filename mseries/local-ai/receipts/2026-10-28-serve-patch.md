# Patched upstream server for the everyday model, 2026-10-28

M1 Pro 32 GB (G13S C0), kernel `7.2.11-elementary-aurora72-wip4`, Honeykrisp `9323171c12`,
omarchy-mlx v0.7.33 (`33630f9c`, mlx-lm 0.31.3), `MLX_OMARCHY_BATCH_WORK=120000`.

## Why patch upstream instead of switching to Rapid-MLX

The everyday model runs on upstream's own launcher, `mlx-omarchy-serve`, which wraps mlx-lm's
server with a memory reservation, a context cap and a speech yield gate (dictation and spoken
replies can pause decoding). Rapid-MLX was faster (Qwen 2B 50 vs 33 tok/s) but would drop all
three. So we kept upstream's launcher and found where its server loses time:

1. **Logprob read per token.** The server copies the sampled token's logprob back from the GPU
   on every token, even when no request asked for logprobs. On Honeykrisp each copy-back is a
   full GPU wait. omarchy-mlx fixed this on its mlx-lm 0.32 line only
   (`patches/mlx-lm-0.32/mlx-lm-server-skip-logprob-read.patch`, an omarchy original).
   We ported it to 0.31.3: `patches/mlx-lm-0.31.3-server-skip-logprob-read.patch`.
2. **Batched cache for a lone request.** mlx-lm's batch generator turns even one request's KV
   cache into a batched cache with a rank-4 mask, which keeps attention off its plain causal
   fast path. Rapid-MLX keeps it single while only one request runs and promotes it when a
   second joins. We vendored that module (Apache-2.0, `serve_singleton_cache.py`, from Rapid-MLX
   `1d09cdb`, attribution in its header) and install it with
   `patches/mlx-lm-0.31.3-server-singleton-cache.patch`.

## How it is installed

`serve-patch.sh build` copies the installed `mlx_lm` into `~/.local/share/mseries-ai/serve-patch`,
applies both patches there, and stamps the SHA-256 of the installed `server.py` it started from.
The omarchy-mlx venv is not modified. `model-worker.py` puts the copy first on `PYTHONPATH` for
MLX profiles only while that stamp still matches, so an omarchy-mlx upgrade can never be shadowed
by a stale copy (the worker logs `SERVE PATCH: skipped`, and the stock server runs).
`install.sh` rebuilds the copy after every runtime install. The journal shows
`SERVE PATCH: skip-logprob-read + singleton cache` when it is active.

## Evidence

`engine-compare.py`, 32 greedy tokens, three rotated rounds, fresh server per run, 6 GiB reserve
and 80 °C guard. Text was identical across every engine in every run. Decode tok/s (for several
requests at once: total) and median time to first token:

| | Stock upstream | + logprob patch | + both patches | Rapid-MLX |
| --- | ---: | ---: | ---: | ---: |
| Qwen 2B, 1 request | 32.6 (0.61 s) | 42.3 (0.59 s) | **56.5** (0.60 s) | 50.4 (0.18 s) |
| Qwen 4B, 1 request | 19.2 (0.88 s) | | **27.4** (0.85 s) | 25.5 (0.22 s) |
| Qwen 2B, 4 at once | 20.3 (4.10 s) | | 27.8 (3.26 s) | **42.7** (1.16 s) |
| Qwen 2B, 8 at once | 20.2 (7.87 s) | | 28.6 (5.97 s) | **48.2** (1.90 s) |

In-process MLX on the same driver and budget: Qwen 2B 56.4, Qwen 4B 27.0 tok/s, so a single
request through the patched server now loses nothing to the server layer. A trial run loading
Rapid's module straight from its checkout gave 56.8 on Qwen 2B, matching the vendored copy.

Through the installed worker (everyday profile, Qwen 3.5 4B): a plain answer (`19`), a native tool
call (`list_calendar_events {"day": "tomorrow"}`) and an explicit `logprobs: true` request
(values returned) all worked; `/v1/models` still reports the pinned snapshot the assistant checks.

Receipts: `2026-10-28-engine-compare-qwen{2b,4b}-short-hk9323171c12[-c4|-c8]-serve-120k+serve-patched-120k+rapid-120k.json`,
`…-qwen2b-short-hk9323171c12-serve-120k+serve-nolp-120k+rapid-120k.json` (logprob patch alone) and
`…-serve-nolp-120k+serve-single-120k+rapid-120k.json` (the trial).

## Still open

- **Several requests at once.** Rapid-MLX is still 1.5–1.7x faster in total and reaches the first
  token 3x sooner. The singleton path only covers one request; Rapid's scheduler (and Locals'
  batching) is the next thing to study for agents that send parallel requests.
- **First token for one request.** 0.6–0.85 s against Rapid's 0.2 s. Not investigated yet; part
  may be prompt-cache reuse between the warmup and the measured request in Rapid.
- **Sampling.** Benchmarks are greedy. Assistants use temperature 0.2; Rapid also fuses the
  top-p sampler (`_sampler_fast_path.py`), which these numbers do not cover.

## Rollback

```bash
systemctl --user set-environment MSERIES_SERVE_PATCH=0   # stock server until unset or logout
systemctl --user restart mseries-ai-everyday
rm -rf ~/.local/share/mseries-ai/serve-patch            # or remove the copy for good
```

Drop both patch files when omarchy-mlx moves its default to the mlx-lm 0.32 line, which already
carries the logprob fix; re-measure the singleton path there before keeping it.
