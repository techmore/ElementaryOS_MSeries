#!/usr/bin/env python3
"""Install a per-user Teams web launcher; never change the default browser."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import official_icon

from teams import APP_ID, BRAVE_BROWSERS, brave_profile, browser_path, load_config, roots

HERE = Path(__file__).resolve().parent


def atomic_write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    # Refuse preexisting symlinks rather than following them while writing.
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb' if isinstance(content, bytes) else 'w') as output:
            output.write(content)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def desktop_quote(path):
    # Desktop Exec has its own quoting grammar (not a shell command).
    value = str(path).replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\' + char)
    # Desktop string parsing consumes one layer of backslash escapes.
    return '"' + value.replace('\\', '\\\\') + '"'


def desktop_entry(launcher):
    return f'''[Desktop Entry]
Version=1.0
Type=Application
Name=Microsoft Teams (Web)
GenericName=Team Collaboration
Comment=Microsoft Teams in a dedicated Chrome or Edge window
Exec=/usr/bin/python3 {desktop_quote(launcher)} %u
Icon={APP_ID}
Terminal=false
Categories=Network;InstantMessaging;VideoConference;
Keywords=Teams;Microsoft;Chat;Meeting;Call;
StartupNotify=true
StartupWMClass={APP_ID}
MimeType=x-scheme-handler/msteams;
'''


def refresh_desktop(data):
    cache = shutil.which('gtk-update-icon-cache')
    icons = data / 'icons/hicolor'
    if cache and icons.exists():
        subprocess.run([cache, '-f', '-t', str(icons)], check=False, capture_output=True)
    tool = shutil.which('update-desktop-database')
    if tool:
        subprocess.run([tool, str(data / 'applications')], check=False, capture_output=True)


def install_icon(root, data):
    generic = data / 'icons/hicolor/scalable/apps' / (APP_ID + '.svg')
    official = data / 'icons/hicolor/256x256/apps' / (APP_ID + '.png')
    try:
        content = official_icon.download()
        atomic_write(official, content)
        generic.unlink(missing_ok=True)
        atomic_write(root / 'icon-source.json', json.dumps({
            'url': official_icon.URL, 'source_sha256': official_icon.SHA256,
            'owner': 'Microsoft', 'use': 'Local shortcut to the Microsoft Teams web client',
        }, indent=2) + '\n')
    except (OSError, ValueError):
        if not official.exists():
            atomic_write(generic, (HERE / 'icon.svg').read_text())
        print('Teams icon: could not fetch the verified Microsoft icon; keeping the existing icon.',
              file=sys.stderr)


def install(browser=None, use_brave_session=False):
    root, data = roots()
    launcher = data / 'mseries/teams-web/mseries-teams'
    desktop = data / 'applications' / (APP_ID + '.desktop')
    if browser is None and not use_brave_session:
        try:
            config = load_config(root)
        except ValueError:
            config = {}  # Reinstall repairs a malformed configuration.
        use_brave_session = config.get('mode') == 'brave-session'
    else:
        config = {} if browser is None else {'browser': str(Path(browser).absolute())}
    if use_brave_session:
        selected = next((shutil.which(name) for name in BRAVE_BROWSERS if shutil.which(name)), None)
        if not selected:
            raise ValueError('Brave is not installed. Install Brave or use the Chrome/Edge option.')
        config = {'browser': selected, 'mode': 'brave-session',
                  'profile_directory': config.get('profile_directory', brave_profile())}
    selected = browser_path(config)  # Check before writing anything.
    config['browser'] = selected
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(launcher, (HERE / 'teams.py').read_text(), 0o755)
    install_icon(root, data)
    entry = desktop_entry(launcher)
    if use_brave_session:
        # Existing Brave owns the window identity; do not promise a separate class.
        entry = entry.replace('StartupWMClass=' + APP_ID + '\n', '')
        entry = entry.replace('dedicated Chrome or Edge window', 'window using your Brave sign-in')
    atomic_write(desktop, entry)
    atomic_write(root / 'config.json', json.dumps(config, indent=2) + '\n', 0o600)
    refresh_desktop(data)
    return launcher, desktop


def uninstall():
    root, data = roots()
    for path in (data / 'mseries/teams-web/mseries-teams',
                 data / 'applications' / (APP_ID + '.desktop'),
                 data / 'icons/hicolor/scalable/apps' / (APP_ID + '.svg'),
                 data / 'icons/hicolor/256x256/apps' / (APP_ID + '.png')):
        path.unlink(missing_ok=True)
    # Keep profile and configuration: uninstalling a shortcut must not erase sessions.
    refresh_desktop(data)
    print('Removed the Teams launcher. The Teams profile and sign-in data are preserved at ' + str(root))


def pin_launcher(settings):
    launchers = list(settings.get_strv('launchers'))
    name = APP_ID + '.desktop'
    if name not in launchers:
        if not settings.set_strv('launchers', launchers + [name]):
            raise ValueError('The dock launcher setting is not writable.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', help='Absolute path to an installed Chrome or Edge executable')
    parser.add_argument('--use-brave-session', action='store_true',
                        help='Use the last-used Brave profile and its existing Microsoft sign-in')
    parser.add_argument('--uninstall', action='store_true')
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--pin', action='store_true', help='Add Teams to the elementary dock')
    args = parser.parse_args(argv)
    try:
        if args.uninstall:
            uninstall()
            return 0
        if args.browser and args.use_brave_session:
            raise ValueError('Choose --browser or --use-brave-session, not both.')
        launcher, desktop = install(args.browser, args.use_brave_session)
        if args.pin:
            from gi.repository import Gio
            pin_launcher(Gio.Settings.new('io.elementary.dock'))
            Gio.Settings.sync()
        print('Installed: ' + str(desktop))
        print('Open Microsoft Teams (Web) in Applications. Sign in directly with Microsoft.')
        if args.launch:
            subprocess.Popen([str(launcher)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        return 0
    except (ValueError, OSError) as error:
        print('Teams install: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
