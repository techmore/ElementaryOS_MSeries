#!/usr/bin/env python3
"""Let mlx-omarchy-serve batch several requests, with their memory reserved up front.

Upstream passes --decode-concurrency 1 --prompt-concurrency 1 to the mlx-lm server so that
admission only has to reserve one request's KV cache. Parallel requests (agents, an assistant
plus a chat) then wait in line: 8 requests took 5.9 s to all see a first token. This edit keeps
that guarantee and makes it scale: MSERIES_SERVE_CONCURRENCY=N (default 1, upstream's behavior)
passes N to both flags and adds (N - 1) x the context's KV to the admission estimate, refusing
when the model's KV-per-token is unknown, exactly like upstream's --prompt-cache-size rule.
For local checkpoints (no catalog facts), MSERIES_SERVE_KV_BYTES_PER_TOKEN supplies the KV size.

Applied in place by install.sh, like configure-prefill.py; idempotent; refuses a changed source.
"""
from pathlib import Path
import argparse

MARK = '# mseries: serve concurrency'
HELPER = f'''

{MARK}. MSERIES_SERVE_CONCURRENCY=N batches N requests and reserves their KV up front
# (mseries/local-ai/configure-serve-concurrency.py). Unset or 1 keeps upstream's behavior.
def _mseries_concurrency() -> int:
    raw = os.environ.get("MSERIES_SERVE_CONCURRENCY", "1")
    try:
        value = int(raw)
    except ValueError:
        raise budget.BudgetError(f"MSERIES_SERVE_CONCURRENCY must be an integer, got {{raw!r}}")
    if not 1 <= value <= 16:
        raise budget.BudgetError("MSERIES_SERVE_CONCURRENCY must be between 1 and 16")
    return value


def _mseries_local_kv():
    raw = os.environ.get("MSERIES_SERVE_KV_BYTES_PER_TOKEN")
    return int(raw) if raw else None
'''

EDITS = [
    # Helper after the module imports.
    ('from . import _mlxlm_server as cap_shim\n',
     'from . import _mlxlm_server as cap_shim\n' + HELPER),
    # Local checkpoints may carry an explicit KV size (both local-path branches).
    ('        memory = {"weights_bytes": weights_override, "kv_bytes_per_token": None, "peak_estimate_bytes": None}\n'
     '    elif resolved.entry is not None:\n',
     '        memory = {"weights_bytes": weights_override, "kv_bytes_per_token": _mseries_local_kv(), "peak_estimate_bytes": None}\n'
     '    elif resolved.entry is not None:\n'),
    # Reserve the extra requests' KV with the prompt-cache reservation, before admission.
    ('        cache_extra = est.kv * prompt_cache_size\n',
     '        cache_extra = est.kv * prompt_cache_size\n'
     '    concurrency = _mseries_concurrency() if backend == "mlx-lm" else 1\n'
     '    if concurrency > 1:\n'
     '        if not est.kv_known:\n'
     '            raise budget.BudgetError(\n'
     '                f"MSERIES_SERVE_CONCURRENCY={concurrency} needs KV facts to budget "\n'
     '                "the extra requests; this entry has unknown KV-per-token "\n'
     '                "(set MSERIES_SERVE_KV_BYTES_PER_TOKEN for a local checkpoint)")\n'
     '        cache_extra += est.kv * (concurrency - 1)\n'),
    ('        lines.append(f"prompt cache: +{cache_extra / GiB:.2f} GiB "\n'
     '                     f"({prompt_cache_size} retained entries x KV at "\n'
     '                     f"{context_tokens} tokens)")\n',
     '        if prompt_cache_size:\n'
     '            lines.append(f"prompt cache: +{est.kv * prompt_cache_size / GiB:.2f} GiB "\n'
     '                         f"({prompt_cache_size} retained entries x KV at "\n'
     '                         f"{context_tokens} tokens)")\n'
     '        if concurrency > 1:\n'
     '            lines.append(f"concurrency:  {concurrency} requests, +{est.kv * (concurrency - 1) / GiB:.2f} GiB "\n'
     '                         f"(KV of {concurrency - 1} more at {context_tokens} tokens)")\n'),
    ('                "--decode-concurrency", "1",\n'
     '                "--prompt-concurrency", "1",\n',
     '                "--decode-concurrency", str(_mseries_concurrency()),\n'
     '                "--prompt-concurrency", str(_mseries_concurrency()),\n'),
]

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument('module', type=Path)
args = parser.parse_args()
text = args.module.read_text()
if MARK in text:
    print('Serve concurrency already configurable (MSERIES_SERVE_CONCURRENCY).')
    raise SystemExit(0)
for old, new in EDITS:
    count = text.count(old)
    # The local-path memory line appears in two branches; only the first is followed by the
    # catalog branch, so each edit must match exactly once.
    if count != 1:
        raise SystemExit(f'Runtime source changed ({count} matches); review the concurrency edit before applying:\n{old}')
    text = text.replace(old, new, 1)
compile(text, str(args.module), 'exec')
args.module.write_text(text)
print('mlx-omarchy-serve: MSERIES_SERVE_CONCURRENCY now batches requests with their KV reserved.')
