# Honeykrisp `honeykrisp-omarchy-v3` candidate vs installed pin — 2026-10-19 (M1 Pro, G13S C0)

**Verdict: do not promote.** The candidate crashes the shader compiler on one cooperative-matrix shape. No decode A/B was possible. Nothing was installed; the `7faf04c065` pin in `install.sh` is unchanged and the desktop Mesa was not touched.

## What was compared

| | Revision |
|---|---|
| Installed pin | `joshuaswarren/mesa-1` `7faf04c065` = branch `honeykrisp-omarchy` tip (0 ahead / 0 behind) |
| Candidate | `honeykrisp-omarchy-v3` tip `f144c7949b` (2026-10-12) |

GitHub's compare API reports about 195,000 commits each way (unrelated histories, merge-base from 2010), so it is useless here. By patch subject, v3 has about 45 Joshua Warren patches the pin lacks: G13 compute codegen defaults, device-load hoisting, shared-memory address folding, log/rcp/division rework, heap sizing (90% of RAM, free-memory reserve), CDM barrier changes, bf16/fp16 cooperative-matrix shapes, optional submit poll (`HK_SUBMIT_POLL_US`). The pin has about 22 subjects v3 lacks (cooperative-matrix commits under older `asahi:` names, the repro directory, FP-control reverts).

## Method

Built the candidate with the exact `install.sh` meson flags, `nice -n 19`, `ninja -j3`, into a scratch prefix. Ran against it with `VK_DRIVER_FILES` plus `OMARCHY_MLX_SYSTEM_PREFIX`/`MLX_OMARCHY_HOME` pointing at a prefix holding the candidate ICD and a matching `mesa-git-sha`. Without that, MLX reports "no qualifying Vulkan device" and skips every test (a first run showed 0 assertions; it was discarded). Tests are the `omarchy-mlx` `61495cb` C++ binaries from `~/.cache/omarchy-mlx-candidate-61495cb` (CPU backend off) and `tests/` from the v3 tree. Each pair ran once, pin then candidate, on a loaded desktop.

## Results

| Test | Pin `7faf04c065` | Candidate `f144c7949b` |
|---|---|---|
| omarchy_runtime_tests | 59/59, 27,057 assertions | 59/59, 27,057 assertions |
| omarchy_reduce_row_tests | 6/6, 216 | 6/6, 216 |
| omarchy_vocab_tail_tests | 4/4, 6,942 | 4/4, 6,942 |
| omarchy_gdn_gqa_bf16a_tests | 6/6, 93 | 6/6, 93 |
| omarchy_matmul_family_tests | 41/43 (2 fail, `vector::_M_range_check`, CPU-off build) | 41/43, same 2 fail; 12 more assertions pass |
| `tests/run_matrix2.sh` (cmshape2) | 28 pass / 2 fail: `precise l32`, `precise l16` (8x8x8 f32, 16 mismatches) | 25 pass / 5 fail: `w 1/8/16/48/33 f16` (16x16x16 f16, workgroup size not 32) |

The pin's `precise` failures do not occur on the candidate (the candidate's run stops printing before that section because the process died, so it also did not execute the precise or divergent sections; they are unverified, not passed).

## The blocker

`./cmshape2 16 16 16 f16 f16 f16 f16 row randint 7 16` (any workgroup size other than 32) segfaults the candidate during pipeline compile: `pick_regs` in `agx_ra`, via `agx_compile_shader_nir` → `hk_compile_nir` → `vk_common_CreateComputePipelines`. The pin passes the same command. Workgroup size 32 passes on both. That is the software cooperative-matrix path; the suspects are the late-October register-allocation and software-lowering patches, but I did not bisect. A segfault in a compile path an MLX kernel could reach is not acceptable for the shared compute driver.

## Not done

- **No decode or token-identity A/B.** `mlx_lm.benchmark` needs the Qwen3.5-4B/9B MLX weights, which are not on this machine (no `*.safetensors` anywhere, no `~/.cache/huggingface/hub`). The wrapper `microbenchmark.py everyday` fails on the missing model path. Fetching them needs the owner's go-ahead.
- No bisect of the crash; no check of other v3 branches (`agent/v3-final3`, `jw16/omacom-pr`).
- Single run per cell; no repeated medians for timings.
- The crash has not been reported upstream. A report to `joshuaswarren/mesa-1` is the next step.

Raw run logs and summaries are in `2026-10-19-honeykrisp-v3-candidate/`.
