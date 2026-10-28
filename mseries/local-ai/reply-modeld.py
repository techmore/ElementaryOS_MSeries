#!/usr/bin/env python3
"""mseries-reply-modeld: the Smart Reply drafting model behind an OpenAI-compatible API on 127.0.0.1:8766/v1.

mseries-ai (and so mseries-reply, Ctrl+Alt+R) asks this endpoint first and falls back to mseries-assistd (8772).
The model loads on the first draft and is dropped after MSERIES_REPLY_IDLE seconds without requests, or after
60 seconds when free memory is below the desktop reserve. Dropping it exits the process, because the Vulkan MLX
backend keeps the model's buffers pinned until exit; systemd starts a fresh, empty server a second later.

While the model is not loaded and there is not enough free memory to load it, /v1/models lists nothing, so
mseries-ai uses the smaller assistant model instead of failing.

Endpoints (127.0.0.1 only):
  GET  /health                 {"model", "loaded", "available_gib", ...}
  GET  /v1/models              OpenAI-style model list
  POST /v1/chat/completions    {"messages", "max_tokens", "temperature", "chat_template_kwargs"}; stream is not supported
"""

import argparse
import gc
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

GIB = 1024 ** 3
# Winner of the 2026-10-28 comparison (reply-model-compare.md).
DEFAULT_MODEL = 'mlx-community/Qwen3.5-4B-MLX-4bit'
DEFAULT_REVISION = '32f3e8ecf65426fc3306969496342d504bfa13f3'
RESERVE_GIB = float(os.environ.get('MSERIES_REPLY_RESERVE_GIB', '4'))  # desktop headroom kept free
ADMISSION_GIB = float(os.environ.get('MSERIES_REPLY_ADMISSION_GIB', '3.5'))  # weights plus working memory
TIGHT_IDLE_SECONDS = 60
MAX_BODY = 1024 * 1024
MAX_TOKENS = 1400


def available_gib():
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) * 1024 / GIB
    except OSError:
        pass
    return 0.0


def model_id(model):
    """A stable, readable id: the last path or repo component, lower-case (e.g. qwen3.5-4b-mlx-4bit)."""
    return str(model).rstrip('/').split('/')[-1].lower()


def resolve(model, revision):
    """A local directory as is; a Hugging Face id from the offline cache, pinned to `revision` when given."""
    if Path(model).expanduser().is_dir():
        return str(Path(model).expanduser())
    from huggingface_hub import snapshot_download
    return snapshot_download(model, revision=revision, local_files_only=True)


class Busy(Exception):
    pass


class Engine:
    def __init__(self, model, idle_seconds, exit_on_unload=True, revision=None):
        self.model_ref = str(model)
        self.revision = revision
        self.id = model_id(model)
        self.idle_seconds = idle_seconds
        self.exit_on_unload = exit_on_unload
        self.lock = threading.Lock()
        self.model = None
        self.tokenizer = None
        self.load_seconds = None
        self.last_used = time.monotonic()
        threading.Thread(target=self._idle_watch, daemon=True).start()

    def can_load(self):
        return self.model is not None or available_gib() >= RESERVE_GIB + ADMISSION_GIB

    def _ensure(self):
        if self.model is not None:
            return
        free = available_gib()
        if free < RESERVE_GIB + ADMISSION_GIB:
            raise Busy(f'Not enough free memory to load the reply model ({free:.1f} GiB available, '
                       f'{RESERVE_GIB + ADMISSION_GIB:.1f} GiB needed).')
        from mlx_lm import load
        started = time.monotonic()
        self.model, self.tokenizer = load(resolve(self.model_ref, self.revision))
        self.load_seconds = time.monotonic() - started
        print(f'reply-modeld: loaded {self.model_ref} in {self.load_seconds:.1f}s', flush=True)

    def _unload(self, why):
        import mlx.core as mx
        self.model = self.tokenizer = None
        gc.collect()
        mx.clear_cache()
        print(f'reply-modeld: unloaded ({why})', flush=True)
        if self.exit_on_unload:
            print('reply-modeld: exiting to release GPU memory', flush=True)
            sys.stdout.flush()
            os._exit(0)

    def _idle_watch(self):
        while True:
            time.sleep(10)
            with self.lock:
                if self.model is None:
                    continue
                idle = time.monotonic() - self.last_used
                if idle > self.idle_seconds:
                    self._unload('idle')
                elif idle > TIGHT_IDLE_SECONDS and available_gib() < RESERVE_GIB:
                    self._unload('memory is tight')

    def chat(self, messages, max_tokens, temperature, template_kwargs):
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler
        with self.lock:
            self._ensure()
            try:
                kwargs = {'enable_thinking': False}
                kwargs.update({k: v for k, v in template_kwargs.items() if k == 'enable_thinking'})
                prompt = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False,
                                                            **kwargs)
                text = generate(self.model, self.tokenizer, prompt, max_tokens=max_tokens,
                                sampler=make_sampler(temp=temperature))
                return text
            finally:
                self.last_used = time.monotonic()


def clean_messages(raw):
    messages = []
    for message in raw if isinstance(raw, list) else []:
        role = message.get('role') if isinstance(message, dict) else None
        content = message.get('content') if isinstance(message, dict) else None
        if role in ('system', 'user', 'assistant') and isinstance(content, str):
            messages.append({'role': role, 'content': content})
    if not messages:
        raise ValueError('No messages to answer.')
    return messages


def handler_for(engine):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'mseries-reply-modeld/1'

        def log_message(self, fmt, *args):
            print('reply-modeld: ' + fmt % args, flush=True)

        def _send(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == '/health':
                return self._send(200, {'model': engine.id, 'loaded': engine.model is not None,
                                        'load_seconds': engine.load_seconds,
                                        'available_gib': round(available_gib(), 2)})
            if path in ('/v1/models', '/models'):
                data = [{'id': engine.id, 'object': 'model', 'owned_by': 'local'}] if engine.can_load() else []
                return self._send(200, {'object': 'list', 'data': data})
            self._send(404, {'error': 'not found'})

        def do_POST(self):
            if urlparse(self.path).path not in ('/v1/chat/completions', '/chat/completions'):
                return self._send(404, {'error': 'not found'})
            try:
                length = int(self.headers.get('Content-Length') or 0)
                if length > MAX_BODY:
                    raise ValueError('Request body too large')
                body = json.loads(self.rfile.read(length) or b'{}')
                if body.get('stream'):
                    raise ValueError('Streaming is not supported.')
                started = time.monotonic()
                text = engine.chat(clean_messages(body.get('messages')),
                                   max(1, min(int(body.get('max_tokens') or 220), MAX_TOKENS)),
                                   float(body.get('temperature', 0.35)),
                                   body.get('chat_template_kwargs') or {})
                print(f'reply-modeld: drafted in {time.monotonic() - started:.2f}s', flush=True)
                self._send(200, {'id': f'reply-{int(time.time() * 1000)}', 'object': 'chat.completion',
                                 'created': int(time.time()), 'model': engine.id,
                                 'choices': [{'index': 0, 'finish_reason': 'stop',
                                              'message': {'role': 'assistant', 'content': text}}]})
            except Busy as error:
                self._send(503, {'error': str(error)})
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self._send(400, {'error': str(error)})
            except Exception as error:  # the model failed; keep serving
                print(f'reply-modeld: error {type(error).__name__}: {error}', file=sys.stderr, flush=True)
                self._send(500, {'error': f'{type(error).__name__}: {error}'})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--model', default=os.environ.get('MSERIES_REPLY_MODEL', DEFAULT_MODEL),
                        help='MLX model directory or downloaded Hugging Face id')
    parser.add_argument('--revision', default=os.environ.get('MSERIES_REPLY_REVISION', DEFAULT_REVISION),
                        help='Hugging Face commit to load from the offline cache')
    parser.add_argument('--port', type=int, default=int(os.environ.get('MSERIES_REPLY_PORT', 8766)))
    parser.add_argument('--idle', type=int, default=int(os.environ.get('MSERIES_REPLY_IDLE', 900)),
                        help='Seconds without requests before the model is unloaded')
    parser.add_argument('--preload', action='store_true')
    args = parser.parse_args()
    engine = Engine(args.model, args.idle, os.environ.get('MSERIES_REPLY_EXIT_ON_UNLOAD', '1') == '1',
                    args.revision or None)
    if args.preload:
        with engine.lock:
            engine._ensure()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(engine))
    print(f'reply-modeld: {engine.id} on 127.0.0.1:{args.port} (loads on first request)', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
