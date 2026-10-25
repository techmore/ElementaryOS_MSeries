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

Hermes has been retired from the maintained assistant setup. New installs no longer fetch its source or create its launcher. Existing Hermes checkout, virtual environment, configuration, and state in a user's home are retained. On the next assistant configuration, the setup removes only its exact, unmodified generated Hermes desktop entry; a customized entry is preserved. The earlier `install-agent.sh`/port-8080 and Ornith/port-8767 instructions are historical; avoid running those workers alongside this setup.

## MCP app coverage

The shared `mseries-ai` crate now provides a local Qwen reply-draft client and
an owner-only SQLite store for cross-app preferences and explicitly saved AI
memories. Rust Messages is its first consumer. It sends a bounded conversation
snapshot only to the loopback model endpoint after the user requests a draft;
it does not save messages or generated drafts. The Messages menu exposes the
local endpoint, writing-style, shared-memory, and saved-memory settings. See
the [Pantheon reply-draft design and app boundary](PANTHEON-REPLY-DRAFTS.md).

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

The existing six-hour GitHub watcher discovers public branch heads, open PR heads, and release/default-branch changes. The ten Elementary repositories in `mseries/rust/elementary-projects.json` now provide its authoritative Elementary roster; new watch entries are seeded from their recorded source pins so upstream drift appears in the review dashboard. Complete branch/PR head lists are saved as workflow artifacts and compact digests fit the issue. Fetch/pagination failures remain visible. Discovery never updates pins, merges code, or qualifies hardware.

## Removal

Disable/stop the `mseries-ai-*` and `mseries-crash-watch` user units, remove the generated launchers and desktop files, and reload user systemd. Model downloads, Newelle memory, any prior Hermes state and troubleshooting reports are retained unless deliberately removed. Newelle settings before configuration are backed up at `~/.config/mseries-ai/newelle-before.json`. The prior private MLX runtime, when present, is kept beside the prefix with a `before-v0.7.33` suffix. The Coreglass and CodexBar integrations remain independent; their earlier receipts are retained in this directory and Git history.

### Update the task adapter without resetting preferences

For an existing installation, run `python3 mseries/local-ai/configure-assistants.py --refresh-tools`. This updates the MCP adapter, installs Assistant Browser/Mail Drafts launchers and enables the added task/calendar/browser/draft tools and invalidates only its schema cache. It preserves model profiles, memory settings, other MCP servers and other tool settings. Fresh installs include the same capability.

## Agent-first Pantheon direction

[Proposed Pantheon MCP redesign](PANTHEON-MCP-DESIGN.md): a headless agent broker, kernel/app alert workflows, typed desktop capabilities, and native/WebRTC speech interaction. This is a feature write-up and phased acceptance plan; these proposed services are not installed by the current adapters.

[Omarchy Mac/MX and MLX feature comparison](UPSTREAM-FEATURE-COMPARISON.md) records current source/branch pins, applicable performance options and exclusions, and the next controlled M1 Pro experiments.
