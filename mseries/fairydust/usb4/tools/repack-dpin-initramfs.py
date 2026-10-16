#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Replace a named set of regular files in one gzip/newc initramfs, offline."""
import argparse, collections, gzip, hashlib, json, pathlib, stat, struct

def canonical(name):
    while name.startswith('./'):name=name[2:]
    p=pathlib.PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts:raise ValueError('unsafe archive path')
    return name.rstrip('/')

def parse(raw):
    pos=0;rows=[];names=set()
    while True:
        if raw[pos:pos+6]!=b'070701':raise ValueError('expected a single newc archive')
        vals=[int(raw[pos+6+i*8:pos+14+i*8],16) for i in range(13)]
        start=pos+110;stop=start+vals[11]
        if stop>len(raw) or raw[stop-1]!=0:raise ValueError('invalid archive name')
        name=raw[start:stop-1].decode();pos=(stop+3)&~3
        end=pos+vals[6]
        if end>len(raw):raise ValueError('truncated archive payload')
        data=raw[pos:end];pos=(end+3)&~3
        if name=='TRAILER!!!':
            if any(raw[pos:]):raise ValueError('multiple archives or trailing payload')
            return rows,vals
        key=canonical(name)
        if key in names:raise ValueError('duplicate archive path')
        names.add(key);rows.append((name,vals,data))

def encode(rows,trailer):
    out=bytearray()
    for name,values,data in [*rows,('TRAILER!!!',trailer,b'')]:
        v=values.copy();encoded=name.encode()+b'\0';v[6]=len(data);v[11]=len(encoded);v[12]=0
        out.extend(b'070701'+''.join(f'{x:08x}' for x in v).encode()+encoded)
        out.extend(b'\0'*((-len(out))%4));out.extend(data);out.extend(b'\0'*((-len(out))%4))
    out.extend(b'\0'*((-len(out))%512));return bytes(out)

def repack(image,replacements):
    rows,trailer=parse(gzip.decompress(image));initial={canonical(n):(v,d) for n,v,d in rows}
    identities=collections.Counter((v[7],v[8],v[0]) for n,v,d in rows if stat.S_ISREG(v[1]))
    replace={canonical(n):pathlib.Path(p).read_bytes() for n,p in replacements.items()}
    updated=[];changed=[];ino=max(v[0] for n,v,d in rows)+1
    for name,values,data in rows:
        key=canonical(name)
        if key in replace:
            if not stat.S_ISREG(values[1]) or values[4] not in (0,1) or identities[(values[7],values[8],values[0])]!=1:raise ValueError('replace only regular non-hardlinked files')
            data=replace.pop(key);changed.append(key)
        updated.append((name,values,data))
    existing={canonical(n) for n,v,d in updated}
    for name,data in replace.items():
        parent=pathlib.PurePosixPath(name).parent;parents=[]
        while str(parent) not in ('.','/'):
            parents.append(str(parent));parent=parent.parent
        for directory in reversed(parents):
            if directory not in existing:
                v=[ino,stat.S_IFDIR|0o755,0,0,2,0,0,0,0,0,0,0,0];ino+=1
                updated.append((directory,v,b''));existing.add(directory)
        v=[ino,stat.S_IFREG|0o644,0,0,1,0,0,0,0,0,0,0,0];ino+=1
        updated.append((name,v,data));changed.append(name)
    raw=encode(updated,trailer);verified,_=parse(raw);after={canonical(n):(v,d) for n,v,d in verified}
    for key,(v,data) in initial.items():
        if key not in changed:
            if after[key]!=(v,data):raise ValueError('unrelated archive entry changed: '+key)
    result=gzip.compress(raw,mtime=0)
    return result,{'status':'prepared only; no system write','old_entries':len(rows),'new_entries':len(updated),
                   'changed_regular_files':sorted(changed),'unrelated_entries_preserved':True,
                   'input_sha256':hashlib.sha256(image).hexdigest(),'output_sha256':hashlib.sha256(result).hexdigest()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,type=pathlib.Path);p.add_argument('--mapping',required=True,type=pathlib.Path)
    p.add_argument('--output',required=True,type=pathlib.Path);p.add_argument('--report',required=True,type=pathlib.Path)
    a=p.parse_args();mapping=json.loads(a.mapping.read_text())
    inputs={a.input.resolve(),a.mapping.resolve(),*(pathlib.Path(v).resolve() for v in mapping.values())}
    if a.output.resolve() in inputs or a.report.resolve() in inputs or a.output.resolve()==a.report.resolve():raise ValueError('output overlaps input')
    result,report=repack(a.input.read_bytes(),mapping)
    with a.output.open('xb') as f:f.write(result)
    with a.report.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
