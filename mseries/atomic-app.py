#!/usr/bin/env python3
"""Activate prepared, publisher-verified app trees with a single selector switch.

Download, signature verification and extraction belong to the calling installer.
No application data is stored here, and no retained release is garbage-collected.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_directory(path):
    missing = []
    parent = path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        sync_directory(directory)
        sync_directory(directory.parent)


def validate_tree(source, entrypoint):
    relative = Path(entrypoint)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Entrypoint must stay inside the release')
    for path in source.rglob('*'):
        if path.is_symlink():
            target = os.readlink(path)
            if os.path.isabs(target) or not path.resolve().is_relative_to(source):
                raise ValueError(f'Release symlink escapes the app: {path}')
        elif not path.is_dir() and not path.is_file():
            raise ValueError(f'Unsupported release file: {path}')
    executable = source / relative
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError('Release entrypoint is missing or not executable')


class Store:
    def __init__(self, root, app):
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', app) or app in {'.', '..'}:
            raise ValueError('Invalid app identifier')
        self.path = Path(root).resolve() / app
        durable_directory(self.path)
        self.releases = self.path / 'releases'
        self.generations = self.path / 'generations'
        durable_directory(self.releases)
        durable_directory(self.generations)
        self.lock = (self.path / '.lock').open('a')

    def __enter__(self):
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_args):
        self.lock.close()

    def selected(self):
        current = self.path / 'current'
        if not current.is_symlink():
            if current.exists():
                raise ValueError('Current selector must be a symlink')
            return None
        selected = current.resolve(strict=True)
        if selected.parent != self.generations:
            raise ValueError('Current selector escapes the generation store')
        return selected

    def switch(self, generation):
        temporary = self.path / ('.current-' + uuid.uuid4().hex)
        temporary.symlink_to(generation.relative_to(self.path))
        try:
            os.replace(temporary, self.path / 'current')
            try:
                sync_directory(self.path)
            except OSError:
                # The switch already happened: report its durability separately.
                return False
            return True
        finally:
            temporary.unlink(missing_ok=True)

    def deploy(self, source, entrypoint, artifact_sha256, publisher_fingerprint):
        if not re.fullmatch(r'[0-9a-f]{64}', artifact_sha256):
            raise ValueError('A verified artifact SHA-256 is required')
        source = Path(source).resolve(strict=True)
        if self.path.is_relative_to(source):
            raise ValueError('Release source contains the deployment store')
        validate_tree(source, entrypoint)
        previous = self.selected()
        release_id = uuid.uuid4().hex
        staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=self.path))
        try:
            shutil.copytree(source, staging / 'app', symlinks=True)
            validate_tree(staging / 'app', entrypoint)
            metadata = {
                'entrypoint': entrypoint, 'artifact_sha256': artifact_sha256,
                'publisher_fingerprint': publisher_fingerprint,
                'verification': 'performed by calling installer',
            }
            (staging / 'release.json').write_text(json.dumps(metadata, indent=2) + '\n')
            # Persist the complete prepared tree before publishing its selector.
            for directory, _dirs, files in os.walk(staging, topdown=False):
                for name in files:
                    path = Path(directory) / name
                    if not path.is_symlink():
                        with path.open('rb') as stream:
                            os.fsync(stream.fileno())
                sync_directory(directory)
            release = self.releases / release_id
            staging.rename(release)
            sync_directory(self.releases)
            generation = self.generations / release_id
            generation.mkdir()
            (generation / 'app').symlink_to(Path('../../releases') / release_id / 'app')
            (generation / 'release.json').symlink_to(Path('../../releases') / release_id / 'release.json')
            if previous:
                (generation / 'previous').symlink_to(Path('..') / previous.name)
            sync_directory(generation)
            sync_directory(self.generations)
            durable = self.switch(generation)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return {**self.status(), 'activation_durable': durable}

    def rollback(self):
        current = self.selected()
        if current is None or not (current / 'previous').is_symlink():
            raise ValueError('No previous generation is available')
        previous = (current / 'previous').resolve(strict=True)
        if previous.parent != self.generations:
            raise ValueError('Previous selector escapes the generation store')
        metadata = json.loads((previous / 'release.json').read_text())
        validate_tree((previous / 'app').resolve(), metadata['entrypoint'])
        durable = self.switch(previous)
        return {**self.status(), 'activation_durable': durable}

    def launch(self):
        current = self.selected()
        if current is None:
            raise ValueError('No release is active')
        metadata = json.loads((current / 'release.json').read_text())
        app = (current / 'app').resolve(strict=True)
        executable = (app / metadata['entrypoint']).resolve(strict=True)
        if not executable.is_relative_to(app) or not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError('Active entrypoint is invalid')
        return executable

    def status(self):
        selected = self.selected()
        if selected is None:
            return {'current': None}
        return {'current': selected.name,
                'previous': (selected / 'previous').resolve().name
                if (selected / 'previous').is_symlink() else None,
                'launch_root': str((selected / 'app').resolve(strict=True)),
                **json.loads((selected / 'release.json').read_text())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home() / '.local/lib/mseries-apps')
    parser.add_argument('--app', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    deploy = commands.add_parser('deploy')
    deploy.add_argument('--source', required=True, type=Path)
    deploy.add_argument('--entrypoint', required=True)
    deploy.add_argument('--artifact-sha256', required=True)
    deploy.add_argument('--publisher-fingerprint', required=True)
    commands.add_parser('rollback')
    commands.add_parser('status')
    run = commands.add_parser('run')
    run.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        with Store(args.root, args.app) as store:
            if args.command == 'deploy':
                result = store.deploy(args.source, args.entrypoint,
                                      args.artifact_sha256, args.publisher_fingerprint)
            elif args.command == 'rollback':
                result = store.rollback()
            elif args.command == 'run':
                executable = store.launch()
            else:
                result = store.status()
        if args.command == 'run':
            arguments = args.arguments
            if arguments[:1] == ['--']:
                arguments = arguments[1:]
            os.execv(executable, [str(executable), *arguments])
        print(json.dumps(result, indent=2))
        if result.get('activation_durable') is False:
            print('App activated; selector durability is unconfirmed because directory sync failed.',
                  file=sys.stderr)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f'atomic-app: {error}\n')


if __name__ == '__main__':
    main()
