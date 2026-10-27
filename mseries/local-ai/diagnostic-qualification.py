#!/usr/bin/python3
"""Fixed synthetic diagnosis qualification; never starts a model or reads journals.

The owner queue supplies the admitted dedicated model and metadata. This program
only calls the production generate() function, one case at a time. A completed
failure is immutable; only incomplete/interrupted cases can resume with identical
metadata, kernel, source and fixture hashes. Automatic passes still need semantic
review. Use --plan (the default) without any inference or output-file writes.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from diagnostic_contract import validate_bundle, evaluate_case, DiagnosticContractError

SCHEMA = 'mseries.diagnostic.qualification.v1'
MODEL_REPO = 'mlx-community/Qwen3.5-9B-MLX-4bit'
MODEL_REVISION = '938d8919941c6e7efd3c7150eff7fe9d12afa631'
SOURCES = ('diagnostic_contract.py', 'diagnostic_agent.py', 'diagnostic_runtime.py',
           'diagnostic-qualification.py', 'machine.py', 'model-worker.py', 'runtime_recovery.py')
FROZEN_MODULES = tuple(Path(name).stem for name in SOURCES if Path(name).stem.isidentifier())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def public(value):
    """Only public/synthetic metadata enters a publishable qualification receipt."""
    if isinstance(value, str):
        return value.replace(str(Path.home()), '<HOME>')
    if isinstance(value, list):
        return [public(v) for v in value]
    if isinstance(value, dict):
        return {key: public(v) for key, v in value.items()}
    return value


def metadata(path):
    if path.stat().st_size > 128*1024:
        raise ValueError('Qualification metadata is oversized')
    result = json.loads(path.read_text())
    if not isinstance(result, dict):
        raise ValueError('Qualification metadata must be an object')
    required = {'model_repo', 'model_revision', 'kernel', 'policy',
                'profile_sha256', 'worker_sha256', 'runtime_sha256'}
    if not required <= set(result):
        raise ValueError('Metadata needs model_repo/model_revision/kernel/policy and profile/worker/runtime SHA256')
    if result['model_repo'] != MODEL_REPO or result['model_revision'] != MODEL_REVISION:
        raise ValueError('This cohort excludes the failed4B and requires the pinned9B')
    if result['kernel'] != os.uname().release:
        raise ValueError('Kernel differs from the qualification metadata')
    for name in ('profile_sha256', 'worker_sha256', 'runtime_sha256'):
        if not isinstance(result[name], str) or not re.fullmatch(r'[0-9a-f]{64}', result[name]):
            raise ValueError('Qualification metadata has malformed source/runtime hashes')
    policy = result['policy']
    if (not isinstance(policy, dict) or any(type(policy.get(k)) not in (int, float)
        for k in ['reserve_gib', 'max_fan_rpm', 'max_temp_c'])
        or policy['reserve_gib'] < 6 or not 0 < policy['max_fan_rpm'] <= 2700
        or not 0 < policy['max_temp_c'] <= 63):
        raise ValueError('Qualification policy must preserve6GiB and bounded2700RPM/63C limits')
    # Avoid accidentally publishing credentials supplied in a metadata file.
    def bounded(value, depth=0):
        if depth > 5:
            raise ValueError('Qualification metadata nesting is oversized')
        if isinstance(value, dict):
            if len(value) > 128:
                raise ValueError('Qualification metadata map is oversized')
            for key, item in value.items():
                if not isinstance(key, str) or len(key) > 200 or re.search(r'(^|_)(?:password|secret|authorization|credential|api_key)(_|$)', key, re.I):
                    raise ValueError('Private/unsupported qualification metadata key')
                bounded(item, depth+1)
        elif isinstance(value, list):
            if len(value) > 128:
                raise ValueError('Qualification metadata list is oversized')
            for item in value: bounded(item, depth+1)
        elif isinstance(value, str):
            if len(value) > 2000: raise ValueError('Qualification metadata string is oversized')
        elif value is not None and type(value) not in (int, float, bool):
            raise ValueError('Qualification metadata value is unsupported')
    bounded(result)
    digest(result)  # Reject NaN/infinity as non-JSON identity data.
    return result


def read_cases(split, *, source=None, validator=None):
    cases = []
    source = HERE if source is None else source
    validator = validate_bundle if validator is None else validator
    for path in sorted((source/'fixtures/diagnostic').glob('*.json')):
        raw = path.read_bytes()
        case = json.loads(raw)
        if case.get('fixture_schema_version') != 'mseries.diagnostic.fixture.v1':
            raise ValueError('Unsupported diagnostic fixture version')
        if split != 'all' and case['split'] != split:
            continue
        validator(case['bundle'])
        if case['case_id'] != case['bundle']['bundle_id'] or not case['expectations']['manual_review']:
            raise ValueError('Fixture identity or independent semantic rubric missing')
        cases.append((case, hashlib.sha256(raw).hexdigest(), raw))
    if not cases or len({c[0]['case_id'] for c in cases}) != len(cases):
        raise ValueError('Diagnostic fixtures absent or repeated')
    return cases


def verify_frozen(directory, source_hashes, fixture_hashes):
    """Bind the exact copied bytes and reject unrecorded import/cache payloads."""
    expected = dict(source_hashes)
    expected.update({'fixtures/diagnostic/' + name + '.json': value
                     for name, value in fixture_hashes.items()})
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Frozen production source/fixture integrity differs; preserve receipt')
    actual = set()
    for path in directory.rglob('*'):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError('Frozen production source/fixture integrity differs; preserve receipt')
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(expected):
        raise ValueError('Frozen production source/fixture file set differs; preserve receipt')
    for name, value in expected.items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest() != value:
            raise ValueError('Frozen production source/fixture integrity differs; preserve receipt')


def checkpoint(path, report):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Refusing a linked qualification receipt')
    fd, temporary = tempfile.mkstemp(prefix='.diagnostic-receipt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def import_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def isolated_frozen_imports():
    """Keep frozen-source module selection and cancellation local to this run.

    A caller can already hold references to the live runtime module. Removing
    it from sys.modules permanently would make later dynamic imports resolve a
    second object and silently bypass caller/test patches. Machine helpers must
    also be imported from the frozen source rather than an existing live cache.
    """
    absent = object()
    previous_modules = {name: sys.modules.get(name, absent) for name in FROZEN_MODULES}
    previous_path = list(sys.path)
    previous_bytecode = sys.dont_write_bytecode
    previous_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        sys.dont_write_bytecode = True
        yield
    finally:
        sys.path[:] = previous_path
        sys.dont_write_bytecode = previous_bytecode
        for name, module in previous_modules.items():
            if module is absent:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        for sig, handler in previous_handlers.items():
            if signal.getsignal(sig) is not handler:
                signal.signal(sig, handler)


def resource_summary(samples, policy):
    if not samples:
        return {'samples': 0, 'quiet_policy_passed': False}
    return {'samples': len(samples),
        'min_available_bytes': min(s['available_bytes'] for s in samples),
        'max_fan_rpm': max(max(s['fans_rpm'].values(), default=9999) for s in samples),
        'max_temp_c': max(max(s['temperatures_c'].values(), default=999) for s in samples),
        'quiet_policy_passed': all(not resource_reasons(s, policy) for s in samples)}


def resource_reasons(sample, policy):
    reasons = []
    if sample['available_bytes'] < policy['reserve_gib']*1024**3:
        reasons.append('desktop reserve')
    if not sample['fans_rpm'] or max(sample['fans_rpm'].values()) >= policy['max_fan_rpm']:
        reasons.append('fan guard')
    if not sample['temperatures_c'] or max(sample['temperatures_c'].values()) >= policy['max_temp_c']:
        reasons.append('temperature guard')
    return reasons


@isolated_frozen_imports()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--run', action='store_true', help='Root-owned admitted queue only; one real request per incomplete case')
    action.add_argument('--plan', action='store_true')
    parser.add_argument('--metadata-file', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--endpoint', default='http://127.0.0.1:8772')
    parser.add_argument('--repeat', type=int, choices=range(1, 4), default=1)
    parser.add_argument('--split', choices=['core', 'heldout', 'all'], default='core')
    args = parser.parse_args()
    cases = read_cases(args.split)
    if not args.run:
        print(json.dumps({'cases': [c[0]['case_id'] for c in cases], 'repeat': args.repeat,
            'inference_requested': False, 'semantic_review_required': True}, indent=2))
        return
    if not args.metadata_file or not args.output:
        parser.error('--run requires --metadata-file and --output')
    supplied = metadata(args.metadata_file)
    # Hash and copy the same captured bytes. A live edit between two separate
    # reads must never give a cohort one identity and different evaluated code.
    source_bytes = {name: (HERE/name).read_bytes() for name in SOURCES}
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in source_bytes.items()}
    identity = {'metadata_sha256': digest(supplied), 'kernel': os.uname().release,
        'source_sha256': hashes, 'fixtures_sha256': {c[0]['case_id']: c[1] for c in cases},
        'repeat': args.repeat, 'split': args.split, 'endpoint': args.endpoint}
    path = args.output.resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix+'.lock')
    with lock_path.open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('This qualification receipt already has an owned worker') from None
        frozen = path.with_suffix('.evaluated-source')
        if path.exists():
            report = json.loads(path.read_text())
            if report.get('schema_version') != SCHEMA or report.get('identity') != identity:
                raise ValueError('Resume metadata/kernel/policy/runtime/source/fixtures differ; preserved original receipt')
            if report.get('complete'):
                print(json.dumps({'complete': True, 'requests_repeated': 0, 'qualified': False,
                    'automatic_passes': report.get('automatic_passes'), 'semantic_review_required': True}))
                return
            verify_frozen(frozen, hashes, identity['fixtures_sha256'])
        else:
            if frozen.exists():
                raise ValueError('Orphan frozen source exists; inspect it before creating a cohort')
            frozen.mkdir(mode=0o700)
            (frozen/'fixtures/diagnostic').mkdir(parents=True)
            for name, raw in source_bytes.items():
                (frozen/name).write_bytes(raw)
            for case, _, raw in cases:
                (frozen/'fixtures/diagnostic'/(case['case_id']+'.json')).write_bytes(raw)
            # Verify the actual copy before recording a cohort or importing code.
            # Failed copies remain as an inspectable orphan, never a valid run.
            verify_frozen(frozen, hashes, identity['fixtures_sha256'])
            report = {'schema_version': SCHEMA, 'identity': identity, 'metadata': public(supplied),
                'complete': False, 'qualified': False, 'manual_review_required': True,
                'scope': 'Fixed synthetic evidence through frozen production generate(); no real journals, private app contents or repair execution',
                'inference_owner': 'Externally admitted dedicated diagnostic service; this harness never starts/stops models',
                'microphone_recorded': False, 'windows_opened': False, 'trials': []}
            checkpoint(path, report)
        def save_report():
            try:
                verify_frozen(frozen, hashes, identity['fixtures_sha256'])
            except (ValueError, OSError):
                # Retain completed answers/failures if disk integrity changes
                # during an owned request. This is never a qualified checkpoint.
                report['frozen_integrity_error'] = True
                report['qualified'] = False
                checkpoint(path, report)
                raise
            checkpoint(path, report)
        # Import only frozen production logic. No request injection seam exists
        # on this CLI; generate() must perform its real model identity check.
        sys.path.insert(0, str(frozen))
        for name in FROZEN_MODULES:
            sys.modules.pop(name, None)
        contract = import_source('diagnostic_contract_qualified', frozen/'diagnostic_contract.py')
        sys.modules['diagnostic_contract'] = contract
        cases = read_cases(args.split, source=frozen, validator=contract.validate_bundle)
        if {case['case_id']: value for case, value, _ in cases} != identity['fixtures_sha256']:
            raise ValueError('Frozen fixture identity differs; preserve receipt')
        agent = import_source('diagnostic_agent_qualified', frozen/'diagnostic_agent.py')
        machine = import_source('diagnostic_machine_qualified', frozen/'machine.py')
        def cancelled(*_): raise InterruptedError('Owned qualification interrupted')
        signal.signal(signal.SIGTERM, cancelled)
        signal.signal(signal.SIGINT, cancelled)
        for case, _, _ in cases:
            for repeat in range(args.repeat):
                key = (case['case_id'], repeat)
                trial = next((t for t in report['trials'] if (t['case_id'], t['repeat']) == key), None)
                if trial and trial['status'] == 'completed':
                    continue  # Includes completed format/semantic-gate failures.
                sample = machine.snapshot()
                reasons = resource_reasons(sample, supplied['policy'])
                if reasons or max(sample['temperatures_c'].values(), default=999) >= 60:
                    report['waiting_for_quiet_admission'] = True
                    save_report()
                    print(json.dumps({'deferred': True, 'incomplete_case': case['case_id'], 'quiet_guard': True}))
                    raise SystemExit(75)
                report.pop('waiting_for_quiet_admission', None)
                if trial is None:
                    trial = {'case_id': key[0], 'repeat': key[1], 'status': 'pending', 'attempts': []}
                    report['trials'].append(trial)
                if trial['status'] == 'running' and trial['attempts']:
                    trial['attempts'][-1].update(status='interrupted', quality_scored=False,
                        interruption='Previous process ended before completion checkpoint')
                attempt = {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'running',
                           'quality_scored': False}
                trial['attempts'].append(attempt)
                trial['status'] = 'running'
                save_report()
                samples = [sample]
                telemetry_errors = []
                stop_sampling = threading.Event()
                def observe():
                    while not stop_sampling.wait(1):
                        try: samples.append(machine.snapshot())
                        except (OSError, ValueError) as error:
                            telemetry_errors.append(type(error).__name__)
                            break
                monitor = threading.Thread(target=observe, daemon=True)
                monitor.start()
                try:
                    verify_frozen(frozen, hashes, identity['fixtures_sha256'])
                    result = agent.generate(case['bundle'], endpoint=args.endpoint)
                    if not isinstance(result, dict) or not isinstance(result.get('raw_answer'), str):
                        raise ValueError('Production generate() result malformed')
                    if not isinstance(result.get('model'), str) or not result['model'].endswith('/'+MODEL_REVISION):
                        raise ValueError('Completed result does not identify the pinned9B revision')
                    attempt['generation'] = public(result)
                    attempt['quality_scored'] = True
                    attempt['status'] = 'completed'
                    if result.get('contract_error') or result.get('response') is None:
                        attempt['evaluation'] = {'automatic_pass': False, 'checks': {'response_contract': False},
                                                 'manual_review_required': True}
                    else:
                        attempt['evaluation'] = contract.evaluate_case(result['response'], case)
                    trial['status'] = 'completed'
                    trial['automatic_pass'] = attempt['evaluation']['automatic_pass']
                except (Exception, KeyboardInterrupt) as error:
                    attempt.update(status='interrupted', quality_scored=False, failure_kind=type(error).__name__)
                    trial['status'] = 'interrupted'
                    report['interruption_scope'] = 'No completed answer available; unscored. Resume only this incomplete case with identical identity.'
                    raise
                finally:
                    stop_sampling.set()
                    monitor.join(2)
                    attempt['resources'] = resource_summary(samples, supplied['policy'])
                    attempt['resources']['telemetry_complete'] = not telemetry_errors
                    if telemetry_errors:
                        attempt['resources']['quiet_policy_passed'] = False
                    save_report()
        report['complete'] = len([t for t in report['trials'] if t['status'] == 'completed']) == len(cases)*args.repeat
        report['automatic_passes'] = sum(t.get('automatic_pass', False) for t in report['trials'])
        report['completed_trials'] = sum(t['status'] == 'completed' for t in report['trials'])
        report['quiet_policy_passed'] = all(t['attempts'][-1]['resources']['quiet_policy_passed'] for t in report['trials'] if t['status'] == 'completed')
        report['qualified'] = False  # Independent semantic review is a required separate decision.
        save_report()
        print(json.dumps({'complete': report['complete'], 'automatic_passes': report['automatic_passes'],
            'completed_trials': report['completed_trials'], 'quiet_policy_passed': report['quiet_policy_passed'],
            'qualified': False, 'semantic_review_required': True}))


if __name__ == '__main__':
    main()
