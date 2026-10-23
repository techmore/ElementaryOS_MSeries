"""Synthetic durable inbox tests. No real journals, models, services or desktop."""
import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from alert_store import AlertStore,AlertConflict,MAX_ALERTS,MAX_EVENTS,MAX_GAPS
spec=importlib.util.spec_from_file_location('durable_watcher',HERE/'crash-watch.py')
watch=importlib.util.module_from_spec(spec);spec.loader.exec_module(watch)
EVENT={'program':'kernel/gpu','signal':'kernel fault','pid':'0','signature':'a'*16,'message':'asahi gpu fault at 0x1234567890'}


def record(cursor='s=one',boot='boot-a',when=1000000,message='asahi gpu fault at 0x1234567890'):
    return {'__CURSOR':cursor,'_BOOT_ID':boot,'__REALTIME_TIMESTAMP':str(when),'_TRANSPORT':'kernel','MESSAGE':message}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)/'state';self.store=AlertStore(self.directory)
    def add(self,cursor='one',when=1000000,boot='boot-a',event=EVENT):
        return self.store.ingest('journal',cursor,boot,when,event)

    def test_storm_counts_exact_cursor_retry_and_separate_boot_incidents(self):
        for i in range(400):self.add(str(i),1000000+i)
        row,=self.store.list_alerts();self.assertEqual(row['occurrence_count'],400)
        self.assertEqual(row['version'],400)
        self.assertTrue(self.add('399',1000399)['duplicate'])
        self.assertEqual(self.store.list_alerts()[0]['occurrence_count'],400)
        self.add('next-boot',1000500,'boot-b')
        self.assertEqual(len(self.store.list_alerts()),2)
        self.add('later-incident',700000000,'boot-a')
        self.assertEqual(len(self.store.list_alerts()),3)

    def test_cursor_and_event_survive_subprocess_restart_without_duplicate_counts(self):
        result=self.add()
        code="import sys;sys.path.insert(0,sys.argv[1]);from alert_store import AlertStore;s=AlertStore(sys.argv[2]);assert s.source_state('journal')['cursor']=='one';assert s.ingest('journal','one','boot-a',1000000,{ 'program':'kernel/gpu','signal':'kernel fault','signature':'"+'a'*16+"'})['duplicate'];print(s.list_alerts()[0]['occurrence_count'])"
        process=subprocess.run([sys.executable,'-c',code,str(HERE),str(self.directory)],capture_output=True,text=True,timeout=10)
        self.assertEqual(process.returncode,0,process.stderr);self.assertEqual(process.stdout.strip(),'1')
        self.assertEqual(AlertStore(self.directory).get_alert(result['alert']['alert_id'])['occurrence_count'],1)

    def test_failed_transaction_rolls_back_event_count_and_cursor_together(self):
        self.add()
        with patch.object(self.store,'_prune',side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaises(RuntimeError):self.add('two',1000001)
        reopened=AlertStore(self.directory)
        self.assertEqual(reopened.source_state('journal')['cursor'],'one')
        self.assertEqual(reopened.list_alerts()[0]['occurrence_count'],1)
        self.assertFalse(reopened.ingest('journal','two','boot-a',1000001,EVENT)['duplicate'])
        self.assertEqual(reopened.list_alerts()[0]['occurrence_count'],2)

    def test_ack_is_versioned_idempotent_and_never_resolves_new_occurrence(self):
        row=self.add()['alert'];seen=self.store.mark_seen(row['alert_id'],row['version'])
        ack=self.store.acknowledge(row['alert_id'],seen['version'])
        self.assertEqual(ack['attention'],'acknowledged');self.assertFalse(ack['resolved'])
        self.assertEqual(self.store.acknowledge(row['alert_id'],seen['version']),ack)
        self.add('new-event',1000001)
        with self.assertRaises(AlertConflict):self.store.acknowledge(row['alert_id'],ack['version'])
        fresh=self.store.get_alert(row['alert_id']);self.assertEqual(fresh['attention'],'new');self.assertFalse(fresh['resolved'])
        with self.assertRaises(ValueError):self.store.list_alerts(attention='resolved')

    def test_concurrent_collectors_count_each_identity_once_and_stale_ack_cannot_hide_occurrence(self):
        original=self.add()['alert']
        code="import sys;sys.path.insert(0,sys.argv[1]);from alert_store import AlertStore;s=AlertStore(sys.argv[2]);[s.ingest('journal',str(i),'boot-a',1000001+i,{'program':'kernel/gpu','signal':'kernel fault','signature':'"+'a'*16+"'}) for i in range(60)]"
        children=[subprocess.Popen([sys.executable,'-c',code,str(HERE),str(self.directory)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(3)]
        for child in children:
            out,err=child.communicate(timeout=20);self.assertEqual(child.returncode,0,err)
        row,=self.store.list_alerts();self.assertEqual(row['occurrence_count'],61)
        with self.assertRaises(AlertConflict):self.store.acknowledge(row['alert_id'],original['version'])

    def test_private_bounded_redacted_legacy_projection_and_read_only_access(self):
        self.add(event=EVENT|{'message':str(Path.home())+'/secret token=abc123 Authorization: Bearer hidden-value\x1b'*100})
        self.store.write_legacy();self.assertEqual(self.directory.stat().st_mode&0o777,0o700)
        for file in self.directory.iterdir():self.assertEqual(file.stat().st_mode&0o077,0)
        row=self.store.list_alerts()[0];self.assertNotIn('abc123',row['evidence']);self.assertNotIn('hidden-value',row['evidence'])
        self.assertLessEqual(len(row['evidence']),500);self.assertNotIn('\x1b',row['evidence'])
        reader=AlertStore(self.directory,read_only=True);self.assertEqual(reader.legacy_snapshot(),self.store.legacy_snapshot())
        with self.assertRaises(ValueError):reader.acknowledge(row['alert_id'],row['version'])
        output=json.loads((self.directory/'crashes.json').read_text());self.assertFalse(output['collector']['automatic_diagnosis'])
        self.assertEqual(output['collector']['notifications'],'disabled')

    def test_symlink_or_public_database_is_rejected(self):
        self.store.path.chmod(0o644)
        with self.assertRaises(ValueError):AlertStore(self.directory)
        self.store.path.chmod(0o600)
        link=Path(self.temp.name)/'link';link.symlink_to(self.directory,target_is_directory=True)
        with self.assertRaises(ValueError):AlertStore(link)
        self.store.path.unlink();self.store.path.symlink_to(Path(self.temp.name)/'outside')
        with self.assertRaises(ValueError):AlertStore(self.directory)

    def test_gaps_and_retention_are_explicit_and_bounded(self):
        self.add()
        with self.assertRaises(ValueError):self.store.clear_cursor('journal')
        self.store.record_gap('journal','cursor-unavailable');self.store.clear_cursor('journal')
        self.store.ingest('journal','one','boot-a',1000000,EVENT,replayed=True)
        self.assertEqual(self.store.source_state('journal')['cursor'],'one')
        for i in range(10):self.store.record_gap('journal','cursor-unavailable')
        self.assertEqual(len(self.store.legacy_snapshot()['collector']['gaps']),1)
        # Lower bounds during the test exercise pruning without thousands of IOs.
        with patch('alert_store.MAX_ALERTS',3),patch('alert_store.MAX_EVENTS',5),patch('alert_store.MAX_GAPS',2):
            for i in range(9):
                self.add('many'+str(i),700000000*i,event=EVENT|{'signature':format(i,'016x')})
                self.store.record_gap('journal','stream-ended')
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertLessEqual(db.execute('SELECT count(*) FROM alerts').fetchone()[0],3)
            self.assertLessEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],5)
            self.assertLessEqual(db.execute('SELECT count(*) FROM gaps').fetchone()[0],2)
        self.assertTrue(self.store.legacy_snapshot()['collector']['retention']['discarded_alerts']>0)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=AlertStore(Path(self.temp.name)/'state');self.collector=watch.Collector(self.store,clock=lambda:10)
    def command(self,body):return [sys.executable,'-u','-c',body]

    def test_real_subprocess_fragmented_stream_and_oversized_record_cleanup(self):
        data=json.dumps(record()).encode()+b'\n'+b'x'*(watch.MAX_LINE+10)+b'\n'+json.dumps(record('two',when=1000001)).encode()+b'\n'
        body='import sys,time;d='+repr(data)+';[(sys.stdout.buffer.write(d[i:i+127]),sys.stdout.buffer.flush()) for i in range(0,len(d),127)]'
        result=self.collector.run_command(self.command(body),replayed=True)
        self.assertEqual(result['returncode'],0)
        row,=self.store.list_alerts();self.assertEqual(row['occurrence_count'],2)
        self.assertTrue(row['replayed']);self.assertEqual(self.store.source_state('journal')['cursor'],'two')
        gaps=self.store.legacy_snapshot()['collector']['gaps'];self.assertEqual(gaps[0]['reason'],'record-too-large')

    def test_finite_provider_timeout_reaps_owned_child_and_records_unavailable(self):
        command=self.command("import os,sys,time;sys.stdout.close();sys.stderr.close();time.sleep(60)")
        self.collector.runner=lambda *_args,**_kwargs:self.collector.run_command(command)
        with patch.object(watch,'COMMAND_DEADLINE',.05):
            self.assertEqual(self.collector.run(),1)
        status=self.store.source_state('journal');self.assertEqual(status['status'],'unavailable')
        self.assertIn('journal-unavailable',[row['reason'] for row in self.store.legacy_snapshot()['collector']['gaps']])

    def test_sigterm_releases_owned_live_provider_and_marks_collector_stopped(self):
        import signal,time
        root=Path(self.temp.name);binary=root/'bin';binary.mkdir()
        pid_file=root/'provider.pid'
        script=binary/'journalctl'
        script.write_text('#!'+sys.executable+'\nimport json,os,sys,time\n'
            +'r='+repr(record())+'\n'
            +"if '--follow' in sys.argv:\n open(os.environ['TEST_PROVIDER_PID'],'w').write(str(os.getpid()))\n while True: time.sleep(1)\n"
            +"else: print(json.dumps(r))\n")
        script.chmod(0o700)
        state=root/'live-state'
        child=subprocess.Popen([sys.executable,str(HERE/'crash-watch.py'),'--state-dir',str(state)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ.get('PATH',''),TEST_PROVIDER_PID=str(pid_file)))
        try:
            deadline=time.monotonic()+5
            while not pid_file.exists() and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue(pid_file.exists())
            provider=int(pid_file.read_text())
            child.send_signal(signal.SIGTERM)
            out,err=child.communicate(timeout=5)
            self.assertEqual(child.returncode,0,err)
            self.assertEqual(AlertStore(state).source_state('journal')['status'],'stopped')
            with self.assertRaises(ProcessLookupError):os.kill(provider,0)
        finally:
            if child.poll() is None:child.kill();child.wait()

    def test_cursor_rotation_gap_backfill_and_follow_are_separate_no_popups_or_models(self):
        self.collector.record(json.dumps(record()))
        calls=[]
        def runner(command,**kwargs):
            calls.append((command,kwargs))
            if len(calls)==1:return {'returncode':1,'cursor_unavailable':True,'records':0}
            if len(calls)==2:
                self.collector.record(json.dumps(record('two',when=1000001)),replayed=True)
                return {'returncode':0,'cursor_unavailable':False,'records':1}
            return {'returncode':0,'cursor_unavailable':False,'records':0}
        self.collector.runner=runner
        self.assertEqual(self.collector.run(),1)
        self.assertIn('--after-cursor=s=one',calls[0][0]);self.assertEqual(calls[1][1],{'replayed':True})
        self.assertIn('--after-cursor=two',calls[2][0])
        snapshot=self.store.legacy_snapshot();self.assertIn('cursor-unavailable',[x['reason'] for x in snapshot['collector']['gaps']])
        self.assertEqual(snapshot['events'][0]['occurrence_count'],2)
        self.assertFalse(snapshot['collector']['automatic_diagnosis'])

    def test_first_boot_anchors_existing_fault_without_replaying_it_as_new(self):
        calls=[]
        def runner(command,**kwargs):
            calls.append((command,kwargs))
            if kwargs.get('anchor'):self.collector.record(json.dumps(record()),anchor=True)
            return {'returncode':0,'cursor_unavailable':False,'records':1 if kwargs else 0}
        self.collector.runner=runner;self.collector.run()
        self.assertEqual(self.store.list_alerts(),[])
        self.assertIn('--after-cursor=s=one',calls[1][0])

    def test_cli_replay_restart_and_ack_have_no_journal_or_model_subprocess(self):
        state=Path(self.temp.name)/'cli';state.mkdir()
        (state/'auto-diagnose').touch()
        fixture=Path(self.temp.name)/'synthetic.jsonl';fixture.write_text('\n'.join(json.dumps(record(str(i),when=1000000+i)) for i in range(5))+'\n')
        command=[sys.executable,str(HERE/'crash-watch.py'),'--state-dir',str(state),'--replay-file',str(fixture)]
        for _ in range(2):
            p=subprocess.run(command,capture_output=True,text=True,timeout=10);self.assertEqual(p.returncode,0,p.stderr)
        store=AlertStore(state);row,=store.list_alerts();self.assertEqual(row['occurrence_count'],5)
        p=subprocess.run([sys.executable,str(HERE/'alerts.py'),'--state-dir',str(state),'ack',row['alert_id'],'--version',str(row['version'])],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr);self.assertFalse(json.loads(p.stdout)['resolved'])
        self.assertEqual(store.list_alerts()[0]['attention'],'acknowledged')


if __name__=='__main__':unittest.main()
