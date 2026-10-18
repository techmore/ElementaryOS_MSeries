# Omarchy Mac/MX and MLX feature comparison — October 18, 2026

This review informs the [agent-first Pantheon MCP/WebRTC proposal](PANTHEON-MCP-DESIGN.md) and the next performance experiments for this **M1 Pro 32 GB**. It compares exact public revisions, not project names or advertised token rates. It does not install a new wheel, change governors, replace desktop Mesa or repeat the completed model trials.

## Which upstream and which revision?

| Source | Reviewed revision | Interpretation |
|---|---|---|
| `maralcbr/omarchy-mx-mac` main | `e5714f9d2fe27f6e4e54d47849b856c596d1a351` | Historical MX feature set and migration reference |
| `omacom/omarchy-mac` quattro-upstream | `a76179cdcf1e844251eecac2708b687c486aa497` | Apple Silicon integration branch named by its convergence spec |
| Same repository's default quattro | `ba546a61f881c1fe9d79d75ec050eab048b8cb63` | Reviewed separately; repository default and integration branch are not identical |
| `joshuaswarren/omarchy-mlx` main | `d8ac5fe1e136f0b3e15ceea7ef91f68a4f209a9c` | 28 commits ahead of our tested source pin at review time |
| Our tested MLX runtime | `33630f9c1eeefe5fc985a28bed0585432c2c014e` | v0.7.33; installed wheel `0.32.4.dev202610160529+33630f9c`, mlx-lm 0.31.3 |

The [Mac convergence spec](https://github.com/omacom/omarchy-mac/blob/a76179cdcf1e844251eecac2708b687c486aa497/docs/apple-silicon-convergence.md) designates quattro-upstream for Apple Silicon integration and limits MX to security/boot fixes. Read its migration goals as a plan, not proof every feature is released. The latest MLX release was still v0.7.33 when checked; a newer main commit is not a newly qualified release.

[Machine-readable source audit](receipts/upstream-review-2026-10-18/source-audit.json) records 27 reviewed files, content hashes, immutable URLs and four developer heads. All three source repositories report MIT licenses; this review redistributes metadata and our analysis, not upstream source. The compare endpoint capped its file list at 300, so this is a targeted review, not a complete 28-commit code audit. Recursive source inventories were not truncated.

## Desktop, agents and interaction

| Upstream function | Our current state | Direction for Pantheon |
|---|---|---|
| Unified notification history, silencing and action routing | Fault signatures are collected; there is no shared alert/workflow inbox yet | Reuse the interaction contract through a native Pantheon broker/inbox. Respect the owner's quiet policy. |
| Crash notification opens a selected coding agent with coredump facts | `recent_faults` supplies bounded kernel/app evidence; automatic model diagnosis is off | Carry event identity, evidence and acknowledgement into the proposed alert agent. Require qualified explanation/action paths. |
| Default-agent launcher supports several coding harnesses | Newelle personal/desktop, Crush coding and experimental Hermes launchers | Share capabilities and grants between clients; do not transplant global bypass-permission flags. |
| Voxtype configuration/model management | Existing F5 native streaming capture with Parakeet; live universal insertion still unqualified | Keep engine/language controls and capture status native; separate dictation from agent commands. |
| MLX assistant voice controls and optional wake word | No speech-to-speech agent session or WebRTC service | Reuse proven components where their contracts fit; add explicit conversation sessions and broker authorization. |

Omarchy's [notification sender](https://github.com/omacom/omarchy-mac/blob/a76179cdcf1e844251eecac2708b687c486aa497/docs/notifications.md) uses typed D-Bus parameters and discrete arguments for action targets. Its Quickshell-specific persistence/hints cannot simply be copied into Pantheon. Borrow the separation between content and actions, and test native notification-server restart behavior. Our proposed durable alert acknowledgement is distinct from notification dismissal.

The [crash launcher](https://github.com/omacom/omarchy-mac/blob/a76179cdcf1e844251eecac2708b687c486aa497/bin/omarchy-agent-crash) forwards facts to the configured agent. That is an interaction precedent, not evidence that our small local model can diagnose kernels. The [general launcher](https://github.com/omacom/omarchy-mac/blob/a76179cdcf1e844251eecac2708b687c486aa497/bin/omarchy-agent) also selects harness-specific unattended flags. Our scoped broker must enforce access independently of a harness's prompting mode.

The default quattro branch's [older MLX menu installer](https://github.com/omacom/omarchy-mac/blob/ba546a61f881c1fe9d79d75ec050eab048b8cb63/bin/omarchy-install-ai-mlx) only admits the base M1. It is not the hardware capability boundary for today's separately maintained MLX runtime. Do not copy that obsolete restriction into the M1 Pro distro.

## Serving, model and voice choices

| Option inspected | Why it matters here | Decision |
|---|---|---|
| MLX-LM single-model serving, shared reservations and explicit context | Matches our one-worker design and bounded context/cache | Retain it as the measured default. Keep the extra six-GiB reserve and live guards. |
| Resident assistant + Laya typed-decision pair | Laya supplies structured choices, not general prose | A future classifier candidate; measure error/calibration and total resident cost before admission. Do not add it merely to receive alerts. |
| oMLX Linux packaging and multi-request/cache paths | Potential shared-agent throughput improvements | Experimental, isolated candidate. Need real 4B M1 Pro completions, cache-hit proof, context cap and shared budget before replacing the current server. |
| Dedicated Bonsai-2 packed MLX module | A different runtime/checkpoint from our tested 9B GGUF | Review separately. Our 5.57 tok/s GGUF result does not score the native 27B packed module. |
| Qwen3-TTS 0.6B and Kokoro 82M | Concrete local speech-output choices for WebRTC conversations | Compare time-to-first-audio, underruns, intelligibility, memory and cancellation. Start opt-in; avoid two resident TTS workers. |
| Whisper/Parakeet input and optional wake word | Reusable speech paths and UI behavior | Compare against existing transcribe.cpp Parakeet on identical clips. Push-to-talk first; no new always-listening default. |

The upstream [serving contract](https://github.com/joshuaswarren/omarchy-mlx/blob/d8ac5fe1e136f0b3e15ceea7ef91f68a4f209a9c/docs/serve.md) retains unqualified pair-level gates even where component tests pass. Its preferred 9B/Laya pair is not our measured retained-app workload. Our 4B default remains based on this Mac's reserve and app results. Its voice section supplies candidate engine/voice controls; it does not qualify our proposed WebRTC session.

The [oMLX Linux guide](https://github.com/joshuaswarren/omarchy-mlx/blob/d8ac5fe1e136f0b3e15ceea7ef91f68a4f209a9c/docs/omlx-linux.md) distinguishes real M2 Max chat from stubbed admin-UI checks and warns against claiming unobserved prefix-cache behavior. Aggregate concurrent throughput must not be presented as single-user latency. Native [Bonsai serving evidence](https://github.com/joshuaswarren/omarchy-mlx/blob/d8ac5fe1e136f0b3e15ceea7ef91f68a4f209a9c/docs/plans/2026-09-20-bonsai2-serve-qualification.md) includes failed/hung attempts and pending HTTP gates; a small packed checkpoint is not sufficient qualification.

## Performance switches: useful candidates and exclusions

| Option/change | Upstream evidence and limits | M1 Pro action |
|---|---|---|
| `MLX_OMARCHY_GDN_PF_GQA=1` with the untiled prefetch route | New opt-in f32-A_log native key-head indexing. PR #229 reports about 8–9% over tiled defaults on M1 Max/M2 Max, unchanged measured tokens/log probabilities; limited prompts/one boot per machine | Highest-interest 9B experiment after installing a separately built pinned candidate. Verify route eligibility for 4B independently. No M1 Pro gain claimed. |
| `MLX_OMARCHY_ARGREDUCE_CHUNKED`, `MLX_OMARCHY_LSE_CHUNKED` | Opt-in large vocabulary-row routes; distinct equality/numerical contracts | Test one flag at a time, then interactions; measure actual serving benefit and quality. |
| `MLX_OMARCHY_ROW_REDUCE` | Newly on by default; changes float summation order. Qwen9/27B profiles cited upstream do not reach that route | Audit new defaults before a bump. Do not promise a 4B speedup from a microkernel improvement. |
| `MLX_OMARCHY_UCLAMP_MIN` | Existing process placement hint; model/kernel-dependent | Already attempted by our runtime; current kernel returns EPERM. Record unsupported placement rather than report a gain. Do not change kernel/governor to hide it. |
| CPU performance governor | Served M1 Max experiment gains about 2.3%, with roughly 2 W greater idle system power | Keep current governor. That tradeoff is unattractive as an always-on quiet default, and is not an M1 Pro result. |
| Batched GDN/SDPA, KV host offset, RoPE and QMV paths | Some improvements apply to batched mlx-lm 0.32/oMLX; our server uses 0.31.3 and one generation | Evaluate only with the intended new server/concurrency, preserving the shared budget. Do not enable inapplicable flags and claim improvement. |
| `MLX_OMARCHY_GATHER_QMM_WORD` / `...WORD2` | Large speed figures accompany rejected/unaccepted fidelity verdicts; developer switches remain off | Exclude from supported presets. Kernel speed is insufficient evidence of acceptable model output. |

Sources: [new native-GQA PR and receipt limits](https://github.com/joshuaswarren/omarchy-mlx/pull/229), [flag routing contracts](https://github.com/joshuaswarren/omarchy-mlx/blob/d8ac5fe1e136f0b3e15ceea7ef91f68a4f209a9c/docs/kernel-flags.md), [known numerical limits](https://github.com/joshuaswarren/omarchy-mlx/blob/d8ac5fe1e136f0b3e15ceea7ef91f68a4f209a9c/docs/KNOWN-ISSUES.md), [governor experiment and workload distinctions](https://github.com/joshuaswarren/omarchy-mlx/blob/d8ac5fe1e136f0b3e15ceea7ef91f68a4f209a9c/docs/BENCHMARKS.md).

The known-issues record also reports a substantial GPU decode loss with a continuously busy ANE on a base M1. Its cause and exact scope are limited. This is a reason to test ASR/TTS plus LLM contention on our Pro, not assume that moving voice to the ANE always makes the system faster or quieter.

## Developer branches are candidates, not upgrades

Against the frozen main revision above:

| Branch | Head | Ahead / behind | Relevance |
|---|---|---|---|
| agent/fambonsai | `a25544592a34` | 5 / 776 | Bonsai kernel work; heavily diverged |
| agent/bonsai2-serving | `98373d10b9b3` | 5 / 1675 | Native packed serving history; heavily diverged |
| agent/OmlxCache-rows | `f5b6478fee33` | 13 / 711 | Cache/benchmark tooling history; heavily diverged |
| w71/muse-gate-up-fusion | `2da255d8a7ba` | 2 / 25 | Open draft PR #201; Muse expert fusion, not a demonstrated dense-4B benefit |

These are Git graph counts, not a patch-equivalence analysis or a performance ranking. A branch can have unique commits and still be far behind the reviewed runtime. PR #229 was already merged by this snapshot; its new flag still defaults off. Continue the existing six-hour all-head/PR watcher rather than treating named branches as the complete discovery set. The repaired run retained 1,114 public heads with zero fetch errors; pins advance only after review and local evidence.

## Next controlled experiments

1. Finish the current Calendar/browser/Mail cohort without changing its runtime. Publish successes, failures, resource samples and cooling time; retain the original source snapshot.
2. Build a separate candidate from the frozen newer MLX revision and its required private driver/wheels. Check hashes, patch status, matrix/compiled primitives, context cap, reservation cleanup and numerical gates before loading a model. The new `--patch-venv`/patch-status support is worth adopting in that reviewed upgrade path, not applying mid-cohort.
3. Run a baseline/candidate A/B with the same model pin, prompts, context, cache treatment, kernel and retained app state. Rotate order over at least three rounds after cool admission. Compare end-to-end workflow quality, first text, decode, total latency, available RAM and fan/temperature samples. Reject a faster candidate that loses task/tool correctness or reserve compliance.
4. Gate GQA and other relevant switches individually on the candidate. Repeat single-user and bounded multi-client workloads separately; label unsupported routes. Preserve failed outcomes instead of tuning the benchmark until it passes.
5. Before voice-agent rollout, compare sequential ASR→LLM→TTS with overlapping engines. Measure microphone release, first audio, interruption, quality, power and fan behavior. Add WebRTC reconnect/permission tests after the local pipeline passes. Keep kernel, bootloader, running audio and display configuration outside this experiment.

The practical recommendation remains the tested 4B/one-worker preset today, with newer native-GQA and properly bounded multi-client serving as the most useful next investigations. The upstream feature comparison is part of the design and experiment backlog; it is not substituted for M1 Pro results.
