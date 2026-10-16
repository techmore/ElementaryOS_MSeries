#!/usr/bin/env python3
"""Bound MLX-LM prefill scratch on the private, pinned Ubuntu runtime."""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('module', type=Path)
args = parser.parse_args()
text = args.module.read_text()
old = '"--prompt-cache-size", str(prompt_cache_size)]'
previous = ('"--prompt-cache-size", str(prompt_cache_size),\n'
            '                "--prefill-step-size", "256"]')
new = ('"--prompt-cache-size", str(prompt_cache_size),\n'
       '                "--prefill-step-size", "256",\n'
       '                "--chat-template-args", \'{"enable_thinking":false}\']')
if new in text:
    print('Private MLX prefill is 256 tokens, with thinking off by default.')
elif text.count(previous) == 1 or text.count(old) == 1:
    patched = text.replace(previous if previous in text else old, new, 1)
    compile(patched, str(args.module), 'exec')
    args.module.write_text(patched)
    print('Set private MLX-LM prefill to 256 tokens and thinking off by default (requests may override).')
else:
    raise SystemExit('Runtime source changed; review prefill patch before applying.')
