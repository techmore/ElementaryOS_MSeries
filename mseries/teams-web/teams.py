#!/usr/bin/env python3
"""Run Microsoft's Teams web client in a dedicated supported-browser window."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

HOME_URL = 'https://teams.microsoft.com/v2/'
APP_ID = 'org.techmore.mseries.TeamsWeb'
SUPPORTED_BROWSERS = ('google-chrome-stable', 'google-chrome', 'microsoft-edge-stable', 'microsoft-edge')
BRAVE_BROWSERS = ('brave-browser-stable', 'brave-browser', 'brave')
BROWSERS = SUPPORTED_BROWSERS + BRAVE_BROWSERS
HOSTS = {'teams.microsoft.com', 'teams.cloud.microsoft', 'teams.live.com'}


def roots():
    home = Path.home()
    config = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    data = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share'))
    return config / 'mseries/teams-web', data


def teams_url(value):
    if not value:
        return HOME_URL
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or '\\' in value:
        raise ValueError('Invalid Teams link.')
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {'https', 'msteams'} or parsed.netloc not in HOSTS:
            raise ValueError()
        if parsed.path and not parsed.path.startswith('/'):
            raise ValueError()
    except ValueError:
        raise ValueError('Only official HTTPS Teams links and msteams:// Teams links are accepted.') from None
    return urlunsplit(('https', parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def browser_path(config):
    configured = config.get('browser')
    if configured:
        if not isinstance(configured, str):
            raise ValueError('Invalid browser configuration. Re-run the Teams installer.')
        path = Path(configured)
        if path.is_absolute() and path.name in BROWSERS and os.access(path, os.X_OK):
            return str(path)
        raise ValueError('The configured browser is missing. Re-run the Teams installer.')
    for name in SUPPORTED_BROWSERS:
        path = shutil.which(name)
        if path:
            return path
    raise ValueError('Install Google Chrome or Microsoft Edge, then run the Teams installer. '
                     'On ARM64, use Google’s official arm64 .deb package. See the Teams Web README.')


def load_config(root):
    path = root / 'config.json'
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, OSError):
        raise ValueError('The Teams launcher configuration is unreadable. Re-run the installer.') from None


def brave_profile():
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    state = config / 'BraveSoftware/Brave-Browser/Local State'
    try:
        name = json.loads(state.read_text()).get('profile', {}).get('last_used', 'Default')
    except (OSError, ValueError, AttributeError):
        name = 'Default'
    return validate_profile(name)


def validate_profile(name):
    if (not isinstance(name, str) or not name or name in {'.', '..'}
            or any(c in name for c in '/\\') or any(ord(c) < 32 for c in name)):
        raise ValueError('Invalid Brave profile directory. Re-run the Teams installer.')
    return name


def command(browser, profile, url, shared_profile=None):
    if shared_profile is not None:
        # Let Brave itself reuse its cookies, keyring and running singleton.
        # Never read, export or copy its authentication databases.
        return [browser, '--profile-directory=' + validate_profile(shared_profile),
                '--no-default-browser-check', '--app=' + url]
    return [browser, '--user-data-dir=' + str(profile), '--class=' + APP_ID,
            '--no-first-run', '--no-default-browser-check', '--app=' + url]


def report_error(message):
    print('Teams: ' + message, file=sys.stderr)
    # A launcher failure must also be visible when launched from Applications.
    if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
        try:
            import gi
            gi.require_version('Gtk', '4.0')
            from gi.repository import Gtk
            app = Gtk.Application(application_id=APP_ID + '.Error')
            def activate(*_):
                window = Gtk.ApplicationWindow(application=app, title='Microsoft Teams')
                window.set_default_size(440, 220)
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
                for edge in ('top', 'bottom', 'start', 'end'):
                    getattr(box, 'set_margin_' + edge)(24)
                label = Gtk.Label(label=message, wrap=True, selectable=True)
                box.append(label)
                close = Gtk.Button(label='Close')
                close.connect('clicked', lambda *_: window.close())
                box.append(close)
                window.set_child(box)
                window.present()
            app.connect('activate', activate)
            app.run([])
        except (ImportError, ValueError, RuntimeError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', nargs='?')
    parser.add_argument('--check', action='store_true', help='Print local diagnostics without launching Teams')
    parser.add_argument('--dry-run', action='store_true', help='Print launch arguments without opening a window')
    args = parser.parse_args(argv)
    try:
        url = teams_url(args.url)
        root, _ = roots()
        config = load_config(root)
        browser = browser_path(config)
        shared = config.get('profile_directory') if config.get('mode') == 'brave-session' else None
        if shared is not None:
            validate_profile(shared)
            if Path(browser).name not in BRAVE_BROWSERS:
                raise ValueError('Session reuse requires Brave. Re-run the installer.')
        profile = root / 'profile'
        if args.check:
            version = subprocess.run([browser, '--version'], capture_output=True, text=True,
                                     timeout=15, check=True).stdout.strip()
            print(json.dumps({'browser': browser, 'version': version,
                              'profile': shared if shared is not None else str(profile),
                              'profile_exists': None if shared is not None else profile.is_dir(),
                              'client': HOME_URL, 'mode': 'existing Brave session' if shared is not None else 'isolated supported browser'}, indent=2))
            return 0
        launch = command(browser, profile, url, shared)
        if args.dry_run:
            print(json.dumps(launch))
            return 0
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if shared is None:
            profile.mkdir(exist_ok=True, mode=0o700)
            profile.chmod(0o700)
        # Chrome owns singleton locking, cookies, updates and OS permission prompts.
        # Leave the browser sandbox and all camera/microphone permissions intact.
        os.execv(browser, launch)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if isinstance(error, ValueError):
            message = str(error)
        else:
            message = 'The Teams browser could not start. Re-run the installer and try again.'
        report_error(message)
        return 1


if __name__ == '__main__':
    sys.exit(main())
