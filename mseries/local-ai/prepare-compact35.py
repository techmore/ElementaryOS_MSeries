#!/usr/bin/python3
"""Download and verify the optional 4B challenger; register an explicit offline test target."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from machine import runtime_prefix

HERE = Path(__file__).resolve().parent


def main():
    prefix = runtime_prefix()
    python = prefix / 'venv/bin/python'
    entry = json.loads((HERE / 'qwen35-4b-catalog-entry.json').read_text())
    # Download uses the runtime's pinned hub client, not an unpinned host package.
    code = '''import sys
from huggingface_hub import snapshot_download
print(snapshot_download(repo_id=sys.argv[1],revision=sys.argv[2],local_files_only=sys.argv[3]=='--offline'))
'''
    mode = '--offline' if '--offline' in sys.argv else '--download'
    result = subprocess.run([str(python), '-c', code, entry['repo'], entry['revision'], mode],
                            check=True, text=True, capture_output=True)
    model = Path(result.stdout.strip().splitlines()[-1])
    for item in entry['extension']['files']:
        path = model / item['path']
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(chunk)
        if path.stat().st_size != item['size_bytes'] or digest.hexdigest() != item['sha256']:
            raise SystemExit('Pinned model verification failed: ' + item['path'])
    # The closed upstream schema remains the authority. Never mark this target
    # recommended or upstream-qualified based on our small local suite.
    registration = '''import json,os,sys,tempfile
from pathlib import Path
from mlx_omarchy_serve import catalog
entry=json.loads(Path(sys.argv[1]).read_text())
path=catalog.cache_path()
data=json.loads((path if path.exists() else catalog.bundled_path()).read_text())
data['models']=[m for m in data['models'] if m['id']!=entry['id']]+[entry]
catalog.validate_catalog(data)
path.parent.mkdir(parents=True,exist_ok=True)
with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as f:
 json.dump(data,f,indent=2);f.write('\\n');name=f.name
os.replace(name,path)
print('Verified optional target: '+entry['id']+' at '+entry['revision'])
'''
    env = dict(os.environ, OMARCHY_MLX_SYSTEM_PREFIX=str(prefix), MLX_OMARCHY_OFFLINE='1',
               PYTHONPATH=str(prefix) + os.pathsep + os.environ.get('PYTHONPATH', ''))
    subprocess.run([str(python), '-c', registration, str(HERE / 'qwen35-4b-catalog-entry.json')],
                   check=True, env=env)


if __name__ == '__main__':
    main()
