#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Prepare one j314s FDT replacement; preserve all other boot payload bytes."""
import argparse, hashlib, json, pathlib, struct
MAGIC = b'\xd0\x0d\xfe\xed'

def parse(data):
    h = struct.unpack_from('>10I', data)
    assert h[0] == 0xd00dfeed and 40 <= h[1] <= len(data)
    assert h[5] == 17 and h[6] <= 17
    assert h[2]+h[9] <= h[1] and h[3]+h[8] <= h[1]
    strings=data[h[3]:h[3]+h[8]]; pos=h[2]; end=h[2]+h[9]; stack=[]; nodes={}
    while pos+4 <= end:
        token=struct.unpack_from('>I',data,pos)[0];pos+=4
        if token == 1:
            stop=data.index(b'\0',pos,end);name=data[pos:stop].decode();pos=(stop+4)&~3
            stack.append(name);nodes['/'+'/'.join(stack[1:])]={}
        elif token == 2:
            assert stack;stack.pop()
        elif token == 3:
            assert stack and pos+8<=end
            size,off=struct.unpack_from('>II',data,pos);pos+=8
            assert off<len(strings) and pos+size<=end
            key=strings[off:strings.index(b'\0',off)].decode()
            nodes['/'+'/'.join(stack[1:])][key]=data[pos:pos+size];pos=(pos+size+3)&~3
        elif token == 4:
            pass
        elif token == 9:
            assert not stack and '/' in nodes
            return h[1],nodes
        else:
            raise ValueError('invalid FDT token')
    raise ValueError('missing FDT end')

def cells(data):
    assert len(data)%4 == 0
    return struct.unpack('>'+str(len(data)//4)+'I',data)

def normalized(nodes):
    ph={cells(v['phandle'])[0]:p for p,v in nodes.items() if 'phandle' in v}
    arrays={'phys':'#phy-cells','power-domains':'#power-domain-cells',
            'iommus':'#iommu-cells','sound-dai':'#sound-dai-cells','mboxes':'#mbox-cells',
            'resets':'#reset-cells','pwms':'#pwm-cells','clocks':'#clock-cells',
            'assigned-clocks':'#clock-cells','assigned-clock-parents':'#clock-cells',
            'dmas':'#dma-cells','interrupts-extended':'#interrupt-cells'}
    bare={'remote-endpoint','panel','apple,sart','post-init-providers','interrupt-parent',
          'apple,dp-source'}
    result={}
    for p,v in nodes.items():
        result[p]={}
        for key,value in v.items():
            if key=='phandle':continue
            if key in bare or key.startswith('pinctrl-') and key!='pinctrl-names':
                value=tuple(ph[x] for x in cells(value))
            elif key in arrays:
                seq=cells(value);i=0;items=[]
                while i<len(seq):
                    if seq[i]==0:
                        items.append(None);i+=1;continue
                    provider=ph[seq[i]];i+=1
                    count=cells(nodes[provider][arrays[key]])[0]
                    assert i+count<=len(seq)
                    items.append((provider,seq[i:i+count]));i+=count
                value=tuple(items)
            result[p][key]=value
    return result

def prepare(boot,dtb):
    size,new=parse(dtb);dtb=dtb[:size]
    assert b'apple,j314s' in new['/']['compatible'].split(b'\0')
    pos=0;trees=[]
    while True:
        off=boot.find(MAGIC,pos)
        if off<0:break
        pos=off+4
        try:
            length,tree=parse(boot[off:])
        except (AssertionError,ValueError,IndexError,KeyError,struct.error,UnicodeError):
            continue
        trees.append((off,length,tree));pos=off+length
    targets=[v for v in trees if b'apple,j314s' in v[2].get('/',{}).get('compatible',b'').split(b'\0')]
    assert len(targets)==1,'expected exactly one embedded apple,j314s tree'
    off,old_size,old=targets[0];a=normalized(old);b=normalized(new)
    base='/soc/cio@b01ac0000'
    added={base+'/phy@e50000',base+'/phy@e58000'}
    assert set(b)-set(a)==added and not set(a)-set(b),'unexpected added/removed nodes'
    allowed={(base+'/nhi@f00000','apple,dp-source'),(base+'/nhi@f00000','apple,dp-in-port'),
             ('/soc/dcp@28cc00000','phys')}
    changed={(p,k) for p in a for k in a[p].keys()|b[p].keys() if a[p].get(k)!=b[p].get(k)}
    assert changed==allowed,('unexpected semantic DT changes',sorted(changed-allowed))
    nhi=new[base+'/nhi@f00000'];dcp=new['/soc/dcp@28cc00000'];dpin=new[base+'/phy@e50000']
    assert cells(nhi['apple,dp-in-port'])==(5,) and nhi['apple,dp-source']==dcp['phandle']
    assert dcp['phys']==dpin['phandle'] and dpin['status']==b'okay\0'
    assert new[base+'/phy@e58000']['status']==b'disabled\0'
    result=boot[:off]+dtb+boot[off+old_size:]
    assert result[:off]==boot[:off] and result[off+len(dtb):]==boot[off+old_size:]
    report={'status':'prepared only; no system write','valid_embedded_trees':len(trees),
            'replaced_tree':'apple,j314s','old_offset':off,'old_size':old_size,'new_size':len(dtb),
            'semantic_property_changes':sorted(changed),'added_nodes':sorted(added),
            'boot_sha256':hashlib.sha256(boot).hexdigest(),
            'dtb_sha256':hashlib.sha256(dtb).hexdigest(),
            'output_sha256':hashlib.sha256(result).hexdigest(),
            'prefix_suffix_unchanged':True}
    return result,report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--boot',required=True,type=pathlib.Path);p.add_argument('--dtb',required=True,type=pathlib.Path)
    p.add_argument('--output',required=True,type=pathlib.Path);p.add_argument('--report',required=True,type=pathlib.Path)
    a=p.parse_args();inputs={a.boot.resolve(),a.dtb.resolve()}
    assert a.output.resolve() not in inputs and a.report.resolve() not in inputs
    assert a.output.resolve()!=a.report.resolve()
    result,report=prepare(a.boot.read_bytes(),a.dtb.read_bytes())
    with a.output.open('xb') as f:f.write(result)
    with a.report.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
