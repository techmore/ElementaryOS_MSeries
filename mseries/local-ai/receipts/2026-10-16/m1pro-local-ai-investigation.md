# Local AI for elementary OS on M1 Pro

Research date: October 16, 2026. Target: the M1 Pro with 32 GB RAM running ElementaryOS_MSeries. Scope: a desktop assistant, a coding assistant, a personal assistant, and continuous system diagnostics.

**Recommended direction:** build on the project's existing private Honeykrisp and Linux MLX integration. Use Qwen3.5-9B 4-bit as the initial shared conversational model, evaluate Newelle as the desktop interface, and evaluate Hermes for persistent personal assistance. Add a separate coding profile using Qwen3-Coder-30B-A3B through llama.cpp Vulkan. Extend the existing robot troubleshooter and upstream watcher for kernel events and developer branches. Bonsai 2 is a high-priority challenger; Liquid's smaller models are candidates for lightweight routing and extraction.

These are deployment candidates, not a measured ranking on this Mac. Published performance, project installation receipts, and proposed integration are distinguished below.

**What the project already has**

The current public project revision checked was `247d5c064dc93029d7944d9f60879feb64cc5ef8`. Its documentation records MLX v0.7.32, a private Honeykrisp compute driver at Mesa `7faf04c065`, MLX Chat, a Crush local agent using Qwen3.5-9B, and a native robot indicator with log diagnosis. It also has performance snapshots, task briefings, and read-only task/energy tools. The recorded services load models on demand; automatic crash diagnosis defaults off. These are documented installation results from October 12–13, not a fresh inspection of the running laptop. [Project integration](https://github.com/techmore/ElementaryOS_MSeries/blob/247d5c064dc93029d7944d9f60879feb64cc5ef8/mseries/local-ai/README.md)

The recorded Crush setup needed prefill chunks of 256 tokens after its full tool prompt exhausted a Vulkan allocation. Coding-specific tools were hidden to reduce overhead. A new coding profile should restore the tools it needs and qualify a real edit/test cycle. The existing synthetic tool call and short replies establish connection, not coding competence. [Agent receipt](https://github.com/techmore/ElementaryOS_MSeries/blob/247d5c064dc93029d7944d9f60879feb64cc5ef8/mseries/local-ai/receipts/2026-10-13-agent.md)

The upstream watcher is operational: the latest three runs returned success. The latest observed run was October 16 at 12:40 PM Eastern. [Latest observed run](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38933805701)

**Which upstreams matter now**

The MX repository is useful, but its README now says it is feature-frozen and accepts security and boot fixes. It directs new Apple Silicon work to `omacom/omarchy-mac` on `quattro-upstream`, and installer work to `omacom/omarchy-mac-installer`. Therefore, following only MX would miss important new work. [MX maintenance notice](https://github.com/maralcbr/omarchy-mx-mac#readme)

For elementary, continue using `omacom/omarchy-mac-pkgs` as the hardware-package reference and translate behavior to Ubuntu/Pantheon. Track `joshuaswarren/omarchy-mlx` for inference, `joshuaswarren/omarchy-ane` for Neural Engine work, `omacom/mesa` and the developer's Mesa branches for compute-driver changes, and both Aurora and Asahi Fairydust for relevant kernel changes. The project's existing port map establishes the Ubuntu/Pantheon boundary. [Port map](https://github.com/techmore/ElementaryOS_MSeries/blob/247d5c064dc93029d7944d9f60879feb64cc5ef8/mseries/PORT-MAP.md)

Observed public heads during this investigation:

| Repository and branch | Revision |
|---|---|
| joshuaswarren/omarchy-mlx main | `f856bf864e3a` |
| omarchy-mlx release v0.7.33 | `33630f9c` |
| joshuaswarren/omarchy-ane main | `f45847c26f74` |
| omacom/omarchy-mac-pkgs main | `ffe5246c98a8` |
| maralcbr/omarchy-mx-mac main | `e5714f9d2fe2` |
| omacom/omarchy-mac quattro-upstream | `a76179cdcf1e` |
| aurora-silicon/linux aurora-stable | `b04581b4e67c` |
| aurora-silicon/linux aurora-rc | `2439016d2e8d` |
| aurora-silicon/linux aurora-edge | `79f87ae69078` |

These are discovery snapshots, not proposed kernel or package upgrades. The accompanying JSON records branch comparisons and their source URLs.

**Performance evidence that changes the choice**

An outside report matches the target configuration: M1 Pro/T6000, 32 GB, on battery, Qwen3.5-9B MLX 4-bit, v0.7.32. Switching from system Mesa 26.2.4 to the private Honeykrisp ICD changed prompt processing from **20.5 to 151.0 tokens/sec**, while generation changed from **23.0 to 23.8 tokens/sec**. It is one reporter's result, not our own benchmark. Nevertheless, it makes the private driver a priority for code, document, and log reading. Our recorded private driver is a different revision and needs its own measurement. [M1 Pro report](https://github.com/joshuaswarren/omarchy-mlx/issues/104#issuecomment-6108693960)

The upstream Linux benchmark table also shows that engine choice depends on the model:

| Model and measured hardware | MLX generation / prompt tokens per second | llama.cpp Vulkan generation / prompt tokens per second |
|---|---:|---:|
| Qwen3.5-9B, M1 Max 64 GB | 37.1 / 299.4 | 19.8 / 171.1 |
| Qwen3-Coder-30B-A3B, M2 Max 94 GB | 11.68 / 132.01 | 34.84 / 299.80 |
| Qwen3.6-35B-A3B, M2 Max 94 GB | 12.87 / 143.62 | 29.13 / 305.79 |

These are directional results from different chips, driver builds and quantization formats, with documented load/governor limitations. They justify testing both engines; they do not predict M1 Pro speed or establish equal output quality. [Benchmark methods and results](https://github.com/joshuaswarren/omarchy-mlx/blob/f856bf864e3a/docs/BENCHMARKS.md)

**Software to package**

| Candidate | Fit for this project | Decision |
|---|---|---|
| Newelle | GTK desktop app with local models, long-term memory, profiles, voice, documents, tools and MCP | First desktop-interface candidate |
| Hermes Agent | Persistent personal memory, user profiles, session recall, reusable skills and custom model endpoints | First personal-agent candidate |
| Existing Crush integration | Already installed and wired to the local API | Keep; create a separate coding profile |
| Open WebUI | Rich browser interface with memory and tool integrations | Strong alternative if browser UX is preferred |
| MLX Chat | Already integrated and close to the hardware stack | Keep as a reference client; its full assistant has qualification gaps |
| LM Studio | Current documentation supports Linux ARM64 | Optional polished model workbench; qualify its bundled backend on Honeykrisp |
| Ollama | Convenient model/API management; current docs enable Vulkan when installed | Optional convenience layer; verify actual Apple GPU use and model compatibility |

Newelle offers much of the requested desktop experience already, and Flathub publishes an aarch64 build. Its GTK interface fits the platform technologically, although Pantheon appearance, global shortcuts and voice behavior still need evaluation. Connect it to the host's pinned inference service so its Flatpak does not determine GPU-driver selection. [Newelle features](https://github.com/qwersyk/Newelle#features), [ARM64 distribution](https://flathub.org/en/apps/io.github.qwersyk.Newelle)

Hermes is an agent application, distinct from the Hermes model family. Its memory and skills make it a stronger candidate for learning the individual's preferences and recurring work. Configure a local endpoint and local tools deliberately: choosing local inference alone does not make optional search, speech or browser providers local. Use separate personal and system-diagnostic profiles. If Newelle and Hermes are both retained, choose one owner for personal memory rather than maintaining conflicting profiles. [Hermes Agent](https://github.com/NousResearch/hermes-agent)

Open WebUI's memory quality depends on the connected model's ability to use tools correctly. The same practical constraint applies to any assistant: remembering a fact, retrieving the right fact, and acting correctly are separate tests. [Open WebUI memory](https://docs.openwebui.com/features/chat-conversations/memory/)

LM Studio now explicitly supports Linux ARM64; older claims that it is x86-only are stale. Ollama's current Vulkan documentation also supersedes older advice that always labels its Vulkan path experimental. Neither generic platform statement qualifies this Mac's driver/model combination. [LM Studio requirements](https://lmstudio.ai/docs/app/system-requirements), [Ollama GPU documentation](https://docs.ollama.com/gpu)

**Model defaults and challengers**

| Role | Initial choice | Reason and qualification needed |
|---|---|---|
| Everyday conversation and personal tools | Qwen3.5-9B MLX 4-bit | Existing project integration and exact-chip outside evidence; start with bounded context |
| Compact mode | Qwen3-4B-Instruct-2507 MLX 4-bit | Already recorded working in project chat |
| Coding | Qwen3-Coder-30B-A3B-Instruct Q4_K_M with llama.cpp Vulkan | Dedicated coding model; upstream Linux MoE results favor this engine |
| Higher-quality conversation | Qwen3.8-27B 4-bit, loaded on demand | Quality challenger; do not inherit the upstream 96 GB paired-profile requirement as the requirement for this model alone |
| Compressed quality challenger | Bonsai 2 27B, then newly published smaller variants | Attractive footprint; exact format and runtime must pass numerical and tool tests |
| Lightweight routing/extraction | LFM2.5-1.2B-Instruct or LFM2.5-350M | Candidate for short structured tasks; no M1 Pro performance qualification here |
| System diagnosis | Existing Qwen3.5-derived profile, compared against Qwen baseline | Project evidence is preliminary; diagnosis must remain tied to supplied logs |

Qwen3-Coder has 30.5B total parameters and 3.3B active; its memory footprint follows the total weights. Start its service around 8K–16K context and measure actual peak usage before raising the limit. Qwen3-Coder-Next has 80B total parameters despite only 3B being active: at four bits, raw weights alone are about 40 GB decimal, making it unsuitable as a conventional fully resident default for this 32 GB desktop. [Qwen3-Coder model](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct), [Coder-Next model](https://huggingface.co/Qwen/Qwen3-Coder-Next)

Bonsai 2 27B is based on Qwen3.8-27B. The published special GGUF packings have 5.95 GB and 7.21 GB language weights; runtime buffers and context add memory. The current demo says recent upstream llama.cpp supports official `Q2_0` with the required model/Hadamard integration, while `PQ2_0` and `PTQ1_0` still require PrismML's fork. Generic Hugging Face launch buttons and the `.gguf` extension do not establish compatibility. [Model packing](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf), [Current upstream support](https://github.com/PrismML-Eng/Bonsai-demo#upstream-support)

Linux Bonsai promotion needs special care: the omarchy-mlx catalog has historical qualified flags alongside an explicit unqualified scope statement, and a build receipt records failed GPU numerical paths. The newer small models are listed on PrismML's account, but their publication is not evidence of Linux performance. Benchmark the supported Q2_0 route first and keep the exact loader, transforms and checkpoint together. [Pinned Linux catalog](https://github.com/joshuaswarren/omarchy-mlx/blob/f856bf864e3a/serve/mlx_omarchy_serve/catalog.json), [GPU build receipt](https://github.com/joshuaswarren/omarchy-mlx/blob/f856bf864e3a/receipts/2026-10-08-bonsai-build/README.md), [PrismML models](https://huggingface.co/prism-ml)

Liquid's models are promising for fast intent classification, extraction and short tool requests. LFM2.5-VL-3B is also a candidate for screen understanding. Advertised AMD/mobile performance is not M1 Pro Linux evidence. The 1.2B card lists the custom LFM license; handle its distribution terms separately from Apache-licensed Qwen/Bonsai artifacts. [LFM2.5 model](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct), [Vision model](https://www.liquid.ai/blog/lfm2-5-vl-3b)

The project's current diagnostic model is Ornith 1.5 9B. Its documentation records a useful initial result on one real journal, but only two inputs and one run per model. It also records an unresolved license at the pinned artifact. Keep it as a personal comparison candidate; choose a clearly licensed baseline before bundling a default for other users. [Project diagnostic profile](https://github.com/techmore/ElementaryOS_MSeries/blob/247d5c064dc93029d7944d9f60879feb64cc5ef8/mseries/local-ai/README.md#ornith-15-9b-local-crash-and-log-troubleshooting)

**Developer branches and recent releases**

The MLX repository exposed 460 branch heads. Selected relevant comparisons show why branch names cannot be treated as a queue of ready upgrades:

| Branch | Unique commits / commits missing from current main | Assessment |
|---|---:|---|
| agent/bonsai2-serving | 5 / 1651 | Old divergent work; inspect current implementation first |
| agent/fambonsai | 5 / 752 | Old divergent kernel work; no promotion from its name |
| agent/OmlxCache-rows | 13 / 687 | Primarily old qualification tooling |
| agent/laya-head-latency | 1 / 996 | Old probe work |
| w71/muse-gate-up-fusion | 2 / 1 | Current draft; no Vulkan timing and cluster blockers |

These are GitHub graph comparisons against `f856bf864e3a`, not patch-equivalence checks. A unique commit can duplicate a squash-merged change. [Current draft PR](https://github.com/joshuaswarren/omarchy-mlx/pull/201)

MLX **v0.7.33 was released today**. It fixes compiled `rsqrt` returning `sqrt`, affecting compiled RMS normalization; it also includes low-bit gather kernels and a long-prefill memory fix. Test this release as the next runtime candidate before spending effort on speculative branches. Preserve the project's prefill patch and compare eager/compiled outputs after upgrading. The release is not proof that the existing local workload was affected. [Release notes](https://github.com/joshuaswarren/omarchy-mlx/releases/tag/v0.7.33)

The newer Honeykrisp optimization PR remains explicitly unready: its current head passed targeted cases, but broad regression qualification is pending and earlier builds had regressions. Keep this work isolated to compute processes during evaluation. [Mesa PR 6](https://github.com/omacom/mesa/pull/6)

Joshua's personal `feat/cpu-governor-on-ac` branch proposes performance governor on AC and schedutil on battery. Its documented gains are on other M1 models; battery and thermals remain unmeasured. Compare governor settings on this M1 Pro under the native power policy before adopting the behavior. [Mac packages PR 33](https://github.com/omacom/omarchy-mac-pkgs/pull/33)

oMLX is worth evaluating for cache reuse and model serving, but avoid treating the engine list's 82–91 tokens/sec claim as a general Qwen Coder result. Its specific offload receipt reports approximately 2.25 tokens/sec on M1 Max for a model with only 25% expert residency. Workload and cache state explain why a headline cannot select the default. [Engine overview](https://github.com/joshuaswarren/omarchy-mlx/blob/f856bf864e3a/docs/ENGINES.md), [Offload measurements](https://github.com/joshuaswarren/omarchy-mlx/blob/f856bf864e3a/receipts/2026-10-09-omlx-upstream-pin/README.md)

MLX Chat's Qwen-plus-Laya pairs also have remaining full-assistant gates. Laya scores bounded choices rather than generating conversation; it does not provide personal memory. The upstream assistant design records incomplete voice/latency qualification. Use the existing text chat where it helps, and evaluate the desktop/personal apps separately. [Assistant qualification boundary](https://github.com/joshuaswarren/omarchy-mlx/blob/f856bf864e3a/docs/plans/2026-09-27-offline-assistant-design.md), [Laya contract](https://github.com/joshuaswarren/omarchy-mlx/blob/f856bf864e3a/serve/mlx_omarchy_laya/CONTRACT.md)

**Always available assistant and kernel diagnostics**

Keep the robot indicator, event collection, personal state and update checks running cheaply. On AC, keep one Qwen3.5-9B worker warm when memory allows. Serialize its requests and reuse it for personal conversation and short diagnostics. Load the larger coding model exclusively when coding begins; unload or pause the conversational worker when its combined memory budget cannot fit. Battery and memory pressure can unload weights while leaving the assistant available to start again. These are proposed service policies, not current settings.

Extend the existing system assistant with the following behavior:

1. **Kernel event collection.** Watch GPU faults/timeouts, OOM kills, lockups, oops traces, storage errors, failed services and suspend/resume failures. Group repeated messages by boot and subsystem. The current watcher filters systemd-coredump events for the user's UID; kernel warnings are collected only when analysis runs. It therefore cannot provide continuous kernel fault detection by itself. [Current watcher](https://github.com/techmore/ElementaryOS_MSeries/blob/247d5c064dc93029d7944d9f60879feb64cc5ef8/mseries/local-ai/crash-watch.py)
2. **After-reboot evidence.** Read the previous persistent journal and pstore when available. A hard panic can prevent final journal writes, so distinguish missing evidence from a clean boot. Capture kernel taint, loaded modules, boot parameters and source/build identity with the fault.
3. **Machine-aware relevance.** Record T6000/j314s, the kernel/config, m1n1 and DTB identities, compute ICD and desktop Mesa separately. Reject M2 Air, M3 or Neo fixes as automatically applicable to M1 Pro.
4. **Developer discovery.** Extend the existing six-hour watcher to inspect selected contributors' forks, open PRs and branch tips. Compare merge bases, patch content, changes to relevant files, numerical evidence and measured hardware. Rank releases and concrete fixes above unmeasured experiments. Keep fetching deterministic; use the model to summarize the resulting evidence.
5. **Optimization comparisons.** Link a relevant patch to a local symptom, then run a bounded before/after workload. Report latency, power, memory, faults and output quality together. Prepare a patch or update proposal with rollback information; preserve the existing known-good boot path.
6. **Notifications.** Show actionable regressions, newly relevant fixes, failed checks and qualified improvements. Deduplicate recurring faults and keep unchanged state quiet.

The present GitHub watcher tracks one configured/default branch and the latest release per repository. Its user-discovery path looks at the most recently pushed repository. It does not perform comprehensive branch/fork/PR discovery. Extend that mechanism rather than creating a second unrelated update monitor. [Watcher implementation](https://github.com/techmore/ElementaryOS_MSeries/blob/247d5c064dc93029d7944d9f60879feb64cc5ef8/mseries/local-ai/github-watch.py)

**Validation and implementation order**

First, qualify v0.7.33 with the existing private driver and prefill behavior. Then connect Newelle to the shared local service and test personal memory and existing task/energy tools. Add kernel-event collection and branch-aware upstream discovery. Finally, compare the dedicated coder and Bonsai/Liquid challengers.

Use fixed, task-relevant inputs: real project bug fixes with hidden tests, noisy logs with known outcomes, cross-session personal-memory questions, and structured tool requests including abstention. Measure cold load, first visible answer, 512/4096-token prompt processing, generation, long-turn peak memory, idle resource use and battery impact. Record exact model hashes, runtime/driver revisions, governor and context settings. A model must complete the task correctly before faster output counts as an improvement.

The investigation produced recommendations and source evidence. It did not install software, change model defaults, enable automatic diagnosis, or alter the laptop's kernel or boot configuration.
