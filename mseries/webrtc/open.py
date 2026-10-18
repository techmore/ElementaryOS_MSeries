#!/usr/bin/python3
"""Open host authentication as a fragment; never print the owner key."""
from pathlib import Path
from urllib.parse import urlencode
import os
import webbrowser
import subprocess
import time
import urllib.request

config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'mseries-webrtc'
subprocess.run(['systemctl', '--user', 'start', 'mseries-webrtc.service'], check=True)
for attempt in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8789/health', timeout=0.5) as response:
            if response.status == 200:
                break
    except OSError:
        time.sleep(0.1)
else:
    raise SystemExit('Screen sharing did not start; check journalctl --user -u mseries-webrtc.')
try:
    key = (config / 'owner.key').read_text().strip()
except FileNotFoundError:
    raise SystemExit('Start mseries-webrtc.service first.')
webbrowser.open('http://127.0.0.1:8789/#' + urlencode({'owner': key}))
