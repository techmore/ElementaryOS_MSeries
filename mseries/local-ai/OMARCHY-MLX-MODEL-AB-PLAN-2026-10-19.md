# omarchy-mlx candidate model A/B plan — October 19, 2026

Planning only. No models were launched or stopped for this plan.

## Current readiness

- Candidate source `61495cb` builds at `~/.cache/omarchy-mlx-candidate-61495cb`; selected C++ results are recorded in [the candidate build receipt](receipts/2026-10-19-omarchy-mlx-candidate-build.md). It has no Python bindings or wheel yet, so it cannot currently run the model A/B.
- The installed runtime remains v0.7.33. Keep it intact as the baseline.
- At 08:00 EDT on October 19, `mseries-ai-everyday.service` was failed, not active. Its log says the explicitly named `qwen3.5-4b-mseries-4bit` target is incomplete locally and offline mode refused to download it. No MLX model worker process was present. `mseries-ai-quality.service` was inactive. Confirm model availability and restore a healthy baseline before any comparison; do not count this failure as an A/B result.
- The 9B profile is configured as `qwen3.5-9b-mlx-4bit`; model files were not confirmed in this readiness check.

## Candidate preparation gate

1. Build the Python-enabled candidate runtime from the frozen `61495cb` source in a separate prefix/venv. Do not run the repository installer or write into `/usr/lib/omarchy-mlx` or `~/.local/share/mlx-omarchy`.
2. Keep mlx-lm pinned to the version/API the candidate supports. Do not apply the upstream 0.32-only server patches to our installed 0.31.3 environment. Use an isolated direct generation harness unless the private server patches are reviewed and applied to the candidate venv.
3. Verify candidate and baseline library provenance and hashes, model revision and file completeness, Vulkan device/ICD, and effective environment flags before the first model load. Verify that logs/counters show the selected kernel route is actually reached.
4. Use fixed local prompts and greedy decoding. Save token IDs, timing samples and telemetry to a new receipt; omit personal prompts or model output containing private data.

## 4B row-reduce comparison

Target: the exact 4B model revision used by the everyday profile, once its complete local files and healthy baseline are confirmed.

1. Compare candidate `MLX_OMARCHY_ROW_REDUCE=1` with candidate `MLX_OMARCHY_ROW_REDUCE=0`; also record installed v0.7.33 as a baseline if it can load the same exact model files. The primary feature comparison is candidate on/off, since v0.7.33 predates this route.
2. First do a short route-reachability/profile check. If this model does not dispatch a qualifying long-row Sum, stop: record “route not reached,” with no performance claim.
3. If reached, run deterministic greedy generations with identical prompt, context and max tokens. Compare token IDs, then compare at least three alternating on/off rounds after equivalent warm-up and cooling. Record load time, first-token latency, decode time, peak/available memory, temperature and fan samples.
4. Accept only exact token identity for the numerics gate. Treat any speed difference as local to this model, prompt, machine and run conditions.

## Optional 9B GDN experiment

Target: `qwen3.5-9b-mlx-4bit`, using the existing `quality` profile's 8K context and 9 GiB admission budget. Do not use the 64K `personal` profile for this kernel comparison.

1. Confirm the exact 9B files are complete and that 9B admission leaves the documented additional 6 GiB desktop reserve. If admission refuses or the model is absent, skip this leg; do not download weights during the quiet window.
2. Compare candidate `MLX_OMARCHY_GDN_PF_GQA=0` and `=1`, with identical greedy prompts, context and token limit. Because the GPU identifies as `Apple M1 Pro (G13S C0)`, do not assume the automatic G13C/G14C route applies. The opt-in must be proven by dispatch evidence before measuring it.
3. Check token identity and route reachability first, then use at least three alternating rounds with the same warm-up/cooling treatment. Capture decode time, memory, temperature and fan. If the flag does not select the native-GQA route on this GPU, record no result rather than treating fallback timing as a kernel comparison.

## Worker control and quiet window

Do not run either leg until the everyday service is healthy and a quiet window is agreed. Suggested window: after 10:00 PM Eastern, with 60 minutes available and the machine plugged in, only if the owner expects no interactive desktop work during that period.

At the start of each leg, stop the managed model-worker services listed in `mseries/local-ai/README.md`, including everyday, quality, coder, compact and optional model units, plus any legacy `mlx-omarchy-chat.service` that is actually running. Verify there are no remaining owned MLX inference workers and that the shared worker lock is free. Do not stop dictation/audio services or other unrelated desktop services. Run only one model at a time. Restore the healthy everyday service after the leg and verify its readiness before ending the window.

Honor the existing policy: 6 GiB minimum desktop reserve; pause at 2700 RPM / 70 C and resume at 2600 RPM / 65 C; stop on the existing hard limits. Missing required telemetry or an unavailable reserve means skip the run. No governor, kernel, system Mesa, boot or audio changes.

## Decision

Do not bump the installed runtime from C++ unit tests alone. A bump candidate needs a Python-capable isolated build, a healthy baseline, route reachability, exact token identity for the 4B comparison, and no reserve/thermal regression. Treat 9B GDN as optional evidence, not a release prerequisite if the route cannot be selected on G13S.
