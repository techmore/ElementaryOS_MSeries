# Mac mini M4, macOS native (Metal) baseline, 2026-10-31

The Apple-native half of a same-machine comparison: these are the scoreboard's models, prompts, token counts and loads
run under macOS on the Mac mini M4, so the same `engine-compare.py` commands can later run under Linux on this mini
and be compared row for row. Table and chart: the "Mac mini M4" section of
[`ENGINE-SCOREBOARD.md`](../../ENGINE-SCOREBOARD.md), `engine-scoreboard-m4-mini-macos.csv` / `.svg`.

## Machine

| Item | Value |
|---|---|
| Hardware | Mac mini, `Mac16,10`, Apple M4, 10 CPU cores, 10-core GPU (`applegpu_g16g`, Metal 4), 16 GB |
| OS | macOS 27.0, build `26A5421a` |
| Power | AC power, low power mode off; `pmset -g therm` recorded no thermal or performance warning in any run |
| MLX's view of the GPU | `Apple M4`, max recommended working set 11.84 GiB (from `mx.device_info()`, in every receipt's `runtime`) |

## Load during the runs (read this before quoting a ratio)

The Lima VM `kbuild` (8 vCPU, 10 GiB, running CI) was busy for the whole session and was left alone. `top` put
`com.apple.Virtualization` at **390-590 % CPU** (about 4-6 of the 10 cores) at the start of every receipt, the
1-minute load average was **15.7-23.2**, and the VM held 10 GiB of the 16 GB, so macOS reported only 44-59 % of
memory free-able (`kern.memorystatus_level`) and 2.1-2.2 GiB of swap in use. Each receipt records `uptime`, the top
six CPU users, `limactl list`, free memory and swap at its start and end (`host_start`, `host_end`) and the load
average every second of every run (`samples[].load_avg`). The granite run also overlapped the last model download.

Decode is mostly GPU- and memory-bandwidth-bound, but per-token dispatch runs on the CPU, so these numbers are a
floor for this machine. Compare them with a Linux run under similar load, or re-run both with the VM stopped.

## Software

| Item | Value |
|---|---|
| Python venv | CPython 3.14.3, `uv venv` at `/private/tmp/claude-501/bench/venv`; full list in [`venv-freeze.txt`](venv-freeze.txt) |
| MLX | `mlx==0.32.3` (`mlx-metal==0.32.3`), `mlx-lm==0.31.3`, `transformers==5.16.1`: the pins omarchy-mlx's `m4-mini-bench` names for macOS (the MLX release mlx-omarchy is built from, and the Linux venv's mlx-lm) |
| LFM3 model code | mlx-lm 0.31.3 has no LFM3: `mlx_lm/models/lfm3.py` from mlx-lm PR 2016 head `9027ac5b062175fba890c612c3905d5d8d5b5294`, sha256 `a4096cdd…9b0c4` (checked by engine-compare, same file as the M1 Pro) |
| TensorFold | v1.1.9 release `tensorfold-1.1.9-macos-arm64.tar.gz` (sha256 `f8330102962550beea7d312eb78553f01539452fd442b7b195d63bc0f3ffa9d7`), `bin/tensorfold-native` sha256 `4b4b5a5ac152eb2dbed7e9d8004805ed9b74f77c64c3de18eb4f35263c7b9eb8`, the release `m4-mini-bench` pins; `serve --backend mlx --context 1024 --no-thinking --no-drafts` (drafts off to match the Vulkan build, which has none) |
| Models | the scoreboard's pins, from Hugging Face at these revisions; `model.safetensors` sha256 checked by engine-compare before each run |

| Model | Revision | `model.safetensors` sha256 |
|---|---|---|
| `mlx-community/granite-4.0-1b-4bit` | `29f108a4e2ff99079a173004871604c2f1e12c1f` | `b7a43ebbc86517b8ecfc4cff265a787ea31620f7eb356984c08abe14646617c7` |
| `LiquidAI/LFM3-1.7B-MLX-8bit` | `ee7667f3cfccb2a41725f91820531823fcabc6b7` | `2b06cea98d75527c248a0b04383f7cf0a1c72fb4ed7b45096618fc4e59d015ad` |
| `mlx-community/Qwen3.5-2B-MLX-4bit` | `93760be4f1f69842a46bc13dbdc0f19e291392a3` | `713fe7e5d3c3965f7106b0d0ee17615f7869c23c8d327996df8c1196fbcf07d5` |
| `mlx-community/Qwen3.5-4B-MLX-4bit` | `32f3e8ecf65426fc3306969496342d504bfa13f3` | `5fb9acd0246866381cf8c5c354c6db1019f6498eec4ccb4f5edcc71ffeacb2db` |

## Engines (macOS arms of `engine-compare.py`)

- `mlx-metal`: upstream MLX on Metal, in-process; the same worker as the M1 Pro's `mlx-*` arms (load, one warmup on
  the same prompt, one timed greedy generation). There is no submit budget on Metal, so there is one MLX arm, not
  two. It is the "same output" reference within each receipt, like `mlx-5k` on the M1 Pro.
- `lm-metal`: plain `python -m mlx_lm.server` from the same venv, none of our server patches (the macOS twin of the
  M1 Pro's `lm031-120k`). Our patched server is not run here: its small-rows patch targets omarchy's Vulkan kernels.
- `tensorfold-metal`: the TensorFold release above, Qwen3.5-2B only (the one checkpoint its Vulkan engine serves).

Guards: shared worker lock, one engine at a time, fresh process per run, three rotated rounds. macOS exposes no fan
or SMC temperature without root, so the thermal guard is `pmset -g therm`'s warning level, and the memory guard
uses `kern.memorystatus_level` with `--reserve-gib 1` (the M1 Pro's 6 GiB cannot be met beside a 10 GiB VM).

## Outcomes worth knowing

- Every completed row produced the same greedy text across its three runs.
- Against the M1 Pro (Linux, Honeykrisp Vulkan) reference text: identical for Granite 1B, LFM3, Qwen3.5-2B at
  32 tokens and all its concurrent rows. Qwen3.5-2B at 256 tokens: MLX and mlx_lm.server on Metal diverge from the
  M1 Pro after 1,207 of 1,301 characters, while TensorFold Metal matches the M1 Pro exactly. Qwen3.5-4B at 32
  tokens: in-process MLX on Metal diverges after 55 characters, while mlx_lm.server on Metal matches the M1 Pro.
  Both look like greedy near-ties resolved differently by different kernels (each output is fluent), not defects.
- `mlx_lm.server` at 8 requests at once failed all three rounds: 1-2 of the 8 simultaneous connections were reset
  (`ECONNRESET`) while the server kept serving the rest. Python's `ThreadingHTTPServer` listens with a backlog of
  5; macOS resets connections past it where Linux retries them. Not a model or GPU fault; at 4 requests it is fine.
  TensorFold served all 8.

## Fixed-work speed gate (omarchy-mlx `m4_mini_bench.py`)

The release-gate bench from techmore/omarchy-mlx branch `m4-mini-bench` (`1690652a`), macOS legs, same venv:
`m4-mini-bench-macos-*.json` here. Pair them with `omarchy-mlx-m4-bench` on Linux and
`m4_mini_bench.py --compare`. 512-token prompt, 128 generated tokens, 1 warmup + 5 runs, medians; all three
started at load average 19.8-21.5 (the script flags anything above 0.5).

| Leg | Prompt tok/s | Generation tok/s | Peak memory | Generated IDs |
|---|---:|---:|---:|---|
| MLX, Qwen3-1.7B 4-bit (default work) | 897.26 | 57.82 | 1.59 GB | `a9fec43a07727b81` |
| MLX, Qwen3.5-2B 4-bit | 852.90 | 54.36 | 1.81 GB | `1f20f523be2f3cfd` |
| TensorFold Metal v1.1.9 (pinned binary), Qwen3.5-2B 4-bit | 586.46 | 37.90 (spread 23 %) | 2.76 GB | `1f20f523be2f3cfd` (same as MLX) |

## Reproduce

```bash
python3.14 -m venv venv   # or: uv venv --python 3.14 venv
venv/bin/pip install mlx==0.32.3 mlx-lm==0.31.3 transformers==5.16.1 huggingface_hub
export HF_HUB_CACHE=$PWD/hf MSERIES_LFM3_MODULE=$PWD/lfm3.py \
  MSERIES_TF_BIN=$PWD/tensorfold-1.1.9-macos-arm64/bin/tensorfold-native
cd mseries/local-ai; O=receipts/2026-10-31-m4-mini-macos; E="../../venv/bin/python engine-compare.py --reserve-gib 1"
$E --model granite1b --output $O/2026-10-31-engine-compare-granite1b-short-metal.json
$E --model lfm3      --output $O/2026-10-31-engine-compare-lfm3-short-metal.json
$E --model qwen2b    --output $O/2026-10-31-engine-compare-qwen2b-short-metal.json
$E --model qwen2b --concurrency 4 --output $O/2026-10-31-engine-compare-qwen2b-short-metal-c4.json
$E --model qwen2b --concurrency 8 --output $O/2026-10-31-engine-compare-qwen2b-short-metal-c8.json
$E --model qwen2b --long --output $O/2026-10-31-engine-compare-qwen2b-long-metal.json
$E --model qwen4b    --output $O/2026-10-31-engine-compare-qwen4b-short-metal.json
$E --model qwen4b --concurrency 4 --output $O/2026-10-31-engine-compare-qwen4b-short-metal-c4.json
python3 scoreboard.py
```
