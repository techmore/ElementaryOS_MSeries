# TensorFold Vulkan feasibility — 2026-10-27

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
