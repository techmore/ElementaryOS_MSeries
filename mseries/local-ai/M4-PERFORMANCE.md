# M4 Mac mini performance tracker

Track the J773g Mac mini across Gravity, the WIP Omarchy port and native macOS.
The goal is to match and, where possible, exceed native performance on the same
workload while retaining correct results and a responsive desktop. A faster
result on one benchmark is a result for that workload, not a claim that the
whole system is faster.

## Current status

| Environment | Kernel or OS | Baseline | Status |
| --- | --- | --- | --- |
| Gravity Linux | `7.1.13-509.gravity.fc44.aarch64+16k` | M4 GPU enumerated; no model speed result | October 28 matrix multiply timed out; October 30 tiny add produced an incorrect result and a GPU timeout. [First receipt](receipts/2026-10-28-m4-mini-first-mlx-attempt.md); [October 30 receipt](receipts/2026-10-30-m4-mlx-preflight.md). |
| Omarchy WIP | WIP5 J773g forward port | Not measured | Integration and build in progress; not boot-qualified. |
| macOS | Same Mac mini | Not measured | Matched native runs and their version are needed. |

The existing [engine scoreboard](ENGINE-SCOREBOARD.md) is from an M1 Pro and
provides workload definitions and reference methods, not M4 performance data.

## Model baseline matrix

Use the existing [`engine-compare.py`](engine-compare.py) model pins, prompts,
generation lengths and resource guards where the runtime supports them.
Record each model's exact revision, quantization and weight hashes so an M4
result can be compared with the same model on native macOS. The table below is
the target set, not a claim that a run completed.

| Workload | Model and format | Gravity | Omarchy | macOS |
| --- | --- | --- | --- | --- |
| Small dense language model | Granite 4.0 1B, MLX 4-bit | Pending | Pending | Pending |
| Small language model | LFM3 1.7B, MLX 8-bit | Pending | Pending | Pending |
| Language and code | Qwen3.5 2B, MLX 4-bit | Pending | Pending | Pending |
| Larger language model | Qwen3.5 4B, MLX 4-bit | Pending | Pending | Pending |
| Native Vulkan engine comparison | TensorFold, Qwen3.5 2B | Pending | Pending | Pending |

Track CPU, GPU, memory bandwidth, storage, graphics responsiveness, sustained
power and thermals alongside AI. Add other workloads when a reproducible
fixture and a comparable native run exist. For sound and desktop use, keep
functional correctness separate from raw speed.

## Recording a run

Save a dated receipt for each run or attempt, including failures, and link it
from this page. Include:

- Local date, time and timezone; machine/model, memory and OS version.
- Kernel release and build identity; firmware, graphics driver, runtime and
  backend versions; whether the workload ran on CPU, GPU or ANE.
- Model identifier, revision, quantization, exact input/prompt, token count,
  settings and run count. Record **SHA-1 and SHA-256** for each model weight
  file and for saved benchmark outputs; record hashes of kernel and driver
  artifacts where available. Hash files in place instead of making copies.
- Correctness checks, time to first token, decode tokens/s, total time, peak
  memory, temperature/power where available, and desktop responsiveness.
  Preserve individual runs and report the statistic used. Keep single-request
  speed distinct from aggregate throughput under concurrency.
- For a native comparison, use the same model files, prompt, token count and
  quantization. State any engine or measurement differences, and calculate
  the ratio only for comparable completed runs.

Use the existing shared worker lock, memory and thermal guards; capture a
failure rather than presenting it as a zero-speed result. Keep downloads and
builds isolated, use one model at a time when space is tight, and remove
temporary copies after recording their hashes and receipts. A benchmark result
does not qualify boot, dual boot, storage durability or the entire GPU stack.
