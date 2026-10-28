# TensorFold Vulkan feasibility — 2026-10-27

## Qwen3.5 2B checkpoint smoke

Upstream identifies checkpoint revision `93760be4f1f69842a46bc13dbdc0f19e291392a3`;
this resolves to `mlx-community/Qwen3.5-2B-MLX-4bit`. The downloaded
`model.safetensors` SHA-256 is
`713fe7e5d3c3965f7106b0d0ee17615f7869c23c8d327996df8c1196fbcf07d5`.
With the compiler paused, the first admission attempt found only 10.39 GiB
available against the 10.5 GiB minimum and refused. After the compiler was
stopped and its memory released, admission passed at 11.4 GiB. The isolated
MLX worker on the Mac loaded the checkpoint in 2.43 seconds, answered `19` to
the short arithmetic prompt and exited successfully in 6.07 seconds. The
reproducible guarded driver is [`test-mlx-model-smoke.py`](../test-mlx-model-smoke.py).
The owner authorized fan operation above 3500 RPM; the 80 C and 6 GiB limits
were retained. No MLX custom-kernel route summary was emitted, so this is not a
metal2vk model qualification or performance test.

Upstream's TensorFold source, binaries, original test inputs and raw receipts
are private according to its [evidence summary](https://gist.github.com/joshuaswarren/0dd7a155bd9d9a691edcf0a51833ed8b).
Consequently this MLX run cannot reproduce its same-engine batching speedup.
The 4B profile retains its separate 6.5 GiB admission allowance; it was not
run when the available memory failed that threshold.

## Earlier compiler build checkpoint

The metal2vk compiler build is **incomplete**. Cloned clspv at upstream's
documented `f2b01dd6dce7058585eb4bcdb5326997cfeebfd4`, fetched its pinned
dependencies, and applied metal2vk `de6faa02c42455963645ac55cbc8191e15b3ac68`
patches in `~/.cache/mseries-metal2vk/clspv`. CMake configured a Release Ninja
build with tests, examples and benchmarks disabled. A two-job build was
restarted at four jobs; it reached 332/3350 remaining tasks before being
interrupted to reduce fan load. Afterwards, while the compiler was stopped,
the second fan rose above the project's 3500 RPM hard limit (3673 RPM on the
last sample). No compiler build or test remains running. The build tree is
retained for resumption. `metal::exp` is still untested through metal2vk, and
the compiler was not installed. Root filesystem had 13 GiB free at last
check; preserve the 5 GiB disk floor and the existing memory/thermal guard.

The owner subsequently authorized higher fan speeds; the build was resumed
with six jobs and independent temperature, memory and disk guards. Its final
result should be recorded before describing the compiler as usable.

To resume a stopped build, use `ninja -C
~/.cache/mseries-metal2vk/clspv/build -j2 clspv clang opt` under continuous
guard, then point `CLANG`, `OPT`, `CLSPV` and
`MLX_OMARCHY_M2V_COMPILE` at the isolated tools and metal2vk checkout. Repeat
the `metal::exp` fixture with a fresh private AOT directory, require m2v=1 and
fallbacks=0, and compare to the independent reference. Check tool versions,
cache paths, and numerical result before claiming success.


## LFM3 1.7B 8-bit model smoke

The user-selected [LiquidAI LFM3 1.7B MLX 8-bit](https://huggingface.co/LiquidAI/LFM3-1.7B-MLX-8bit)
checkpoint at `ee7667f3cfccb2a41725f91820531823fcabc6b7` was downloaded into
an isolated cache. `model.safetensors` SHA-256:
`2b06cea98d75527c248a0b04383f7cf0a1c72fb4ed7b45096618fc4e59d015ad`.
The installed mlx-lm 0.31.3 lacks LFM3. An isolated copy of the single model
file from [mlx-lm PR 2016](https://github.com/ml-explore/mlx-lm/pull/2016)
head `9027ac5b062175fba890c612c3905d5d8d5b5294`, SHA-256
`a4096cddc8f0d3f7923008b2e6afb896dabc9aef963a5ebe7d76d13a6069b0c4`,
was loaded via Python module injection; no installed package was changed.
Its unmerged upstream implementation is not qualified against a reference.

With the private ICD and MLX `auto` selected, the worker acquired the shared
AI lock and passed admission at 11.59 GiB available with 4.5 GiB model
allowance and 6 GiB desktop reserve. A one-second resource guard used the
existing 6 GiB, 3500 RPM and 80 C limits. The model loaded in 2.74 s and
answered `19` to “What is 12 plus 7? Reply with the number only.”, then exited
successfully after 5.03 s. Its route summary produced no custom-kernel entries:
this shows a short whole-model Vulkan inference run, **not** metal2vk execution
within LFM3, correctness qualification, throughput, or an 8-bit/4-bit comparison.
No network code from the model repository was enabled deliberately; the
tokenizer displayed a trust-remote-code prompt and continued without approval.


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

For the requested TensorFold batching result specifically, obtain the public
before/after engine revisions and original prompt and compare on the same M1
Pro, driver and Qwen3.5-2B checkpoint. Retain generated IDs, full logits,
submission counts and reset results. Use the upstream 24-token prompt,
64-token generation and 256 context when the actual inputs are released;
alternate at least three old/new pairs and report each pair's whole-token
latency and median gain, rather than comparing against an MLX timing. Apply
the maintainer's predeclared teacher-forced float64 fidelity gate and record
all failures. The author's public receipt says the raw inputs and executables
are private, and the batching code will follow the engine PR, so this is an
unexecuted plan rather than evidence of a 30% gain on this machine.
