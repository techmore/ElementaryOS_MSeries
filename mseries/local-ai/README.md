# Local assistants on the M1 Pro

The October 16 setup uses private Linux MLX v0.7.33, Newelle for desktop and personal assistance, and a separate 16K coding profile for Crush. It targets the 32 GB M1 Pro. [Measured results, methods and limits](receipts/2026-10-16.md) explain the provisional model choices. [Exact revisions and licenses](receipts/2026-10-16/source-pins.json) accompany the synthetic raw results.

## Install and launch

```sh
bash mseries/local-ai/install-assistants.sh --runtime  # install/update the private MLX runtime first
bash mseries/local-ai/install-assistants.sh            # explicit model/client downloads and user setup
mseries-assistant desktop
mseries-assistant personal
mseries-assistant coding
```

The Applications menu has Desktop Assistant, Personal Assistant, Coding Assistant and an experimental Hermes launcher. Desktop and Personal open Newelle, with a local user-summary memory that can be inspected and reset in Memory preferences. No embedding model is needed for this memory. Tasks, calendar components, workspace notes, system measurements and fault signatures are available through the local MCP adapter. Tool execution stays within the configured adapter surface. Broad Newelle shell, arbitrary-file, subagent, screenshot and network tools are hidden in the preconfigured profile. User-defined modes or later settings can expand that surface.

The initial setup downloads pinned Qwen9 and Qwen4 weights (roughly 8 GB combined), Newelle's ARM64 Flatpak/runtime, and the pinned clients. Model weights and personal state stay in the user's home. Factory images stage the offline runtime and compute ICD under `/usr/lib/omarchy-mlx`, llama.cpp under `/usr/lib/mseries-ai/llama`, and user setup under `/usr/share/elementary-mac`. First-user setup uses those runtimes without apt writes to immutable `/usr`. Factory runtime staging and pruning pass; a full image build and hardware boot with this AI layer remain separate qualification steps.

`install.sh` preserves a previous runtime and restores it on failed updates, refuses active MLX workers, pins both MLX and the private compute Mesa, and defaults to two build jobs. System Mesa, the bootloader, kernel and audio stack are preserved. Our private patch bounds prefill to 256 tokens and disables thinking by default; an API request may explicitly enable thinking. The compiled rsqrt/RMSNorm check covers the numerical fix in v0.7.33.

## Memory and cooling

`~/.config/mseries-ai/profiles.json` owns the policy. One supervised inference worker holds `~/.local/state/mseries-ai/worker.lock`. Launchers switch between managed profiles and check the model identity at readiness. Initial admission budgets are 7.5 GiB for everyday (the upstream 8K estimate is 7.43), 8 GiB for coding (16K estimate 7.93), 4.5 GiB for the older compact model, 5.5 GiB for the optional newer 4B challenger, and 11 GiB for experimental 64K Hermes, in addition to a 6 GiB desktop reserve. Estimates include workspace/cache allowance; live telemetry still enforces the reserve.

Fresh profiles sample every second, pause owned submissions at 2700 fan RPM and resume at 2600, with 70/65 C temperature hysteresis. Three-second work bursts after thirty-second cooling intervals permit progress when the idle baseline shifts. Three consecutive samples below the six-GiB reserve, above 3500 RPM, or above 80 C stop the owned model. Missing fan/temperature telemetry refuses admission. Existing policy files are preserved on upgrades; absent soft thresholds use the launch baseline plus 300/100 RPM and a three-second sample interval. Fan RPM is a noise proxy, not a dBA measurement. A cooling pause increases response time; it does not change governors or fan control. Unrelated workloads can still make the whole computer loud and stop a model.

```sh
systemctl --user status mseries-ai-everyday
journalctl --user -u mseries-ai-coder -n 40
systemctl --user stop mseries-ai-everyday mseries-ai-compact mseries-ai-personal mseries-ai-coder mseries-ai-coder7 mseries-ai-liquid
```

Newelle uses an 8K chat budget on port 8766. Crush needs a 16K server context on port 8768 because its tool/system prompt exceeds 11K. Both use the pinned Qwen9 snapshot. Only one is resident at a time. The 7B GGUF coder and Liquid profiles are optional comparisons; the 30B profile is an uninstalled plan that refuses when its 21 GiB admission budget plus reserve does not fit. No ANE or voice stack is qualified.

Hermes is installed at a pinned revision with pinned dependencies and an isolated home. Its current 64K context minimum makes it a heavier option for a busy 32 GB desktop. `mseries-assistant hermes` is experimental; Newelle's tested memory is the default personal assistant. No cloud fallback is configured. The earlier `install-agent.sh`/port-8080 and Ornith/port-8767 instructions are historical; avoid running those workers alongside this setup.

## MCP app coverage

`os-mcp.py` is a stdio MCP server with ten typed tools. It has no generic shell tool. Workspace paths are relative to `~/Documents/Assistant Workspace`; reads reject traversal/symlink escapes and note creation refuses overwrites. OS measurements, app inventory and fault collection are read-only. Calendar recurrences are labeled, not expanded. Tasks and Calendar use Evolution Data Server. Energy uses the existing Energy Monitor cache and reports stale/missing data.

The installed-app inventory identifies adapter coverage. It does not imply that every app can be controlled. Mail, browser interaction, messaging, arbitrary windows, and cross-app writes beyond new workspace notes need dedicated adapters and tests. The capability matrix in the results records this boundary. This is the first MCP OS layer, not a claim of complete app automation.

## Fault collection and local diagnosis

`mseries-crash-watch` is enabled at login and retains ten bounded application/kernel event summaries. It groups changing addresses/PIDs, deduplicates kernel signatures for ten minutes, and inspects previous-boot warnings and pstore filenames. A missing previous journal does not prove a clean shutdown. It recognizes GPU faults, OOM, lockups, oops/panics, storage errors, suspend failures and selected USB4 errors without changing the kernel.

```sh
mseries-troubleshoot --start --release-model --file /path/to/log 'Explain this failure'
mseries-troubleshoot --start --previous-boot 'Why did the last boot fail?'
mseries-troubleshoot --performance --collect-only
mseries-brief --collect-only
mseries-ask 'Which tasks need attention?'
```

Diagnosis borrows an existing Qwen9 everyday/personal worker and releases only a worker it started. A different active profile causes a refusal rather than an eviction. Reports and exact excerpts stay mode 0600 in `~/.local/state/mseries-troubleshooter`. The watcher does not execute suggested repairs. Automatic diagnosis is controlled by the existing robot toggle and is off unless enabled; when enabled it is limited to one active analysis and three starts per fifteen minutes. The native robot menu is installed separately with `mseries/install-troubleshooter-wingpanel.sh`. The existing deterministic Restart Panel action and speaker protection are unchanged.

## Benchmarks and updates

```sh
python3 -m unittest discover -s mseries/local-ai -p 'test_*.py'
python3 mseries/local-ai/benchmark.py --label Qwen9 --output result.json
python3 mseries/local-ai/tool-benchmark.py --label Qwen9 --output tools.json
# Stop managed models before a runtime-native microbenchmark:
python3 mseries/local-ai/microbenchmark.py everyday --prompt 512 --output micro.json
python3 mseries/local-ai/branch-watch.py
# Optional newer 4B challenger; verified weights and closed-schema registration:
python3 mseries/local-ai/prepare-compact35.py
# Local app data services; creates/removes owned synthetic sources only:
python3 mseries/local-ai/eds-smoke.py --output eds.json
python3 mseries/local-ai/app-benchmark.py --label baseline --output apps.json
```

Task tests record answers, first-text latency, estimated decode rate, caching and machine telemetry. MCP workflow v3 tests use the real stdio adapter in synthetic workspaces, an explicit exact-text note instruction and a recorded fifteen-second cooling delay. The earlier ambiguous note instruction is preserved as exploratory data. Interrupted streams are excluded from quality scoring. Microbenchmarks have a shared lock, three trials with cooling delays and the same cooling/stop policy; their native runtime workloads differ and should not be treated as identical cross-runtime tests. Run only in a quiet window; preserve interrupted receipts.

The existing six-hour GitHub watcher now discovers all public branch heads in the selected Mac/MLX/Mesa/ANE/kernel repositories, plus all open PR heads and detailed comparisons for named branches and the ten most recently updated PRs. Complete head lists are saved as workflow artifacts; compact digests fit the issue dashboard. A changed digest signals even an unselected personal experiment. Fetch/pagination failures remain visible. Discovery never updates pins, merges code, or qualifies hardware.

## Removal

Disable/stop the `mseries-ai-*` and `mseries-crash-watch` user units, remove the generated launchers and desktop files, and reload user systemd. Model downloads, Newelle memory, Hermes state and troubleshooting reports are retained unless deliberately removed. Newelle settings before configuration are backed up at `~/.config/mseries-ai/newelle-before.json`. The prior private MLX runtime, when present, is kept beside the prefix with a `before-v0.7.33` suffix. The Coreglass and CodexBar integrations remain independent; their earlier receipts are retained in this directory and Git history.
