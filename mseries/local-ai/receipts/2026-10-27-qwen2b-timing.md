# Qwen3.5 2B initial timing — 2026-10-27

M1 Pro, Aurora `7.2.11-elementary-aurora72-wip4`, private Honeykrisp Mesa
`7faf04c065`, MLX checkpoint `mlx-community/Qwen3.5-2B-MLX-4bit` revision
`93760be4f1f69842a46bc13dbdc0f19e291392a3`. Both used the same 27-token
chat prompt: “Explain in plain language how a rainbow forms. Give four distinct
sentences.” Greedy decoding, up to 64 tokens, no thinking. Both returned the
same 64-token text and stopped at the limit. A shared worker lock and six-GiB
desktop reserve were used. Owner allowed higher fan RPM; 80 C guard remained.

| Run | Model load | First token | Completion | Decode |
| --- | --- | --- | --- | --- |
| mlx-lm 0.31.3, one warmup then one measured request | 2.632 s | 0.563 s, local generator wall time | 2.306 s total | 37.14 tokens/s, mlx-lm reported |
| Rapid-MLX `1d09cdb684bbf58fac130f5804b08ee2e1f56558`, one server-warmed request | not separately timed | 0.250 s, server-reported | 2.618 s HTTP request wall time | 24.8 tokens/s, server completion log; mean inter-token 34.93 ms |

Rapid's cache lookup was a miss and all 27 prompt tokens were prefetched. Its
standalone server rejected `--disable-prefix-cache` before the successful run;
the successful run used default cache settings. The measurement surfaces and
warmups differ: MLX runs in-process and Rapid includes HTTP, scheduling and
server accounting. The first-token and decode definitions are not equivalent;
do not infer a speedup or regression from this single pair. No repeatability,
thermal, quality or general model ranking is established. These are not
TensorFold runs, and no metal2vk custom kernel was observed.

The first timing attempt was refused at 10.28 GiB available because the 4.5
GiB model allowance plus the six-GiB reserve did not fit. After competing work
finished, the MLX run was admitted at 11.36 GiB and the Rapid run at 11.06 GiB.
The refusal was expected policy behavior. The smoke helper now requires an
explicit per-model admission allowance; a larger model can no longer silently
reuse the 2B allowance.

Guard audit: the managed worker previously returned success after stopping on
three consecutive policy violations, hiding a memory/thermal stop as normal
service completion. It now returns exit 3 for policy stops while preserving
normal external shutdown behavior. Lock files are explicitly closed on these
paths. Admission refusals now show available memory, model allowance and
reserve; the reserve itself is unchanged. The unit tests simulate low memory
and confirm the failure exit and child cleanup. These are source changes, not
yet installed on the live system.
