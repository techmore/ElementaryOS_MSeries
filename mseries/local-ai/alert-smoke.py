#!/usr/bin/python3
"""Synthetic subprocess collector/restart/ack receipt. Never reads a real journal."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from alert_store import AlertStore
from machine import snapshot


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Preserve existing evidence')
    checks={};samples=[];started=time.monotonic()
    result={'schema':1,'complete':False,'passed':False,'checks':checks,
            'real_journal_read':False,'model_inference':False,'desktop_notifications':False,
            'services_changed':False,'owner_windows_opened':False,'synthetic_input':True,
            'source_sha256':{name:sha(HERE/name) for name in ['alert_store.py','alerts.py','crash-watch.py','alert-smoke.py']}}
    try:
        with tempfile.TemporaryDirectory(prefix='mseries-alert-smoke-') as directory:
            root=Path(directory);state=root/'state';state.mkdir(mode=0o700)
            (state/'auto-diagnose').touch()
            rows=[]
            for i in range(200):
                rows.append({'__CURSOR':'synthetic-'+str(i),'_BOOT_ID':'fixture-boot-a',
                    '__REALTIME_TIMESTAMP':str(1000000+i),'_TRANSPORT':'kernel',
                    'MESSAGE':'asahi gpu fault at 0x'+format(12345678+i,'012x')+' pid '+str(100+i)})
            rows.append(rows[-1]) # Exact replay is not another occurrence.
            rows.append({'__CURSOR':'unrelated-user','_BOOT_ID':'fixture-boot-a',
                '__REALTIME_TIMESTAMP':'1000500','COREDUMP_UID':str(os.getuid()+1),
                'COREDUMP_PID':'123','COREDUMP_COMM':'fixture-private-other-user'})
            fixture=root/'synthetic.jsonl';fixture.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
            command=[sys.executable,str(HERE/'crash-watch.py'),'--state-dir',str(state),'--replay-file',str(fixture)]
            for iteration in range(2):
                samples.append(snapshot())
                p=subprocess.run(command,capture_output=True,text=True,timeout=15)
                if p.returncode:raise RuntimeError('Synthetic collector subprocess failed')
                store=AlertStore(state);alert,=store.list_alerts()
                checks['storm_count_'+str(iteration+1)]=alert['occurrence_count']==200
            checks['restart_cursor_retained']=store.source_state('journal')['cursor']=='unrelated-user'
            checks['different_user_ignored']=len(store.list_alerts())==1
            before=alert['version']
            ack=subprocess.run([sys.executable,str(HERE/'alerts.py'),'--state-dir',str(state),'ack',alert['alert_id'],'--version',str(before)],capture_output=True,text=True,timeout=5)
            if ack.returncode:raise RuntimeError('Synthetic acknowledgement failed')
            acknowledged=json.loads(ack.stdout)
            checks['acknowledgement_is_not_resolution']=acknowledged['attention']=='acknowledged' and not acknowledged['resolved']
            new=rows[0]|{'__CURSOR':'new-occurrence','__REALTIME_TIMESTAMP':'1001000'}
            fixture.write_text(json.dumps(new)+'\n')
            p=subprocess.run(command,capture_output=True,text=True,timeout=15)
            if p.returncode:raise RuntimeError('Synthetic recurrence failed')
            fresh=store.get_alert(alert['alert_id'])
            checks['recurrence_reopens_attention']=fresh['attention']=='new' and fresh['occurrence_count']==201
            stale=subprocess.run([sys.executable,str(HERE/'alerts.py'),'--state-dir',str(state),'ack',alert['alert_id'],'--version',str(before)],capture_output=True,text=True,timeout=5)
            checks['stale_ack_denied']=stale.returncode!=0
            legacy=json.loads((state/'crashes.json').read_text())
            checks['legacy_auto_diagnosis_disabled']=not legacy['collector']['automatic_diagnosis']
            checks['notifications_disabled']=legacy['collector']['notifications']=='disabled'
            checks['private_database']=store.path.stat().st_mode&0o077==0
            checks['compatibility_projection_count']=legacy['events'][0]['occurrence_count']==201
            result['observed']={'alerts':len(store.list_alerts()),'storm_occurrences':200,'recurrence_count':fresh['occurrence_count'],
                                'attention':fresh['attention'],'resolved':fresh['resolved']}
            result.update(complete=True,passed=all(checks.values()))
    except Exception as error:
        result['failure_kind']=type(error).__name__
    result['elapsed_s']=time.monotonic()-started
    if samples:
        result['resources']={'samples':len(samples),'min_available_bytes':min(row['available_bytes'] for row in samples),
                             'max_fan_rpm':max(max(row['fans_rpm'].values(),default=9999) for row in samples),
                             'max_temp_c':max(max(row['temperatures_c'].values(),default=999) for row in samples)}
    args.output.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as output:json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps({'complete':result['complete'],'passed':result['passed'],'checks':len(checks),'model_inference':False}))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
