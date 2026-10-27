#!/usr/bin/env python3
"""Run the explicit cutover with private files and inert service/privilege tools."""
import os
from pathlib import Path
import subprocess
import tempfile

script = Path(__file__).resolve().parents[1] / 'activate-t3-panel.sh'
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    directory = root / 'indicators'
    directory.mkdir()
    pending = root / 'mseries-pending-indicators'
    pending.mkdir()
    (pending / 'libmseries-t3.so').write_text('unified fixture')
    legacy = ['libcodexbar.so', 'librepobar.so', 'libclaude-pantheon.so']
    for name in legacy:
        (directory / name).write_text(name)
    tools = root / 'tools'
    tools.mkdir()
    for name, source in {
        'pkg-config': '#!/bin/sh\nprintf "%s\\n" "$TEST_DIRECTORY"\n',
        'systemctl': '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LOG"\n',
        'sudo': '''#!/bin/sh
[ "$(head -n1 "$TEST_LOG")" = '--user stop pantheon-wingpanel.service' ] || exit 40
exec "$@"
''',
    }.items():
        tool = tools / name
        tool.write_text(source)
        tool.chmod(0o755)
    env = os.environ | {'PATH': f'{tools}:/usr/bin:/bin', 'TEST_DIRECTORY': str(directory), 'TEST_LOG': str(root / 'calls')}
    subprocess.run(['bash', str(script)], env=env, check=True, capture_output=True, text=True)
    assert (root / 'calls').read_text().splitlines() == [
        '--user stop pantheon-wingpanel.service', '--user start pantheon-wingpanel.service']
    assert sorted(p.name for p in directory.iterdir()) == ['libmseries-t3.so']
    assert (directory / 'libmseries-t3.so').read_text() == 'unified fixture'
    for name in legacy:
        assert (root / 'mseries-retired-indicators' / name).read_text() == name
print('PASS explicit cutover stops the host before migration and retains all rollback modules')
