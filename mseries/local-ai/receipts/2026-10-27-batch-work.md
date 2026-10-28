# M1 Pro Vulkan batch-budget experiment — 2026-10-27

## Result

The installed omarchy-mlx runtime already batches work. Its M1 Pro G13S is
uncalibrated in the pinned upstream source and therefore falls back to the
5,000-work-group per-submission budget. We tested the existing process-local
`MLX_OMARCHY_BATCH_WORK` override on the M1 Pro with the private ICD, not
TensorFold's unpublished engine or batching implementation.

![M1 Pro batch-budget paired timings](2026-10-27-batch-work-ab.png)

| Work budget | Submissions per measured request | Median paired total-time reduction vs 5,000 | Median reported decode tokens/s, baseline → candidate |
| --- | ---: | ---: | ---: |
| 10,000 | 429 → 248 | 10.34% | 36.99 → 43.24 |
| 20,000 | 429 → 141 | 16.37% | 36.98 → 45.98 |
| 40,000 | 429 → 104 | 13.82% | 37.84 → 47.11 |

The median decode rates compare medians of three runs per side, not a
confidence interval; timing and scheduler definitions are MLX's. The measured
submission delta includes prompt prefill and generation, so it is **not** a
per-token count. 40,000 had a slower first candidate run and is not a clear
winner over 20,000. All generated token IDs were identical across the 18 runs.
Token identity on one prompt does not prove general numerical equivalence.

## Method and limits

Each setting used three alternating pairs: baseline/candidate,
candidate/baseline, baseline/candidate. Separate processes each loaded the
same Qwen3.5-2B MLX 4-bit checkpoint at
`93760be4f1f69842a46bc13dbdc0f19e291392a3`, warmed up on the same prompt,
then generated 32 tokens greedily from the same 27-token prompt. The installed
MLX runtime ran on `7.2.11-elementary-aurora72-wip4`, private Honeykrisp
Mesa `7faf04c065`; its C trace ABI size was checked before reading counters.
Six-GiB desktop reserve, shared model lock, 4.5-GiB allowance and 80 C guard
were enforced. The user authorized fan speeds above 3500 RPM. Across the
three sweeps, the lowest sampled available memory was 9.11 GiB, highest fan
2522 RPM, and highest sampled temperature 52.129 C.

These short runs did not measure compositor frame pacing, long contexts,
4B/9B, multi-user concurrency, numerical logits, other prompts or sustained
thermals. Upstream intentionally caps submissions to protect desktop
responsiveness; raising the cap could cause stutter. **Do not enable this as
the default** based on these data. A guarded, process-local 20,000 smoke can be
run with `test-mlx-model-smoke.py --model <local-2B-checkpoint> --admission-gib
4.5 --batch-work 20000`; add `--allow-fan-above-3500` only with owner
authorization. The optional switch was verified by a successful short `19`
response in a separate run. No installed setting, worker or kernel was changed.

Raw per-run timings, counts, token IDs and samples: [10k](2026-10-27-batch-work-ab.json),
[20k](2026-10-27-batch-work-20k-ab.json), [40k](2026-10-27-batch-work-40k-ab.json).
The branch includes the guarded experiment and plotting scripts. To promote a
candidate, measure actual GPU submission duration and desktop frame pacing,
compare logits and output across representative models and contexts, retain
matched timing pairs, and verify reserve/thermal behavior. TensorFold's own
before/after benchmark still requires its unpublished source.

## Follow-up: higher budget and desktop animation probe

Two additional alternating six-process sweeps ran the same 2B workload with a
visible GTK 3 animated window. The probe records monotonic frame-clock callback
times, filtered to the measured inference interval. The frame clock observed
approximately 60 Hz even though the connected display advertises 119.91 Hz;
these are application callbacks, not scanout timestamps or input latency.

| Candidate | Median paired request-time reduction | Submissions baseline → candidate | Largest measured callback gap (baseline / candidate) | Gaps >33.33 ms |
| --- | ---: | ---: | ---: | ---: |
| 20,000 | 14.29% | 429 → 141 | 29.73 / 24.55 ms | 0 / 0 |
| 80,000 | 17.55% | 429 → 69 | 29.24 / 25.04 ms | 0 / 0 |

Each row is three matched pairs. All 12 generated sequences matched each other
and the previous experiment. The 80,000 reductions in individual pairs were
20.03%, 17.55% and 17.07%; the original 20,000 run without the desktop probe
showed 16.37%. These small, short tests do not establish a statistically reliable
winner, 30% improvement, sustained responsiveness, compositor input latency,
frame presentation, long-context behavior or numerical fidelity. 80,000 is an
experimental setting only; no default was changed. The probe can be occluded,
composited or throttled, and must not be mistaken for display presentation or
an interactive usability test. Full raw frame times and samples are retained in
[20k desktop](2026-10-27-batch-work-20k-desktop.json) and
[80k desktop](2026-10-27-batch-work-80k-desktop.json). Across both sweeps,
minimum sampled available memory was 9.38 GiB, maximum temperature 48.853 C,
and maximum fan speed 2528 RPM. The six-GiB reserve and 80 C stop remained.

The cached Qwen3.5 4B checkpoint was located at revision
`32f3e8ecf65426fc3306969496342d504bfa13f3`, but the guarded 20k model smoke
was refused before loading: 11.28 GiB available versus a 6.5 GiB model
allowance plus 6 GiB reserve. This is an admission result, not a 4B benchmark.
Retry when sufficient memory is available, then measure multiple prompts,
longer/sustained loads, presentation and interaction, and teacher-forced
fidelity before considering a default. After the MLX path is characterized,
repeat a matched Rapid-MLX comparison; the earlier Rapid numbers are not a
valid apples-to-apples ranking. The unpublished TensorFold engine remains
separate from this MLX budget experiment.
