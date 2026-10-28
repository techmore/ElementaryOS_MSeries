# Qwen distillation: Mac H13 export and Rapid-MLX trials — 2026-10-27

## Mac mini export

An M4 mini running macOS 26.6.2, with 16 GiB memory, was accessed over SSH
using the user-provided account. Work was isolated to
`~/Library/Caches/mseries-ane-qwen-20261027`; no system packages or settings
were modified. Its Apple ANECompiler helper was compiled locally. The public
ANEForge source was fetched at `2ea941ce7ec58a802de792c152726c3a9a881706`.
The upstream Qwen GGUF contract checkpoint was downloaded at Hugging Face
revision `f4f73582d0b149595450c719b9a7521a03894f9c`, transferred to the mini,
and SHA-256 verified at both ends as
`4aa0fb13c431514262f259d420ecc95a8714df58ac2a2384514e20b93983f0ff`.

The staged manifest exporter produced 38 program source directories. The
`ane-compile-hwx` helper compiled all 38 with explicit `TargetArchitecture=h13`,
the M1-family target; representative first and last HWX files contain the
compiler invocation `-t h13`. The raw HWX programs total 2.6 GiB and the
source export another 2.6 GiB. H13 output and export remain on the mini;
manifest, logs and hash inventory were copied to the laptop's
`~/.cache/mseries-metal2vk/qwen38-ane/mac-receipts`. The
[40-entry SHA-256 inventory](2026-10-27-qwen38-h13-sha256.txt) is retained here.
Export and individual compiles monitored memory pressure, disk, and deadlines;
no guard stopped the completed compilation. No ANE commands were issued on
the Linux machine.

Conversion was attempted on the mini with upstream
`ane-linux-experiments` `b1f2cbe338ef33f9befb320b98ef83096b37980b`; it stopped
before producing the first program: `NameError: uniform_task_relayout is not
defined` inside `convert_hwx_file`. Static inspection also found `payload`
referenced before its assignment in that branch, and task-stream relocation,
weights, channel mappings and mixed-unit layouts require validation. Do not
bypass these errors or submit the resulting artifacts. The output is a compiled
HWX set, not a complete executable Linux ANE bundle; no ANE Qwen comparison
has run. A safe fix must include structural tests on real generated artifacts,
correctness against macOS reference outputs, and hardware-specific layout and
unit checks. The separate guarded tile-unit patch does not fix this missing
relayout branch.

## MLX and Rapid-MLX exploratory timing

Model: `nvythong/Qwen3.8-2B-Distill-mlx-4Bit` revision
`0afdb6850d218024c7788eda5659aa25475b7d51`, weights SHA-256
`b0d5de688567bf4acd5e421027acd410dabcdc255a5bd46fdbf06c75dc2e6863`.
This MLX checkpoint and the ANE GGUF derive from the same named base model but
have different quantization and are not identical weights. Linux M1 Pro,
private Honeykrisp, reserve 6 GiB, 4.5 GiB allowance, thermal stop 80 C,
user-authorized fan speeds above 3500. First a guarded 20k MLX smoke returned
`19`. Then separate fresh processes used the same 27-token rainbow prompt,
32 greedy tokens and 5k/20k work budgets.

| Runtime and timing boundary | 5k request seconds | 20k request seconds | Median within-budget change |
| --- | --- | --- | --- |
| Direct MLX generator, 3 alternating pairs | 1.353, 1.345, 1.388 | 1.194, 1.187, 1.209 | 11.79% shorter paired request time |
| Rapid-MLX loopback HTTP, 2 alternating pairs | 1.318, 1.328 | 1.101, 1.070 | 17.95% shorter paired request time |

Rapid at `1d09cdb684bbf58fac130f5804b08ee2e1f56558` used fresh servers,
a separate arithmetic warmup, a cache miss for the measured request,
loopback-only binding, disabled telemetry and disabled prefix-cache disk
restore/save. All four measured Rapid texts matched each other and the text
decoded from direct MLX's generated IDs. The direct MLX run warmed up using
the measured prompt; Rapid used a different prompt. HTTP and in-process timing
boundaries differ; therefore the table is evidence that the work-budget change
helps within these tiny experiments, not a valid Rapid-versus-MLX ranking.
Rapid's model-specific optimization paths on Vulkan remain unqualified; no
TensorFold or ANE speedup is established. Across the Rapid trials the lowest
sampled available memory was 11.63 GiB, max temperature 47.093 C, max fan 2516
RPM. Rapid server teardown completed. Raw receipts:
[direct MLX](2026-10-27-qwen38-mlx-ab.json),
[Rapid](2026-10-27-qwen38-rapid-batch.json).

The user-provided [neural-engine](https://github.com/hollance/neural-engine)
repository (`beef0000ab38df4807acef6dc331ddc97525b897`, MIT) is a general ANE
research reference. Its reverse-engineering section links external work, but
it does not supply the missing task-stream relayout implementation or qualify
this Linux Qwen bundle. Keep it as background rather than evidence of a fix.
