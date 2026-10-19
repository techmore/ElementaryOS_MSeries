#!/usr/bin/python3
"""Launch an app with IBus; --chromium enables focused-field accessibility metadata."""
import argparse
import os

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--chromium', action='store_true')
parser.add_argument('command', nargs=argparse.REMAINDER)
args = parser.parse_args()
if not args.command: parser.error('Supply an application command')
os.environ.update(GTK_IM_MODULE='ibus', QT_IM_MODULE='ibus', XMODIFIERS='@im=ibus')
command = args.command
if args.chromium and '--force-renderer-accessibility' not in command:
    command = command[:1] + ['--force-renderer-accessibility'] + command[1:]
os.execvp(command[0], command)
