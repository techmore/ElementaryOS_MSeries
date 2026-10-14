#!/usr/bin/env python3
"""Keep one GitHub issue containing unacknowledged public upstream changes."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
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
    snapshots = dict(previous.get('snapshots', {}))
    pending = {} if acknowledged else dict(previous.get('pending', {}))
    for key, current in observations.items():
        old = snapshots.get(key)
        if old is not None and old != current:
            pending[key] = {'from': pending.get(key, {}).get('from', old), 'to': current}
        snapshots[key] = current
    return {'snapshots': snapshots, 'pending': pending, 'errors': errors}


def render(state):
    lines = [MARKER, '# Public upstream watch', '',
             'Checks every six hours. Close this issue to acknowledge the listed observations. '
             'New changes reopen this same issue. Review licenses, hardware applicability and diffs before importing.', '',
             'This watcher does not merge, deploy, change build pins, or qualify hardware.', '',
             '## Changes awaiting review', '']
    for key, change in sorted(state['pending'].items()):
        lines += [f'- **{key}**', '  - Before: `' + json.dumps(change['from'], sort_keys=True) + '`',
                  '  - Now: `' + json.dumps(change['to'], sort_keys=True) + '`']
    if not state['pending']:
        lines += ['No unacknowledged changes. Initial observations establish a baseline.']
    lines += ['', '## Fetch failures', ''] + (['- ' + e for e in state['errors']] or ['None.'])
    lines += ['', f"Tracking {len(state['snapshots'])} successfully observed sources.", '',
              '<!-- mseries-watch-state\n' + json.dumps(state, sort_keys=True) + '\n-->']
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
        previous = json.loads(match.group(1))
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
    if not issue:
        previous = {'snapshots': {e['repo']: dict(observations[e['repo']], sha=e['observed_revision'])
                                  for e in refs if e['repo'] in observations}}
    state = reconcile(previous, observations, errors, bool(issue and issue['state'] == 'closed'))
    body = render(state)
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
