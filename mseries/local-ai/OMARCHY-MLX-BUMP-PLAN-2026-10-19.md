# omarchy-mlx bump-candidate plan — October 19, 2026

Review only. Nothing was installed, built or pinned. Sources were read from shallow/full clones of public `main`; no kernel, governor, Mesa or running-model changes.

## Revisions

| Item | Revision |
|---|---|
| Our pin | v0.7.33, `33630f9c1eeefe5fc985a28bed0585432c2c014e` (still the latest GitHub release on 2026-10-19) |
| Upstream main reviewed | `61495cb66cb9a5fb8e127001c7c1eb959a9d6c22` (#239, 2026-10-18), 36 commits past our pin, none released |
| `mil-hwx-compiler` | main `45f7670` (2026-10-18), CHANGELOG cut 0.3.0; `ane-compiler.lock` in omarchy-mlx pins `a8392e6` |
| `omarchy-ane` | main `94cceca` (2026-10-16), release 0.4.9; MIT |

## What changed, and what it means for the M1 Pro (T6000, 32 GB, Qwen3.5-4B default)

| Change | Default | M1 Pro relevance | Verdict |
|---|---|---|---|
| #231 GDN decode: untiled prefetch + native GQA | **On, only when the Vulkan device name contains G14C or G13C** | Needs f32 A_log and Hk != Hv (Qwen3.5-9B). Upstream measured about 8% on M1 Max/M2 Max. Our M1 Pro's device string is not recorded; it may be G13S/G13C-class. Our 4B route eligibility is unchecked. | **Does not apply by default here**: the device is `Apple M1 Pro (G13S C0)` (measured 2026-10-19), which contains neither G14C nor G13C. Only the explicit `MLX_OMARCHY_GDN_PF_GQA=1` opt-in could reach it; test that on 9B only |
| #229/#225 GDN native GQA opt-in flags | Off | Superseded by #231 for f32; #225 is for bf16 A_log models | Skip unless a model needs it |
| #226 Row-reduce Sum (workgroup per row) | **On** (`MLX_OMARCHY_ROW_REDUCE=0` disables) | Changes summation order for float sums over rows of 256 or more outside fused kernels. Upstream says Qwen3.5-9B and 27B profiles contain no Reduce dispatch. Qwen3.5-4B is not profiled. One Muse NLL check fell outside the registered bound (Apache passage −0.0124 vs 0.01). | Bit-compare 4B greedy output on/off before accepting; keep the kill switch in the profile |
| #223 ArgMax/LogSumExp chunked routes | Off | Possible large-vocab sampling help; separate numerics contract | Optional one-at-a-time test |
| #232 rotating-KV maskless, #233 skip per-token logprob read | Opt-in patch / applied by serve patches | #233 touches mlx-lm server behavior our `mseries-ai` supervisor wraps; #232 targets the 0.32 series (we run mlx-lm 0.31.3) | Review `mlx-lm-server-skip-logprob-read.patch` against our private prefill-256 / thinking-off patch for conflicts. Skip #232 |
| #224/#216/#214 gather_qmm word / mxfp4 kernels | Off / developer switch | MoE only; numerics verdict REJECT upstream | Exclude |
| 6-bit affine quantized_matmul decode (`75cc013b`) | On | Only if a 6-bit model is used | Low value |
| #239 mlx-audio depthwise Metal gate backport | Optional | Not used by our stack | Skip |
| #227 governor doc | n/a | +2.3% for about +2 W idle, M1 Max | Keep current governor (already our decision) |
| `--patch-venv`, versioned patch directories (`patches/mlx-lm-0.32/`) | n/a | `install.sh` refactor: our `mseries/local-ai/install.sh` wraps the upstream installer at v0.7.33 and expects the old flat `patches/` layout | Must re-test our wrapper on the new installer |
| #213 known issue: busy ANE costs 44% of 9B decode (13-inch M1) | n/a | Directly relevant if ANE voice is added; not measured on the Pro | Measure before any ANE+LLM use |

Net: no commit is a clear win for the 4B default. The only plausible gain is the 9B decode route (#231), which is hardware-name gated and unverified on T6000.

## ANE side (your two links)

- **omarchy-ane**: lists M1 Pro (T6000) "on by default", with one passing smoke row. This host already has the driver bound: `/dev/accel/accel0`, driver `ane`, `apple,t6000-ane` on `7.1.12-elementary-aurora20-enh1`. Verified it is the in-tree module (`intree: Y`), so the Arch-oriented DKMS package is not needed; do not replace the working driver.
- **mil-hwx-compiler**: a MIL to ANE-package compiler (H13 = M1 family, targets our chip). It is a build-time input to omarchy-mlx's ANE bundles (`ane-compiler.lock`), not a runtime dependency for chat. Relevant only if we want our own ANE programs or Parakeet encoder bundles; the omarchy-mlx aarch64 wheel already ships the pinned Parakeet bundles. H13 support is fixed-shape fp16 with a limited op set. LICENSE file present (verify terms before redistributing).
- Existing doc `ANE-PREFLIGHT.md` already covers part of this; the ANE+GPU contention risk (#213) is the main gate.

## Proposed bump procedure (not executed)

1. ~~Record device string and ANE driver source~~ Done 2026-10-19, read-only: Vulkan `Apple M1 Pro (G13S C0)`, Honeykrisp, system Mesa 26.0.8-1ubuntu0.3 (the private compute ICD is separate); ANE bound to `ane` (`apple,t6000-ane`), in-tree module `kernel/drivers/accel/ane/ane.ko` (`CONFIG_DRM_ACCEL_ANE=m`, no DKMS).
2. Build a candidate **beside** the running runtime (separate prefix, `MSERIES_AI_SOURCES` copy), using main `61495cb` or a release if one appears. Preserve the v0.7.33 runtime; do not touch desktop Mesa.
3. Read the `apply-mlx-lm-patches.sh` diff; confirm our private patch (prefill 256, thinking off, rsqrt/RMSNorm numerics) still applies.
4. Run upstream C++ tests (`omarchy_reduce_row_tests`, `omarchy_gdn_gqa_bf16a`) on the Pro.
5. A/B with workers stopped, one change at a time, medians over repetitions: Qwen3.5-4B greedy token identity with `ROW_REDUCE` on/off; Qwen3.5-9B decode with `GDN_PF_GQA` on/off; record load, temperature and fan.
6. Promote only on token-identical output and no reserve/thermal regression. Otherwise keep v0.7.33 and set `MLX_OMARCHY_ROW_REDUCE=0` if the next release defaults it on.
7. Update `local-ai/install.sh` pin, `UPSTREAM-FEATURE-COMPARISON.md`, `OS9-HANDOFF.md` and `ROADMAP.md` only after the measurements.

## Not verified

Whether the 4B model reaches the row-reduce or GDN routes; license terms for `mil-hwx-compiler` binaries; any benefit on this host (all figures above are upstream's on M1 Max/M2 Max, one boot each).
