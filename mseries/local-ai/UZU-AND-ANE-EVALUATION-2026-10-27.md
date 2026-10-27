# uzu and omarchy-ane evaluation — October 27, 2026

Target: M1 Pro (T6000, j314s), kernel 7.2.11-elementary-aurora72-wip4. Question: can Mirai's [uzu](https://github.com/trymirai/uzu) or [omarchy-ane](https://github.com/joshuaswarren/omarchy-ane) give faster local AI than the current MLX-on-Honeykrisp path?

## Verdict

Keep MLX on Honeykrisp (`mseries-ai-everyday`, Qwen3.5 4B 4-bit) as the GPU path. Do not add uzu to `rust/mseries-ai`. The only ANE item worth pursuing is the Parakeet dictation engine, for CPU and power, not speed.

## uzu

- MIT, v0.6.13 (2026-10-22), Rust workspace, edition 2024. `rust-toolchain.toml` pins `nightly`; running cargo in the checkout auto-installs a 2.8 GB nightly. It is **not required**: the CLI builds on stable 1.99 with `RUSTUP_TOOLCHAIN=stable cargo build --release -p cli --no-default-features --features backend-cpu` (3m15s, 2.3 GB target, 44 MB binary). A scratch `alsa.pc` is needed because `libasound2-dev` is not installed (rodio pulls alsa-sys).
- Backends: `cpu` and `metal` only. The Linux aarch64 target is "in progress" in its README. CPU kernels are scalar reference code (no NEON).
- GPU kernels: 51 hand-written `.metal` files (about 13k lines with headers), a macro layer (`VARIANTS`, `KERNEL`, `GROUPS`, `THREADS`, `SPECIALIZE`) and a `build.rs` that generates Rust bindings. A second GPU backend means rewriting every kernel.
- Upstream: Vulkan scaffold PR #444 was closed unmerged (2026-05-26). Maintainers: WebGPU first (branches `webgpu`, `vulkan`), Vulkan later on top of it, no date.
- Own model format via `lalamo`; registry downloads come from Mirai's service. The CLI has an OpenAI-compatible `server` subcommand.
- Measured (`alibaba:qwen3.5:0.8b:mirai:mirai-m:4`, about 439 MB, SMS-reply prompt): time to first token 65 s, prefill 0.54 tokens/s, generation 0.36 tokens/s, 247 s total, 556 MB peak RSS.

## Metal on Linux

Metal does not exist on Linux, and no Metal-to-SPIR-V route was found in uzu's repo or tracker (SPIRV-Cross and naga only emit MSL; Apple's compiler is macOS-only; not searched beyond that). MLX on Honeykrisp Vulkan already runs on the Apple GPU: Vulkan 1.4, subgroup 32, fp16/int8/int dot, 16-bit and 8-bit storage, 32 KiB shared memory, no cooperative matrix, 15.8 GiB unified heap, private Mesa 26.3.0-devel.

## Current path, measured live (desktop busy, fan about 2300 rpm)

`mseries-ai-everyday`, Qwen3.5-4B-MLX-4bit: 35-token prompt, 0.8 s to first token warm (5 s cold); 620-token prompt, 4.0 s (about 154 tokens/s); generation about 8-10 tokens/s under load (counted by streamed chunks, approximate). Service memory 6.0 GB current, 6.25 GB peak. The quiet-machine receipt (`receipts/2026-10-16.md`) records pp512 221.7 and tg128 25.2 tokens/s. The first start attempt was refused by the admission policy (11 GiB available, 12.5 needed); a later one passed.

## ANE

- The driver is in the kernel: `CONFIG_DRM_ACCEL_ANE=m`, `ane.ko` and `ane_t6021.ko` in `drivers/accel/ane`, "Dual MIT/GPL", loaded at boot, `/dev/accel/accel0`, node `/soc/ane@285c04000` (`apple,t6000-ane`). omarchy-ane's `dkms.conf` excludes itself on such kernels, so no DKMS and no overlay are needed.
- `omarchy-ane-check` (v0.4.9 copy, read-only): device tree, module, load and bind all pass. The one FAIL is `/dev/accel/accel0` being `root:render` 0660 (a udev rule overrides systemd's 0666); users in `render` are unaffected.
- Earlier results (`mseries/dictation/STT-RESEARCH.md` addenda): smoke 20/20 bit-exact; Parakeet encoder matches with private Mesa 26.2.4; 1.98 s for 10.4 s audio versus 1.07 s for CPU whisper on 7 s. No speed win; benefit would be CPU and power (unmeasured).
- omarchy-ane documents a staged Qwen3.8-2B decode on a 13-inch M1 (same H13 family): step p50 0.086 s fp16, 0.061 s int8, about 12-16 tokens/s. It is its own Python runtime with compiler-built packages not in the repo; not tried here.
- Risk: a hung ANE submission needs a reboot, per upstream.

## Next steps (owner decides)

1. Measure CPU and power of the ANE dictation engine against CPU whisper.
2. Optionally try the omarchy-ane Qwen decode runtime.
3. Revisit uzu only if it gains a Vulkan/WebGPU backend or NEON CPU kernels.
