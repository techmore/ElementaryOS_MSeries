#!/usr/bin/env python3
"""Multi-turn chat against the patched upstream server (everyday 4B, worker env).
Usage: multiturn-probe.py <prompt-cache-size> [KEY=VAL ...]. Prints per turn: prompt tokens,
cached tokens, client first-token seconds."""
import fcntl, json, os, socket, subprocess, sys, time, urllib.request
from pathlib import Path

HOME = Path.home()
size = sys.argv[1]
extra = dict(a.split('=', 1) for a in sys.argv[2:])
SYSTEM = ('You are the desktop assistant on an elementary OS laptop. You can read the calendar, '
          'mail, files and reminders through tools when asked. Answer briefly and plainly. '
          'Never invent appointments or messages. ' * 6).strip()
USERS = ['What is a good way to plan a short week of work?',
         'Make that into three bullet points.',
         'Which of those should come first, and why?',
         'Shorten the reason to one sentence.']

lock = (HOME / '.local/state/mseries-ai/worker.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
with socket.socket() as s:
    s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
env = {k: v for k, v in os.environ.items() if not k.startswith(('MLX_OMARCHY_', 'MSERIES_'))}
env.update(VK_DRIVER_FILES=str(HOME / '.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json'),
           HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='2',
           MLX_OMARCHY_BATCH_WORK='120000', MSERIES_SERVE_CONCURRENCY='4',
           OMARCHY_MLX_SYSTEM_PREFIX=str(HOME / '.local/share/mlx-omarchy'),
           PYTHONPATH=str(HOME / '.local/share/mseries-ai/serve-patch'))
env.update(extra)
logdir = HOME / '.cache/mseries-serve-patch'; logdir.mkdir(exist_ok=True)
log = open(logdir / f'turns-{size}.log', 'w')
child = subprocess.Popen([str(HOME / '.local/bin/mlx-omarchy-serve'), 'serve', 'qwen3.5-4b-mseries-4bit',
                          '--context', '8192', '--prompt-cache-size', size, '--host', '127.0.0.1',
                          '--port', str(port), '--offline', '--yes'],
                         env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ask(messages):
    body = {'model': MODEL_ID, 'messages': messages, 'max_tokens': 64, 'temperature': 0,
            'stream': True, 'stream_options': {'include_usage': True}}
    req = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions', json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    t0 = time.monotonic(); first = None; text = ''; usage = None
    with op.open(req, timeout=300) as r:
        for line in r:
            if not line.startswith(b'data: {'):
                continue
            d = json.loads(line[6:])
            if d.get('usage'):
                usage = d['usage']
            for c in d.get('choices') or []:
                piece = (c.get('delta') or {}).get('content') or ''
                if piece and first is None:
                    first = time.monotonic()
                text += piece
    return text, first - t0, usage


try:
    for _ in range(240):
        try:
            MODEL_ID = json.load(op.open(f'http://127.0.0.1:{port}/v1/models', timeout=2))['data'][0]['id']; break
        except OSError:
            if child.poll() is not None:
                raise SystemExit('server exited; see ' + log.name)
            time.sleep(1)
    ask([{'role': 'user', 'content': 'Say ok.'}])  # warmup, unrelated prefix
    rows = []
    for convo in range(2):
        messages = [{'role': 'system', 'content': SYSTEM}]
        for i, u in enumerate(USERS):
            messages.append({'role': 'user', 'content': u + ('' if convo == 0 else ' Please.')})
            text, ttft, usage = ask(messages)
            messages.append({'role': 'assistant', 'content': text})
            det = (usage or {}).get('prompt_tokens_details') or {}
            rows.append(dict(convo=convo, turn=i + 1, prompt=usage and usage.get('prompt_tokens'),
                             cached=det.get('cached_tokens'), ttft=round(ttft, 3), text=text[:40]))
            print(json.dumps(rows[-1]), flush=True)
            time.sleep(0.3)
    (logdir / f'turns-{size}.json').write_text(json.dumps(rows, indent=1))
finally:
    os.killpg(child.pid, 15); child.wait(timeout=60)
    log.close()
