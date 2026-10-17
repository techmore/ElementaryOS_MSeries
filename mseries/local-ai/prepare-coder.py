#!/usr/bin/python3
"""Prepare the pinned coding runtime and verified 7B weights. No model is started."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

COMMIT = '7182ef71e6d5dd0c8ea76486fac134fcd25025d4'
MODEL = 'qwen2.5-coder-7b-instruct-q4_k_m.gguf'
SHA = '509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=str(Path.home() / '.local/share/mlx-omarchy/venv/bin/python'))
    parser.add_argument('--runtime-only', action='store_true', help='Do not download optional 7B comparison weights')
    args = parser.parse_args()
    root = Path.home() / '.local/share/mseries-ai'
    if not (root / 'llama/bin/llama-server').exists() and not Path('/usr/lib/mseries-ai/llama/bin/llama-server').exists():
        subprocess.run(['sudo', 'apt-get', 'install', '-y', 'cmake', 'ninja-build', 'glslc', 'spirv-headers', 'libvulkan-dev', 'libssl-dev'], check=True)
        source = root / 'sources/llama'
        if not (source / '.git').exists():
            source.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'init', str(source)], check=True)
            subprocess.run(['git', '-C', str(source), 'remote', 'add', 'origin', 'https://github.com/ggml-org/llama.cpp.git'], check=True)
            subprocess.run(['git', '-C', str(source), 'fetch', '--depth', '1', 'origin', COMMIT], check=True)
            subprocess.run(['git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
        if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != COMMIT:
            raise SystemExit('Unexpected llama.cpp source revision')
        if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
            raise SystemExit('Modified llama.cpp source')
        build = source / 'build'
        subprocess.run(['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja', '-DGGML_VULKAN=ON', '-DGGML_NATIVE=OFF', '-DLLAMA_BUILD_TESTS=OFF', '-DCMAKE_BUILD_TYPE=Release'], check=True)
        subprocess.run(['nice', '-n', '15', 'cmake', '--build', str(build), '--target', 'llama-server', 'llama-bench', '-j', '2'], check=True)
        target = root / 'llama/bin'; target.mkdir(parents=True, exist_ok=True)
        for path in list((build / 'bin').glob('lib*.so*')) + [build / 'bin/llama-server', build / 'bin/llama-bench']:
            shutil.copy2(path, target / path.name)
        shutil.copy2(source / 'LICENSE', root / 'llama/LICENSE')
    if args.runtime_only:
        print('Prepared pinned optional llama runtime; no comparison weights downloaded.')
        return
    # Download using the pinned MLX environment's HF client; verify actual weight bytes.
    modeldir = root / 'models'; modeldir.mkdir(parents=True, exist_ok=True)
    code = "from huggingface_hub import hf_hub_download; import sys; hf_hub_download('Qwen/Qwen2.5-Coder-7B-Instruct-GGUF',sys.argv[1],revision='13fb94bfda8c8cf22497dc57b78f391a9acb426a',local_dir=sys.argv[2])"
    subprocess.run([args.python, '-c', code, MODEL, str(modeldir)], check=True)
    with (modeldir / MODEL).open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    if digest != SHA:
        raise SystemExit('Coding model checksum mismatch')
    print('Prepared verified coding weights and pinned runtime.')


if __name__ == '__main__':
    main()
