# omarchy-mlx main candidate build and C++ tests — 2026-10-19 (M1 Pro, G13S C0)

Candidate: omarchy-mlx `61495cb` (main, unreleased), MLX 0.32.3 pin `9c3d355`. Built in `~/.cache/omarchy-mlx-candidate-61495cb` (disk, not tmpfs), `nice -n 19`, `ninja -j2`. Nothing installed; the v0.7.33 runtime and its workers were untouched and kept running.

## Configuration

`prepare-mlx.sh` then cmake Release with `MLX_BUILD_OMARCHY=ON MLX_BUILD_TESTS=ON MLX_BUILD_CPU=OFF`, no Python bindings, no wheel (the wheel build also needs the 458 MB pinned whole-encoder bundle, not fetched). `MLX_BUILD_CPU=ON` failed to configure: no BLAS/LAPACK dev packages (`lapacke.h` absent). I did not install them.

## Result: 1350/1350 build steps linked

Tests were run against the private Honeykrisp ICD (`VK_DRIVER_FILES=~/.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json`), concurrently with the normal desktop load. Only 5 of the 52 test binaries were built.

| Binary | Cases | Result |
|---|---|---|
| omarchy_runtime_tests | 59 | pass (27,057 assertions) |
| omarchy_reduce_row_tests (row-reduce Sum, now default) | 6 | pass (216) |
| omarchy_gdn_gqa_bf16a_tests (GDN native GQA) | 6 | pass (93) |
| omarchy_vocab_tail_tests (chunked ArgMax/LogSumExp) | 4 | pass (6,942) |
| omarchy_matmul_family_tests | 43 | 41 pass, **2 fail**, 83,471,241 assertions passed, 0 failed |

The 2 failures are `gather_qmm tile route stays off below four rows per expert` and `gather_qmm sorted-expert tile route matches the f32 reference…`, each throwing `vector::_M_range_check` on an empty vector (lines 6084 and 6128). These tests build an f32 reference on the CPU stream; other cases in the same binary print `Skipping: no CPU backend`. The likely cause is my CPU-off build, **not confirmed**. They cover MoE gather_qmm only, which the dense Qwen3.5-4B default does not use.

## What this does not show

- No model run: no Qwen3.5-4B token-identity check with `MLX_OMARCHY_ROW_REDUCE`, no 9B decode A/B. The test passes are unit-level, one boot, one run.
- Not tested with CPU=ON, the sanitizer flags, or the other 47 binaries.
- No wheel was built, so the Python side (mlx-lm patches against 0.31.3) is unchanged from the dry-run receipt.
