#!/usr/bin/env python3
"""Keep one GitHub issue containing unacknowledged public upstream changes."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import base64
import gzip
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
MARKER = '<!-- mseries-upstream-dashboard -->'
TITLE = 'Upstream watch: changes awaiting review'


def api(path, method='GET', data=None):
    args = ['gh', 'api', '--method', method, path]
    if data is not None:
        args += ['--input', '-']
    result = subprocess.run(args, input=json.dumps(data) if data is not None else None,
                            text=True, capture_output=True, timeout=60, check=True)
    return json.loads(result.stdout)


def reconcile(previous, observations, errors, acknowledged=False):
    # Older dashboard issues stored the full observation in each snapshot and
    # both ends of every pending change. Keep only the fields used to detect a
    # change, and keep the original value only; the latest value is the current
    # snapshot. This preserves provenance while keeping the issue body bounded.
    snapshots = {key: change_marker(value)
                 for key, value in previous.get('snapshots', {}).items()}
    pending = {}
    if not acknowledged:
        for key, change in previous.get('pending', {}).items():
            # Migrate legacy {from, to} entries without losing the first value.
            pending[key] = (change['from'] if isinstance(change, dict)
                            and 'from' in change and 'to' in change else change)
    for key, current in observations.items():
        current = change_marker(current)
        old = snapshots.get(key)
        if old is not None and old != current:
            pending.setdefault(key, change_marker(old))
        snapshots[key] = current
    return {'snapshots': snapshots, 'pending': pending, 'errors': errors}


def change_marker(value):
    """Keep enough change evidence without duplicating long metadata in the issue state."""
    if not isinstance(value, dict):
        return value
    fields = ('sha', 'base_sha', 'branch', 'release', 'sha256', 'count', 'latest', 'pushed', 'ahead', 'behind', 'status')
    return {k: value[k] for k in fields if k in value}


def encode_state(state):
    raw = json.dumps(state, sort_keys=True, separators=(',', ':')).encode()
    return {'encoding': 'gzip+base64', 'data': base64.b64encode(gzip.compress(raw, mtime=0)).decode()}


def decode_state(value):
    if value.get('encoding') != 'gzip+base64':
        return value  # Migrate the earlier plain-JSON dashboard without losing acknowledgments.
    import zlib
    packed = base64.b64decode(value['data'], validate=True)
    raw = zlib.decompressobj(31).decompress(packed, 2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Dashboard state exceeds the bounded decoder')
    return json.loads(raw)


def render(state):
    lines = [MARKER, '# Public upstream watch', '',
             'Checks every six hours. Close this issue to acknowledge the listed observations. '
             'New changes reopen this same issue. Review licenses, hardware applicability and diffs before importing.', '',
             'This watcher does not merge, deploy, change build pins, or qualify hardware.', '',
             '## Changes awaiting review', '']
    for key, before in sorted(state['pending'].items())[:20]:
        lines += [f'- **{key}**', '  - Before: `' + json.dumps(before, sort_keys=True) + '`',
                  '  - Now: `' + json.dumps(state['snapshots'].get(key), sort_keys=True) + '`']
    if not state['pending']:
        lines += ['No unacknowledged changes. Initial observations establish a baseline.']
    elif len(state['pending']) > 20:
        lines += [f"{len(state['pending']) - 20} additional changes are retained in the dashboard state. Closing acknowledges all {len(state['pending'])} changes."]
    lines += ['', '## Fetch failures', ''] + (['- ' + e for e in state['errors']] or ['None.'])
    lines += ['', f"Tracking {len(state['snapshots'])} successfully observed sources.", '',
              '<!-- mseries-watch-state\n' + json.dumps(encode_state(state), sort_keys=True) + '\n-->']
    return '\n'.join(lines)


def main():
    repository = os.environ['GITHUB_REPOSITORY']
    spec = importlib.util.spec_from_file_location('people_watch', HERE / 'people-watch.py')
    watch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(watch)
    entries = json.loads((HERE / 'people-watch.json').read_text())
    refs = json.loads((HERE.parent / 'upstreams/omarchy-m.json').read_text())['projects']
    branches = {e['repo']: e['branch'] for e in refs}
    known = {e.get('repo') for e in entries}
    entries += [e for e in refs if e['repo'] not in known]
    # Include closed issues so acknowledgment never creates a duplicate dashboard.
    issues = []
    page = 1
    while True:
        batch = api(f'repos/{repository}/issues?state=all&per_page=100&page={page}')
        issues += batch
        if len(batch) < 100:
            break
        page += 1
    issue = next((i for i in issues if 'pull_request' not in i and i.get('title') == TITLE
                  and i.get('user', {}).get('login') in {'github-actions[bot]', repository.split('/')[0]} and MARKER in (i.get('body') or '')), None)
    previous = {}
    if issue:
        match = re.search(r'<!-- mseries-watch-state\n(.*?)\n-->', issue['body'], re.S)
        if not match:
            raise RuntimeError('Dashboard state missing; refusing to discard observations')
        previous = decode_state(json.loads(match.group(1)))
    observations, errors = {}, []
    for entry in entries:
        key = entry.get('repo') or '@' + entry['user']
        try:
            if 'repo' in entry:
                info = watch.get('/repos/' + key)
                if not info or info.get('private'):
                    raise RuntimeError('public repository unavailable')
                branch = branches.get(key, info['default_branch'])
                tip = watch.get('/repos/' + key + '/commits/' + quote(branch, safe=''))
                if not tip:
                    raise RuntimeError('tracked branch unavailable')
                release = watch.get('/repos/' + key + '/releases/latest')
                observations[key] = {'branch': branch, 'sha': tip['sha'],
                                     'release': release['tag_name'] if release else None}
            else:
                repos = watch.get('/users/' + entry['user'] + '/repos?sort=pushed&per_page=1')
                if repos is None:
                    raise RuntimeError('public user unavailable')
                observations[key] = {'latest': repos[0]['full_name'], 'pushed': repos[0]['pushed_at']} if repos else {'latest': None, 'pushed': None}
        except Exception as error:
            errors.append(f'{key}: {type(error).__name__}: {error}')
    branch_spec = importlib.util.spec_from_file_location('branch_watch', HERE / 'branch-watch.py')
    branch_watch = importlib.util.module_from_spec(branch_spec)
    branch_spec.loader.exec_module(branch_watch)
    raw_heads = {}
    branch_observations, branch_errors = branch_watch.collect(
        watch.get, json.loads((HERE / 'branch-watch.json').read_text())['sources'], raw_heads)
    Path('mseries-upstream-branch-heads.json').write_text(json.dumps(raw_heads, indent=2) + '\n')
    observations.update(branch_observations)
    errors.extend(branch_errors)
    if not issue:
        previous = {'snapshots': {e['repo']: dict(observations[e['repo']], sha=e['observed_revision'])
                                  for e in refs if e['repo'] in observations}}
    state = reconcile(previous, observations, errors, bool(issue and issue['state'] == 'closed'))
    body = render(state)
    if len(body) > 65000:
        raise ValueError('Dashboard exceeds GitHub issue size; observations retained in the workflow artifact, refusing to discard state')
    if not issue:
        issue = api(f'repos/{repository}/issues', 'POST', {'title': TITLE, 'body': body})
    elif body != issue['body'] or (issue['state'] == 'closed' and (state['pending'] or errors)):
        data = {'body': body}
        if state['pending'] or errors:
            data['state'] = 'open'
        issue = api(f"repos/{repository}/issues/{issue['number']}", 'PATCH', data)
    print(issue['html_url'])
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
