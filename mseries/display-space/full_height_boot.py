#!/usr/bin/python3
"""Prepare full height using the running kernel's exact existing GRUB stanza.

Leaves all recovery/trial entries and next_entry intact. No kernel, initramfs,
firmware, or generated grub.cfg edits. Requires the native panel installed first.
"""
import argparse
from collections import Counter
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile

BEGIN = '# BEGIN M-series full-height desktop (managed)\n'
END = '# END M-series full-height desktop\n'
ENTRY = 'mseries-full-height'


def without_managed(text):
    if BEGIN not in text and END not in text:
        return text
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError('Ambiguous full-height block; refusing to edit')
    start = text.index(BEGIN)
    end = text.index(END) + len(END)
    if end <= start:
        raise ValueError('Invalid full-height block order')
    return text[:start] + text[end:]


def prepare(text, cmdline):
    base = without_managed(text)
    words = shlex.split(cmdline)
    images = [w.split('=', 1)[1] for w in words if w.startswith('BOOT_IMAGE=')]
    if len(images) != 1:
        raise ValueError('Running kernel BOOT_IMAGE is missing or ambiguous')
    live = [w for w in words if not w.startswith(('BOOT_IMAGE=', 'appledrm.show_notch='))]
    if not any(w.startswith('rootflags=') and 'subvol=@elementary' in w[10:].split(',') for w in live):
        raise ValueError('Running root is not the elementary subvolume')
    matches = []
    for stanza in re.finditer(r'^menuentry [^\n]+\{\n(?P<body>.*?)^}\s*$', base, re.M | re.S):
        body = stanza.group('body')
        linux = re.findall(r'^[ \t]*linux[ \t]+([^\n]+)$', body, re.M)
        if len(linux) != 1:
            continue
        args = shlex.split(linux[0])
        if not args or args[0] != images[0]:
            continue
        candidate = [w for w in args[1:] if not w.startswith('appledrm.show_notch=')]
        if Counter(candidate) == Counter(live):
            if not re.search(r'^\s*initrd\s+\S+', body, re.M):
                raise ValueError('Matching stanza has no initrd')
            matches.append(body)
    if len(matches) != 1:
        raise ValueError(f'Expected one exact running-kernel stanza; found {len(matches)}')
    body = re.sub(r'(?m)^([ \t]*linux[ \t]+)([^\n]+)$',
                  lambda m: m[1] + ' '.join(w for w in shlex.split(m[2])
                                          if not w.startswith('appledrm.show_notch=')) + ' appledrm.show_notch=1',
                  matches[0])
    return (base.rstrip() + '\n\n' + BEGIN +
            f"menuentry 'elementary OS (M-series full-height desktop)' --id {ENTRY} {{\n" + body + '}\n' +
            '# Preserve one-shot kernel trials; use full height on normal boots.\n' +
            'if [ "${boot_once}" != "true" ]; then\n' +
            f'    set default="{ENTRY}"\nfi\n' + END)


def write_atomic(path, text):
    stat = path.stat()
    fd, temporary = tempfile.mkstemp(prefix='.mseries-full-height-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.st_mode)
        os.chown(temporary, stat.st_uid, stat.st_gid)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preview', 'prepare', 'revert'])
    args = parser.parse_args()
    path = Path('/boot/grub/custom.cfg')
    if args.action != 'preview' and os.geteuid() != 0:
        parser.error('prepare/revert require root')
    model = Path('/proc/device-tree/model').read_text().rstrip('\0')
    if '14-inch, M1 Pro' not in model:
        parser.error('This full-height panel profile targets the 14-inch M1 Pro (J314)')
    text = path.read_text()
    if args.action == 'revert':
        result = without_managed(text)
    else:
        result = prepare(text, Path('/proc/cmdline').read_text())
    if args.action == 'preview':
        print(result[result.index(BEGIN):], end='')
        return
    backup = path.with_name('custom.cfg.pre-mseries-full-height')
    if not backup.exists():
        shutil.copy2(path, backup)
    if result != text:
        write_atomic(path, result)
    print('Full-height boot choice prepared; reboot to use it.' if args.action == 'prepare'
          else 'Full-height choice removed; previous boot selection restored.')


if __name__ == '__main__':
    main()
