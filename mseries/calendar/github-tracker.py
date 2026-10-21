#!/usr/bin/env python3
"""Read-only, bounded GitHub outcome snapshot. Uses the user's existing gh login."""
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

DEFAULTS = [
    {'repo': 'techmore/rupert', 'issue': 207, 'title': 'Rupert deployment ready'},
    {'repo': 'techmore/tm-daedalus', 'issue': 17, 'title': 'Daedalus deployment ready'},
]
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'mseries/github-tracker.json'
CACHE = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'mseries/github-tracker.json'
CHECKS = '''statusCheckRollup { contexts(first:100) { pageInfo { hasNextPage } nodes {
    __typename ... on CheckRun { name status conclusion } ... on StatusContext { context state }
} } }'''
QUERY = '''query($owner:String!, $name:String!, $issue:Int!) {
 repository(owner:$owner, name:$name) {
  issue(number:$issue) { title url state stateReason
   milestone { title url state }
   subIssues(first:100) { pageInfo { hasNextPage } nodes { title number url state stateReason } }
  }
  defaultBranchRef { name target { ... on Commit { oid CHECKS } } }
  pullRequests(first:10, states:OPEN, orderBy:{field:UPDATED_AT,direction:DESC}) {
   pageInfo { hasNextPage } nodes { title number url headRefOid headRefName
    closingIssuesReferences(first:100) { pageInfo { hasNextPage } nodes { number repository { nameWithOwner } } }
    commits(last:1) { nodes { commit { oid CHECKS } } }
   }
  }
 }
}'''.replace('CHECKS', CHECKS)


def targets():
    if not CONFIG.exists():
        return DEFAULTS
    config = json.loads(CONFIG.read_text())
    if not isinstance(config, dict) or config.get('version') != 1:
        raise ValueError('Unsupported tracking configuration')
    rows = config['targets']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise ValueError('Choose between one and twenty outcomes')
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Expected a tracking object')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', row['repo']):
            raise ValueError('Expected owner/repository')
        if type(row['issue']) is not int or row['issue'] <= 0:
            raise ValueError('Expected a positive tracking issue number')
        if not isinstance(row.get('title'), str) or not 1 <= len(row['title']) <= 200:
            raise ValueError('Expected an outcome title')
        key = (row['repo'], row['issue'])
        if key in seen:
            raise ValueError('Duplicate tracking issue')
        seen.add(key)
    return rows


def ci(commit):
    connection = ((commit or {}).get('statusCheckRollup') or {}).get('contexts') or {}
    rows = connection.get('nodes') or []
    states = []
    for row in rows:
        if row['__typename'] == 'CheckRun':
            states.append(row.get('conclusion') if row.get('status') == 'COMPLETED' else 'PENDING')
        else:
            states.append(row.get('state'))
    if any(s in {'FAILURE', 'ERROR', 'TIMED_OUT', 'ACTION_REQUIRED', 'STARTUP_FAILURE'} for s in states):
        return 'failing'
    if 'PENDING' in states or 'EXPECTED' in states:
        return 'pending'
    if not states or connection.get('pageInfo', {}).get('hasNextPage'):
        return 'unknown'
    if all(s == 'SUCCESS' for s in states):
        return 'passing'
    return 'incomplete'  # skipped, neutral and cancelled never imply success


def collect(target, api=None):
    owner, name = target['repo'].split('/')
    if api is None:
        result = subprocess.run(['gh', 'api', '--hostname', 'github.com', 'graphql', '-f', 'query=' + QUERY,
                                 '-f', 'owner=' + owner, '-f', 'name=' + name,
                                 '-F', 'issue=' + str(target['issue'])],
                                capture_output=True, text=True, timeout=40, check=True)
        data = json.loads(result.stdout)
    else:
        data = api(target)
    if data.get('errors'):
        raise ValueError('GitHub could not return complete tracking data')
    repo = data['data']['repository']
    outcome = repo['issue']
    if not outcome:
        raise ValueError('Tracking issue unavailable')
    connection = outcome['subIssues']
    gates = connection['nodes']
    complete = [g for g in gates if g['state'] == 'CLOSED' and g.get('stateReason') == 'COMPLETED']
    remaining = [g for g in gates if g not in complete]
    branch = repo.get('defaultBranchRef') or {}
    commit = branch.get('target') or {}
    related, other = [], 0
    scope = {target['issue'], *(g['number'] for g in gates)}
    for pr in repo['pullRequests']['nodes']:
        refs = pr['closingIssuesReferences']
        if not any(i['number'] in scope and i['repository']['nameWithOwner'] == target['repo'] for i in refs['nodes']):
            other += 1
            continue
        nodes = pr['commits']['nodes']
        tip = nodes[-1]['commit'] if nodes else {}
        related.append({'title': pr['title'], 'url': pr['url'], 'number': pr['number'],
                        'sha': pr['headRefOid'],
                        'ci': ci(tip) if tip.get('oid') == pr['headRefOid'] else 'unknown'})
    truncated = connection['pageInfo']['hasNextPage']
    done = bool(gates) and not remaining and not truncated and outcome['state'] == 'CLOSED' and outcome.get('stateReason') == 'COMPLETED'
    return {**target, 'url': outcome['url'], 'milestone': outcome.get('milestone'),
            'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'error': None,
            'completed': len(complete), 'total': len(gates), 'truncated': truncated,
            'done': done, 'gates': gates, 'next': remaining[0]['title'] if remaining else 'Review release and acceptance evidence',
            'branch': branch.get('name', 'unknown'), 'sha': commit.get('oid', ''), 'ci': ci(commit),
            'prs': related, 'other_prs': other, 'prs_truncated': repo['pullRequests']['pageInfo']['hasNextPage']}


def refresh(rows, previous, collector=collect):
    cached = previous.get('outcomes', []) if isinstance(previous, dict) else []
    old = {(r.get('repo'), r.get('issue')): r for r in cached if isinstance(r, dict)} if isinstance(cached, list) else {}
    def one(target):
        try:
            return collector(target)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            # Preserve dated evidence; do not leak gh stderr or credentials to the panel.
            return {**old.get((target['repo'], target['issue']), {}), **target,
                    'error': 'Refresh unavailable. Check network and gh auth status.'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        return {'version': 1, 'outcomes': list(pool.map(one, rows))}


def main():
    try:
        rows = targets()
        try:
            previous = json.loads(CACHE.read_text())
        except (OSError, ValueError):
            previous = {}
        snapshot = refresh(rows, previous)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix='.github-tracker-', dir=CACHE.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(snapshot, stream)
            os.replace(filename, CACHE)
        finally:
            if os.path.exists(filename):
                os.unlink(filename)
        print(json.dumps(snapshot))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'version': 1, 'error': 'Could not load tracking configuration or write cache.', 'outcomes': []}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
