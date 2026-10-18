#!/usr/bin/env python3
"""Private stdin/stdout bridge. Never log protocol payloads: vault data is sensitive."""
import json
import logging
import re
import sys
import subprocess


def emit(event_type, **fields):
    print(json.dumps(dict(type=event_type, **fields)), flush=True)


def prompt(kind, label, **fields):
    emit('prompt', kind=kind, label=label, **fields)
    return read_reply()


def read_reply():
    line = sys.stdin.readline(65536)
    if not line:
        raise KeyboardInterrupt
    value = json.loads(line)
    if value.get('cancel'):
        raise KeyboardInterrupt
    return value.get('value', '')


def friendly_error(message):
    # Never forward raw server errors, headers, account identifiers or tokens.
    text = str(message)
    if '-80045' in text:
        return 'Apple rejected this experimental client (−80045). Stop here; repeated sign-ins will not fix this compatibility problem.'
    if 'CERTIFICATE' in text.upper() or 'SSLError' in text:
        return 'The secure connection to Apple could not be verified. No insecure fallback is allowed.'
    if 'passcode' in text.lower() or 'escrow' in text.lower() or 'join failed' in text.lower():
        return 'Keychain recovery failed. Do not guess or automatically retry the device passcode. Your account may already be signed in.'
    if 'authentication helper' in text.lower():
        return 'The local authentication helper could not start. Check its installation before signing in again.'
    if 'keyring' in text.lower() or 'Secret Service' in text:
        return 'Unlock your login keyring, then try again.'
    codes = re.findall(r'(?:ec=|HTTP |status )(-?\d+)', text)
    suffix = f' (code {codes[0]})' if codes else ''
    return 'Apple Passwords could not complete this step' + suffix + '. Your existing encrypted data has been kept.'


def progress(message):
    text = str(message).lower()
    if '2fa' in text:
        label = 'Check your trusted Apple device for a verification code…'
    elif 'bottle' in text or 'escrow' in text:
        label = 'Looking for a trusted device for keychain recovery…'
    elif 'sync' in text or 'decrypt' in text:
        label = 'Refreshing your encrypted password snapshot…'
    elif 'sign' in text or 'token' in text or 'auth' in text:
        label = 'Signing in securely with Apple…'
    else:
        label = 'Connecting to iCloud…'
    emit('progress', text=label)


def snapshot():
    from icp import paths
    from icp.auth import session
    from icp.octagon.client import is_joined
    from icp.vault.store import load_vault
    record = session.load() if paths.session_file().exists() else None
    creds = load_vault().all() if paths.vault_file().exists() else []
    # Only the in-memory GUI receives this. Never send auth records or TOTP seeds.
    emit('vault', signed_in=bool(record), joined=is_joined(record or {}),
         credentials=[{'domain': c.domain, 'username': c.username,
                       'password': c.password, 'title': c.title} for c in creds],
         updated=paths.vault_file().stat().st_mtime if paths.vault_file().exists() else None)


def main():
    logging.disable(logging.CRITICAL)
    from icp.cli import app, ui
    action = sys.argv[1]
    if action not in ('login', 'sync', 'load', 'logout'):
        raise ValueError('Unknown operation')
    failed = False
    phase = 'Sign-in'
    code_box_open = False

    # Show code entry before the notification HTTP request finishes. The request
    # happens once; the actual code submission still waits for the user's reply.
    from icp.auth.gsa import GSAClient
    original_trigger = GSAClient.trigger_trusted_factor

    def trigger(gsa, *args, **kwargs):
        nonlocal phase, code_box_open
        phase = 'Sending device approval'
        code_box_open = True
        emit('prompt', kind='code', label='Approve sign-in on your iPhone',
             description='Tap Allow on your trusted Apple device, then enter its six-digit code here. This window will wait for you.')
        return original_trigger(gsa, *args, **kwargs)

    GSAClient.trigger_trusted_factor = trigger

    def error(message):
        nonlocal failed
        failed = True
        emit('error', text=phase + ': ' + friendly_error(message))

    def ask(label):
        nonlocal phase, code_box_open
        if 'Apple ID' in label:
            return prompt('email', 'Apple Account')
        if 'code' in label.lower():
            phase = 'Verifying your device code'
            if code_box_open:
                code_box_open = False
                return read_reply()
            return prompt('code', 'Verification code')
        raise RuntimeError('Unsupported sign-in prompt')

    def secret(label):
        recovery = 'passcode' in label.lower() or 'security code' in label.lower()
        value = prompt('passcode' if recovery else 'password',
                       'Device passcode' if recovery else 'Apple Account password')
        if recovery and value:
            emit('recovery', active=True)
        return value

    def choose(bottles):
        value = prompt('device', 'Choose your trusted device',
                       choices=[app._describe_bottle(b) for b in bottles])
        try:
            index = int(value)
        except (ValueError, TypeError):
            return None
        return bottles[index] if 0 <= index < len(bottles) else None

    ui.ask, ui.secret = ask, secret
    ui.step = progress
    ui.out = lambda message='': None  # no CLI status dumps or password output
    ui.warn = lambda message: emit('warning', text=friendly_error(message))
    ui.err = error
    ui.confirm_yn = lambda _: prompt('confirm', 'Allow one keychain recovery attempt?') == 'yes'
    app._select_bottle = choose  # always explicitly choose, including a single device
    if action == 'load':
        snapshot()
        return 0
    if action in ('login', 'sync'):
        emit('progress', text='Starting the local authentication helper…')
        result = subprocess.run(['systemctl', '--user', 'start', 'mseries-icloud-anisette.service'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if result.returncode:
            raise RuntimeError('Local authentication helper could not start')
    if action == 'login':
        import secretstorage
        collection = secretstorage.get_default_collection(secretstorage.dbus_init())
        if collection.is_locked():
            raise RuntimeError('Unlock GNOME Keyring before signing in')
    argv = [action]
    if action == 'login' and '--remember-password' not in sys.argv[2:]:
        argv.append('--no-save-password')
    try:
        result = app.main(argv)
    except Exception as exc:
        error(exc)
        result = 1
    if result == 0 and not failed:
        if action == 'logout':
            from icp import paths
            paths.vault_file().unlink(missing_ok=True)
            paths.aliases_file().unlink(missing_ok=True)
        snapshot()
    emit('done', ok=result == 0 and not failed)
    return result


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        emit('done', ok=False, cancelled=True)
        sys.exit(130)
    except Exception as exc:
        emit('error', text=friendly_error(exc))
        emit('done', ok=False)
        sys.exit(1)
