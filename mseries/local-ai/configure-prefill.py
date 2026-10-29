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
# v0.7.34 passes its own budgeted --prefill-step-size (default 512, issue #240). Keep 256 as the
# default chunk (its budget still sizes scratch for 512, so it stays conservative) and add thinking off.
v0734_old = ("                    prefill_step_tokens or budget.DEFAULT_PREFILL_STEP_TOKENS,\n"
             "                    context_tokens))]")
v0734_new = ("                    prefill_step_tokens or 256,\n"
             "                    context_tokens)),\n"
             "                \"--chat-template-args\", '{\"enable_thinking\":false}']")
if new in text or v0734_new in text:
    print('Private MLX prefill is 256 tokens, with thinking off by default.')
elif text.count(previous) == 1 or text.count(old) == 1:
    patched = text.replace(previous if previous in text else old, new, 1)
    compile(patched, str(args.module), 'exec')
    args.module.write_text(patched)
    print('Set private MLX-LM prefill to 256 tokens and thinking off by default (requests may override).')
elif text.count(v0734_old) == 1:
    patched = text.replace(v0734_old, v0734_new, 1)
    compile(patched, str(args.module), 'exec')
    args.module.write_text(patched)
    print('Set private MLX-LM prefill to 256 tokens and thinking off by default (requests may override).')
else:
    raise SystemExit('Runtime source changed; review prefill patch before applying.')
