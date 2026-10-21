# Desired: evaluate omarchy-mlx main and a Draw Things-style local image app on the M1 Pro

Draft, not posted. Companion to [OMARCHY-MLX-BUMP-PLAN-2026-10-19.md](OMARCHY-MLX-BUMP-PLAN-2026-10-19.md).

## Summary

Qualify (or reject) omarchy-mlx `main` against our v0.7.33 pin on the 32 GB M1 Pro, and decide whether a local image-generation app comparable to Draw Things is feasible on this stack.

## Why

- omarchy-mlx main is 36 commits past v0.7.33 with no release. Several routes changed defaults (row-reduce Sum on; GDN decode route gated to G14C/G13C devices).
- This host reports `Apple M1 Pro (G13S C0)`, so the new GDN default does not apply here. Any gain is unmeasured on this chip.
- Owner interest in an app like Draw Things (local, GPU-accelerated image generation with a native UI).

## Draw Things reference (what is known)

- Draw Things is an Apple-platform app (iPhone, iPad, Mac). No native Linux desktop app was found.
- The project publishes a Docker image, `drawthingsai/draw-things-grpc-server-cli`, a CUDA gRPC server for the app. Listed builds are linux/amd64 only, so it does not run on this ARM64 Apple GPU. Official docs and the GitHub repo were not read; treat this as unconfirmed until they are.
- So a Draw Things-like experience here means a different stack: an MLX image model (diffusion) on the Honeykrisp Vulkan backend, behind a simple local UI. Feasibility, model licenses, and memory fit (6 GiB desktop reserve plus the resident assistant) are unknown.

## Scope

1. Bump track (from the plan): candidate build beside the running runtime; Qwen3.5-4B token identity with `MLX_OMARCHY_ROW_REDUCE` on/off; Qwen3.5-9B decode with `MLX_OMARCHY_GDN_PF_GQA` on/off; check our private patch and `local-ai/install.sh` wrapper against the new installer layout.
2. Image-gen track: survey MLX diffusion models that run on omarchy-mlx's Vulkan backend; measure memory and time per image; confirm licenses; no resident worker alongside the assistant without admission control.
3. ANE: no ANE+LLM concurrency until the busy-ANE decode loss (-44% on a 13-inch M1, upstream KNOWN-ISSUES) is measured on this Pro. `ane` is already bound in-tree (`apple,t6000-ane`).

## Acceptance

- Medians over repetitions, one change at a time, workers stopped, load/temperature/fan recorded.
- Token-identical greedy output or a documented difference; no reserve or thermal regression.
- Handoff, roadmap and pin docs updated only after measurements.

## Out of scope

Kernel, bootloader, governor, desktop Mesa and audio changes. No new always-resident model.

## Not verified

Whether the 4B model reaches the changed routes; any image model's fit or speed here; Draw Things' current Linux status beyond the Docker listing.
