# M1 Pro Metal profiles: model and prompt shapes

**Scope correction:** These are exploratory Apple MLX profiles, not TensorFold Vulkan benchmark results. They do not cover the TensorFold 2B checkpoint or the full engine scoreboard. See [README](README.md) for the exact relevant model set and next comparison.

Captured October 30, 2026 on the M1 Pro Mac, macOS 27.2, MLX 0.31.2, mlx-lm 0.31.3. Each row is one instrumented measured trial after a warmup, batch 1, 128 generated tokens, prefill step 256, offline and two OMP/OpenBLAS threads. These are profiling runs under variable background load, not three-trial controlled baselines. Tracing can affect timing.

| Model | Prompt tokens | Prompt tok/s | Generation tok/s | Peak MLX GiB | Trace |
|---|---:|---:|---:|---:|---|
| Qwen3.5 4B MLX 4-bit | 512 | 275.781 | 53.441 | 3.088 | Complete System Trace, full run |
| Qwen3.5 4B MLX 4-bit | 4096 | 283.301 | 48.802 | 3.273 | Complete System Trace, last 3 seconds |
| Qwen3 4B Instruct 2507 4-bit | 512 | 283.930 | 52.096 | 2.856 | Complete System Trace, full run |
| Qwen3 4B Instruct 2507 4-bit | 4096 | 255.632 | 43.227 | 3.333 | Complete retry, last 3 seconds |
| Qwen3.5 9B MLX 4-bit | 512 | 151.570 | 30.633 | 5.680 | Complete System Trace, last 10 seconds |
| Qwen3.5 9B MLX 4-bit | 4096 | 153.487 | 30.322 | 5.826 | Complete System Trace, last 3 seconds |

The Qwen3 4096 initial run produced 256.876 / 41.495 tok/s; its trace save was stopped when disk space fell below 5 GiB. That interrupted attempt's log (`qwen3-4b/p4096.log`) is retained and is not a completed trace; the table uses the separately completed bounded-window retry. A rolling window covers only the end of its run and cannot establish full-run kernel counts or prefill coverage. The Instruments table of contents recorded successful target exit for all six completed traces. Trace data may include system process metadata; keep it local or review it before sharing.

## Model and shape clues

The Qwen3 4B 512 trace shader list includes quantized QMV/QMM and `sdpa_vector_bfloat16_t_128_128...`, plus steel attention kernels. The Qwen3.5 4B 512 and Qwen3.5 9B lists include quantized QMV/QMM, a gated-delta step, and `sdpa_vector_bfloat16_t_256_256...`. The 9B 4096 trace's shader list also includes `sdpa_vector_2pass_1_bfloat16_t_256_256...` and `sdpa_vector_2pass_2_bfloat16_t_256`; those names were not present in the exported 9B 512 list. The rolling windows differ, so absence from a list does not prove a kernel never ran. Shader-list entries are pipeline metadata, not kernel time rankings, invocation counts, or proof of the source of the Linux gap. No GPU counters or shader timeline were enabled in these recordings.

## Linux work to target

- Capture the matching three models and 512/4096 shapes on bare-metal elementary OS with the existing memory, fan, temperature and quiet guards. Record actual kernel dispatch names, shapes, counts and GPU times. Use the same model revisions, prefill step and token budget; compare instrumented profiles separately from uninstrumented speed trials.
- Check whether Linux selects fast 4-bit group-64 quantized matrix-vector/matrix kernels for these shapes; distinguish single-token decode from prompt prefill. Measure before changing launch dimensions, fusion, memory access or dispatch behavior.
- For Qwen3.5, check the real gated-delta path and the attention route, including whether longer-context inputs trigger a two-pass equivalent. Compare Qwen3 attention shapes independently rather than assuming the 4B models execute alike.
- Establish route reachability before testing candidate row-reduce or GDN switches. Preserve existing fidelity and deterministic token gates, alternative-off controls, and at least three alternating uninstrumented baseline/candidate trials. The existing Honeykrisp candidate compiler regression remains a blocker to promotion.
- Preserve Linux/Mac hardware, runtime, ICD/driver and load metadata. A macOS profile cannot establish an elementary OS bottleneck or guarantee the same effect on M4.

## Model provenance

- Qwen3.5 4B revision `32f3e8ecf65426fc3306969496342d504bfa13f3`; model SHA-256 `5fb9acd0246866381cf8c5c354c6db1019f6498eec4ccb4f5edcc71ffeacb2db` matched the project catalog.
- Qwen3 4B revision `50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b`; SHA-256 `2a73c6c248601ab904e035548abd8e6abb65ea27dcb5f342fb0a8910eb44173f` matched the previous benchmark download.
- Qwen3.5 9B revision `938d8919941c6e7efd3c7150eff7fe9d12afa631`; shard hashes `a68b87558c6ef43f74c2bd63ce7e9092ceddc3101f3def0030774bae5f42aadd` and `b0a770bf8469c7f3f18756a0e0283f1c1174344a83e059a4e483f6af4907352d` matched the earlier benchmark.

Sanitized raw logs are committed alongside this report. The large trace bundles and warmed single-step `.gputrace` remain local only; they contain system process metadata or model buffers and are not committed. Temporary downloaded model directories were removed after profiling.
