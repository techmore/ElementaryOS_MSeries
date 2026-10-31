# macOS MLX measurements and TensorFold comparison scope — 2026-10-30

## Scope correction

These Mac measurements ran Apple MLX, not the TensorFold engine. They cover Qwen3.5 4B, Qwen3 4B Instruct and Qwen3.5 9B; they do **not** test Qwen3.5 2B, Liquid LFM3, Granite, Linux Vulkan, or TensorFold. The 4B model overlaps the project engine scoreboard, but the Mac runs used random synthetic 512/4096-token prompts and 128-token outputs, not the scoreboard's same-text 32/256-token workloads. They cannot be inserted into the scoreboard as matched comparisons. No Linux runtime, kernel, driver or service was changed.

## The intended project benchmarks

The current [`engine-compare.py`](../../engine-compare.py) has four named local scoreboard model configurations:

| Selector | Pinned model | Revision | Model weights SHA-256 | Current comparison arms |
|---|---|---|---|---|
| `qwen2b` | `mlx-community/Qwen3.5-2B-MLX-4bit` | `93760be4f1f69842a46bc13dbdc0f19e291392a3` | `713fe7e5d3c3965f7106b0d0ee17615f7869c23c8d327996df8c1196fbcf07d5` | MLX, servers, Rapid, oMLX, **TensorFold** |
| `qwen4b` | `mlx-community/Qwen3.5-4B-MLX-4bit` | `32f3e8ecf65426fc3306969496342d504bfa13f3` | `5fb9acd0246866381cf8c5c354c6db1019f6498eec4ccb4f5edcc71ffeacb2db` | MLX, servers, Rapid, oMLX |
| `lfm3` | `LiquidAI/LFM3-1.7B-MLX-8bit` | `ee7667f3cfccb2a41725f91820531823fcabc6b7` | `2b06cea98d75527c248a0b04383f7cf0a1c72fb4ed7b45096618fc4e59d015ad` | MLX 5k and 120k |
| `granite1b` | `mlx-community/granite-4.0-1b-4bit` (dense) | `29f108a4e2ff99079a173004871604c2f1e12c1f` | `b7a43ebbc86517b8ecfc4cff265a787ea31620f7eb356984c08abe14646617c7` | MLX, Rapid and selected servers |

The dense Granite selection is intentional; the hybrid Granite 4.0 H 1B is excluded because the GPU multi-token gate found a severe correctness failure. LFM3 used a separately pinned mlx-lm model implementation; check compatibility and pin its implementation when establishing a Mac reference. The project also has separate exploratory Qwen3.8-2B and ANE work; it is not one of these four `engine-compare.py` configurations. See [scoreboard](../../ENGINE-SCOREBOARD.md) and [Qwen3.8 receipt](../2026-10-27-qwen38-mac-rapid.md).

The benchmark harness uses short and long fixed rainbow prompts, greedy decoding, 32 or 256 generated tokens, fresh processes, one warmup and three rotated rounds. MLX in-process and server HTTP have different timing boundaries. The Linux experiments enforce the shared worker lock, memory reserve and temperature guard; use matched measurement boundaries when comparing macOS and Linux.

TensorFold's installed opt-in Vulkan engine is pinned to PR 1544 head `b3ab9ba217a80c63fcc48f7643ddfe339a8f4bdc`, and its current compatible scoreboard arm is Qwen3.5 2B. The [October 30 engine receipt](../2026-10-30-tensorfold-b3ab9ba/README.md) records a 32-token TensorFold loopback median of 2.89 tok/s and installed MLX in-process 54.51 tok/s with different timing boundaries; it does not justify a direct speed ratio. Long free-running text diverged after 880 characters, and strict teacher-forced exact-ID checks failed on near-ties in some cases. Do not claim full fidelity or a submit-batching gain. The [package receipt](../2026-10-30-tensorfold-package/README.md) records the installed opt-in package.

## What we actually measured on this Mac

[Model and shape report](model-shape-comparison.md) records six instrumented one-trial runs and their limits. Earlier three-trial native Apple MLX runs are retained in `*-baseline.log`. Separate synthetic 512/4096 prompt runs have their raw stdout in `*-p512.log` and `*-p4096.log`; the interrupted first Qwen3 4096 trace-save log is retained as `qwen3-4b-p4096-interrupted.log`. All six completed trace targets exited 0. The Mac's model files matched the hashes listed in the shape report; no correctness/fidelity comparison to TensorFold was performed. The first 4B baseline wrapper printed all results but failed when recording its shell exit status; its target exit status was not retained.

The original 4B System Trace contained 4,978 target-process active compute intervals over warmup and the measured trial; overlapping intervals are not a per-kernel dispatch count or elapsed GPU time. The Xcode Metal System Trace preflight also completed a synthetic 1024×1024 MLX matrix multiplication on the M1 Pro. Instruments did not collect shader timing or counters. Its shader pipeline lists are not dispatch counts or evidence that any named kernel dominates. The longer rolling captures include only the end of the workload. The separately captured warmed decode trace includes model buffers, and the system traces may contain private process metadata. The approximately 2.7 GiB trace bundles are retained locally on the Mac, not committed; this repository contains the synthetic logs and interpretation, not the original trace bundles or weights. `decode-capture.log` records the one-step capture result. These artifacts do not prove a Linux bottleneck or support a TensorFold speedup.

## Proposed next comparison for agreement

Use the four scoreboard model pins above, starting with Qwen3.5 2B for the TensorFold port. Reproduce the project's short 32-token and long 256-token synthetic prompts, greedy settings, warmup and round count on native macOS MLX. Capture the exact tokenizer/chat-template setup and token IDs, runtime versions and timing boundaries. Compare Apple MLX in-process to Linux MLX in-process first; compare HTTP servers only with equivalent HTTP servers. Then evaluate the TensorFold Vulkan 2B arm and preserve its separate numerical and text-fidelity gates. Repeat on M4 only with exact chip, OS and runtime recorded. A fresh Linux benchmark requires booting the M1 Pro into elementary OS; do not claim a fresh paired run from the historical results.
