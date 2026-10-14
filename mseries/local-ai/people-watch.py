#!/usr/bin/python3
"""Exit 0 when any watched project or person has pushed or released something since you last acknowledged.

Used as a precondition by mseries-verify. The list lives in people-watch.json (repo or GitHub user, who,
why). Polls GitHub at most every 6 hours (cached; set GITHUB_TOKEN for a higher rate limit). The first run
only records a baseline. `--list` prints what changed, `--ack` accepts the current state as the new baseline.
Read-only: nothing here installs or enables anything.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = HERE / 'people-watch.json'
CACHE = Path.home() / '.cache/mseries-people-watch.json'
BASELINE = Path.home() / '.local/state/mseries-people-watch-baseline.json'
REFRESH = 6 * 3600
API = 'https://api.github.com'


_TOKEN = []


def token_value():
    """GITHUB_TOKEN, else the user's own `gh auth token` (read-only API calls to api.github.com only)."""
    if not _TOKEN:
        token = os.environ.get('GITHUB_TOKEN', '')
        if not token:
            try:
                token = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, timeout=10).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                token = ''
        _TOKEN.append(token)
    return _TOKEN[0]


def get(path):
    headers = {'User-Agent': 'mseries-people-watch', 'Accept': 'application/vnd.github+json'}
    token = token_value()
    if token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def snapshot_entry(entry):
    if 'user' in entry:
        repos = get('/users/%s/repos?sort=pushed&per_page=1' % entry['user']) or []
        if not repos:
            return {'state': 'no public repos', 'pushed': ''}
        return {'state': '%s pushed %s' % (repos[0]['full_name'], repos[0]['pushed_at']), 'pushed': repos[0]['pushed_at'],
                'latest': repos[0]['full_name']}
    info = get('/repos/' + entry['repo'])
    if info is None:
        return {'state': 'repository not found', 'pushed': ''}
    release = get('/repos/%s/releases/latest' % entry['repo']) or {}
    return {'state': 'pushed %s%s%s' % (info['pushed_at'], ', release ' + release['tag_name'] if release else '',
                                        ' (archived)' if info.get('archived') else ''),
            'pushed': info['pushed_at'], 'release': release.get('tag_name', '')}


def fetch(entries, previous=None):
    """Snapshot every entry; one that fails keeps its previous value and is listed in `errors`."""
    data = {'checked': time.time(), 'items': {}, 'errors': []}
    for entry in entries:
        key = entry.get('repo') or '@' + entry['user']
        try:
            item = snapshot_entry(entry)
            if 'repo' in entry and item['pushed']:
                commits = get('/repos/%s/commits?per_page=3' % entry['repo']) or []
                item['recent'] = [c['commit']['message'].splitlines()[0][:90] for c in commits]
            data['items'][key] = item
        except (OSError, ValueError) as error:
            data['errors'].append('%s: %s' % (key, error))
            if previous and key in previous.get('items', {}):
                data['items'][key] = previous['items'][key]
    return data


def load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def main():
    entries = json.loads(LIST.read_text())
    cached = load(CACHE)
    if cached is None or time.time() - cached['checked'] > REFRESH or '--ack' in sys.argv:
        fresh = fetch(entries, cached)
        if fresh['items']:
            cached = fresh
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cached))
        elif cached is None:
            return 1  # offline and nothing cached: not applicable
    errors = cached.get('errors', [])
    if '--ack' in sys.argv and (errors or len(cached['items']) != len(entries)):
        print('not acknowledged: %d entries could not be read (%s)' % (len(errors), errors[0] if errors else 'incomplete'))
        return 2
    baseline = load(BASELINE)
    if baseline is None or '--ack' in sys.argv:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(cached['items']))
        if '--ack' in sys.argv:
            print('baseline updated for %d watched projects' % len(cached['items']))
        baseline = cached['items']
    changes = []
    for entry in entries:
        key = entry.get('repo') or '@' + entry['user']
        now, then = cached['items'].get(key), baseline.get(key)
        if now and then and (now['pushed'] != then['pushed'] or now.get('release') != then.get('release')):
            changes.append('%s (%s): %s\n    %s' % (key, entry['who'], now['state'], '\n    '.join(now.get('recent', []))
                                                  or entry['why']))
    if '--list' in sys.argv:
        if errors:
            print('WARNING: %d of %d entries could not be read this time, e.g. %s' % (len(errors), len(entries), errors[0]))
        print('watching %d projects; last checked %s' % (len(cached['items']), time.strftime('%F %T', time.localtime(cached['checked']))))
        print('\n'.join(changes) or 'no changes since the baseline')
    return 0 if changes else 1


if __name__ == '__main__':
    raise SystemExit(main())
