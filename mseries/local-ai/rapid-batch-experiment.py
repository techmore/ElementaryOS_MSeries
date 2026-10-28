#!/usr/bin/env python3
"""Guarded loopback-only Rapid-MLX batch-budget comparison."""
import argparse, fcntl, hashlib, json, os, signal, socket, subprocess, sys, tempfile, threading, time
import urllib.request, urllib.error
from pathlib import Path
from machine import GIB, snapshot, violations

HOME = Path.home()
MODEL = HOME / '.cache/mseries-metal2vk/qwen38-mlx'
SHA = 'b0d5de688567bf4acd5e421027acd410dabcdc255a5bd46fdbf06c75dc2e6863'
PROMPT = 'Explain in plain language how a rainbow forms. Give four distinct sentences.'
OUT = Path(__file__).resolve().parent / 'receipts/2026-10-27-qwen38-rapid-batch.json'
POLICY = {'reserve_gib': 6, 'max_fan_rpm': float('inf'), 'max_temp_c': 80}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=int, choices=[5000, 20000, 80000], default=5000)
    parser.add_argument("--candidate", type=int, choices=[20000, 80000], default=20000)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--prefix-cache-probe", action="store_true", help="Measure cold and repeat long prompts in one server")
    args = parser.parse_args()
    if args.baseline == args.candidate:
        parser.error("baseline and candidate must differ")
    with (MODEL / 'model.safetensors').open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != SHA:
            raise SystemExit('Unrecognized model weights')
    lock = (HOME / '.local/state/mseries-ai/worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    report = {'status': 'running', 'model': 'nvythong/Qwen3.8-2B-Distill-mlx-4Bit@0afdb6850d218024c7788eda5659aa25475b7d51',
              'weights_sha256': SHA, 'rapid_revision': '1d09cdb684bbf58fac130f5804b08ee2e1f56558',
              'mode': 'prefix_cache' if args.prefix_cache_probe else 'batch_budget', 'runs': []}
    try:
        with tempfile.TemporaryDirectory(prefix='rapid-mseries-ab-') as tmp:
            sequence = (args.candidate,) if args.prefix_cache_probe else (args.baseline, args.candidate, args.candidate, args.baseline, args.baseline, args.candidate)
            for i, budget in enumerate(sequence):
                s = snapshot(); reasons = violations(s, POLICY, extra_bytes=int(4.5*GIB))
                if reasons: raise RuntimeError('Admission refused: ' + '; '.join(reasons))
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
                env = {k:v for k,v in os.environ.items() if not k.startswith('MLX_OMARCHY_')}
                env.update(PYTHONPATH=f"{HOME}/.cache/mseries-metal2vk/rapid-python:/tmp/mseries-rapid-mlx",
                    VK_DRIVER_FILES=str(HOME/'.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json'),
                    MLX_OMARCHY_BATCH_WORK=str(budget), HF_HUB_OFFLINE='1', RAPID_MLX_TELEMETRY='0',
                    DO_NOT_TRACK='1', RAPID_MLX_PREFIX_CACHE_AUTOLOAD='0', XDG_CONFIG_HOME=f'{tmp}/config-{i}',
                    XDG_CACHE_HOME=f'{tmp}/cache-{i}', XDG_STATE_HOME=f'{tmp}/state-{i}',
                    OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
                log = tempfile.TemporaryFile(mode='w+t')
                child = subprocess.Popen([str(HOME/'.local/share/mlx-omarchy/venv/bin/python'), '-m', 'rapid_mlx.server',
                    '--model', str(MODEL), '--no-mllm', '--host', '127.0.0.1', '--port', str(port)],
                    env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                outcome = {}; samples = []; started = time.monotonic()
                def work():
                    try:
                        url=f'http://127.0.0.1:{port}/v1/chat/completions'
                        def request(prompt):
                            payload={'model':str(MODEL), 'messages':[{'role':'user','content':prompt}],
                                'max_tokens':32, 'temperature':0, 'chat_template_kwargs':{'enable_thinking':False}}
                            req=urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
                            begin=time.monotonic()
                            with urllib.request.urlopen(req, timeout=45) as r:
                                data=json.load(r)
                            return {'elapsed_s':time.monotonic()-begin, 'response':data}
                        while time.monotonic()-started < 90:
                            if child.poll() is not None: raise RuntimeError('Server exited during startup')
                            try:
                                with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz',timeout=2): break
                            except (OSError, urllib.error.HTTPError): time.sleep(.5)
                        else: raise RuntimeError('Server readiness timeout')
                        outcome['warmup']=request('What is 12 plus 7? Reply with the number only.')
                        if args.prefix_cache_probe:
                            outcome['pairs'] = []
                            for pair in range(3):
                                text = f'Case {pair}: Summarize the following explanation in two sentences. ' + (
                                    'Sunlight enters raindrops and changes direction. Internal reflection returns light, while refraction separates colors. ' * 28)
                                outcome['pairs'].append({'cold': request(text), 'repeat': request(text)})
                        else:
                            outcome['measured']=request(PROMPT)
                    except Exception as exc: outcome['error']=str(exc)
                thread=threading.Thread(target=work, daemon=True); thread.start(); bad=0; stopped=None
                try:
                    while thread.is_alive():
                        sample=snapshot(); samples.append({'available_bytes':sample['available_bytes'],
                            'max_temp_c':max(sample['temperatures_c'].values(),default=0),
                            'max_fan_rpm':max(sample['fans_rpm'].values(),default=0)})
                        reasons=violations(sample,POLICY); bad=bad+1 if reasons else 0
                        if bad>=3 or time.monotonic()-started>180:
                            stopped=reasons or ['deadline']; break
                        thread.join(.5)
                finally:
                    if child.poll() is None:
                        os.killpg(child.pid,signal.SIGTERM)
                        try: child.wait(timeout=10)
                        except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL); child.wait()
                    thread.join(timeout=2)
                log.seek(0); row={'budget':budget,'admission_available_bytes':s['available_bytes'],
                    'samples':samples,'outcome':outcome,'stopped':stopped,'log_tail':log.read()[-30000:]}; log.close()
                report['runs'].append(row)
                if stopped or 'error' in outcome or ('pairs' if args.prefix_cache_probe else 'measured') not in outcome: raise RuntimeError(str(stopped or outcome))
                if args.prefix_cache_probe:
                    print(f"prefix probe completed {len(outcome['pairs'])} cold/repeat pairs at budget={budget}", flush=True)
                else:
                    print(f"run {i+1} budget={budget} HTTP={outcome['measured']['elapsed_s']:.3f}s",flush=True)
                time.sleep(2)
        report['status']='complete'
    except BaseException as exc:
        report['status']='interrupted'; report['error']=str(exc); raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n'); lock.close()

if __name__=='__main__': main()
