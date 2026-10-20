# Omarchy Mac optimization audit — 2026-10-12

Target: elementary OS on MacBookPro18,3 (M1 Pro / j314s).
Observed kernel: `7.1.13-1-2-fairydust-usb4-ARCH`.
The initial port used omacom/omarchy-mac quattro at
ba546a61f881c1fe9d79d75ec050eab048b8cb63. The current package source was
audited separately on 2026-10-13; see the source refresh below.

## Source refresh — 2026-10-13

The maintained Apple Silicon package repository is
[omacom/omarchy-mac-pkgs](https://github.com/omacom/omarchy-mac-pkgs), checked
at main commit 222f7a8599bbdd287ac6a95362cd51c5b024baae. Its packages are
Arch-specific add-ons; each stages independently into DESTDIR and owns its
package tests, with separate integration tests for runtime contracts. Mac-only
installed hardware behavior belongs there, general desktop behavior belongs in
omacom/omarchy, and one-shot installation belongs in the installer repo.

For this elementary port, treat those packages as the current behavioral
reference. Do not copy Arch packages or package-manager hooks into Ubuntu.
Translate only useful hardware behavior into apt/mkosi and Pantheon/Gala, and
keep any change in its proper upstream repository.

## What our code already carries

Audit correction — 2026-10-14: the keyboard-brightness slider is implemented
in `mseries/quick-settings/KeyboardBrightness.vala` and installed by
`mseries/install-quick-settings-brightness.sh`. The manual post-install
`quick` stage and the transform's network firstboot `quick` module both call
that installer. It is distinct from `mseries/keyboard-backlight/backlight.py`,
which automatically adjusts brightness using ambient light. The Apple Silicon
overlay now builds and preserves the Quick Settings plugin for the matching
package version; image build/boot and live-panel operation still need checks.

| Area | Local implementation | Audit disposition |
| --- | --- | --- |
| Display brightness and OSD | `mkosi.images/apple-silicon/overlay/usr/libexec/mseries-brightness`, `mseries/rust/desktop-settings` (Python reference retained) | Pantheon-specific translation already present; preserve the working path. |
| Keyboard brightness slider | `mseries/quick-settings/KeyboardBrightness.vala`, installed by `mseries/install-quick-settings-brightness.sh` and `mkosi.images/apple-silicon/build-quick-settings` | Present in manual post-install, transform firstboot, and factory overlay build; ISO build/boot and visible UI checks remain. |
| Command shortcuts, screenshots, window controls | `mseries/rust/desktop-settings` | Already translated for Gala; Hyprland bindings should not be copied. |
| Wi-Fi firmware and resume | Apple image firmware/resume scripts and systemd services | The recovery script now has focused regression coverage; factory-image provisioning and live suspend/resume still need an M1 Pro image test. |
| Early Apple HID loading | Apple image initramfs module configuration | Port exists; check the actual booted Arch initramfs as well as the Ubuntu image. |
| Dock USB and Ethernet | `mseries/fairydust/usb4/` | USB2 peripherals and USB3 Ethernet verified in the kit's current report; older desktop/port-map wording was stale. DP tunneling remains a separate unresolved feature. |
| Gestures | `mseries/install-touchegg.sh` | Pantheon integration exists; verify gestures after session restart. |
| Panel integration | CodexBar, Signal, clockright and network installers | Existing elementary integrations, outside Omarchy hardware porting. |

Code presence is not a fresh hardware regression test. This audit did not reboot,
cycle the dock, suspend the machine or benchmark the GPU.

## Highest-value gaps

Audit correction, 2026-10-13: the earlier list wrongly marked ambient keyboard
lighting as missing. `mseries/keyboard-backlight/backlight.py` already reads the
AOP ALS sensor, changes only the keyboard through UPower, and pauses after manual
adjustments. On the M1 Pro it adjusted the keyboard from 0 to 59/255 at 141 lx.
The remaining work is interactive qualification of appearance, lock/lid and
suspend/resume behavior, not another port.

The transformed desktop also now has a tested internal-speaker path:
speakersafetyd protects the amplifier, the Asahi DSP packages supply the model
profile, and a PipeWire LV2 filter plugin built for Ubuntu's exact PipeWire
version enables the DSP graph. The audio check passed after installation. The
factory image still lacks this install path; do not enable internal speakers
without the safety daemon and preserve the existing volume during setup.

1. **Factory-image video integration and DRM validation.** The earlier audit
   claim that AVD was absent is superseded: the transformed desktop now has the
   VA-API bridge installed and H.264 decode was verified at 720p, 1080p and 4K
   on the current kernel. Long-uptime validation, actual Brave/player use, and
   AVD provisioning in the factory image remain open. Widevine is separate:
   the manual post-install includes it, but the affected Brave DRM movies still
   need an end-to-end playback check.
2. **Image audio packaging.** The tested desktop install is described above,
   but `mseries/packages.arm64` does not yet reproduce its complete safe DSP
   chain. Carry the pinned PipeWire LV2 build and audio package sources into the
   image only after their build and volume-preservation path are reviewed.
3. **Touch ID / SEP.** The old categorical unsupported statement is outdated.
   [Omarchy's official September announcement](https://omarchy.org/news/2026/09/introducing-omarchy-m/)
   reports SEP-based Touch ID work and lists it as an initial-release target.
   [SiliconForested's September 29 X post](https://x.com/SiliconForested/status/2104994209434574999)
   advertises a test kernel with Thunderbolt, SEP and AVD work.
   Direct X access returned HTTP 403; the post was discovered via
   [this community archive](https://www.omarchyarchive.com/posts/siliconforested-omarchy-mac-test-kernel/).
   The [Asahi M1 matrix](https://github.com/AsahiLinux/docs/blob/main/docs/platform/feature-support/m1.md)
   still lists TouchID as TBA. No `/dev/*sep*` was observed here, which alone
   does not prove absence of all SEP support. Obtain the exact M1 Pro-supported
   source/release, firmware protocol, enrollment service and PAM instructions;
   validate enrollment, unlock and password fallback before enabling it.
   Intel T1/T2 and VM host authentication bridges are different implementations.
4. **USB4 sleep and dock video.** The current kernel can bring up dock hubs,
   input and Ethernet. ACIO blocks suspend while a USB4 link is up; a separate
   non-USB4 Type-C path can lose devices after suspend. DP tunnelling remains
   unsupported. See `ROADMAP.md` and `fairydust/usb4/README.md`.

## Combining elementary beta with Omarchy M beta

Use elementary as the desktop/package base and selectively port hardware
components. Omarchy's pacman hooks, package repositories and Hyprland settings
cannot be merged into Ubuntu/Pantheon as a single update stream.

Recommended experiment lanes:

- Baseline: record the current kernel, DTBs, m1n1, firmware, Mesa, package versions
  and working rescue boot entry before changing any component.
- Desktop: elementary beta updates plus our reproducible Pantheon settings.
- Hardware: one pinned Omarchy/Asahi kernel or firmware change per trial, with
  the original boot artifacts and recovery procedure retained.
- Compute: isolated Python environment and private Vulkan driver for MLX,
  avoiding replacement of the compositor's Mesa libraries.

For each lane record boot-to-login time, idle CPU/RAM and power at a fixed
brightness, suspend/resume success, Wi-Fi recovery, dock/monitor behavior,
video CPU utilization and thermals. Repeat comparable workloads at least three
times with the same power source and temperature conditions. Report median and
range, errors and the exact versions; no performance claim follows from this audit.

## Local AI: Ollama and MLX

[Ollama hardware documentation](https://docs.ollama.com/gpu) describes Linux
Vulkan support; its Apple Metal path is not a Linux backend. Actual Apple GPU
selection and successful model execution must be checked on this installation.
Ollama was not found on PATH during this audit.

[joshuaswarren/omarchy-mlx](https://github.com/joshuaswarren/omarchy-mlx)
is a relevant experimental Linux port: MLX APIs use a Honeykrisp Vulkan backend
rather than Metal. Its documentation requires a patched compute driver for the
advertised results. It also describes ANE work, but M1/M1 Max results must not
be assumed to cover this M1 Pro. Start with GPU inference; treat ANE as a
separate model-specific experiment.

Next implementation: inspect its current installer and Python wheel ABI,
package Ubuntu dependencies, keep the Vulkan ICD private, then benchmark a
small fixed quantized model against CPU inference. Record prompt processing,
time to first token, decode tokens/sec, peak RAM, correctness and thermals.
An MLX server and Ollama are separate runtimes; check API compatibility before
connecting OpenCode or CodexBar to either. This describes the initial audit
state; the refreshed local inventory below supersedes it.

## OpenCode Desktop

Already installed: native ARM64 Debian package `opencode` 2.0.27, executable
`/opt/OpenCode/ai.opencode.desktop`. The visible desktop launcher was invoked
successfully and an application process appeared. Interactive sign-in and
inference were not tested. The separate terminal executable remains at
`~/.opencode/bin/opencode`. GitHub's legacy latest release endpoint returned
1.19.0; it was downloaded and checksum-verified in `/tmp`, but not installed
because it would downgrade the existing desktop.

## Local agent and model refresh — 2026-10-13

This refresh includes a memory preflight, model download, host-level device
report, GPU compute, a complete Qwen 9B answer and a structured synthetic tool
call. No NAS write was run. Earlier Qwen 4B API qualification is also recorded
in `local-ai/receipts/2026-10-12.md`.

### Current host state

- Host memory is 30 GiB; `MemAvailable` was 19.79 GiB during the preflight.
  The root filesystem had 38 GiB free.
- The MLX-on-Vulkan runtime is already staged in
  `~/.local/share/mlx-omarchy` (1.6 GiB). It has `mlx-omarchy` 0.32.4.dev,
  `mlx-lm` 0.31.3, and a private Vulkan ICD. Its pinned Mesa git identifier is
  `7faf04c065`. This keeps the compute driver separate from the desktop Mesa.
- The model directory contains the 0.84 GB Laya helper model. Qwen3.5-9B 4-bit
  was downloaded successfully to the Hugging Face cache (about 5.82 GiB); its
  weights are present and the on-demand `mseries-agent-model` service serves
  them on loopback port 8080.
- The local model planner identifies this machine as SoC `t6000`. Its offline
  16k-context plan for Qwen3.5-9B 4-bit estimated 5.54 GiB of weights, 0.50
  GiB of KV cache, 1.39 GiB of workspace margin, and 7.43 GiB total against
  19.79 GiB available: **FITS**. This is a memory admission estimate, not a
  full-model inference qualification.
- The cached catalog marks every model “not recommended,” so automatic serve
  selection refuses to choose one. The named 9B model has generation and HTTP
  qualification receipts in the catalog, but those do not qualify this exact
  M1 Pro. An explicit target was used to download it. A complete on-device
  answer and structured tool-call response now pass on this machine; this
  does not establish whole-model numerical parity or NAS agent reliability.

### Model choice

Start with
[`mlx-community/Qwen3.5-9B-MLX-4bit`](https://huggingface.co/mlx-community/Qwen3.5-9B-MLX-4bit)
at a capped 32k context with one retained prompt-cache entry. The initial
16k preflight was followed by a 32k plan: 8.93 GiB estimated requirement,
22.33 GiB available, 11.40 GiB headroom after the safety reserve. It is the best balance in this machine’s current
catalog between model capacity and memory headroom. Qwen’s model card describes
Qwen3.5-9B as capable at tool calling and shows an agent configuration using
MCP. [Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B)

The local project’s benchmark receipt measured 26 generated tokens/s, 0.78 s
to first token, and 6.47 GiB peak for the 9B 4-bit model on an M2 Max with 96
GB. Those are not M1 Pro results, and the suite measured structured chat and
reasoning proxies rather than end-to-end NAS agent reliability. The 4B Qwen
variant is the fallback if live memory or latency is poor. The 27B variant is
not a sensible first pick here: its pinned catalog entry is restricted to
`t6021`, and its measured engine peak is about 16 GiB before desktop and other
process memory.

### Accelerator limits

The host-level `mlx-omarchy-info` report identifies this machine as an Apple
M1 Pro (T6000), with the private Honeykrisp Vulkan ICD and Mesa git `7faf04c065`.
A small MLX kernel ran on `Device(gpu, 0)` and returned the expected value, so
GPU compute is verified here. Qwen 9B also returned the requested answer over
the loopback API in 1.29 seconds (21 prompt and 6 completion tokens), with a
Honeykrisp response fingerprint. A separate synthetic directory-listing request
returned structured `tool_calls`; the requested tool was not executed.

The project's README matrix lists M1 and M1 Max GPU paths as tested, M2 Max as
tested, M1 Pro GPU as untested, M3 as experimental and M4 without a Linux GPU
driver in this stack. There is a documentation mismatch on ANE: `omarchy-mlx`
marks M1 Pro ANE untested, while the separate `omarchy-ane` repository says its
T6000 driver has been tested. On this elementary OS boot, the host report sees
no ANE device-tree node, `/dev/accel/accel0` or loaded ANE module, so ANE is not
available here regardless. ANE experiments are a separate model-specific
lane; the repository's verified examples do not imply general-purpose model
acceleration across every M-series generation. [omarchy-mlx hardware matrix](https://github.com/joshuaswarren/omarchy-mlx#supported-hardware)
and [omarchy-ane chip coverage](https://github.com/joshuaswarren/omarchy-ane#chip-coverage)

This elementary/Ubuntu host has a working, isolated user-level runtime and
private Vulkan ICD, but the upstream project's primary installer and system
package instructions target Arch/Omarchy and pacman. Keep the existing private
ICD arrangement; do not replace elementary's system Mesa just to follow those
instructions. The existing `local-ai/install.sh` already translates the runtime install to
Ubuntu dependencies and private launchers. Its prior installation receipt
qualifies the compact Qwen 4B API. The new Crush integration adds a user service
and Applications launcher without changing the kernel or boot chain.

### Joshua Warren repositories that apply

- [`omarchy-mlx`](https://github.com/joshuaswarren/omarchy-mlx) is the main
  runtime: MLX-style Python APIs over Honeykrisp/Vulkan, model serving, a local
  chat UI and memory-aware model planning. This is already the code staged on
  the host. Its install docs are Arch/pacman-oriented; the user-level runtime
  we have is a workable Ubuntu experiment, not an elementary-native package.
- [`mesa-1`](https://github.com/joshuaswarren/mesa-1) carries the pinned Honeykrisp Vulkan
  driver work needed by that GPU backend. We already select its private ICD,
  which avoids replacing the Mesa libraries used by Pantheon.
- [`omarchy-ane`](https://github.com/joshuaswarren/omarchy-ane) is a separate
  DRM driver and userspace library. Its README claims tested M1 Pro (T6000)
  support, but the current elementary boot does not expose the device node or
  module. The broader `omarchy-mlx` README still labels M1 Pro ANE untested, so
  actual integration on this boot is not established. A matching module and
  private board DTB were already compiled and staged; see
  `local-ai/ANE-PREFLIGHT.md`. Activation changes boot artifacts and remains
  outside this agent integration.
- [`ane-linux-experiments`](https://github.com/joshuaswarren/ane-linux-experiments)
  contains working ANE primitives and experimental staged Qwen decode on M1
  hardware. Its measured reports are not a ready-to-enable ANE backend on this
  elementary installation, and do not establish performance on this M1 Pro.
- [`mil-hwx-compiler`](https://github.com/joshuaswarren/mil-hwx-compiler) is
  compiler research for M-series ANE programs, rather than an end-user model
  server. [`omarchy-inference-fleet`](https://github.com/joshuaswarren/omarchy-inference-fleet)
  is useful for repeatable backend/model comparisons. Neither replaces the
  runtime or fixes the current ANE enumeration gap.
- [`remnic`](https://github.com/joshuaswarren/remnic) adds scoped agent memory
  and MCP/HTTP access. It may help later with remembered NAS organization
  context, but it does not provide GPU acceleration or NAS access itself.
- [`omarchy-mac`](https://github.com/joshuaswarren/omarchy-mac) and its package
  ecosystem target Arch/Hyprland. They provide upstream porting references,
  not elementary/Pantheon packages to install directly.

### Agent front end

The owner requested an OpenCode competitor. Crush v0.98.1 is now installed as
an ARM64 executable from its official release, with a pinned archive SHA-256
and retained license. `local-ai/install-agent.sh` reproduces the setup.
Applications > Local Agent runs Crush with the local Qwen provider in
`~/Documents/Local Agent`; cloud providers and provider-catalog refresh are
turned off for this workspace. Model context is 32,768 tokens and normal
output allowance is 2,048. Thinking is disabled for this initial local agent.
[Crush configuration](https://github.com/charmbracelet/crush/blob/v0.98.1/docs/config/README.md)

The user explicitly requested stopping the service on port 8080. `whop2p`
was stopped and its login autostart disabled. After confirming the port was
free and no MLX server was running, approval review accepted a fresh launch.
The previous rejection on 8081 is resolved by this reviewed fresh launch.
The model now runs under `mseries-agent-model.service`, on demand, with offline
model loading and the catalog's known KV memory budget. A local snapshot path
alone loses those KV facts, so the service uses the pinned catalog ID instead.

Crush's configured model listing succeeds. Its full agent prompt has roughly
14k tokens, so cold prompt processing is substantially slower than the short
API smoke. The first long prefill hit GPU allocation failure; reducing prefill
chunks to 256 tokens allowed the full agent answer to complete. The 16k client
context then triggered immediate summarization; the admitted 32k configuration
adds useful conversation room. One retained cache is explicitly budgeted to
reduce repeated processing. The client timeout is 180 seconds. NAS scope remains pending
the owner's share path/address. No NAS mount or write was performed.
