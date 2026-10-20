# Phosphene feasibility on elementary OS M-Series — 2026-10-19

## Decision

Do not port Phosphene's video-generation stack to this machine as a project priority.
The application is aimed at local generative video, image editing, audio/video and
character LoRA workflows; those features are outside the dock HDMI primary goal.
Revisit only if local video creation becomes a concrete owner priority or the
Linux/Vulkan backend situation changes substantially.

This is a source and hardware assessment, not an installation or runtime test.
No Phosphene package or model was installed, no render was attempted, and no
performance result is claimed.

## What was assessed

- Project: [Phosphene](https://github.com/mrbizarro/Phosphene), the repository
  linked by the supplied `joshuaswarren/Phosphene` URL.
- Upstream state reviewed: release `v4.19.5`, commit
  [`287a964`](https://github.com/mrbizarro/Phosphene/commit/287a96403f178030eba96eb3f2a341092c469b91).
- Machine: Apple M1 Pro (T6000/G13S), 32 GB unified memory, elementary OS M-Series
  Linux ARM64, with the project’s existing `omarchy-mlx` Vulkan fork rather than
  Apple's Metal MLX runtime.
- Files reviewed: upstream README and `install.js`; local hardware/stack details
  were read from the project handoff and Omarchy MLX planning notes.

## Fit and blockers

Phosphene's README describes LTX-Video 2.5 and Hailuo H3 video engines, Qwen Image
Edit, and optional YuE2 audio generation. Its panel now calls Linux on Apple
Silicon a community-maintained, best-effort target, but the checked Pinokio
installer explicitly skips unless the platform is Darwin on ARM64. This means
the standard install path is not enabled for elementary OS; a Linux community
path does not establish compatibility with this machine's Vulkan MLX fork.

The engines are built around Apple's MLX and MLX-specific companion projects.
Our installed MLX is a Linux Vulkan port, with a pinned release and changes
focused on language-model inference. Compatibility of the video diffusion,
audio, VAE and image-edit operations with that fork is unknown. A functional
port would need backend support and output-quality validation across those
operations, plus a Linux-native install/update and UI integration path. This is
substantial engineering with no demonstrated fit to the primary project goal.

The memory tiers also rule out key features: Phosphene says character mode,
advanced keyframing/extension and Q8 HQ pipelines require 48 GB or more. Hailuo
H3's compact Q8 engine is listed at 36 GB or more of unified memory, above this
machine's 32 GB. The listed LTX base install is about 27.5 GB of model files
(storage, not a claim of 27.5 GB runtime memory); its README says the basic
surface adapts to lower-memory Macs, but does not establish an acceptable Linux
Vulkan footprint or render speed here. The README's example of a 7-second
character clip taking about 6 minutes is on an M4 Max with 64 GB and is not a
performance estimate for this M1 Pro.

## Practical follow-up

If the need is local still-image generation/editing, evaluate a smaller
Linux/Vulkan-native candidate independently against the resident assistant and
the existing desktop-memory reserve. Do not assume it can reuse Phosphene's MLX
pipeline. If the need is video, the practical current option is a supported Mac
with sufficient unified memory; do not spend porting effort on this host unless
the owner reprioritizes the use case.

## Privacy and licensing notes

Phosphene says prompts and media stay on-device, while its default install sends
anonymous usage counts (including hardware class and render statistics); the
README documents a Settings control to disable analytics. Model downloads still
contact their respective hosts. The panel code is MIT-licensed, but model and
dependency terms vary: the README identifies separate LTX, MiniMax, YuE2 and
other terms. Review the exact model/dependency licenses before redistribution
or commercial use; this assessment does not qualify those rights.

## Sources

- [Phosphene README at reviewed release](https://github.com/mrbizarro/Phosphene/blob/v4.19.5/README.md)
- [Phosphene install.js at reviewed release](https://github.com/mrbizarro/Phosphene/blob/v4.19.5/install.js)
- [M-Series Omarchy MLX bump plan](OMARCHY-MLX-BUMP-PLAN-2026-10-19.md)
- [Project port boundary](../PORT-MAP.md)
