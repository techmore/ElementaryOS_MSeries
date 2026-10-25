"""Local Calendar writes, managed-browser reads and unsent Mail drafts."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import quote, urlencode, urlsplit
import urllib.request
import uuid


def retry_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{7,79}', value):
        raise ValueError('request_id must be a stable 8–80 character ASCII retry label')
    return value


def line(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Expected bounded, nonempty single-line text')
    return value


def body_text(value, maximum=8000):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 and c not in '\n\t' for c in value) or '\x7f' in value:
        raise ValueError('Invalid or oversized body/details')
    return value


@contextmanager
def locked(directory, name):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / name, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def load_json(path, maximum=65536):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as handle:
        text = handle.read(maximum + 1)
    if len(text) > maximum: raise ValueError('Metadata exceeds its limit')
    return json.loads(text)


def private_create(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle: handle.write(data)


def calendar_uid(state, create=False):
    marker = state / 'calendar-source.json'
    if marker.is_symlink(): raise ValueError('Calendar ownership marker must not be a link')
    if not marker.exists():
        if not create: return None
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        value = {'schema': 1, 'source_uid': 'mseries-assistant-calendar-' + str(uuid.uuid4())}
        temporary = state / ('.calendar-' + str(uuid.uuid4()))
        try:
            private_create(temporary, json.dumps(value).encode())
            os.replace(temporary, marker)
        finally: temporary.unlink(missing_ok=True)
    value = load_json(marker)
    uid = value.get('source_uid') if isinstance(value, dict) else None
    if not isinstance(value, dict) or value.get('schema') != 1 or not isinstance(uid, str) or not re.fullmatch(
            r'mseries-assistant-calendar-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', uid):
        raise ValueError('Invalid Assistant Calendar ownership marker')
    return uid


def calendar_source(source, extension):
    if source is None or source.get_parent() != 'local-stub' or not source.has_extension(extension) or source.get_extension(extension).get_backend_name() != 'local':
        raise ValueError('Assistant Calendar must remain a local calendar')


def event_time(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})', value):
        raise ValueError('Use RFC3339 date/time with seconds and explicit UTC offset or Z')
    if value.endswith('-00:00') or (not value.endswith('Z') and int(value[-2:]) > 59):
        raise ValueError('Use a known UTC offset with valid minutes')
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def create_event(state, args):
    title = line(args['title'], 240); key = retry_id(args['request_id'])
    details = body_text(args.get('details', ''), 4000)
    start, end = event_time(args['start']), event_time(args['end'])
    if not timedelta(0) < end - start <= timedelta(days=366):
        raise ValueError('Event end must follow start by no more than 366 days')
    import gi
    gi.require_version('EDataServer', '1.2'); gi.require_version('ECal', '2.0'); gi.require_version('ICalGLib', '3.0')
    from gi.repository import EDataServer, ECal, ICalGLib, GLib
    with locked(state, 'calendar.lock'):
        source_uid = calendar_uid(state, True)
        registry = EDataServer.SourceRegistry.new_sync(None)
        extension = EDataServer.SOURCE_EXTENSION_CALENDAR
        source = registry.ref_source(source_uid)
        if source is None:
            source = EDataServer.Source.new_with_uid(source_uid, None)
            source.set_display_name('Assistant Calendar'); source.set_parent('local-stub')
            source.get_extension(extension).set_backend_name('local')
            registry.commit_source_sync(source, None); source = registry.ref_source(source_uid)
        calendar_source(source, extension)
        client = ECal.Client.connect_sync(source, ECal.ClientSourceType.EVENTS, 5, None)
        uid = str(uuid.uuid5(uuid.UUID(source_uid.removeprefix('mseries-assistant-calendar-')), key))
        stamp = lambda dt: dt.strftime('%Y%m%dT%H%M%SZ')
        existing = None
        try:
            ok, existing = client.get_object_sync(uid, None, None)
            if not ok: raise ValueError('Event lookup failed')
        except GLib.Error as error:
            if not error.matches(ECal.Client.error_quark(), ECal.ClientError.OBJECT_NOT_FOUND): raise
        if existing is not None:
            a, b = existing.get_dtstart(), existing.get_dtend()
            if existing.get_summary() != title or (existing.get_description() or '') != details or not a or not b or a.as_ical_string() != stamp(start) or b.as_ical_string() != stamp(end):
                raise ValueError('request_id already belongs to different event data; existing event unchanged')
        else:
            component = ICalGLib.Component.new(ICalGLib.ComponentKind.VEVENT_COMPONENT)
            component.set_uid(uid); component.set_summary(title); component.set_description(details)
            component.set_dtstart(ICalGLib.Time.new_from_string(stamp(start)))
            component.set_dtend(ICalGLib.Time.new_from_string(stamp(end)))
            component.set_dtstamp(ICalGLib.Time.new_from_timet_with_zone(int(time.time()), False, ICalGLib.Timezone.get_utc_timezone()))
            ok, actual_uid = client.create_object_sync(component, ECal.OperationFlags.NONE, None)
            if not ok or actual_uid != uid: raise ValueError('Local backend did not confirm the event UID')
        return {'created': existing is None, 'uid': uid, 'calendar': source.get_display_name(), 'title': title,
                'start': start.isoformat().replace('+00:00', 'Z'), 'end': end.isoformat().replace('+00:00', 'Z'),
                'scope': 'local Assistant Calendar only; no attendees/invitations'}


def proc_ticks(pid):
    return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19]


def browser_endpoint(state):
    metadata = load_json(state / 'browser-session.json')
    if not isinstance(metadata, dict): raise ValueError('Invalid managed browser metadata')
    profile = state.resolve() / 'browser-profile'
    pid, port = metadata.get('pid'), metadata.get('port')
    if type(pid) is not int or pid <= 0 or type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Invalid managed browser metadata')
    if profile.is_symlink() or proc_ticks(pid) != metadata.get('start_ticks'):
        raise ValueError('Managed browser is no longer running')
    cmdline = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
    if ('--user-data-dir=' + str(profile)).encode() not in cmdline:
        raise ValueError('Browser PID does not belong to the Assistant profile')
    active = (profile / 'DevToolsActivePort').read_text().splitlines()
    if not active or active[0] != str(port): raise ValueError('Managed browser port changed')
    return 'http://127.0.0.1:' + str(port), port


def browser_targets(state):
    endpoint, port = browser_endpoint(state)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(endpoint + '/json/list', timeout=3) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024: raise ValueError('Browser target list exceeds its limit')
    rows = json.loads(raw)
    return [r for r in rows if r.get('type') == 'page' and re.fullmatch(r'[A-Za-z0-9_-]{16,80}', r.get('id', '')) and
            urlsplit(r.get('url', '')).scheme in ('http', 'https', 'about')][:20], port


def browser_tabs(state):
    try: targets, _ = browser_targets(state)
    except (OSError, ValueError): return {'available': False, 'tabs': [], 'scope': 'Open Assistant Browser to share pages with the local assistant'}
    return {'available': True, 'tabs': [{'id': r['id'], 'title': r.get('title', '')[:240], 'url': r.get('url', '')[:2048]} for r in targets],
            'scope': 'managed Assistant Browser profile only; up to 20 tabs'}


def browser_read(state, tab_id):
    targets, port = browser_targets(state)
    target = next((r for r in targets if r['id'] == tab_id), None)
    if target is None: raise ValueError('Tab is not in the managed Assistant Browser')
    from websockets.sync.client import connect
    with connect(f'ws://127.0.0.1:{port}/devtools/page/{tab_id}', proxy=None, open_timeout=3, close_timeout=1, max_size=1024 * 1024) as ws:
        sequence = 0
        def command(method, params=None):
            nonlocal sequence
            sequence += 1; ws.send(json.dumps({'id': sequence, 'method': method, 'params': params or {}}))
            for _ in range(100):
                result = json.loads(ws.recv(timeout=3))
                if result.get('id') == sequence:
                    if 'error' in result: raise ValueError('Browser read failed')
                    return result['result']
            raise ValueError('Browser event limit exceeded')
        frame = command('Page.getFrameTree')['frameTree']['frame']['id']
        context = command('Page.createIsolatedWorld', {'frameId': frame, 'worldName': 'MSeries page reader'})['executionContextId']
        # Fixed read expression. No JavaScript, URL or CDP method is accepted from the model.
        result = command('Runtime.evaluate', {'contextId': context, 'expression':
            'JSON.stringify({title:document.title.slice(0,240),url:location.href.slice(0,2048),text:(document.body?document.body.innerText:"").slice(0,12000)})',
            'returnByValue': True, 'timeout': 1000})
        if 'exceptionDetails' in result: raise ValueError('Page text unavailable')
        value = json.loads(result['result']['value'])
        return value | {'tab_id': tab_id, 'scope': 'untrusted page data; managed browser only', 'text_limit': 12000}


def start_browser(state, url='about:blank', headless=False):
    if url != 'about:blank' and urlsplit(url).scheme not in ('http', 'https'):
        raise ValueError('Assistant Browser opens only HTTP(S) URLs or about:blank')
    state = state.resolve(); state.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile = state / 'browser-profile'
    if profile.is_symlink(): raise ValueError('Assistant Browser profile must not be a symlink')
    profile.mkdir(exist_ok=True, mode=0o700)
    binary = shutil.which('brave-browser')
    if binary is None: raise ValueError('Native Brave is required for Assistant Browser')
    try: browser_endpoint(state)
    except (OSError, ValueError): pass
    else:
        if headless: raise ValueError('An Assistant Browser is already running')
        subprocess.run([binary, '--user-data-dir=' + str(profile), url], check=True)
        return None
    (profile / 'DevToolsActivePort').unlink(missing_ok=True)
    command = [binary, '--user-data-dir=' + str(profile), '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1', '--no-first-run']
    if headless:
        command += ['--headless=new', '--disable-gpu', '--disable-background-networking', '--disable-component-update',
                    '--disable-extensions', '--disable-sync', '--renderer-process-limit=1']
    log = (state / 'browser.log').open('ab')
    child = subprocess.Popen(command + [url], stdout=log, stderr=log, start_new_session=True)
    log.close()
    try:
        for _ in range(100):
            if child.poll() is not None: raise ValueError('Assistant Browser exited; inspect its private log')
            portfile = profile / 'DevToolsActivePort'
            if portfile.exists():
                port = int(portfile.read_text().splitlines()[0])
                metadata = {'pid': child.pid, 'start_ticks': proc_ticks(child.pid), 'port': port}
                temporary = state / ('.browser-' + str(uuid.uuid4()))
                private_create(temporary, json.dumps(metadata).encode()); os.replace(temporary, state / 'browser-session.json')
                browser_endpoint(state)
                return child
            time.sleep(.1)
        raise TimeoutError('Assistant Browser did not become ready')
    except BaseException:
        child.terminate(); child.wait(timeout=10)
        raise


def drafts_dir(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = root / 'Mail Drafts'
    if directory.is_symlink(): raise ValueError('Mail Drafts must not be a link')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not directory.resolve().is_relative_to(root.resolve()): raise ValueError('Draft folder leaves workspace')
    return directory


def draft_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value):
        raise ValueError('Use a draft_id returned by create_mail_draft')
    return value


def mailto(value):
    return 'mailto:' + quote(value['to'], safe='@') + '?' + urlencode(
        {'subject': value['subject'], 'body': value['body'].replace('\n', '\r\n')}, quote_via=quote)


def elementary_mailto(value):
    # Mail 8's Application decodes GUri, then Composer decodes each field again.
    # Keep reserved characters encoded across that first decode. Used only with Mail.
    uri = mailto(value)
    path, query = uri.removeprefix('mailto:').split('?', 1)
    return 'mailto:' + quote(path, safe='@') + '?' + quote(query, safe='=&')


def draft_payload(args):
    address = line(args['to'], 254)
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", address):
        raise ValueError('Use one plain ASCII email address, without display names, CC or BCC')
    local, domain = address.split('@')
    if local.startswith('.') or local.endswith('.') or '..' in local or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in domain.split('.')):
        raise ValueError('Invalid email address')
    return {'to': address, 'subject': line(args['subject'], 240), 'body': body_text(args['body'])}


def create_draft(root, args):
    key = retry_id(args['request_id'])
    payload = draft_payload(args); address = payload['to']
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, str(root.resolve()) + ':mail:' + key))
    directory = drafts_dir(root)
    with locked(directory, '.drafts.lock'):
        marker, eml = directory / (identifier + '.json'), directory / (identifier + '.eml')
        if marker.exists() or marker.is_symlink():
            previous = read_draft(root, identifier)
            if any(previous[k] != v for k, v in payload.items()):
                raise ValueError('request_id belongs to different draft data; existing draft unchanged')
            return {'created': False, 'draft_id': identifier, 'path': 'Mail Drafts/' + eml.name, 'status': 'local unsent review draft', 'review_app': 'Assistant Mail Drafts'}
        message = EmailMessage(policy=policy.SMTP)
        message['To'] = address; message['Subject'] = payload['subject']
        message['Message-ID'] = '<' + identifier + '@assistant.invalid>'
        message.set_content(payload['body'])
        raw = message.as_bytes()
        if eml.exists() or eml.is_symlink():
            fd = os.open(eml, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as handle: old = handle.read(65537)
            parsed = BytesParser(policy=policy.default).parsebytes(old)
            expected_body = payload['body'] if payload['body'].endswith('\n') else payload['body'] + '\n'
            if str(parsed['To']) != address or str(parsed['Subject']) != payload['subject'] or parsed['Message-ID'] != message['Message-ID'] or parsed.get_content().replace('\r\n', '\n') != expected_body:
                raise ValueError('An uncommitted draft exists with different contents; unchanged')
            raw = old
        else: private_create(eml, raw)
        metadata = payload | {'schema': 1, 'draft_id': identifier, 'eml_sha256': hashlib.sha256(raw).hexdigest()}
        private_create(marker, json.dumps(metadata, ensure_ascii=False).encode())
        return {'created': True, 'draft_id': identifier, 'path': 'Mail Drafts/' + eml.name, 'status': 'local unsent review draft', 'review_app': 'Assistant Mail Drafts'}


def read_draft(root, identifier):
    identifier = draft_id(identifier); directory = drafts_dir(root)
    value = load_json(directory / (identifier + '.json'))
    if not isinstance(value, dict) or value.get('schema') != 1 or value.get('draft_id') != identifier:
        raise ValueError('Invalid draft metadata')
    fd = os.open(directory / (identifier + '.eml'), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle: raw = handle.read(65537)
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != value['eml_sha256']:
        raise ValueError('Draft was changed outside the assistant; review it directly')
    payload = draft_payload(value)
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    expected_body = payload['body'] if payload['body'].endswith('\n') else payload['body'] + '\n'
    if str(parsed['To']) != payload['to'] or str(parsed['Subject']) != payload['subject'] or parsed['Message-ID'] != '<' + identifier + '@assistant.invalid>' or parsed.get_content().replace('\r\n', '\n') != expected_body:
        raise ValueError('Draft metadata and message contents differ')
    return {k: value[k] for k in ['draft_id', 'to', 'subject', 'body']} | {'status': 'local unsent review draft'}


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    b = sub.add_parser('browser'); b.add_argument('url', nargs='?', default='about:blank')
    m = sub.add_parser('review-mail'); m.add_argument('draft_id')
    args = p.parse_args()
    state = Path(os.environ.get('MSERIES_MCP_STATE', Path.home() / '.local/state/mseries-os-mcp'))
    root = Path(os.environ.get('MSERIES_ASSISTANT_WORKSPACE', Path.home() / 'Documents/Assistant Workspace')).resolve()
    if args.action == 'review-mail':
        value = read_draft(root, args.draft_id)
        subprocess.run(['/usr/bin/io.elementary.mail', elementary_mailto(value)], check=True)
    else:
        child = start_browser(state, args.url)
        if child is not None:
            try: child.wait()
            except KeyboardInterrupt: child.terminate(); child.wait(timeout=10)
            finally:
                metadata = state / 'browser-session.json'
                if metadata.exists() and load_json(metadata).get('pid') == child.pid: metadata.unlink()


if __name__ == '__main__': main()
