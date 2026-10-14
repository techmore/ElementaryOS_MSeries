#!/usr/bin/env python3
"""Bound MLX-LM prefill scratch on the private, pinned Ubuntu runtime."""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('module', type=Path)
args = parser.parse_args()
text = args.module.read_text()
old = '"--prompt-cache-size", str(prompt_cache_size)]'
new = ('"--prompt-cache-size", str(prompt_cache_size),\n'
       '                "--prefill-step-size", "256"]')
if new in text:
    print('Private MLX prefill chunk is already 256 tokens.')
elif text.count(old) == 1:
    patched = text.replace(old, new, 1)
    compile(patched, str(args.module), 'exec')
    args.module.write_text(patched)
    print('Set private MLX-LM prefill chunk to 256 tokens.')
else:
    raise SystemExit('Runtime source changed; review prefill patch before applying.')
