#!/usr/bin/env python3
"""Per-module timing and an opt-in, dependency-aware parallel runner (#47).

Used by mseries/enhance-firstboot.sh. It never installs anything itself: it runs
the commands it is given, so a test can hand it fake modules.

  modrun.py run --graph GRAPH.json [--only a,b,c] [--jobs N | --serial]
                [--cmd 'bash script {name}'] [--timing-log F] [--summary-json F]
                [--fail-fast] [--no-replay]
  modrun.py summarize --timing-log F [--summary-json F]
  modrun.py check --graph GRAPH.json [--only a,b,c]

GRAPH.json describes the tasks (modules). Per task:
  deps   tasks that must finish OK first; a failed or skipped dependency makes
         the task "skipped" and it never runs
  locks  named mutexes held for the whole task; two tasks that share a lock never
         overlap (apt/dpkg holders share "apt"; see mseries/enhance-modules.json)
  cmd    argv list; --cmd supplies a template (with {name}) for tasks without one
  why    free text: the reason for the deps and locks, kept next to them

Behaviour:
  * bounded workers: at most --jobs tasks run at once; --serial or --jobs 1 runs
    one at a time in declared order (dependencies first)
  * failure propagation: a failed task skips its dependents; independent tasks
    still run (best effort, like the first-boot job) unless --fail-fast, which
    starts nothing new after the first failure
  * deterministic logs: each task's output is captured and replayed in declared
    order, never interleaved, whatever order the tasks finish in
  * timing: every task appends one JSON line (start, end, wall and CPU seconds)
    to --timing-log; the run ends with a table sorted by wall time, a one-line
    summary, and optionally a JSON document (--summary-json)

A task may exit with status 77 to say it does not apply on this machine (the
first-boot job uses this for a module that is a final "not applicable"): it is
recorded as "not-applicable", is not a failure, and its dependents still run.

Exit status: 0 when every task is ok or not applicable, 1 when any failed or was
skipped, 2 for a bad graph or arguments.
"""
import argparse
import json
import os
import queue
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time


NOT_APPLICABLE_RC = 77


class GraphError(Exception):
    pass


def load_graph(path, only=None):
    """Return (order, tasks): selected task names in declared order and their specs."""
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    raw = data.get('tasks')
    if not isinstance(raw, dict) or not raw:
        raise GraphError(f'{path}: "tasks" must be a non-empty object')
    names = list(raw)
    if only is None:
        order = names
    else:
        unknown = [n for n in only if n not in raw]
        if unknown:
            raise GraphError('unknown task(s): ' + ', '.join(unknown))
        order = list(dict.fromkeys(only))
    tasks = {}
    for name in order:
        spec = raw[name] or {}
        deps = list(spec.get('deps', []))
        for dep in deps:
            if dep not in raw:
                raise GraphError(f'{name}: dependency {dep!r} is not a task in the graph')
        tasks[name] = {
            # Dependencies on tasks outside the selection are already satisfied
            # (they finished on an earlier boot or were skipped on purpose).
            'deps': [d for d in deps if d in order],
            'locks': sorted(set(spec.get('locks', []))),
            'cmd': spec.get('cmd'),
            'why': spec.get('why', ''),
        }
    _reject_cycles(order, tasks)
    return order, tasks


def _reject_cycles(order, tasks):
    state = {}

    def visit(name, path):
        if state.get(name) == 'done':
            return
        if state.get(name) == 'open':
            raise GraphError('dependency cycle: ' + ' -> '.join(path + [name]))
        state[name] = 'open'
        for dep in tasks[name]['deps']:
            visit(dep, path + [name])
        state[name] = 'done'

    for name in order:
        visit(name, [])


class Runner:
    def __init__(self, order, tasks, jobs, template=None, fail_fast=False, out=None, timing_log=None, replay=True):
        self.order = order
        self.tasks = tasks
        self.jobs = max(1, jobs)
        self.template = template
        self.fail_fast = fail_fast
        self.out = out or sys.stdout
        self.timing_log = timing_log
        self.replay = replay
        self.results = {}          # name -> record
        self.outputs = {}          # name -> path of the captured output
        self.emitted = 0           # how many tasks of `order` have been replayed
        self.peak = 0
        self._done = queue.Queue()
        self._tmp = tempfile.mkdtemp(prefix='modrun.')

    # -- running one task -------------------------------------------------
    def argv(self, name):
        cmd = self.tasks[name]['cmd']
        if cmd:
            return [str(a).replace('{name}', name) for a in cmd]
        if self.template:
            return [a.replace('{name}', name) for a in shlex.split(self.template)]
        raise GraphError(f'{name}: no cmd in the graph and no --cmd template')

    def _work(self, name):
        path = os.path.join(self._tmp, name + '.out')
        self.outputs[name] = path
        start_wall, start = time.time(), time.monotonic()
        user = system = 0.0
        try:
            with open(path, 'wb') as fh:
                try:
                    proc = subprocess.Popen(self.argv(name), stdin=subprocess.DEVNULL,
                                            stdout=fh, stderr=subprocess.STDOUT)
                except OSError as exc:
                    fh.write(f'modrun: cannot run {name}: {exc}\n'.encode())
                    rc = 127
                else:
                    # wait4 (not Popen.wait) so the child's CPU time comes with it.
                    _, status, usage = os.wait4(proc.pid, 0)
                    rc = os.waitstatus_to_exitcode(status)
                    user, system = usage.ru_utime, usage.ru_stime
        except Exception as exc:  # never lose a task to a runner bug
            with open(path, 'ab') as fh:
                fh.write(f'modrun: internal error for {name}: {exc}\n'.encode())
            rc = 1
        end = time.monotonic()
        record = {
            'name': name,
            'status': 'ok' if rc == 0 else 'not-applicable' if rc == NOT_APPLICABLE_RC else 'failed',
            'rc': rc,
            'start': round(start_wall, 3),
            'end': round(start_wall + (end - start), 3),
            'wall_s': round(end - start, 3),
            'cpu_user_s': round(user, 3),
            'cpu_sys_s': round(system, 3),
        }
        self._done.put(record)

    # -- scheduling -------------------------------------------------------
    def _blocked_by(self, name):
        for dep in self.tasks[name]['deps']:
            if self.results.get(dep, {}).get('status') in ('failed', 'skipped'):
                return dep
        return None

    def _record_skip(self, name, reason):
        now = time.time()
        self.results[name] = {
            'name': name, 'status': 'skipped', 'rc': None, 'start': round(now, 3), 'end': round(now, 3),
            'wall_s': 0.0, 'cpu_user_s': 0.0, 'cpu_sys_s': 0.0, 'reason': reason,
        }
        self.outputs[name] = None
        self._log_record(self.results[name])

    def _log_record(self, record):
        if not self.timing_log:
            return
        with open(self.timing_log, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(record, sort_keys=True) + '\n')

    def _emit_ready(self):
        """Replay finished tasks in declared order, stopping at the first unfinished one."""
        while self.emitted < len(self.order):
            name = self.order[self.emitted]
            record = self.results.get(name)
            if record is None:
                return
            if not self.replay:
                self.emitted += 1
                continue
            print(f'==> {name}', file=self.out)
            if record['status'] == 'skipped':
                print(f'    skipped: {record["reason"]}', file=self.out)
            else:
                with open(self.outputs[name], 'rb') as fh:
                    text = fh.read().decode('utf-8', 'replace')
                if text:
                    self.out.write(text if text.endswith('\n') else text + '\n')
            suffix = '' if record['status'] in ('ok', 'not-applicable') else f' (rc={record["rc"]})' if record['rc'] is not None else ''
            print(f'<== {name}: {record["status"]}{suffix}', file=self.out)
            self.out.flush()
            self.emitted += 1

    def run(self):
        try:
            return self._run()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    def _run(self):
        pending = list(self.order)
        running = {}               # name -> locks held
        held = set()
        failed_once = False
        started = time.monotonic()
        while pending or running:
            progressed = False
            for name in list(pending):
                blocker = self._blocked_by(name)
                if blocker:
                    pending.remove(name)
                    self._record_skip(name, f'dependency {blocker} did not succeed')
                    progressed = True
                elif failed_once and self.fail_fast:
                    pending.remove(name)
                    self._record_skip(name, 'an earlier task failed (--fail-fast)')
                    progressed = True
            for name in list(pending):
                if len(running) >= self.jobs:
                    break
                task = self.tasks[name]
                if any(self.results.get(d, {}).get('status') not in ('ok', 'not-applicable') for d in task['deps']):
                    continue                      # a dependency is still running or queued
                if held.intersection(task['locks']):
                    continue                      # a lock holder is running; later tasks may go first
                pending.remove(name)
                running[name] = task['locks']
                held.update(task['locks'])
                self.peak = max(self.peak, len(running))
                threading.Thread(target=self._work, args=(name,), daemon=True).start()
                progressed = True
            if running:
                record = self._done.get()
                name = record['name']
                held.difference_update(running.pop(name))
                self.results[name] = record
                self._log_record(record)
                failed_once = failed_once or record['status'] == 'failed'
            elif pending and not progressed:
                raise GraphError('nothing can start: ' + ', '.join(pending))
            self._emit_ready()
        self._emit_ready()
        self.wall = time.monotonic() - started
        return self.results


# -- summaries ------------------------------------------------------------
def summarize(records, wall=None, jobs=None, peak=None, mode=None):
    """records: list of per-task dicts. Returns the summary document."""
    by_name = {}
    for rec in records:
        by_name[rec['name']] = rec         # a later line for the same task wins
    tasks = sorted(by_name.values(), key=lambda r: (-r['wall_s'], r['name']))
    counts = {s: sum(1 for r in tasks if r['status'] == s) for s in ('ok', 'failed', 'skipped', 'not-applicable')}
    busy = round(sum(r['wall_s'] for r in tasks), 3)
    if wall is None:   # recorded timestamps: first start to last end
        ran = [r for r in tasks if r['status'] != 'skipped']
        wall = (max(r['end'] for r in ran) - min(r['start'] for r in ran)) if ran else 0.0
    cpu = round(sum(r['cpu_user_s'] + r['cpu_sys_s'] for r in tasks), 3)
    return {
        'mode': mode,
        'jobs': jobs,
        'peak_concurrency': peak,
        'tasks_total': len(tasks),
        'ok': counts['ok'], 'failed': counts['failed'], 'skipped': counts['skipped'],
        'not_applicable': counts['not-applicable'],
        'wall_s': round(wall, 3),
        'cpu_s': cpu,
        'sum_task_wall_s': busy,
        'speedup_vs_sum': round(busy / wall, 2) if wall > 0 else None,
        'tasks': tasks,
    }


def human_table(doc):
    lines = [f'{"module":<20} {"status":<8} {"wall s":>8} {"cpu s":>8}']
    for r in doc['tasks']:
        lines.append(f'{r["name"]:<20} {r["status"]:<8} {r["wall_s"]:>8.1f} {r["cpu_user_s"] + r["cpu_sys_s"]:>8.1f}')
    return '\n'.join(lines)


def human_line(doc):
    slow = next((r for r in doc['tasks'] if r['status'] != 'skipped'), None)
    parts = [f'{doc["tasks_total"]} modules', f'ok={doc["ok"]}', f'failed={doc["failed"]}',
             f'skipped={doc["skipped"]}', f'n/a={doc["not_applicable"]}', f'wall={doc["wall_s"]:.1f}s', f'cpu={doc["cpu_s"]:.1f}s']
    if doc.get('mode'):
        parts.append(f'mode={doc["mode"]}')
        if doc['mode'] == 'parallel':
            parts.append(f'jobs={doc["jobs"]} peak={doc["peak_concurrency"]}')
    if doc['speedup_vs_sum']:
        parts.append(f'sum-of-modules={doc["sum_task_wall_s"]:.1f}s ({doc["speedup_vs_sum"]}x)')
    if slow:
        parts.append(f'slowest={slow["name"]} {slow["wall_s"]:.1f}s')
    return 'timing: ' + ' '.join(parts)


def report(doc, summary_json, out):
    print(human_table(doc), file=out)
    print(human_line(doc), file=out)
    if summary_json:
        tmp = summary_json + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write('\n')
        os.replace(tmp, summary_json)


def read_timing_log(path):
    records = []
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# -- command line ---------------------------------------------------------
def split_only(text):
    return [n for n in text.split(',') if n] if text else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    run = sub.add_parser('run')
    run.add_argument('--graph', required=True)
    run.add_argument('--only')
    run.add_argument('--jobs', type=int, default=1)
    run.add_argument('--serial', action='store_true', help='one task at a time, whatever --jobs says')
    run.add_argument('--cmd', dest='template', help='argv template for tasks without cmd; {name} is the task')
    run.add_argument('--timing-log')
    run.add_argument('--summary-json')
    run.add_argument('--fail-fast', action='store_true')
    run.add_argument('--no-replay', action='store_true',
                     help="do not replay the tasks' output; print only the summary")
    summ = sub.add_parser('summarize')
    summ.add_argument('--timing-log', required=True)
    summ.add_argument('--summary-json')
    summ.add_argument('--mode', help='label for the summary, e.g. serial')
    chk = sub.add_parser('check')
    chk.add_argument('--graph', required=True)
    chk.add_argument('--only')
    args = ap.parse_args(argv)

    try:
        if args.cmd == 'summarize':
            records = read_timing_log(args.timing_log)
            if not records:
                print('timing: nothing was run', file=sys.stdout)
                return 0
            report(summarize(records, mode=args.mode), args.summary_json, sys.stdout)
            return 0
        order, tasks = load_graph(args.graph, split_only(args.only))
        if args.cmd == 'check':
            for name in order:
                t = tasks[name]
                print(f'{name}: deps={",".join(t["deps"]) or "-"} locks={",".join(t["locks"]) or "-"}')
            return 0
        jobs = 1 if args.serial else args.jobs
        runner = Runner(order, tasks, jobs, args.template, args.fail_fast, sys.stdout, args.timing_log,
                        replay=not args.no_replay)
        results = runner.run()
        mode = 'parallel' if jobs > 1 else 'serial'
        doc = summarize([results[n] for n in order], wall=runner.wall, jobs=jobs, peak=runner.peak, mode=mode)
        report(doc, args.summary_json, sys.stdout)
        return 0 if doc['failed'] == 0 and doc['skipped'] == 0 else 1
    except (GraphError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'modrun: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
