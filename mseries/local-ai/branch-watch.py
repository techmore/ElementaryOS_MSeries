#!/usr/bin/python3
"""Read-only discovery of selected public branches and open PR heads, including forks."""
import json
import hashlib
from pathlib import Path
from urllib.parse import quote
from urllib.error import HTTPError


def tracked_tip(get, repo, branch):
    """GitHub uses 422, not 404, for a deleted named commit/ref."""
    try:
        return get('/repos/' + repo + '/commits/' + quote(branch, safe=''))
    except HTTPError as error:
        if error.code != 422: raise
        try:
            detail = json.loads(error.read(8193))
        except (ValueError, OSError):
            raise error
        finally:
            error.close()
        if detail.get('message') != 'No commit found for SHA: ' + branch:
            raise error
        return None


def pages(get, path, limit=5):
    result = []
    for page in range(1, limit + 1):
        join = '&' if '?' in path else '?'
        batch = get(f'{path}{join}per_page=100&page={page}')
        if batch is None:
            raise ValueError('Public source unavailable: ' + path)
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise ValueError('Pagination limit reached; refusing an incomplete discovery snapshot: ' + path)


def collect(get, sources, raw_heads=None):
    observations, errors = {}, []
    for source in sources:
        repo, base = source['repo'], source['base']
        base_repo = source.get('base_repo', repo)
        try:
            info = get('/repos/' + repo)
            if not info or info.get('private'):
                raise ValueError('public repository unavailable')
            base_info = get('/repos/' + base_repo + '/commits/' + quote(base, safe=''))
            if not base_info:
                raise ValueError('base branch unavailable')
            candidates = []
            if source.get('discover_branches'):
                branches = pages(get, '/repos/' + repo + '/branches')
                heads = sorted(
                    [{'branch': b['name'], 'sha': b['commit']['sha']} for b in branches],
                    key=lambda b: b['branch'])
                if raw_heads is not None:
                    raw_heads[repo] = heads
                observations['heads:' + repo] = {'count': len(heads),
                    'sha256': hashlib.sha256(json.dumps(heads, sort_keys=True).encode()).hexdigest(),
                    'url': 'https://github.com/' + repo + '/branches',
                    'detail': 'All public branch heads captured in the workflow artifact; digest changes detect unselected experiments.'}
                # Record every public head; named branches and PRs below get
                # detailed comparisons against the immutable base commit.
            for branch in source.get('branches', []):
                tip = tracked_tip(get, repo, branch)
                if not tip:
                    observations['branch:' + repo + ':' + branch] = {
                        'repo': repo, 'branch': branch, 'sha': None, 'status': 'named ref absent',
                        'qualification': 'Previously tracked ref is absent; public branch/PR discovery continues. No merge or hardware qualification inferred.'}
                    continue
                candidates.append({'repo': repo, 'branch': branch, 'sha': tip['sha']})
            if source.get('open_prs'):
                prs = pages(get, '/repos/' + repo + '/pulls?state=open&sort=updated&direction=desc')
                # Record every open head; detailed compare calls are limited to the most active.
                heads = sorted([
                    {'number': pr['number'], 'sha': pr['head']['sha'], 'draft': pr.get('draft', False),
                     'repo': (pr['head'].get('repo') or {}).get('full_name'), 'branch': pr['head']['ref'],
                     'url': pr['html_url']} for pr in prs], key=lambda p: p['number'])
                if raw_heads is not None:
                    raw_heads['prs:' + repo] = heads
                observations['prs:' + repo] = {'count': len(heads),
                    'sha256': hashlib.sha256(json.dumps(heads, sort_keys=True).encode()).hexdigest(),
                    'recent_numbers': [pr['number'] for pr in prs[:10]],
                    'url': 'https://github.com/' + repo + '/pulls',
                    'detail': 'Every open PR head is retained in the workflow artifact.'}
                for pr in prs[:10]:
                    head_repo = (pr['head'].get('repo') or {}).get('full_name')
                    if head_repo:
                        candidates.append({'repo': head_repo, 'branch': pr['head']['ref'], 'sha': pr['head']['sha']})
            seen = set()
            for item in candidates:
                key = item['repo'] + ':' + item['branch']
                if key in seen:
                    continue
                seen.add(key)
                # Use immutable commits so a moving branch cannot change mid-comparison.
                comparison = get('/repos/' + base_repo + '/compare/' + base_info['sha'] + '...' + item['sha'])
                if not comparison:
                    raise ValueError('comparison unavailable: ' + key)
                observations['branch:' + key] = item | {
                    'base_repo': base_repo, 'base': base, 'base_sha': base_info['sha'],
                    'ahead': comparison['ahead_by'], 'behind': comparison['behind_by'],
                    'status': comparison['status'], 'url': comparison['html_url'],
                    'qualification': 'discovered; applicability, patch equivalence and M1 Pro tests required'}
        except Exception as error:
            errors.append(f'{repo}: {type(error).__name__}: {error}')
    return observations, errors


def merge_registered_sources(sources, projects):
    """Use the Elementary Rust project register as the source roster."""
    registered = []
    for project in projects:
        url = project.get('url', '')
        prefix = 'https://github.com/'
        if not url.startswith(prefix):
            raise ValueError(f"Unsupported Elementary project URL: {url!r}")
        repo = url.removeprefix(prefix).strip('/')
        branch = project.get('default_branch')
        if len(repo.split('/')) != 2 or not branch:
            raise ValueError(f"Incomplete Elementary source record: {project.get('id')}")
        registered.append({'repo': repo, 'base': branch,
                           'open_prs': True, 'discover_branches': True})
    repo_names = {source['repo'] for source in registered}
    return [source for source in sources if source['repo'] not in repo_names] + registered


if __name__ == '__main__':
    import importlib.util
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('people_watch', here / 'people-watch.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    raw_heads = {}
    elementary = json.loads((here.parent / 'rust/elementary-projects.json').read_text())['projects']
    sources = merge_registered_sources(
        json.loads((here / 'branch-watch.json').read_text())['sources'], elementary)
    observations, errors = collect(module.get, sources, raw_heads)
    print(json.dumps({'observations': observations, 'branch_heads': raw_heads, 'errors': errors}, indent=2))
    raise SystemExit(bool(errors))
