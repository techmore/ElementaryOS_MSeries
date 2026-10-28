# TensorFold Vulkan feasibility — 2026-10-27

## Related metal2vk route

[metal2vk](https://github.com/joshuaswarren/metal2vk) is a separate Metal
compute-to-Vulkan compiler, not the unpublished TensorFold engine and submit
batching implementation. Its `main` was `de6faa02c42455963645ac55cbc8191e15b3ac68`
at inspection. [omarchy-mlx PR 70](https://github.com/joshuaswarren/omarchy-mlx/pull/70)
merged an opt-in metal2vk route for custom MLX kernels. Its merge commit
`242a86509a6f88b49e7c5265d78bfc60dabbc2b7` is an ancestor of our pinned
omarchy-mlx source `33630f9c1eeefe5fc985a28bed0585432c2c014e`. The installed
`libmlx.so` contains the route and summary environment variable names, and its
adjacent `m2v_aot` directory contains 67 files. This establishes presence, not
that a particular module dispatched or produced correct output on this host.
The normal route remains the translator by default; `auto` is opt-in and may
fall back. The compiler toolchain itself is not installed (`clang-23`, `opt-23`
and `clspv` were not found on PATH). No runtime or setting was changed.

Next, use a controlled custom-kernel fixture from the pinned MLX/metal2vk
contract, with process-local private ICD and `MLX_OMARCHY_METAL_KERNEL_BACKEND=auto`,
and collect route summary plus numerical reference and fallback results before
making any performance or integration claim. Avoid concurrent GPU work. A full
translator build requires LLVM/clspv and sufficient disk; 16 GiB was free on
the root filesystem at inspection.

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
