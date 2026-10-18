#!/usr/bin/python3
"""Read-only verification of the merged English F5 deployment; never activates it.

No receipt or runtime inspection occurs without --verify. Only public source
pins, file hashes, bounded service state and equality booleans enter the receipt.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

WORK = Path(__file__).resolve().parent
DEFAULT_REPO = WORK/'ElementaryOS_MSeries'
HOME = Path.home()
BASE = HOME/'.local/share/mseries/stream'
LIB_SHA = '9f1f839d89a6d3a874c939ecf3108007cc0964a338596a35adb47c7e6c5c921d'
NEMO_SHA = '90d8c89714cd31efc88be62a40c6b2bea57e0cc2063af1ffe2c28f1a228ca110'
DEBUG_KEYS = {'STREAM_KEEP', 'STREAM_DRY', 'STREAM_TEST_WAV', 'STREAM_TEST_RAW',
              'STREAM_TEST_INSERT', 'STREAM_FORCE_FALLBACK', 'MSERIES_INPUT_TEST_SESSION'}


def run(command, *, timeout=20, check=True, cwd=None, binary=False):
    return subprocess.run(command, capture_output=True, text=not binary, timeout=timeout,
                          check=check, cwd=cwd)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def literal(source, name):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Required public source constant is unavailable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--source-ref', help='Exact merged Git commit to verify; required with --verify')
    parser.add_argument('--baseline', type=Path, default=WORK/'f5-deployment-baseline-private.json')
    args = parser.parse_args()
    if not args.verify:
        print('Prepared only. Run --verify --source-ref MERGED_COMMIT after deployment.')
        return
    if not args.source_ref:
        parser.error('--verify requires the exact merged --source-ref')
    output = WORK/'f5-deployment-v1/receipt.json'
    if output.exists():
        raise SystemExit('Receipt already exists; preserve it before a distinct verification attempt.')
    report = {'schema': 1, 'complete': False, 'passed': False,
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'checks': {},
        'method': 'Read-only installed-file and live listener metadata verification against merged Git blobs',
        'microphone_recorded': False, 'inference_requested': False, 'windows_opened': False,
        'services_changed': False, 'settings_changed': False, 'git_changed': False,
        'private_settings_or_contents_exported': False,
        'limits': [
            'No microphone, physical F5, app-window, grammar-model, audio playback or inference test in this receipt.',
            'Ready state proves the idle listener/bridge is available; functional app acceptance uses separate synthetic/public-file receipts.',
            'Optional ANE/MLX availability is static asset/runtime inspection, not a repeated hardware inference qualification.',
            'Settings fingerprints prove equality to the private baseline at inspection time; raw preferences/environment are excluded.'
        ]}
    checks = report['checks']
    def check(name, value):
        checks[name] = bool(value)
    def git(*parts, binary=False, check=True):
        return run(['git', *parts], cwd=args.repo, binary=binary, check=check)
    def source(path):
        return git('show', commit+':'+path, binary=True).stdout
    def properties(unit, names):
        result = run(['systemctl', '--user', 'show', unit, *sum((['-p', n] for n in names), [])])
        return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    def environment(text):
        return dict(item.split('=', 1) for item in shlex.split(text) if '=' in item)
    def runtime_namespace(key):
        return (key.startswith(('STREAM_', 'ANE_', 'MLX_STT_', 'TRANSCRIBE_'))
                or key in {'VK_DRIVER_FILES', 'MLX_OMARCHY_CACHE_DIR', 'MSERIES_INPUT_TEST_SESSION'})
    try:
        baseline = json.loads(args.baseline.read_text())
        commit = git('rev-parse', '--verify', args.source_ref+'^{commit}').stdout.strip()
        check('source_is_merged_in_origin_main', git('merge-base', '--is-ancestor', commit, 'refs/remotes/origin/main', check=False).returncode == 0)
        origin = git('remote', 'get-url', 'origin').stdout.strip().removesuffix('.git')
        check('source_origin_is_expected_repository', origin.endswith(('github.com/techmore/ElementaryOS_MSeries', 'github.com:techmore/ElementaryOS_MSeries')))
        uname = os.uname()
        report['source'] = {'repository': 'https://github.com/techmore/ElementaryOS_MSeries',
            'commit': commit, 'commit_time': git('show', '-s', '--format=%cI', commit).stdout.strip()}
        report['machine'] = {'kernel': uname.release, 'architecture': uname.machine, 'kernel_build': uname.version,
            'boot_id_sha256': sha(Path('/proc/sys/kernel/random/boot_id').read_bytes())}
        check('kernel_matches_private_baseline', uname.release == baseline['kernel'])
        installer = source('mseries/install-dictation-english.py')
        manager = source('mseries/install-dictation-input.py')
        selector = source('mseries/dictation/dictation-engine.py')
        runtime_files = literal(installer, 'RUNTIME_FILES')
        mapping = {name: 'mseries/dictation/'+name for name in runtime_files}
        mapping.update({'dictation_voice.py': 'mseries/dictation/dictation_voice.py',
            'voice-assistant.py': 'mseries/dictation/voice-assistant.py', 'machine.py': 'mseries/local-ai/machine.py',
            'dictation-manage.py': 'mseries/install-dictation-input.py',
            'dictation-english-manage.py': 'mseries/install-dictation-english.py'})
        manifests = {}
        source_texts = {}
        for name, origin_path in mapping.items():
            expected = source(origin_path)
            actual_path = BASE/name
            actual = file_sha(actual_path) if actual_path.is_file() and not actual_path.is_symlink() else None
            digest = sha(expected)
            manifests[name] = {'source': origin_path, 'source_sha256': digest,
                               'installed_sha256': actual, 'exact': actual == digest}
            source_texts[name] = expected
        report['runtime_files'] = manifests
        check('all_runtime_voice_panel_engine_manager_files_exact', all(x['exact'] for x in manifests.values()))
        units = HOME/'.config/systemd/user'
        input_unit = units/'mseries-dictation-input.service'
        expected_unit = source('mseries/dictation/mseries-dictation-input.service')
        check('installed_input_unit_exact', input_unit.is_file() and not input_unit.is_symlink() and file_sha(input_unit) == sha(expected_unit))
        report['input_unit_sha256'] = sha(expected_unit)

        # Execute only the public launcher's pure rendering function with an
        # in-memory install sink; never instantiate its installer/transaction.
        class Capture:
            def __init__(self): self.values = {}
            def install(self, path, data, mode): self.values[Path(path)] = data
        capture = Capture()
        manager_tree = ast.parse(manager)
        panel_renderer = next(n for n in manager_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'install_panel')
        panel_path = HOME/'.local/share/applications/org.techmore.Dictation.desktop'
        namespace = {'BASE': BASE, 'PANEL_DESKTOP': panel_path}
        exec(compile(ast.Module(body=[panel_renderer], type_ignores=[]), '<public-panel-renderer>', 'exec'), namespace)
        namespace['install_panel'](capture)
        installer_tree = ast.parse(installer)
        stage = next(n for n in installer_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'stage')
        voice_block = next(n for n in stage.body if isinstance(n, ast.If) and any(
            isinstance(child, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'desktop' for t in child.targets) for child in n.body))
        quote = next(n for n in voice_block.body if isinstance(n, ast.FunctionDef) and n.name == 'quote')
        desktop = next(n for n in voice_block.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'desktop' for t in n.targets))
        namespace = {'BASE': BASE}
        exec(compile(ast.Module(body=[quote], type_ignores=[]), '<public-desktop-quote>', 'exec'), namespace)
        voice = eval(compile(ast.Expression(desktop.value), '<public-voice-launcher>', 'eval'), namespace).encode()
        capture.values[HOME/'.local/share/applications/org.techmore.VoiceAssistant.desktop'] = voice
        report['launchers'] = {}
        for path, expected in capture.values.items():
            exact = path.is_file() and not path.is_symlink() and file_sha(path) == sha(expected)
            report['launchers'][path.name] = {'exact': exact, 'expected_sha256': sha(expected),
                                            'installed_sha256': file_sha(path) if path.is_file() else None}
        check('dictation_and_voice_launchers_exact', all(x['exact'] for x in report['launchers'].values()))

        nemo = literal(selector, 'NEMOTRON')
        check('merged_source_uses_qualified_nemotron_pin', literal(selector, 'NEMOTRON_SHA256') == NEMO_SHA)
        model = BASE/'models'/nemo
        actual_model = file_sha(model) if model.is_file() and not model.is_symlink() else None
        report['nemotron_model'] = {'filename': nemo, 'sha256': actual_model, 'expected_sha256': NEMO_SHA}
        check('installed_nemotron_model_exact', actual_model == NEMO_SHA)
        stream_name, stream_sha = literal(selector, 'STREAM_MODEL'), literal(selector, 'STREAM_SHA256')
        stream_model = BASE/'models'/stream_name
        stream_actual = file_sha(stream_model) if stream_model.is_file() and not stream_model.is_symlink() else None
        report['unified_compatibility_model'] = {'filename': stream_name, 'sha256': stream_actual,
                                               'expected_sha256': stream_sha}
        check('installed_unified_compatibility_model_exact', stream_actual == stream_sha)
        library = BASE/'native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so'
        report['native_cpu_library_sha256'] = file_sha(library) if library.is_file() else None
        check('qualified_native_cpu_library_exact', report['native_cpu_library_sha256'] == LIB_SHA)

        service = 'mseries-stream-dictate.service'
        services = {unit: properties(unit, ['ActiveState', 'SubState', 'UnitFileState', 'MainPID'])
                    for unit in [service, 'mseries-dictation-input.service', 'mseries-ai-everyday.service']}
        report['services'] = {unit: {key: row[key] for key in ['ActiveState', 'SubState', 'UnitFileState']}
                              for unit, row in services.items()}
        for unit, row in services.items():
            check(unit+'-active', row['ActiveState'] == 'active' and int(row['MainPID']) > 0)
            check(unit+'-enabled', row['UnitFileState'] == 'enabled')
        speech_pid = int(services[service]['MainPID'])
        ai_pid = int(services['mseries-ai-everyday.service']['MainPID'])
        check('default_4b_pid_unchanged', ai_pid == baseline['default_ai_pid'] == 1568)
        ticks = int(Path('/proc/'+str(ai_pid)+'/stat').read_text().rpartition(')')[2].split()[19])
        btime = next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
        check('default_4b_process_predates_baseline', btime+ticks/os.sysconf('SC_CLK_TCK') <= args.baseline.stat().st_mtime)
        lifecycle = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/'+str(os.getuid())))/'mseries-dictation/status.json'
        info = lifecycle.lstat()
        check('lifecycle_file_owned_private_regular', stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0)
        status = json.loads(lifecycle.read_text())
        check('idle_listener_reports_ready', status.get('pid') == speech_pid and status.get('phase') == 'ready'
              and status.get('output') == 'ibus' and status.get('backend') == 'cpu')
        report['listener'] = {'phase': status.get('phase') if status.get('phase') in {'ready','waiting','error','listening','finishing','cancelled','stopped','loading'} else 'invalid',
                              'pid_matches_service': status.get('pid') == speech_pid}
        children = Path('/proc/'+str(speech_pid)+'/task/'+str(speech_pid)+'/children').read_text().split()
        check('idle_listener_has_no_capture_worker', not children)
        import gi
        from gi.repository import Gio
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        ready = connection.call_sync('org.techmore.DictationInput', '/org/techmore/DictationInput',
            'org.techmore.DictationInput', 'Ready', None, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()
        check('input_bridge_ready_read_only_rpc', ready == (True,))

        configured = properties(service, ['Environment', 'UnsetEnvironment'])
        effective = environment(configured['Environment'])
        for unset in shlex.split(configured.get('UnsetEnvironment', '')):
            if '=' in unset:
                key, value = unset.split('=', 1)
                if effective.get(key) == value: effective.pop(key, None)
            else:
                effective.pop(unset, None)
        live = {}
        for item in Path('/proc/'+str(speech_pid)+'/environ').read_bytes().split(b'\0'):
            if b'=' in item:
                key, value = item.split(b'=', 1)
                key = key.decode('utf-8', 'replace')
                if runtime_namespace(key): live[key] = value.decode('utf-8', 'replace')
        required = {'STREAM_ENGINE': 'nemotron', 'STREAM_MODE': baseline['mode'], 'STREAM_THREADS': '4',
                    'STREAM_BACKEND': 'cpu', 'STREAM_OUTPUT': 'ibus', 'STREAM_UNVERIFIED_FALLBACK': '0',
                    'STREAM_MODEL': str(model), 'TRANSCRIBE_LIBRARY': str(library)}
        report['strict_runtime'] = {'engine': 'nemotron', 'backend': 'cpu', 'threads': 4,
            'output': 'ibus', 'mode_matches_baseline': live.get('STREAM_MODE') == baseline['mode'],
            'raw_environment_exported': False}
        check('strict_configured_effective_settings', all(effective.get(k) == v for k, v in required.items()))
        check('strict_running_process_settings', all(live.get(k) == v for k, v in required.items()))
        check('toggle_mode_preserved', baseline['mode'] == live.get('STREAM_MODE') == 'toggle')
        check('debug_recording_test_injection_controls_unset', all(not live.get(key) for key in DEBUG_KEYS))
        allowed = {'TRANSCRIBE_LIBRARY', 'STREAM_ENGINE', 'STREAM_MODEL', 'STREAM_MODE', 'STREAM_THREADS',
            'STREAM_BACKEND', 'STREAM_OUTPUT', 'STREAM_UNVERIFIED_FALLBACK', 'STREAM_IDLE_SECONDS',
            'STREAM_SOURCE', 'STREAM_CARD', 'STREAM_GAIN', 'STREAM_POPUP', 'STREAM_KEY', 'STREAM_QUIET',
            'STREAM_SPEECH_DB', 'STREAM_ANE_HOLD', 'STREAM_ANE_AGREE', 'STREAM_ANE_TRACE', 'STREAM_ANE_INTERVAL',
            'ANE_PREFIX', 'ANE_VK_ICD', 'ANE_DEADLINE_MS', 'MLX_OMARCHY_CACHE_DIR', 'VK_DRIVER_FILES',
            'MLX_STT_PREFIX', 'MLX_STT_PYTHON', 'MLX_STT_MODEL_DIR', 'MLX_STT_MODULES', 'MLX_STT_VK_ICD'}
        unexpected = set(live)-allowed
        report['strict_runtime']['unrecognized_setting_count'] = len(unexpected)
        check('runtime_environment_keys_allowlisted', not unexpected)
        check('finite_idle_residency', live.get('STREAM_IDLE_SECONDS', '').isdigit() and 0 <= int(live['STREAM_IDLE_SECONDS']) <= 180)

        values = [run(command, timeout=5).stdout.strip() for command in [
            ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'sources'],
            ['gsettings', 'get', 'org.gnome.desktop.input-sources', 'current'],
            ['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-im-module'], ['ibus', 'engine']]]
        fingerprint = sha(json.dumps(values).encode())
        report['input_preferences'] = {'fingerprint_sha256': fingerprint,
            'matches_baseline': fingerprint == baseline['baseline_input_fingerprint'],
            'selected_engine_matches_baseline': values[-1] == baseline['baseline_input_engine']}
        check('input_preferences_fingerprint_preserved', report['input_preferences']['matches_baseline'])
        check('selected_native_input_engine_preserved', report['input_preferences']['selected_engine_matches_baseline'])

        prefix = Path(live.get('ANE_PREFIX', str(HOME/'.local/share/mlx-omarchy'))).expanduser()
        sites = list((prefix/'venv/lib').glob('python*/site-packages/mlx/coreml'))
        ane_available = (prefix/'venv/bin/python').is_file() and len(sites) == 1
        if ane_available:
            lock = json.loads((sites[0]/'parakeet-reference.lock').read_text())
            cache = HOME/'.cache/mlx-omarchy/parakeet-reference'/lock['model_repo']/lock['model_revision']
            ane_available = all((cache/x['path']).is_file() and (cache/x['path']).stat().st_size == x['size'] for x in lock['files'])
            ane_available &= (sites[0].parent/'share/mlx-omarchy/parakeet-1/parakeet-runtime-pin.json').is_file()
            ane_available &= (HOME/'.local/share/mseries/ane/mesa-hk/share/vulkan/icd.d/asahi_icd.aarch64.json').is_file()
        mlx_files = literal(source_texts['mlx-speech-worker.py'], 'MODEL_FILES')
        mlx_available = all((BASE/'optional-mlx/model'/name).is_file()
            and (BASE/'optional-mlx/model'/name).stat().st_size == pin[0] for name, pin in mlx_files.items())
        mlx_available &= (BASE/'optional-mlx/modules/mlx_audio-0.5.6.dist-info/METADATA').is_file()
        mlx_available &= (prefix/'venv/bin/python').is_file() and (prefix/'vulkan/honeykrisp_icd.aarch64.json').is_file()
        report['retained_options'] = {'ane_static_assets_present': bool(ane_available),
            'mlx_static_assets_present': bool(mlx_available), 'inference_repeated': False}
        check('native_ane_option_retained_static', ane_available)
        check('native_mlx_option_retained_static', mlx_available)
        report['complete'] = True
        report['passed'] = all(checks.values())
    except Exception as error:
        report['failure_kind'] = type(error).__name__
        report['failure_scope'] = 'Read-only deployment verification interrupted; inspect private environment. No command output, paths, settings or content exported.'
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.receipt-', dir=output.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(report, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    print(json.dumps({'complete': report['complete'], 'passed': report['passed'],
        'failed_checks': [name for name, ok in checks.items() if not ok],
        'failure_kind': report.get('failure_kind'), 'private_contents_exported': False}))
    if not report['passed']: raise SystemExit(1)


if __name__ == '__main__':
    main()
