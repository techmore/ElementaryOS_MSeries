#!/usr/bin/env python3
"""Tests for mseries/modrun.py and the first-boot module graph (#47).

Everything here runs fake modules (sleep, echo, a short CPU loop) in a temporary
directory: no apt, no network, no install script, nothing outside the temp dir.
Timing assertions compare recorded start/end times of tasks that each sleep long
enough to overlap, so they do not depend on how fast the machine is.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODRUN = os.path.join(HERE, 'modrun.py')
GRAPH = os.path.join(HERE, 'enhance-modules.json')
SLEEP = 0.4


def read(path):
    with open(path) as fh:
        return fh.read()


def load(path):
    return json.loads(read(path))


def sleeper(seconds=SLEEP, text=None, rc=0):
    code = f'import time; time.sleep({seconds}); '
    if text is not None:
        code += f'print({text!r}); '
    code += f'raise SystemExit({rc})'
    return [sys.executable, '-c', code]


class Run:
    """One invocation of `modrun.py run` on a fake graph."""

    def __init__(self, tasks, *args, only=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        graph = os.path.join(self.dir, 'graph.json')
        with open(graph, 'w') as fh:
            json.dump({'tasks': tasks}, fh)
        self.timing = os.path.join(self.dir, 'timing.jsonl')
        self.summary = os.path.join(self.dir, 'summary.json')
        cmd = [sys.executable, MODRUN, 'run', '--graph', graph, '--timing-log', self.timing,
               '--summary-json', self.summary, *args]
        if only:
            cmd += ['--only', ','.join(only)]
        self.proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.out = self.proc.stdout
        self.rc = self.proc.returncode
        self.records = {}
        if os.path.exists(self.timing):
            with open(self.timing) as fh:
                for line in fh:
                    rec = json.loads(line)
                    self.records[rec['name']] = rec
        self.doc = load(self.summary) if os.path.exists(self.summary) else None

    def cleanup(self):
        self.tmp.cleanup()

    def overlap(self, a, b):
        ra, rb = self.records[a], self.records[b]
        return ra['start'] < rb['end'] and rb['start'] < ra['end']


class Base(unittest.TestCase):
    def run_graph(self, tasks, *args, only=None):
        r = Run(tasks, *args, only=only)
        self.addCleanup(r.cleanup)
        return r


class SerialTests(Base):
    def test_serial_runs_one_at_a_time_in_declared_order(self):
        r = self.run_graph({n: {'cmd': sleeper(0.15)} for n in 'abc'}, '--serial', '--jobs', '8')
        self.assertEqual(r.rc, 0, r.proc.stderr)
        self.assertEqual(r.doc['mode'], 'serial')
        self.assertEqual(r.doc['peak_concurrency'], 1)
        starts = sorted(r.records, key=lambda n: r.records[n]['start'])
        self.assertEqual(starts, ['a', 'b', 'c'])
        self.assertFalse(r.overlap('a', 'b') or r.overlap('b', 'c'))

    def test_jobs_one_is_serial_even_without_the_flag(self):
        r = self.run_graph({n: {'cmd': sleeper(0.1)} for n in 'ab'}, '--jobs', '1')
        self.assertEqual(r.doc['mode'], 'serial')
        self.assertFalse(r.overlap('a', 'b'))

    def test_serial_honours_dependencies_over_declared_order(self):
        r = self.run_graph({'late': {'cmd': sleeper(0.1), 'deps': ['early']}, 'early': {'cmd': sleeper(0.1)}},
                           '--serial')
        self.assertLessEqual(r.records['early']['end'], r.records['late']['start'])


class ParallelTests(Base):
    def test_independent_tasks_overlap(self):
        r = self.run_graph({n: {'cmd': sleeper()} for n in 'abcd'}, '--jobs', '4')
        self.assertEqual(r.rc, 0, r.proc.stderr)
        self.assertEqual(r.doc['mode'], 'parallel')
        self.assertEqual(r.doc['peak_concurrency'], 4)
        self.assertTrue(r.overlap('a', 'd'))
        # four 0.4 s tasks at once: well under the 1.6 s they would take one by one
        self.assertLess(r.doc['wall_s'], 1.2)
        self.assertGreater(r.doc['speedup_vs_sum'], 1.5)

    def test_workers_are_bounded(self):
        r = self.run_graph({n: {'cmd': sleeper(0.3)} for n in 'abcdef'}, '--jobs', '2')
        self.assertEqual(r.doc['peak_concurrency'], 2)
        # never more than two intervals cover any task's start
        for n in r.records:
            live = [m for m in r.records if r.records[m]['start'] <= r.records[n]['start'] < r.records[m]['end']]
            self.assertLessEqual(len(live), 2, live)

    def test_tasks_sharing_a_lock_never_overlap(self):
        tasks = {
            'apt1': {'cmd': sleeper(0.3), 'locks': ['apt']},
            'apt2': {'cmd': sleeper(0.3), 'locks': ['apt']},
            'apt3': {'cmd': sleeper(0.3), 'locks': ['apt']},
            'free': {'cmd': sleeper(0.3)},
        }
        r = self.run_graph(tasks, '--jobs', '4')
        for a, b in (('apt1', 'apt2'), ('apt2', 'apt3'), ('apt1', 'apt3')):
            self.assertFalse(r.overlap(a, b), (a, b))
        # the lock does not hold up work that does not need it
        self.assertTrue(r.overlap('apt1', 'free'))

    def test_a_blocked_task_does_not_hold_up_later_ones(self):
        tasks = {
            'one': {'cmd': sleeper(0.4), 'locks': ['x']},
            'two': {'cmd': sleeper(0.1), 'locks': ['x']},
            'three': {'cmd': sleeper(0.1)},
        }
        r = self.run_graph(tasks, '--jobs', '4')
        self.assertLess(r.records['three']['start'], r.records['two']['start'])

    def test_dependent_starts_after_its_dependency_ends(self):
        tasks = {'base': {'cmd': sleeper(0.3)}, 'top': {'cmd': sleeper(0.1), 'deps': ['base']},
                 'side': {'cmd': sleeper(0.3)}}
        r = self.run_graph(tasks, '--jobs', '4')
        self.assertLessEqual(r.records['base']['end'], r.records['top']['start'])
        self.assertTrue(r.overlap('base', 'side'))

    def test_dependency_outside_the_selection_counts_as_satisfied(self):
        tasks = {'base': {'cmd': sleeper(0.1)}, 'top': {'cmd': sleeper(0.1), 'deps': ['base']}}
        r = self.run_graph(tasks, '--jobs', '2', only=['top'])
        self.assertEqual(r.rc, 0, r.proc.stderr)
        self.assertEqual(list(r.records), ['top'])


class FailureTests(Base):
    def tasks(self):
        return {
            'bad': {'cmd': sleeper(0.1, text='boom', rc=3)},
            'child': {'cmd': sleeper(0.1), 'deps': ['bad']},
            'grandchild': {'cmd': sleeper(0.1), 'deps': ['child']},
            'other': {'cmd': sleeper(0.3)},
        }

    def test_failure_skips_dependents_and_spares_independent_tasks(self):
        r = self.run_graph(self.tasks(), '--jobs', '4')
        self.assertEqual(r.rc, 1)
        self.assertEqual({n: r.records[n]['status'] for n in r.records},
                         {'bad': 'failed', 'child': 'skipped', 'grandchild': 'skipped', 'other': 'ok'})
        self.assertEqual(r.records['bad']['rc'], 3)
        self.assertEqual((r.doc['ok'], r.doc['failed'], r.doc['skipped']), (1, 1, 2))
        self.assertIn('dependency bad did not succeed', r.out)

    def test_fail_fast_starts_nothing_new(self):
        tasks = {'bad': {'cmd': sleeper(0.1, rc=1)}, 'later': {'cmd': sleeper(0.1)}}
        r = self.run_graph(tasks, '--serial', '--fail-fast')
        self.assertEqual(r.records['later']['status'], 'skipped')
        self.assertIn('--fail-fast', r.out)

    def test_missing_command_is_a_failure_not_a_crash(self):
        r = self.run_graph({'ghost': {'cmd': ['/nonexistent/module']}, 'ok': {'cmd': sleeper(0.05)}}, '--jobs', '2')
        self.assertEqual(r.records['ghost']['status'], 'failed')
        self.assertEqual(r.records['ghost']['rc'], 127)
        self.assertEqual(r.records['ok']['status'], 'ok')


class LogOrderTests(Base):
    def tasks(self):
        # finishing order is the reverse of declared order
        return {
            'first': {'cmd': sleeper(0.5, text='output of first')},
            'second': {'cmd': sleeper(0.25, text='output of second')},
            'third': {'cmd': sleeper(0.05, text='output of third')},
        }

    def test_output_is_replayed_in_declared_order_not_finish_order(self):
        r = self.run_graph(self.tasks(), '--jobs', '3')
        positions = [r.out.index(f'output of {n}') for n in ('first', 'second', 'third')]
        self.assertEqual(positions, sorted(positions))
        finished = sorted(r.records, key=lambda n: r.records[n]['end'])
        self.assertEqual(finished, ['third', 'second', 'first'])   # the test really ran out of order

    def test_replay_is_identical_between_runs_and_modes(self):
        parallel = [self.run_graph(self.tasks(), '--jobs', '3').out.split('timing:')[0] for _ in range(2)]
        serial = self.run_graph(self.tasks(), '--serial').out.split('timing:')[0]
        self.assertEqual(parallel[0].split('module ')[0], parallel[1].split('module ')[0])
        self.assertEqual(parallel[0].split('module ')[0], serial.split('module ')[0])

    def test_no_replay_prints_only_the_summary(self):
        r = self.run_graph(self.tasks(), '--jobs', '3', '--no-replay')
        self.assertNotIn('output of first', r.out)
        self.assertIn('timing: 3 modules', r.out)


class TimingTests(Base):
    def test_every_task_is_recorded_with_start_end_wall_and_cpu(self):
        burn = [sys.executable, '-c', 'import time; t=time.process_time()\nwhile time.process_time()-t<0.3: pass']
        r = self.run_graph({'burn': {'cmd': burn}, 'idle': {'cmd': sleeper(0.3)}}, '--jobs', '2')
        for name in ('burn', 'idle'):
            rec = r.records[name]
            for key in ('start', 'end', 'wall_s', 'cpu_user_s', 'cpu_sys_s', 'status', 'rc'):
                self.assertIn(key, rec)
            self.assertGreaterEqual(rec['end'] - rec['start'], rec['wall_s'] - 0.01)
            self.assertGreaterEqual(rec['wall_s'], 0.25)
        self.assertGreater(r.records['burn']['cpu_user_s'] + r.records['burn']['cpu_sys_s'], 0.2)
        self.assertLess(r.records['idle']['cpu_user_s'] + r.records['idle']['cpu_sys_s'], 0.2)

    def test_summary_json_and_table_are_sorted_slowest_first(self):
        r = self.run_graph({'quick': {'cmd': sleeper(0.05)}, 'slow': {'cmd': sleeper(0.5)},
                            'middle': {'cmd': sleeper(0.25)}}, '--jobs', '3')
        self.assertEqual([t['name'] for t in r.doc['tasks']], ['slow', 'middle', 'quick'])
        for key in ('wall_s', 'cpu_s', 'sum_task_wall_s', 'speedup_vs_sum', 'jobs', 'peak_concurrency', 'mode'):
            self.assertIn(key, r.doc)
        table = [line.split()[0] for line in r.out.splitlines() if re.match(r'^(quick|slow|middle) ', line)]
        self.assertEqual(table, ['slow', 'middle', 'quick'])
        line = next(line for line in r.out.splitlines() if line.startswith('timing: '))
        self.assertIn('3 modules', line)
        self.assertIn('slowest=slow', line)
        self.assertRegex(line, r'wall=\d+\.\ds cpu=\d+\.\ds')

    def test_summarize_reads_a_log_written_elsewhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, 'timing.jsonl')
            rows = [('a', 'ok', 1.5, 100.0), ('b', 'failed', 4.0, 100.5), ('c', 'ok', 0.5, 101.0)]
            with open(log, 'w') as fh:
                for name, status, wall, start in rows:
                    fh.write(json.dumps({'name': name, 'status': status, 'rc': 0 if status == 'ok' else 1,
                                         'start': start, 'end': start + wall, 'wall_s': wall,
                                         'cpu_user_s': wall / 2, 'cpu_sys_s': 0.0}) + '\n')
            out = os.path.join(tmp, 'summary.json')
            proc = subprocess.run([sys.executable, MODRUN, 'summarize', '--timing-log', log, '--summary-json', out],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            doc = load(out)
            self.assertEqual([t['name'] for t in doc['tasks']], ['b', 'a', 'c'])
            self.assertEqual((doc['ok'], doc['failed']), (2, 1))
            self.assertEqual(doc['cpu_s'], 3.0)
            self.assertAlmostEqual(doc['wall_s'], 4.5, places=3)   # first start to last end
            self.assertIn('slowest=b 4.0s', proc.stdout)


class GraphTests(Base):
    def check(self, tasks, only=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'g.json')
            with open(path, 'w') as fh:
                json.dump({'tasks': tasks}, fh)
            cmd = [sys.executable, MODRUN, 'check', '--graph', path] + (['--only', only] if only else [])
            return subprocess.run(cmd, capture_output=True, text=True)

    def test_cycle_is_rejected(self):
        p = self.check({'a': {'deps': ['b']}, 'b': {'deps': ['a']}})
        self.assertEqual(p.returncode, 2)
        self.assertIn('dependency cycle', p.stderr)

    def test_unknown_dependency_and_task_are_rejected(self):
        self.assertIn('not a task', self.check({'a': {'deps': ['zzz']}}).stderr)
        self.assertIn('unknown task', self.check({'a': {}}, only='nope').stderr)


class ShippedGraphTests(unittest.TestCase):
    """The real first-boot graph, checked against the real scripts (read, never run)."""

    @classmethod
    def setUpClass(cls):
        cls.graph = load(GRAPH)['tasks']
        text = read(os.path.join(HERE, 'enhance-firstboot.sh'))
        cls.default = re.search(r'^DEFAULT=\(([^)]*)\)', text, re.M).group(1).split()
        cls.scripts = dict(re.findall(r'\[([\w-]+)\]=(install-[\w.-]+\.sh)', text))
        cls.deps = set(re.findall(r'^\s+\[([\w-]+)\]="', text, re.M))

    def test_every_module_has_a_node_with_a_reason(self):
        for m in self.default + ['firefox']:
            self.assertIn(m, self.graph, f'{m} is missing from enhance-modules.json')
            self.assertTrue(self.graph[m].get('why', '').strip(), f'{m} has no stated reason')
        self.assertTrue(set(self.graph) <= set(self.default + ['firefox']), 'graph names a module firstboot lacks')

    def test_the_whole_graph_loads_and_is_acyclic(self):
        p = subprocess.run([sys.executable, MODRUN, 'check', '--graph', GRAPH], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_every_apt_holder_carries_the_apt_lock(self):
        """A module whose script runs apt/dpkg itself must share the apt lock with every other one."""
        pattern = re.compile(r'^\s*(sudo\s+)?(apt-get|apt|dpkg)\s+(install|update|remove|upgrade|-i)\b|^\s*mseries_apt_refresh\b', re.M)
        for m, script in self.scripts.items():
            text = read(os.path.join(HERE, script))
            holder = bool(pattern.search(text))
            self.assertEqual('apt' in self.graph[m].get('locks', []), holder,
                             f'{m} ({script}): apt lock {"missing" if holder else "declared but the script runs no apt command"}')
        self.assertIn('apt', self.graph['desktop-user-deps']['locks'])   # no script, but it is only packages

    def test_the_wingpanel_plugin_installers_are_ordered_with_each_other(self):
        for m in ('network', 'quick', 'sound', 'keyboard', 'battery-panel'):
            self.assertIn('wingpanel-plugins', self.graph[m]['locks'], m)

    def test_independent_modules_can_overlap(self):
        free = [m for m, spec in self.graph.items() if not spec.get('locks') and not spec.get('deps')]
        self.assertTrue({'video', 'files', 'osk'} <= set(free), free)


class BenchmarkHarnessTests(unittest.TestCase):
    """The synthetic serial-vs-parallel harness runs on fake modules and says so."""

    def test_harness_compares_serial_and_parallel_on_fake_modules(self):
        bench = os.path.join(HERE, 'benchmarks', 'installer-speed.py')
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'bench.json')
            proc = subprocess.run([sys.executable, bench, '--scale', '0.01', '--repeat', '1', '--what-if', '--out', out],
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            doc = load(out)
        self.assertIs(doc['synthetic'], True)
        self.assertIn('SYNTHETIC', proc.stdout)
        serial, locked, relaxed = doc['rows']
        self.assertEqual(serial['peak_concurrency'], 1)
        self.assertGreater(locked['peak_concurrency'], 1)
        self.assertLess(locked['wall_s_median'], serial['wall_s_median'])
        self.assertGreater(locked['speedup_vs_serial'], 1.3)
        # removing a lock can only help, within noise
        self.assertLessEqual(relaxed['wall_s_median'], locked['wall_s_median'] + 0.3)
        self.assertGreaterEqual(locked['wall_s_median'], doc['lock_graph_lower_bound_s'] * 0.95)


if __name__ == '__main__':
    unittest.main(verbosity=1)
