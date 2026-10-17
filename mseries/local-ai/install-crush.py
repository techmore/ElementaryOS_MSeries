#!/usr/bin/python3
"""Install the checksum-pinned ARM64 coding client and isolated coding profile."""
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request
import shutil

URL = 'https://github.com/charmbracelet/crush/releases/download/v0.98.1/crush_0.98.1_Linux_arm64.tar.gz'
SHA = '098e875c1d9501822d08ef14ab094f24cfc87396385af5402994bf741a673b99'


def main():
    home = Path.home()
    with urllib.request.urlopen(URL, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA:
        raise SystemExit('Crush archive checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for name, target, mode in [('crush', home / '.local/bin/crush', 0o755),
                                   ('LICENSE.md', home / '.local/share/crush/LICENSE.md', 0o644)]:
            matches = [member for member in archive.getmembers() if member.isfile() and Path(member.name).name == name]
            if len(matches) != 1:
                raise SystemExit('Unexpected archive layout')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(matches[0]).read()); target.chmod(mode)
    for directory, name, pin in [
            ('Coding Assistant', 'Qwen3.5-4B-MLX-4bit', '32f3e8ecf65426fc3306969496342d504bfa13f3'),
            ('Coding Assistant Quality', 'Qwen3.5-9B-MLX-4bit', '938d8919941c6e7efd3c7150eff7fe9d12afa631')]:
        workspace = home / 'Documents' / directory
        workspace.mkdir(parents=True, exist_ok=True)
        rc = workspace / '.crushrc'
        model = str(home / '.cache/huggingface/hub' / ('models--mlx-community--' + name) / 'snapshots' / pin)
        if rc.exists():
            old = str(home / '.cache/huggingface/hub/models--mlx-community--Qwen3.5-9B-MLX-4bit/snapshots/938d8919941c6e7efd3c7150eff7fe9d12afa631')
            text = rc.read_text()
            if directory == 'Coding Assistant' and text.startswith('# Local coding profile;') and old in text:
                backup = rc.with_name('.crushrc.before-qwen35-4b')
                if not backup.exists(): shutil.copy2(rc, backup)
                rc.write_text(text.replace(old, model)); rc.chmod(0o600)
            continue
        rc.write_text(f'''# Local coding profile; coding tools retain their approval defaults.
option default-providers false
option provider-auto-update false
option metrics false
option request-timeout 600
permissions deny lsp_diagnostics lsp_references lsp_definition lsp_symbols lsp_call_hierarchy lsp_rename lsp_replace_symbol lsp_restart sourcegraph crush_info crush_logs
provider add mseries --name 'Local coding GPU' --type openai-compat --base-url http://127.0.0.1:8768/v1 --api-key local
model add 'mseries/{model}' --name 'Local Coder' --context-window 16384 --default-max-tokens 2048
model large 'mseries/{model}' --max-tokens 2048
model small 'mseries/{model}' --max-tokens 1024
''')
        rc.chmod(0o600)
    print('Installed pinned Crush coding client; existing profile retained if present.')


if __name__ == '__main__':
    main()
