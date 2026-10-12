#!/usr/bin/python3
"""Restart only this user's Wingpanel and verify the desktop respawns it."""
import os
from pathlib import Path
import signal
import time


def panel_pids():
    found = set()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if proc.stat().st_uid == os.getuid() and args[0].split(b'/')[-1] == b'io.elementary.wingpanel':
                found.add(int(proc.name))
        except (OSError, IndexError):
            continue
    return found


def main():
    before = panel_pids()
    if not before:
        raise SystemExit('No running Wingpanel found. Log out and back in to restore the desktop shell.')
    if len(before) != 1:
        raise SystemExit('Multiple panels found; leaving them untouched for manual inspection.')
    os.kill(next(iter(before)), signal.SIGTERM)
    for _ in range(20):
        time.sleep(1)
        after = panel_pids() - before
        if after:
            time.sleep(3)
            if after <= panel_pids():
                print('Wingpanel restarted and remained running. Check that the bar responds; recurring crashes need log analysis.')
                return
    raise SystemExit('Wingpanel did not stay running after restart. Open Local Troubleshooter to inspect the crash logs.')


if __name__ == '__main__':
    main()
