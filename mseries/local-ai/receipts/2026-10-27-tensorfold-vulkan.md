# TensorFold Vulkan feasibility — 2026-10-27

## MLX route follow-up

The shipped AOT entry matches the oMLX probe's `metal::precise::exp` variant;
the first trial used its `metal::exp` variant, which produces a different
content-addressed source key. With the precise variant, the repeatable
[`test-metal2vk-probe.py`](../test-metal2vk-probe.py) ran separate translator
and auto processes using the private ICD. Auto reported `m2v=1 translator=0
fallbacks=0 refusals=0`; translator reported `m2v=0 translator=1 fallbacks=0
refusals=0`. Both passed the float64 SiLU reference at 1e-5 absolute and
relative tolerance on 131,072 inputs in [-8, 8]. Maximum absolute reference
error was 4.64653531e-7 for each; maximum difference between routes was
4.76837158e-7, so they were not bit-identical. Command:
`~/.local/share/mlx-omarchy/venv/bin/python mseries/local-ai/test-metal2vk-probe.py`.
The kernel and installed runtime were not changed. This qualifies this one
variant and input range, not the unmatched `metal::exp` variant, model
inference, numerical edge cases, sustained operation, or speed.

## M1 Pro kernel trial

On the running `7.2.11-elementary-aurora72-wip4`, using the private ICD and
the installed MLX runtime, tested `omlx_gdn_sigmoid_probe` on 131,072 float32
values evenly spaced from -8 to 8, with 256 threads per workgroup. The
independent reference was float64 `x / (1 + exp(-x))`, tolerance 1e-5
absolute and relative. Source: the sigmoid probe in
[oMLX qwen35_gdn_verify_fused.py at e2396c7](https://github.com/jundot/omlx/blob/e2396c765d274785ce23abb764dc7eaf6b13db11/omlx/patches/qwen35_gdn_verify_fused.py).

* MLX `auto` returned finite values within tolerance (maximum absolute error
  4.65e-7), **but did not run metal2vk**: the exact generated source missed
  the AOT cache and the compiler was absent. Its route summary was `m2v=0
  translator=1 fallbacks=1 refusals=0`.
* As a separate test, the installed AOT sigmoid module was dispatched directly
  with the upstream `metal2vk` Vulkan runner (`metal2vk` commit
  `de6faa02c42455963645ac55cbc8191e15b3ac68`, runner source SHA-256
  `6d282a1d1abddc029d8c287c22a923eb26bc022265edac9d28706df8f8616de6`).
  Its module SHA-256 was
  `6eb3c7d0ea5aa30d35c7c430ef706b7f183259b8e4d563aca815b03d39006ca8`.
  One dispatch on M1 Pro completed; all output was finite and within the same
  reference tolerance, maximum absolute error 4.65e-7. Maximum difference from
  the MLX translator result was 4.77e-7; results were not bit-identical.

This earlier direct run demonstrates one translated module executing on the
GPU; the later precise-variant MLX route result is recorded above. Neither
establishes general model correctness or a speedup. No installed settings changed.

## Related metal2vk route

[metal2vk](https://github.com/joshuaswarren/metal2vk) is a separate Metal
compute-to-Vulkan compiler, not the unpublished TensorFold engine and submit
batching implementation. Its `main` was `de6faa02c42455963645ac55cbc8191e15b3ac68`
at inspection. [omarchy-mlx PR 70](https://github.com/joshuaswarren/omarchy-mlx/pull/70)
merged an opt-in metal2vk route for custom MLX kernels. Its merge commit
`242a86509a6f88b49e7c5265d78bfc60dabbc2b7` is an ancestor of our pinned
omarchy-mlx source `33630f9c1eeefe5fc985a28bed0585432c2c014e`. The installed
`libmlx.so` contains the route and summary environment variable names, and its
adjacent `m2v_aot` directory contains 67 files. The subsequent bounded
precise-variant dispatch and numerical result are recorded above.
The normal route remains the translator by default; `auto` is opt-in and may
fall back. The compiler toolchain itself is not installed (`clang-23`, `opt-23`
and `clspv` were not found on PATH). No runtime or setting was changed.

The controlled precise-variant fixture and its route summary are recorded
above. A full translator build requires LLVM/clspv and sufficient disk; 16 GiB
was free on the root filesystem at inspection.

The requested native Vulkan engine and subsequent per-token submit batching are
being developed upstream in [TensorFold issue 1420](https://github.com/ashhart/TensorFold/issues/1420).
The author reports that the batching code is not yet in a public branch; the
maintainer requests a staged engine PR first. An open-PR search for Vulkan and
`git ls-remote --heads` for Vulkan-named branches found no candidate on the
upstream repository on October 27. Do not substitute the older Python/MLX fork.

## Local baseline

On the installed M1 Pro desktop, `uname -r` returned
`7.2.11-elementary-aurora72-wip4`. With only the process-local variable
`VK_DRIVER_FILES=$HOME/.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json`,
`vulkaninfo --summary` exited 0 and identified Apple M1 Pro (G13S C0),
Honeykrisp, Mesa 26.3.0-devel git `7faf04c065`, device Vulkan API 1.4.359.
The private `libvulkan_asahi.so` SHA-256 was
`e92aa6fed95f1add1f712c28294937983583b52984bfc739f5840f30f86a2f8c`.
This is device enumeration only; it does not validate TensorFold, shaders,
model output, performance, or the factory image. No inference was run.

## Next gate

When the engine and batching sources are public, pin their exact revisions and
review build instructions, licensing, model requirements, and driver/UAPI
requirements. Build in a separate prefix, selecting the private ICD only for
the test process. Before model runs, check existing GPU jobs and memory/thermal
headroom. Exercise upstream kernel contract and correctness gates on the M1 Pro;
record failures and exact checkpoint, driver, kernel, toolchain, and resource
use. Only then compare matched old/new batching runs and the existing local AI
baseline. Preserve desktop Mesa, boot configuration and installed workers.
