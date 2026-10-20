#!/usr/bin/env python3
"""Replace the dock's Mail shortcut with Outlook Web using the existing Brave session."""
import argparse
import json
import os
from pathlib import Path
import sys
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parent / 'teams-web'))
from teams import BRAVE_BROWSERS, brave_profile, roots
from setup import atomic_write, desktop_quote, refresh_desktop

APP_ID = 'org.techmore.mseries.OutlookWeb'


def replace_mail(launchers):
    result = []
    replaced = False
    for launcher in launchers:
        if launcher == 'io.elementary.mail.desktop':
            launcher = APP_ID + '.desktop'
            replaced = True
        if launcher not in result:
            result.append(launcher)
    return result, replaced


def install(settings=None):
    from gi.repository import Gio
    browser = next((shutil.which(name) for name in BRAVE_BROWSERS if shutil.which(name)), None)
    if not browser:
        raise ValueError('Install Brave before setting up Outlook Web.')
    profile = brave_profile()
    _, data = roots()
    desktop = data / 'applications' / (APP_ID + '.desktop')
    entry = f'''[Desktop Entry]
Version=1.0
Type=Application
Name=Outlook (Web)
GenericName=Mail
Comment=Outlook Web using your existing Brave sign-in
Exec={desktop_quote(browser)} {desktop_quote('--profile-directory=' + profile)} --app=https://outlook.office.com/mail/
Icon=io.elementary.mail
Terminal=false
Categories=Network;Email;
Keywords=Mail;Email;Microsoft;Outlook;
StartupNotify=true
'''
    atomic_write(desktop, entry)
    refresh_desktop(data)
    if settings is None:
        settings = Gio.Settings.new('io.elementary.dock')
    previous = list(settings.get_strv('launchers'))
    updated, replaced = replace_mail(previous)
    backup = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'mseries/outlook-web/dock-before.json'
    if replaced:
        if not backup.exists():
            atomic_write(backup, json.dumps({'launchers': previous}, indent=2) + '\n', 0o600)
        if not settings.set_strv('launchers', updated):
            raise ValueError('The dock launcher setting is not writable.')
        Gio.Settings.sync()
    print('Installed Outlook (Web) using Brave profile ' + profile + '.')
    print('Replaced the dock Mail shortcut.' if replaced else 'The dock Mail shortcut was already replaced or is not pinned.')
    return desktop


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        install()
        return 0
    except (ValueError, OSError) as error:
        print('Outlook setup: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
