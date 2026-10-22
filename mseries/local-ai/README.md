# Local assistants on the M1 Pro

The October 16 setup uses private Linux MLX v0.7.33, Newelle for desktop and personal assistance, and a separate 16K coding profile for Crush. Qwen3.5 4B is the measured default for the 32 GB M1 Pro; Qwen9 is an optional larger preset. [Measured results, methods and limits](receipts/2026-10-16.md) explain the provisional model choices. [Exact revisions and licenses](receipts/2026-10-16/source-pins.json) accompany the synthetic raw results.

## Install and launch

```sh
bash mseries/local-ai/install-assistants.sh --runtime  # install/update the private MLX runtime first
bash mseries/local-ai/install-assistants.sh            # explicit model/client downloads and user setup
mseries-assistant desktop
mseries-assistant personal
mseries-assistant coding
# Larger presets only when enough RAM is available:
mseries-assistant --quality desktop
mseries-assistant --quality coding
```

The Applications menu has Desktop Assistant, Personal Assistant and Coding Assistant. Desktop and Personal open Newelle, with a local user-summary memory that can be inspected and reset in Memory preferences. No embedding model is needed for this memory. Tasks, calendar components, workspace notes, system measurements and fault signatures are available through the local MCP adapter. Tool execution stays within the configured adapter surface. Broad Newelle shell, arbitrary-file, subagent, screenshot and network tools are hidden in the preconfigured profile. User-defined modes or later settings can expand that surface.

## T3-R assistant provider

The same local assistant can be added to T3-R as a server-side ACP command. On
the paired T3 server, run `python3 mseries/local-ai/configure-assistants.py
--install-acp`, then choose **Settings → Providers → Add an ACP provider →
MSeries Assistant…** in T3-R. This installs only `mseries-assistant-acp`; it
does not change Newelle settings, model profiles or running services. The bridge
uses the already-supervised `127.0.0.1:8766` endpoint and existing sixteen-tool
`os-mcp.py`; it does not start or switch a model, connect to a remote endpoint,
or add shell/arbitrary-file tools. Each local write goes through T3's ACP
permission policy. The opted-in Newelle user-summary memory is read at session
start when Flatpak/Newelle is installed; T3 retains chat history, while edits to
that summary still belong to Newelle. If another supervised MSeries profile is
already running on port 8768, the ACP command can be given
`--endpoint http://127.0.0.1:8768/v1`; the bridge still does not start or switch
that profile. Start the supervised Desktop Assistant service if the default
local endpoint is unavailable.

The ACP bridge bounds prompts, retained history and tool results for the
default 8K context. Long individual results and aggregate tool output in a turn
are truncated before they return to the model. Completed turns are kept in a
bounded ACP context cache under `$XDG_STATE_HOME/mseries-ai/acp-sessions` (or
`~/.local/state/mseries-ai/acp-sessions`): at most 24 messages / 12,000
characters per thread and 512 threads. Snapshot writes are atomic, with a
private directory and owner-only files. ACP `session/load` restores context
after a T3 or agent restart; `session/close` frees its MCP process but retains
the snapshot. The current Newelle summary is loaded again on resume. These
snapshots are chat context, not model KV state; the bridge keeps using the
supervised llama.cpp worker's single prompt-cache slot and stable system/tool
prefix.

The initial setup downloads pinned Qwen3.5 4B and 9B weights (roughly 9 GB combined), Newelle's ARM64 Flatpak/runtime, and the pinned clients. Model weights and personal state stay in the user's home. Factory images stage the offline runtime and compute ICD under `/usr/lib/omarchy-mlx`, llama.cpp under `/usr/lib/mseries-ai/llama`, and user setup under `/usr/share/elementary-mac`. First-user setup uses those runtimes without apt writes to immutable `/usr`. Factory runtime staging and pruning pass; a full image build and hardware boot with this AI layer remain separate qualification steps.

`install.sh` preserves a previous runtime and restores it on failed updates, refuses active MLX workers, pins both MLX and the private compute Mesa, and defaults to two build jobs. System Mesa, the bootloader, kernel and audio stack are preserved. Our private patch bounds prefill to 256 tokens and disables thinking by default; an API request may explicitly enable thinking. The compiled rsqrt/RMSNorm check covers the numerical fix in v0.7.33.

## Memory and cooling

`~/.config/mseries-ai/profiles.json` owns the policy. One supervised inference worker holds `~/.local/state/mseries-ai/worker.lock`. Launchers switch between managed profiles and check the model identity at readiness. Admission budgets are 6.5 GiB for Qwen3.5 4B everyday/coding, 9 GiB for 9B/8K, and 10 GiB for 9B/16K coding, all in addition to a six-GiB desktop reserve. A real busy-desktop Qwen9 MCP run crossed that reserve despite the earlier upstream estimate, so its budgets were raised and it is no longer the everyday default. The 4B coding fixture completed with at least 8.51 GiB available. These are admission estimates; live telemetry stops inference if real use exceeds the available headroom. Full setup explicitly adopts these primary presets while retaining policy and unrelated profiles; standalone configuration preserves existing choices unless `--adopt-compact-defaults` is specified.

Fresh profiles sample every second, pause owned submissions at 2700 fan RPM and resume at 2600, with 70/65 C temperature hysteresis. Three-second work bursts after thirty-second cooling intervals permit progress when the idle baseline shifts. Three consecutive samples below the six-GiB reserve, above 3500 RPM, or above 80 C stop the owned model. Missing fan/temperature telemetry refuses admission. Existing policy files are preserved on upgrades; absent soft thresholds use the launch baseline plus 300/100 RPM and a three-second sample interval. Fan RPM is a noise proxy, not a dBA measurement. A cooling pause increases response time; it does not change governors or fan control. Unrelated workloads can still make the whole computer loud and stop a model.

```sh
systemctl --user status mseries-ai-everyday
journalctl --user -u mseries-ai-coder -n 40
systemctl --user stop mseries-ai-everyday mseries-ai-quality mseries-ai-coder9 mseries-ai-compact mseries-ai-compact35 mseries-ai-personal mseries-ai-coder mseries-ai-coder7 mseries-ai-liquid mseries-ai-bonsai
```

Newelle uses the pinned Qwen3.5 4B on port 8766 with an 8K server cap. Crush uses the same weights on port 8768 with 16K: the initial full prompt exceeded 11K; disabling unused tools reduced the tested prompt to 7,720 tokens. Only one supervised model is resident at a time. `--quality` selects Qwen9 and a separate coding workspace; a refused switch attempts to restore the previous managed model. Older Qwen3 4B, 7B GGUF, Liquid and Bonsai profiles are optional comparisons. The uninstalled 30B plan budgets 21 GiB plus reserve and does not fit this retained app mix. No ANE or conversational voice stack is qualified. Native CPU Parakeet F5 dictation and its Dictation panel are installed, with an owner-reported speech-to-field pass; translation is still post-utterance. [Speech status and retained limits](SPEECH-INTEGRATION.md).

### Liquid 24B and ANE candidate on Asahi — 2026-10-22

Liquid AI publishes [LFM2.5-24B-A2B in GGUF for llama.cpp](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B-GGUF)
as well as [MLX for Apple Silicon](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B-MLX-4bit).
The official model card reports 24B total / 2.45B active parameters; the
published Q4_0 GGUF is about 13.6 GB and a
[community Q4_K_M build](https://huggingface.co/m9ter1a/LFM2.5-24B-A2B-GGUF)
is about 14.5–15.0 GB. Active-parameter count does not remove the need to load the full
weights. Liquid's product page reports 184 tok/s on an Apple M5 Max; that is not
an M1 Pro estimate. The installed llama.cpp is build `7182ef7`; its
[pinned source](https://github.com/ggml-org/llama.cpp/blob/7182ef71e6d5dd0c8ea76486fac134fcd25025d4/src/llama-model.cpp#L303-L306)
includes the `lfm2moe` model loader, so the architecture is present in
this runtime. A current upstream [tool-call parsing report](https://github.com/ggml-org/llama.cpp/issues/30490)
shows that some LFM2.5-24B turns can surface alternate tool syntax as plain
text instead of structured function calls, so the tool workflow needs its own
quality check. Our prior LFM2.5 1.2B trial reached 63.59 estimated tok/s but
passed only 3/9 tool workflows, so it is not a quality or
speed proxy for this larger checkpoint.

The latest M1 Pro snapshot (October 22) reports 15.5 GiB available, with fans
at 2503 RPM and maximum sampled temperature 49.3 C. After the six-GiB desktop
reserve, only 9.5 GiB remains. Liquid AI's published 4-bit MLX checkpoint is
13.6 GB (12.7 GiB) before runtime and context memory; this host still fails the
supervisor admission gate. The GGUF is not downloaded, and no service start or
inference was attempted. Recheck the existing supervisor admission gate before
a later trial, then qualify the GGUF's actual tool-call formatting and the same
six synthetic app workflows before considering it for daily use. The experimental
[Linux Qwen-on-ANE repo](https://github.com/joshuaswarren/ane-linux-experiments)
reports a staged Qwen 2B decode at 8.23 tok/s on an M1, with 100/100 tokens
exact; its end-to-end timing was 0.69x the paired macOS result. That is a more
promising research candidate than the earlier arithmetic-only evidence, but
the repo targets an original M1 and has no measurement for this M1 Pro/T6000 or
supervised OpenAI-compatible assistant service. Its bring-up guide warns that
raw device operations can hard-reset the machine, so those scripts are not a
safe desktop inference trial. This host's custom kernel does have a bound ANE
driver (`modinfo` reports `intree=Y`); Asahi's feature table still classifies
the Neural Engine driver as out of tree. The installed ANE-backed Parakeet path
remains speech transcription. Neither it nor the experimental Qwen path is
qualified as the daily T3 assistant yet.

### MSeries ACP live T3 check — October 22

After the supervised Qwen3.5 4B everyday profile passed its existing admission
check, a real T3 `orchestration.launchThread` reached the local ACP provider,
called the production MCP `add_minutes` tool for 09:45 + 135 minutes, and
returned `12:00` in a completed T3 projection. The first T3 attempt exposed a
6,000-character bridge prompt cap; bridge version 0.3.0 now allows 16,000
characters (about 4K ordinary tokens) and has boundary tests. A fresh ACP 0.3.0
thread then used the same tool to return `13:00` for 12:15 + 45 minutes. Both
T3 projections completed and both temporary threads were archived. This proves
two local T3-to-model-to-tool turns. It does not qualify broad answer quality,
multi-turn restoration or daily use. The Liquid 24B model remains unloaded
because its weights plus runtime do not fit the host's memory budget with the
six-GiB desktop reserve. A live preflight with Qwen3.5 4B active measured
10.56 GiB available; the 13.6 GB weights plus reserve need at least 18.67 GiB
before runtime/context overhead, and the supervisor refused admission. No
experimental ANE conversation service was started.

Hermes has been retired from the maintained assistant setup. New installs no longer fetch its source or create its launcher. Existing Hermes checkout, virtual environment, configuration, and state in a user's home are retained. On the next assistant configuration, the setup removes only its exact, unmodified generated Hermes desktop entry; a customized entry is preserved. The earlier `install-agent.sh`/port-8080 and Ornith/port-8767 instructions are historical; avoid running those workers alongside this setup.

## MCP app coverage

`os-mcp.py` is a stdio MCP server with sixteen typed tools. It has no generic shell tool. Workspace paths are relative to `~/Documents/Assistant Workspace`; reads reject traversal/symlink escapes and note creation refuses overwrites. OS measurements, app inventory and fault collection are read-only. Calendar recurrences are labeled, not expanded. Tasks and Calendar use Evolution Data Server. Task and event creation are restricted to dedicated local Assistant Tasks and Assistant Calendar sources; retries reuse a stable request ID and cannot overwrite existing objects. Events require explicit time-zone offsets and do not send invitations. `list_tasks` and `list_calendar_events` limit reads to those sources with `scope=assistant`. See [app integration coverage](APP-INTEGRATION.md) for qualification and limits. Energy uses the existing Energy Monitor cache and reports stale/missing data.

The installed-app inventory identifies adapter coverage. It does not imply that every app can be controlled. Assistant Browser provides read-only tab titles and bounded page text from a separate Brave profile launched from the Applications menu. Only pages opened in that profile are shared; the normal Brave profile is untouched. Local unsent RFC822 drafts are stored under Assistant Workspace/Mail Drafts. Open Assistant Mail Drafts to preview a message and explicitly open its composer in Mail. Inbox reading, sending, attachments, general browser control, messaging and arbitrary window control remain outside this adapter. The capability matrix in the results records this boundary. This is the first MCP OS layer, not a claim of complete app automation.

## Fault collection and local diagnosis

`mseries-crash-watch` is enabled at login and retains ten bounded application/kernel event summaries. It groups changing addresses/PIDs, deduplicates kernel signatures for ten minutes, and inspects previous-boot warnings and pstore filenames. A missing previous journal does not prove a clean shutdown. It recognizes GPU faults, OOM, lockups, oops/panics, storage errors, suspend failures and selected USB4 errors without changing the kernel.

```sh
mseries-troubleshoot --start --release-model --file /path/to/log 'Explain this failure'
mseries-troubleshoot --start --previous-boot 'Why did the last boot fail?'
mseries-troubleshoot --performance --collect-only
mseries-brief --collect-only
mseries-ask 'Which tasks need attention?'
```

Optional model diagnosis borrows an existing Qwen9 quality/personal worker and releases only a worker it started. A different active profile causes a refusal rather than an eviction. Reports and exact excerpts stay mode 0600 in `~/.local/state/mseries-troubleshooter`. The small 4B model failed repair-advice checks and is excluded from this path. The optional 9B diagnosis needs at least 15 GiB available before loading and remains unqualified on the current retained app mix. The deterministic watcher is independently active and does not execute suggested repairs. Automatic diagnosis is controlled by the existing robot toggle and is off unless enabled; when enabled it is limited to one active analysis and three starts per fifteen minutes. The native robot menu is installed separately with `mseries/install-troubleshooter-wingpanel.sh`. The existing deterministic Restart Panel action and speaker protection are unchanged.

## Benchmarks and updates

```sh
python3 -m unittest discover -s mseries/local-ai -p 'test_*.py'
python3 mseries/local-ai/benchmark.py --label Qwen35-4B --output result.json
python3 mseries/local-ai/tool-benchmark.py --label Qwen35-4B --output tools.json
# Stop managed models before a runtime-native microbenchmark:
python3 mseries/local-ai/microbenchmark.py everyday --prompt 512 --output micro.json
python3 mseries/local-ai/branch-watch.py
# Verify/register the default 4B target (also done by full setup):
python3 mseries/local-ai/prepare-compact35.py
# Local app data services; creates/removes owned synthetic sources only:
python3 mseries/local-ai/eds-smoke.py --output eds.json
python3 mseries/local-ai/app-benchmark.py --label baseline --output apps.json
```

Task tests record answers, first-text latency, estimated decode rate, caching and machine telemetry. MCP workflow v3 tests use the real stdio adapter in synthetic workspaces, an explicit exact-text note instruction and a recorded fifteen-second cooling delay. The earlier ambiguous note instruction is preserved as exploratory data. Interrupted streams are excluded from quality scoring. Microbenchmarks have a shared lock, three trials with cooling delays and the same cooling/stop policy; their native runtime workloads differ and should not be treated as identical cross-runtime tests. The real Crush fixture is published under `fixtures/coding/`; copy it to an isolated scratch directory, use a model-matching local `.crushrc`, allow only view/ls/grep/edit/write, deny bash/fetch/web_search, and run `check_unique.py` independently after the edit. Keep approval defaults for real projects. Run only in a quiet window; preserve interrupted receipts.

The existing six-hour GitHub watcher now discovers all public branch heads in the selected Mac/MLX/Mesa/ANE/kernel repositories, plus all open PR heads and detailed comparisons for named branches and the ten most recently updated PRs. Complete head lists are saved as workflow artifacts; compact digests fit the issue dashboard. A changed digest signals even an unselected personal experiment. Fetch/pagination failures remain visible. Discovery never updates pins, merges code, or qualifies hardware.

## Removal

Disable/stop the `mseries-ai-*` and `mseries-crash-watch` user units, remove the generated launchers and desktop files, and reload user systemd. Model downloads, Newelle memory, any prior Hermes state and troubleshooting reports are retained unless deliberately removed. Newelle settings before configuration are backed up at `~/.config/mseries-ai/newelle-before.json`. The prior private MLX runtime, when present, is kept beside the prefix with a `before-v0.7.33` suffix. The Coreglass and CodexBar integrations remain independent; their earlier receipts are retained in this directory and Git history.

### Update the task adapter without resetting preferences

For an existing installation, run `python3 mseries/local-ai/configure-assistants.py --refresh-tools`. This updates the MCP adapter, installs Assistant Browser/Mail Drafts launchers and enables the added task/calendar/browser/draft tools and invalidates only its schema cache. It preserves model profiles, memory settings, other MCP servers and other tool settings. Fresh installs include the same capability.

## Agent-first Pantheon direction

[Proposed Pantheon MCP redesign](PANTHEON-MCP-DESIGN.md): a headless agent broker, kernel/app alert workflows, typed desktop capabilities, and native/WebRTC speech interaction. This is a feature write-up and phased acceptance plan; these proposed services are not installed by the current adapters.

[Omarchy Mac/MX and MLX feature comparison](UPSTREAM-FEATURE-COMPARISON.md) records current source/branch pins, applicable performance options and exclusions, and the next controlled M1 Pro experiments.
