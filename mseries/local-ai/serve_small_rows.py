"""Run short prompt passes (2-6 tokens) through the decode kernel's batched rows.

On Honeykrisp, omarchy's quantized matmul for 2 or more rows costs a flat ~0.7 ms per call up to
32 rows, against ~0.1 ms for one row; Qwen 3.5 4B makes ~220 such calls per pass, so any prompt
pass longer than one token paid ~140 ms before doing real work. The server reads every chat
prompt in two passes (the question, then the 4-token reply header kept apart for the prompt
cache), so a lone request paid it twice.

omarchy already has a fast kernel for this shape when the rows come as a decode batch: a bf16
[B, 1, K] input with 2 <= B <= 4 against a 4-bit group-64 weight reads each weight word once per
block (`QmmVecQ4WordSubgroupBatch4BF16`, MLX_OMARCHY_QMV_BATCH). Reshaping a [1, T, K] pass into
blocks of up to 4 rows takes that kernel: 2 rows 68 -> 20 ms, 4 rows 69 -> 38 ms per 96 calls
(9216 x 2560); from 8 rows the matrix kernel is as fast, so only T <= 6 is rerouted. Every row
is bit-identical to computing that token alone with the one-row kernel, which is how decode
computes it (receipts/2026-10-28-serve-patch.md, round 4).

Ours (mseries). Installed by mlx-lm-0.31.3-server-small-rows.patch;
MSERIES_SERVE_SMALL_ROWS=0 turns it off.
"""
import mlx.core as mx
import mlx.nn as nn

MAX_ROWS = 6
BLOCK = 4


def install_small_rows():
    cls = nn.QuantizedLinear
    if getattr(cls, "_mseries_small_rows", False):
        return
    stock = cls.__call__

    def __call__(self, x):
        if (
            x.ndim == 3
            and x.shape[0] == 1
            and 2 <= x.shape[1] <= MAX_ROWS
            and x.dtype == mx.bfloat16
            and self.bits == 4
            and self.group_size == 64
            and getattr(self, "mode", "affine") == "affine"
        ):
            rows, k = x.shape[1], x.shape[2]
            parts = [stock(self, x[0, i : i + BLOCK].reshape(-1, 1, k)) for i in range(0, rows, BLOCK)]
            out = parts[0] if len(parts) == 1 else mx.concatenate(parts, axis=0)
            return out.reshape(1, rows, -1)
        return stock(self, x)

    cls.__call__ = __call__
    cls._mseries_small_rows = True
