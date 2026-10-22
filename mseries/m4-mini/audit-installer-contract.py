#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit pinned Gravity partition handling with mocks; never operate on disks."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid
import zipfile

COMMIT = '6420623289fe7544cb8589b658355e57f0290fcc'
ARCHIVE_SHA256 = '7fe8e31fce11990485195ea01f7a530c84ec71060fac9ddeb9d6ea67c2539c47'
TYPES = {
    'usr': 'b0e01050-ee5f-4390-949a-9101b17104e9',
    'usr-verity': '6e11a4e7-fbca-4ded-b9e9-e1a512bb664e',
    'usr-verity-sig': 'c23ce4ff-44bd-4b00-b2d4-b41b3419e02a',
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive', type=Path, required=True)
parser.add_argument('--receipt', type=Path, required=True)
args = parser.parse_args()
if args.receipt.exists():
    raise ValueError('new receipt required')
if hashlib.sha256(args.archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
    raise ValueError('exact pinned installer archive required')

with tempfile.TemporaryDirectory(prefix='m4-contract-', dir=args.archive.resolve().parent) as temp:
    with tarfile.open(args.archive) as archive:
        archive.extractall(temp, filter='data')
    source = Path(temp) / ('installer-' + COMMIT) / 'src'
    sys.path.insert(0, str(source))
    from diskutil import DiskUtil, Partition
    from osinstall import OSInstaller

    # Exercise real UUID/type selection while all diskutil methods are mocked.
    for guid in TYPES.values():
        old = Partition('disk0s4', 0, 4096, False, guid, 'existing')
        new = Partition('disk0s6', 8192, 4096, False, guid.upper(), 'new')
        helper = Partition('disk0s5', 4096, 4096, False, 'Apple_Boot', 'helper')
        disk = DiskUtil()
        disk.disk_parts = {}
        disk.get_partitions = Mock(side_effect=[[old], [old, helper, new]])
        disk.action = Mock()
        disk.get_list = Mock()
        disk.get_partition_info = Mock(return_value=new)
        assert disk.addPartition('disk0s4', '%' + guid + '%', '%noformat%', 4096) is new
        disk.action.assert_called_once_with('addPartition', 'disk0s4', '%' + guid + '%',
                                           '%noformat%', '4096', verbose=True)

    # Synthetic metadata requirements, not a released layout or owner disk plan.
    parts = [{'name': 'EFI', 'type': 'EFI', 'size': '1.5GiB'}]
    for suffix in ['active', 'spare']:
        for role, guid in TYPES.items():
            parts.append({'name': role + '-' + suffix, 'type': guid,
                          'size': '7GiB' if role == 'usr' else '400MiB',
                          'gpt_label': 'elementary_contract_' + role + '_' + suffix,
                          'gpt_uuid': str(uuid.uuid5(uuid.NAMESPACE_URL, role + suffix)),
                          'gpt_attributes': (1 << 63) if suffix == 'spare' else (1 << 60)})
    parts.append({'name': 'root', 'type': 'b921b045-1df0-41c3-af44-4c6f280d3fae',
                  'size': '15GiB', 'expand': True})
    disk = Mock()
    count = 4
    def add(after, kind, label, size):
        global count
        count += 1
        return SimpleNamespace(name='disk0s' + str(count), uuid='generated-' + str(count),
                               type=kind.strip('%'), label=label, size=size)
    disk.addPartition.side_effect = add
    template = {'default_os_name': 'elementary M4 contract fixture', 'partitions': parts}
    installer = OSInstaller(disk, {}, template)
    extra = 2 * 1024**3
    # Any accidental command execution aborts this audit before reaching macOS tools.
    with patch('subprocess.run', side_effect=AssertionError('native command forbidden')), \
            contextlib.redirect_stdout(io.StringIO()):
        installer.partition_disk('disk0s4', installer.min_size + extra)
    assert len(installer.part_info) == len(parts)
    assert all(call[0] == 'addPartition' for call in disk.method_calls)
    assert all(call.args[2] == '%noformat%' for call in disk.addPartition.call_args_list)
    assert installer.part_info[-1].size == 17 * 1024**3
    lost = []
    for wanted, actual in zip(parts, installer.part_info):
        if 'gpt_uuid' in wanted:
            assert actual.uuid != wanted['gpt_uuid'] and actual.label != wanted['gpt_label']
            lost.append(wanted['name'])

    # Exercise both raw-image rejection paths; opening a device is forbidden.
    for length, message in [(1, 'multiple of 4KiB'), (8192, 'exceeds destination')]:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as package:
            package.writestr('partition.img', b'x' * length)
        buffer.seek(0)
        probe = OSInstaller(Mock(), {}, {'default_os_name': 'fixture', 'partitions': [
            {'name': 'usr', 'type': TYPES['usr'], 'size': '4KiB', 'image': 'partition.img'}]})
        probe.pkg = zipfile.ZipFile(buffer)
        probe.part_info = [SimpleNamespace(name='disk0s5')]
        probe.dutil.get_partition_info.return_value = SimpleNamespace(size=4096)
        with patch('builtins.open', side_effect=AssertionError('device open forbidden')), \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                probe.install(SimpleNamespace())
            except Exception as error:
                assert message in str(error), str(error)
            else:
                raise AssertionError('invalid raw image accepted')
        probe.pkg.close()

args.receipt.write_text(json.dumps({
    'installer_commit': COMMIT, 'archive_sha256': ARCHIVE_SHA256,
    'scope': 'real pinned source with mocked disk methods and in-memory ZIP fixtures',
    'exact_guid_type_selection': 'three ARM64 usr/verity GUID fixtures pass; actual macOS Content spelling unmeasured',
    'partition_chain_and_expand': 'fixture passes; no actual disk or free-space facts',
    'raw_image_guards': 'unaligned and oversized images rejected before any device open',
    'metadata_findings': {'gpt_labels': 'not set by partition_disk',
                          'unique_partition_uuids': 'generated by diskutil, not restored from source image',
                          'attributes': 'no no-auto/read-only metadata operation in this path',
                          'affected_fixture_roles': lost},
    'elementary_partition_roundtrip_supported': False,
    'installer_admission': False, 'hardware_validated': False,
    'required_adapter_work': ['preserve GPT type/unique UUID/label/attributes from real exported partitions',
                              'export matching usr/verity/signature and writable root images',
                              'validate ESP loader handoff, boot filters and macOS/Recovery round trip'],
}, indent=2) + '\n')
print('Contract audit completed: raw-image/type guards hold; elementary GPT metadata adapter remains required')
