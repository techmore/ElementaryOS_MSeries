# Local AI on elementary Apple Silicon

Installed and verified on M1 Pro / j314s, 2026-10-12.

- **Coreglass:** application launcher and `~/.local/bin/coreglass`.
  Select `local`, then press `l` for live counters. `r` runs a benchmark only
  when the laptop is quiet; it correctly refuses our current busy desktop.
  `coreglass-local.patch` adds local subprocess execution for preflight and
  scripted commands, matching the upstream sampler's existing local support.
- **MLX Chat (Apple GPU):** application launcher or `~/.local/bin/mlx-omarchy-chat`.
  Use the saved **Compact** pair (Qwen3 4B Instruct 4-bit plus Laya), initially
  at 4096 context. Quality's 27B pair exceeded available memory during setup;
  Compact was selected to resolve that admission failure. Model download
  requirements are shown in the app. Voice and ANE are not installed.
- **Local API:** run
  `~/.local/bin/mlx-omarchy-serve serve qwen3-4b-instruct-2507-4bit --context 4096 --host 127.0.0.1 --port 8766 --yes`.
  This keeps access on the laptop. `--yes` explicitly approves the model
  download. The API test server was stopped after verification to release RAM
  for desktop chat. Ollama is a separate runtime and was not installed.

## Reproduce

Run `bash mseries/local-ai/install.sh` from this repo, with Python 3.14 on an
ARM64 Ubuntu-based Apple Silicon system. It installs Ubuntu build dependencies,
builds only the Honeykrisp Vulkan driver, and installs a checksum-verified
MLX v0.7.32 wheel into a private environment. No Arch packages are installed.
Sources default to `~/Documents`; use `MSERIES_AI_SOURCES` for another directory.
Build parallelism defaults to four; override with `MSERIES_AI_JOBS`.

The installer pins source commits and rejects unexpected tracked changes.
It accepts only our recorded Coreglass patch. Do not reinstall while a chat or
model server is running: upstream's installer recreates its Python environment.

The private ICD lives in `~/.local/share/mlx-omarchy/vulkan/`. Only MLX launchers
set `OMARCHY_MLX_SYSTEM_PREFIX`. System Mesa, Gala and other applications retain
the distribution's graphics driver. `mlx-omarchy-info` must report `packaged`
ICD selection and matching expected/actual driver SHA `7faf04c065`.

## Verification and limits

See `receipts/2026-10-12.md`. Small float matrix and integer-shift/XOR checks
passed against NumPy. Qwen3 4B returned the requested text over the local API.
These checks establish basic operation, not comprehensive numerical correctness
or performance parity. No inference speed comparison, ANE qualification,
suspend test or reboot was performed.

Coreglass baseline recordings stay in `~/.local/share/coreglass/captures`,
outside this public repo. They may contain local machine metadata. Use its
anonymization options before sharing reports.

For clean benchmark runs, record the experiment and check `coreglass hosts local`
first. The configured GPU lock is `/tmp/mseries-ai-gpu.lock`. Avoid forcing runs
while the user or another agent is using the GPU.

## Removal

Upstream MLX removal: `bash ~/Documents/omarchy-mlx/install.sh --uninstall`.
It preserves chat history and model downloads; inspect its `--purge` behavior
before deleting data. Our additional private `vulkan` directory can be removed
separately after stopping MLX. Remove the Coreglass desktop entry, terminal link
and source environment if no longer needed. Ubuntu build dependencies are not
automatically removed because other projects may use them.

## CodexBar reference

Reviewed `joshuaswarren/codexbar-omarchy` at
`42f24d038c0102a49315383f11e6e408e81afbf2`. Its Quickshell frontend cannot be
loaded into Wingpanel. Our native frontend already delegates provider data,
authentication and spending to upstream CodexBar. This pass adds its convenient
middle-click refresh interaction to the native panel item. Provider switchers,
inline spending charts and adaptive polling remain future work; the separate
Spending window and upstream refresh settings are available today.

For the full upstream project screen, see [Joshua repository review](../JOSHUA-REPOSITORY-REVIEW.md).

## Ornith 1.5 9B local crash and log troubleshooting

Install `bash mseries/local-ai/install-troubleshooter.sh`. This adds **Local
Troubleshooter** to Applications and the `mseries-troubleshoot` command.
Uses Joshua's Linux MLX runtime and private Honeykrisp driver, with
`ornith-ai/Ornith-1.5-9B-MLX-4bit` pinned to
`a48173b246ac705be75c05bedf1a0666db522d53` (about 5.0 GB download). It is a
post-trained Qwen3.5 9B (same `qwen3_5` architecture and 4-bit grouping as
before, so the same tuned kernels apply) and the model card states no license:
check it before redistributing.

History: Gemma 4 E4B, then Qwen3.5-9B, then Ornith (2026-10-13). On this Mac
Ornith matched Qwen3.5-9B on speed (about 17.7 tok/s decode) and tool calls,
was smaller (4.71 GiB against 5.57 GiB) and was better calibrated on a real
journal: Qwen over-claimed a Wi-Fi firmware fault, Ornith ranked it as noise.
Both refused a planted `rm -rf` line in a test log. One run each on two inputs,
so a first look, not a benchmark.

```sh
mseries-troubleshoot --start "Why did my desktop crash?"
mseries-troubleshoot --start --previous-boot "Why did the last boot fail?"
mseries-troubleshoot --start --file /path/to/crash.log "Explain this failure"
mseries-troubleshoot --collect-only
systemctl --user stop mseries-troubleshooter-model
```

If the memory check refuses to start the model while MLX Chat is resident, the
troubleshooter pauses `mlx-omarchy-chat` for the analysis and restarts it after.
The admission check itself is never lowered. The native GTK application offers current/previous boot analysis and a release
memory button. The model runs on demand, not at login. An existing MLX chat
session is preserved; current free memory is admission-checked before the model
loads. If admission fails, close other large workloads and retry. Do not bypass
that check. No ANE driver, bootloader or system Mesa change is involved.

The dedicated inference API binds only `127.0.0.1:8767`, with a 4096-token
prompt/output cap, no prompt cache and serialized inference. Model serving
uses offline Hugging Face/Transformers mode after installation. The client
refuses non-loopback endpoints, redirects and environment HTTP proxies.
Local programs can access the unauthenticated loopback API; it is intended
for this single-user workstation, not a network service.

Collection reads failed units, up to 70 kernel and 70 user-session warnings, eight user coredump summaries,
or the tail of a user-selected log. Evidence is limited to 8000 characters
before line numbering. The server rejects input/output combinations beyond
its token cap; shorten unusually dense logs if necessary. Missing journal
access or an unavailable previous boot is included as missing evidence.
No root escalation or log permission changes are used. Basic redaction covers
common token/password fields and the home path; it is not a comprehensive
secret scrubber. Both inference and reports remain on-device.

Reports are written with mode 0600 under
`~/.local/state/mseries-troubleshooter/`. They include the exact supplied
excerpt and model identity, so review before sharing. The model is instructed
to cite evidence lines and separate facts from hypotheses. It does not run
suggested commands or automatically repair the system. A plausible answer
is not proof of a diagnosis; verify its cited evidence.

Regression checks:

```sh
/usr/bin/python3 -m unittest discover -s mseries/local-ai -p 'test_*.py' -v
```

To remove: stop the service, remove its unit under `~/.config/systemd/user/`,
`~/.local/bin/mseries-troubleshoot`, the UI under `~/.local/libexec/`, and
`~/.local/share/applications/mseries-troubleshooter.desktop`, then run
`systemctl --user daemon-reload`. Cached models and reports are retained.

### Native robot menu and crash watcher

```sh
bash mseries/install-troubleshooter-wingpanel.sh
```

Builds a native Wingpanel indicator with a symbolic robot, bounded crash count,
latest crash metadata, an **Analyze Logs** action, and an **Automatically diagnose
new crashes** toggle. Reload Wingpanel after installation. Uses the installed
GTK app; no Quickshell or Omarchy desktop session is needed.

The user service `mseries-crash-watch` follows new systemd-coredump events and
filters by `COREDUMP_UID` (the crashed process owner, not the collector's UID).
It retains ten event summaries, deduplicates each program for sixty seconds,
and does not replay historical crashes when restarted. The local snapshot
contains only program/PID/signal/timestamp fields. It does not extract memory
images, environment variables or command lines from coredumps.

Automatic diagnosis is off by default. When enabled in the robot menu, a new
crash starts the same local model command, with at most one watcher-launched
analysis active. Reports appear in the app on its next launch. The idle watcher
does not load a model; disable the toggle and use **Release Model Memory** to
stop a previously loaded model. No generic repair commands are taken from model
output.

**Restart Panel** in the GTK app is a deterministic repair action: it sends
SIGTERM only to a single Wingpanel owned by the current user, lets Gala respawn
it, and checks the new process remains running for three seconds. It refuses
ambiguous/missing panels. This restores a stuck panel; it does not establish
that a recurring crash's root cause is fixed.

The watcher is inspired by Omarchy Mac quattro's `omarchy-crash-watch` and
`omarchy-agent-crash` at `ba546a61f881c1fe9d79d75ec050eab048b8cb63`.
Those upstream scripts notify and open a selected coding agent; the watcher
itself is not an autonomous repair loop. Our version uses a local model and a
native elementary frontend.

Remove the robot/watcher with
`bash mseries/install-troubleshooter-wingpanel.sh --uninstall`, then reload
Wingpanel. Reports and opt-in settings are retained.

### Native performance checks and memory release

Choose **Check Performance…** in the robot menu, or enable **Check native desktop
performance** in the application. CLI equivalent:

```sh
mseries-troubleshoot --start --performance --release-model "Find native desktop bottlenecks"
mseries-troubleshoot --performance --collect-only
```

The performance snapshot is collected before this request loads the model. It records
available RAM/swap, CPU/memory/I/O pressure, load averages, cpufreq governors,
thermal readings, the native power profile, disk space and top process names by
CPU/memory. Process arguments and environments are excluded. Missing sensors or
optional tools appear as missing evidence. CPU percentages are lifetime averages;
a single snapshot and thermal readings alone do not prove a speedup or throttling.
The model recommends reversible native changes with verification steps.

**Release model memory after analysis** defaults on in the GTK app and automatic
crash diagnoses. It stops only the dedicated troubleshooting model after the
report is saved, or after inference fails, returning its memory to the desktop.
Uncheck it for repeated warm requests. Other chat services are untouched. A
same-user lock prevents the app and crash watcher from running competing analyses
or unloading a model during an active analysis. The manual memory-release button
uses the same lock and runs off the UI thread.

## Daily task briefing

`mseries-brief` reads the open tasks in the local **Homeboard** task list
(read-only), asks the same on-device model for a short plan (do today, overdue,
quick wins, needs clarifying) and unloads the model afterwards. Briefings are
saved in `~/.local/state/mseries-brief/`. `mseries-brief --collect-only` prints
exactly what the model would see. The tool only advises: it never edits tasks.
It is installed as `~/.local/bin/mseries-brief` from `brief.py`.

## Ask about tasks and energy

`mseries-ask "question"` lets the on-device model use two **read-only** tools:
`list_tasks` (open Homeboard tasks) and `get_energy` (power now, today, this
month). It runs the tools, then answers from their results; it cannot add or
change anything. Examples: `mseries-ask "Which tasks mention plumbing?"`,
`mseries-ask "What costs the most today?"`.

Energy data comes from the local file the Energy Monitor tray app publishes
(`~/.local/state/energy-monitor/summary.json`), so it works on any network once
that app is signed in to the collector. If the app is offline, signed out or
the data is stale, the tool says so and the model must not invent readings.
The model is started for the question and unloaded afterwards.
