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
