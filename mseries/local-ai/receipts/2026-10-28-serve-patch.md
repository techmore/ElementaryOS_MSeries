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

## Round 2: first token and parallel requests (same day, PR after #672)

**First token.** A trace of the 0.6 s first token on a 27-token prompt (launcher's
`MLX_OMARCHY_TTFT_TRACE=1` plus per-step timing) showed reading the prompt took 0.23 s, and
0.31 s went to building two streaming detokenizers per request, each copying Qwen 3.5's
248k-token vocabulary (`get_vocab`, ~0.15 s each, holding the GIL).
`patches/mlx-lm-0.31.3-detokenizer-tokenmap-cache.patch` builds that map once per tokenizer.

**Parallel requests.** Upstream's launcher passes `--decode-concurrency 1 --prompt-concurrency 1`
so its admission only has to reserve one request's KV: 8 parallel requests got their first tokens
one by one, 0.8 s apart (5.9 s for the last). `configure-serve-concurrency.py` (applied in place
by `install.sh`, like `configure-prefill.py`) makes `MSERIES_SERVE_CONCURRENCY=N` pass N to both
flags and adds (N-1) x the context's KV to admission, refusing when KV-per-token is unknown, as
upstream does for `--prompt-cache-size`. Unset, upstream behavior is unchanged. `model-worker.py`
sets 4 for MLX profiles (`concurrency` in a profile overrides): +0.75 GiB reserved for the
everyday Qwen 4B at 8,192 tokens (32 KiB/token; only 8 of its 32 layers keep a growing cache).
For local folders `engine-compare.py` computes `MSERIES_SERVE_KV_BYTES_PER_TOKEN` from config.json.

Decode tok/s (several requests: total) and median first token; text identical in every run:

| | Stock upstream | Patched + batching of 4 | Rapid-MLX |
| --- | ---: | ---: | ---: |
| Qwen 2B, 1 request | 33.0 (0.62 s) | **56.2** (0.25 s) | 50.6 (**0.21 s**) |
| Qwen 2B, 4 at once | 20.2 (4.08 s) | **57.0** (**0.77 s**) | 42.6 (1.15 s) |
| Qwen 2B, 8 at once | 20.3 (8.08 s) | **57.7** (2.97 s) | 49.2 (**1.93 s**) |
| Qwen 4B, 1 request | 20.4 (0.85 s) | **27.9** (0.51 s) | 25.7 (**0.22 s**) |
| Qwen 4B, 4 at once | 12.8 (6.27 s) | **25.8** (**2.04 s**) | 21.2 (2.25 s) |

Receipts: the same names as above with `-round2`, plus
`…-qwen4b-short-hk9323171c12-c4-serve-120k+serve-patched-120k+rapid-120k.json`.
Through the installed worker: plain answer, tool call, logprobs, and 4 parallel requests answered
together in 2.2 s.

## Round 3: multi-turn chats reuse the conversation (same day)

Chats re-send the whole conversation every turn. mlx-lm 0.31.3 already saves a cache at the end of
the system prompt and at the end of each question (before the 4-token reply header), which is
the prompt-only copy Rapid-MLX makes by hand, and Qwen 3.5's untrimmable recurrent layers can
resume from it. But our worker passed `--prompt-cache-size 1`, and with a system prompt the
eviction order keeps the system entry and drops the question, so every turn re-read all history.

Everyday Qwen 4B through the patched server, 236-token system prompt, two 4-turn
conversations, greedy, identical text in both settings (`multiturn-probe.py 1` and `4`, receipts
`2026-10-28-multiturn-qwen4b-hk9323171c12-cache{1,4}.json`):

| Turn | Prompt tokens | Reused, 1 entry | First token, 1 entry | Reused, 4 entries | First token, 4 entries |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 258 | 0 | 1.44 s | 0 | 1.45 s |
| 2 | 310 | 236 | 0.72 s | 254 | 0.69 s |
| 3 | 362 | 236 | 0.78 s | 306 | 0.66 s |
| 4 | 402 | 236 | 1.02 s | 358 | 0.63 s |
| 2nd chat, turn 4 | 450 | 236 | 1.12 s | 401 | 0.65 s |

With 4 entries only the last reply and the new question are read (~50 tokens), so first token
stays flat as the chat grows. `model-worker.py` now defaults to 4 entries at 8k context and 2 at
16k (each entry reserves a full context of KV: +0.75 GiB for the everyday 4B); `personal` keeps its
explicit 1 at 64k. Through the installed worker: turns 2 and 3 reused 257 and 271 tokens.

## Still open

- **Batching does not add throughput here.** 4 or 8 requests share about the same total
  tok/s as one (56-58 on Qwen 2B), on Rapid too; batching buys fairness and first-token time,
  not more tokens. Worth a look at the batched decode path on Honeykrisp.
- **First token for one request.** 0.25 s (2B) and 0.51 s (4B) against Rapid's 0.21-0.22 s.
  The prompt is read in two GPU passes (user part, then a 4-token tail kept for the prompt
  cache), and each pass with more than one token has ~70 ms fixed cost on this stack.
- **Sampling.** Benchmarks are greedy. Assistants use temperature 0.2; Rapid also fuses the
  top-p sampler (`_sampler_fast_path.py`), which these numbers do not cover.

## Rollback

```bash
systemctl --user set-environment MSERIES_SERVE_PATCH=0 MSERIES_SERVE_CONCURRENCY=1   # stock server, one at a time
systemctl --user restart mseries-ai-everyday
rm -rf ~/.local/share/mseries-ai/serve-patch            # or remove the copy for good
```

Drop both patch files when omarchy-mlx moves its default to the mlx-lm 0.32 line, which already
carries the logprob fix; re-measure the singleton path there before keeping it.
