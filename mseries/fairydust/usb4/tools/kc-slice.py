#!/usr/bin/env python3
"""
kc-slice.py -- read Apple macOS kernelcache (MH_FILESET) entries on Linux.

Apple packs a kernelcache as a Mach-O fileset (filetype 12).  Each kext is an
"entry" whose segments live at *absolute* offsets in the collection file and are
NOT contiguous (all __TEXT blocks first, then all __TEXT_EXEC, ...).  That is why
carving the entry's header only and handing it to objdump fails with
"truncated or malformed object".

This tool parses the load commands, maps vmaddr <-> file offset through the
entry's own segments, and can:
  list        -- list fileset entries
  segs        -- show an entry's segments
  syms        -- dump / grep the entry's symbols (demangled)
  dis         -- disassemble symbols of an entry (capstone)

No Mach-O-capable objdump required.  ARM64 is disassembled with capstone;
arm64e pointer-auth instructions are decoded by capstone's ARM64 backend.

Usage:
  kc-slice.py <kc-file> list
  kc-slice.py <kc-file> segs  com.apple.driver.AppleDisplayCrossbar
  kc-slice.py <kc-file> syms  com.apple.driver.AppleDisplayCrossbar [regex]
  kc-slice.py <kc-file> dis   com.apple.driver.AppleDisplayCrossbar [regex]
"""
import sys, struct, re, subprocess

MH_MAGIC_64 = 0xfeedfacf
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_FILESET_ENTRY = 0x80000035


def parse_tlv(b, o):
    t = b[o]; o += 1
    l = b[o]; o += 1
    if l & 0x80:
        n = l & 0x7F; l = int.from_bytes(b[o:o + n], 'big'); o += n
    return t, b[o:o + l], o + l


def im4p_payload(path):
    d = open(path, 'rb').read()
    if d[:4] == b'\xcf\xfa\xed\xfe':
        return d
    t, seq, _ = parse_tlv(d, 0)
    o = 0
    while o < len(seq):
        t, v, o = parse_tlv(seq, o)
        if t == 0x04:
            return v
    raise SystemExit("no payload in %s" % path)


def fileset_entries(d):
    ncmds = struct.unpack_from('<I', d, 16)[0]
    off, out = 32, []
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', d, off)
        if cmd == LC_FILESET_ENTRY:
            vmaddr, fileoff = struct.unpack_from('<QQ', d, off + 8)
            eidoff = struct.unpack_from('<I', d, off + 24)[0]
            s = off + eidoff
            eid = d[s:d.index(b'\0', s)].decode('latin1')
            out.append((eid, fileoff, vmaddr))
        off += cmdsize
    return out


def entry_info(d, foff):
    """Parse one entry's Mach-O header/load commands."""
    magic, cputype, cpusub, ftype, ncmds, sizeofcmds, flags, resv = \
        struct.unpack_from('<8I', d, foff)
    assert magic == MH_MAGIC_64, hex(magic)
    segs, symtab = [], None
    off = foff + 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', d, off)
        if cmd == LC_SEGMENT_64:
            name = d[off + 8:off + 24].split(b'\0')[0].decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', d, off + 24)
            segs.append(dict(name=name, vmaddr=vmaddr, vmsize=vmsize,
                             fileoff=fileoff, filesize=filesize, cmd_off=off))
        elif cmd == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', d, off + 8)
            symtab = dict(symoff=symoff, nsyms=nsyms, stroff=stroff, strsize=strsize)
        off += cmdsize
    return dict(foff=foff, filetype=ftype, segs=segs, symtab=symtab)


def vaddr_to_foff(info, va):
    for s in info['segs']:
        if s['vmaddr'] <= va < s['vmaddr'] + s['vmsize']:
            return s['fileoff'] + (va - s['vmaddr'])
    return None


def read_syms(d, info):
    st = info['symtab']
    if not st:
        return []
    out = []
    for i in range(st['nsyms']):
        o = st['symoff'] + i * 16
        if o + 16 > len(d):
            break
        n_strx, n_type, n_sect, n_desc, n_value = struct.unpack_from('<IBBHQ', d, o)
        if n_strx == 0:
            continue
        e = st['stroff'] + n_strx
        nm = d[e:d.index(b'\0', e)].decode('latin1')
        out.append(dict(name=nm, value=n_value, sect=n_sect, type=n_type))
    return out


def demangle(names):
    # Mach-O prepends one extra underscore to every symbol; strip exactly one
    # so c++filt can demangle (otherwise everything comes back unchanged).
    cleaned = [n[1:] if n.startswith('_') else n for n in names]
    try:
        p = subprocess.run(['c++filt'], input='\n'.join(cleaned).encode(),
                           capture_output=True)
        return p.stdout.decode().splitlines()
    except FileNotFoundError:
        return names


def find_entry(d, want):
    for eid, foff, vm in fileset_entries(d):
        if eid == want or want in eid:
            return eid, foff
    raise SystemExit("entry not found: %s" % want)


def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    path, cmd = sys.argv[1], sys.argv[2]
    d = im4p_payload(path)

    if cmd == 'list':
        for eid, foff, vm in fileset_entries(d):
            print('%-56s foff=0x%08x vmaddr=0x%x' % (eid, foff, vm))
        return

    entry = sys.argv[3] if len(sys.argv) > 3 else None
    if not entry:
        raise SystemExit("need entry id")
    eid, foff = find_entry(d, entry)
    info = entry_info(d, foff)

    if cmd == 'segs':
        print(eid)
        for s in info['segs']:
            print('  %-14s vmaddr=0x%-12x vmsize=%-9d fileoff=0x%-9x filesize=%d'
                  % (s['name'], s['vmaddr'], s['vmsize'], s['fileoff'], s['filesize']))
        st = info['symtab']
        print('  LC_SYMTAB', st)
        return

    syms = read_syms(d, info)
    dm = demangle([s['name'] for s in syms])

    if cmd == 'syms':
        pat = re.compile(sys.argv[4]) if len(sys.argv) > 4 else None
        for s, n in zip(syms, dm):
            if pat and not (pat.search(n) or pat.search(s['name'])):
                continue
            print('0x%016x  %s' % (s['value'], n))
        return

    if cmd == 'xref':
        # find every "bl <target symbol>" and show the instructions that set up
        # the arguments.  This is how you recover register/offset/value
        # constants without reading whole functions.
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        md.skipdata = True
        pat = re.compile(sys.argv[4])
        targets = {}
        for s, n in zip(syms, dm):
            if pat.search(n) or pat.search(s['name']):
                targets[s['value']] = n
        if not targets:
            print("no target symbols matched %r" % sys.argv[4]); return
        for v, n in targets.items():
            print(";; target %s @0x%x" % (n, v))
        ctx = int(sys.argv[5]) if len(sys.argv) > 5 else 8
        for seg in info['segs']:
            if seg['name'] not in ('__TEXT_EXEC', '__TEXT'):
                continue
            code = d[seg['fileoff']:seg['fileoff'] + seg['filesize']]
            insns = list(md.disasm(code, seg['vmaddr']))
            for i, ins in enumerate(insns):
                if ins.mnemonic != 'bl':
                    continue
                try:
                    tgt = int(ins.op_str.lstrip('#'), 16)
                except ValueError:
                    continue
                if tgt not in targets:
                    continue
                print('\n;; ---- %s  called from 0x%x by %s ----'
                      % (targets[tgt], ins.address, '?'))
                for j in range(max(0, i - ctx), i + 1):
                    p = insns[j]
                    print('  0x%x:\t%-10s %s' % (p.address, p.mnemonic, p.op_str))
        return

    if cmd == 'dis':
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        md.detail = False
        md.skipdata = True
        pat = re.compile(sys.argv[4]) if len(sys.argv) > 4 else None
        if not pat:
            raise SystemExit("dis needs a symbol regex")
        picked = [(s, n) for s, n in zip(syms, dm)
                  if pat.search(n) or pat.search(s['name'])]
        if not picked:
            print("no symbols matched %r" % sys.argv[4]); return
        for s, n in picked:
            fo = vaddr_to_foff(info, s['value'])
            if fo is None:
                print(';; %s @0x%x : address not in any segment' % (n, s['value']))
                continue
            print('\n;; ===== %s  @0x%x (file 0x%x) =====' % (n, s['value'], fo))
            code = d[fo:fo + 0x600]
            for ins in md.disasm(code, s['value']):
                print('  0x%x:\t%-10s %s' % (ins.address, ins.mnemonic, ins.op_str))
        return

    print(__doc__)


if __name__ == '__main__':
    main()
