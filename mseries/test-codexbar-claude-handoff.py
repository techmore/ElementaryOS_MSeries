#!/usr/bin/env python3
"""Handoffs use isolated fixtures. Never read owner conversations or contact a provider/GitHub."""
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

import codexbar_claude_handoff as h
import codexbar_claude_history as history

S = '11111111-1111-4111-8111-111111111111'
T = '22222222-2222-4222-8222-222222222222'
O = '33333333-3333-4333-8333-333333333333'
SID = 'local_44444444-4444-4444-8444-444444444444'
CLI = '55555555-5555-4555-8555-555555555555'
SECRET = 'sk-ant-this-is-a-private-fixture-token'
SUMMARY = '# Goal\nImplement fixture handoff.\n\n# Progress\nTests pass.\n\n# Next steps\nReview and continue work.\n'

class HandoffTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name)
        self.cwd = self.root / 'workspace'; self.cwd.mkdir()
        self.projects = self.root / 'projects'; self.project = self.projects / 'workspace'; self.project.mkdir(parents=True)
        self.transcript = self.project / (CLI + '.jsonl')
        rows = [dict(type='user', message={'content':'Implement the fixture'}),
                dict(type='assistant',message={'content':[{'type':'thinking','thinking':SECRET,'signature':SECRET},
                    {'type':'text','text':'Updated app.py and tests passed.'}, {'type':'tool_use','input':SECRET}]}),
                dict(type='user',message={'content':[{'type':'tool_result','content':SECRET}]} )]
        self.transcript.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
        self.record = {'sessionId':SID,'cliSessionId':CLI,'cwd':str(self.cwd),'title':'Fixture task','lastFocusedAt':5}
        self.item = {'record':self.record,'transcript':self.transcript,'existing':False}
        self.plan = history.TransferPlan(S,T,O,self.root/'Claude',self.projects,[self.item])
        source=self.plan.app_root/'claude-code-sessions'/S/O
        source.mkdir(parents=True)
        (source/(SID+'.json')).write_text(json.dumps(self.record))
        self.store = self.root/'private/handoffs'
        self.info = {'root':str(self.cwd),'repository':'owner/repo','branch':'feature','status':' M app.py'}

    def prepare(self):
        with mock.patch.object(h,'summarize',return_value=(SUMMARY,'model-summary')), mock.patch.object(h,'git_info',return_value=self.info):
            return h.prepare(self.plan,self.store,'fake-claude')

    def test_extract_visible_text_only(self):
        text=h.excerpts(self.transcript)
        self.assertIn('Implement the fixture',text); self.assertIn('app.py',text)
        self.assertNotIn(SECRET,text); self.assertNotIn('signature',text); self.assertNotIn('tool_result',text)

    def test_context_is_bounded_and_malformed_lines_are_ignored(self):
        self.transcript.write_text('{broken\n'+ '\n'.join(json.dumps({'type':'user','message':{'content':'x'*10000}}) for _ in range(100)))
        self.assertLessEqual(len(h.excerpts(self.transcript)),h.MAX_CONTEXT)

    def test_source_selection_prefers_focus_and_skips_archived(self):
        archived={'record':dict(self.record,lastFocusedAt=100,isArchived=True)}
        self.plan.sessions.append(archived)
        self.assertIs(h.active_item(self.plan),self.item)
        self.record['isArchived']=True
        self.assertIsNone(h.active_item(self.plan))

    def test_tool_free_fresh_cli_call_receives_text_on_stdin(self):
        response=subprocess.CompletedProcess([],0,json.dumps({'result':SUMMARY}),SECRET)
        with mock.patch.dict(h.os.environ,{'ANTHROPIC_API_KEY':SECRET,'ANTHROPIC_BASE_URL':'https://invalid.example'}), mock.patch.object(h.subprocess,'run',return_value=response) as run:
            text,kind=h.summarize('claude','visible text',self.info,'Fixture')
        args=run.call_args.args[0]; options=run.call_args.kwargs
        self.assertEqual(kind,'model-summary'); self.assertIn(SUMMARY,text)
        for flag in ('--safe-mode','--setting-sources','--no-session-persistence','--strict-mcp-config','--disable-slash-commands'):self.assertIn(flag,args)
        self.assertEqual(args[args.index('--tools')+1],'')
        self.assertNotIn('visible text',args); self.assertIn('visible text',options['input'])
        self.assertEqual(options['timeout'],45)
        self.assertNotIn('ANTHROPIC_API_KEY',options['env'])
        self.assertNotIn('ANTHROPIC_BASE_URL',options['env'])

    def test_quota_timeout_invalid_output_and_missing_cli_use_labeled_emergency(self):
        for result in (subprocess.CompletedProcess([],1,'{"is_error":true,"result":"quota"}',SECRET),
                       subprocess.CompletedProcess([],0,'not json',SECRET)):
            with mock.patch.object(h.subprocess,'run',return_value=result):
                text,kind=h.summarize('claude','visible '+SECRET,self.info,'Fixture')
            self.assertEqual(kind,'emergency-excerpts');self.assertNotIn(SECRET,text)
        with mock.patch.object(h.subprocess,'run',side_effect=subprocess.TimeoutExpired('claude',45)):
            self.assertEqual(h.summarize('claude','text',self.info,'Fixture')[1],'emergency-excerpts')
        self.assertEqual(h.summarize(None,'text',self.info,'Fixture')[1],'emergency-excerpts')

    def test_private_artifact_and_fresh_seed_preserve_original(self):
        before=self.transcript.read_bytes(); brief=self.prepare()
        self.assertEqual((brief['folder']/'handoff.md').stat().st_mode&0o777,0o600)
        self.assertEqual(self.store.stat().st_mode&0o777,0o700)
        h.install(self.plan,brief)
        receipt,text,_=h.load_latest(self.store)
        destination=self.plan.app_root/'claude-code-sessions'/T/O/(receipt['handoffSession']+'.json')
        record=json.loads(destination.read_text())
        self.assertNotEqual(record['cliSessionId'],CLI);self.assertEqual(record['cwd'],str(self.cwd))
        seeded=(self.project/(record['cliSessionId']+'.jsonl')).read_text()
        self.assertIn('Next steps',seeded);self.assertNotIn(SECRET,seeded)
        self.assertNotIn('thinking',seeded);self.assertNotIn('signature',seeded)
        self.assertEqual(self.transcript.read_bytes(),before)
        self.assertEqual(record['permissionMode'],'default');self.assertFalse(record['isArchived'])

    def test_no_active_source_creates_no_handoff(self):
        self.record['isArchived']=True
        self.assertIsNone(h.prepare(self.plan,self.store,None))

    def test_reinstall_is_idempotent_and_prepared_copy_is_recoverable_before_switch(self):
        brief=self.prepare()
        self.assertEqual(h.load_latest(self.store)[0]['id'],brief['receipt']['id'])
        h.install(self.plan,brief)
        first=dict(brief['receipt'])
        h.install(self.plan,brief)
        self.assertEqual(first['handoffCliSession'],brief['receipt']['handoffCliSession'])
        self.assertEqual(len(list(self.project.glob('*.jsonl'))),2)

    def test_same_account_restart_does_not_spend_tokens_for_a_new_handoff(self):
        self.plan.target=self.plan.source
        with mock.patch.object(h,'summarize') as summary:
            self.assertIsNone(h.prepare(self.plan,self.store,'claude'))
        summary.assert_not_called()

    def test_credential_screen_handles_json_and_authorization(self):
        for text in ('api_key=abc123', '{"accessToken":"abc123"}', 'Authorization: Bearer abc123'):
            self.assertNotIn('abc123',h.scrub(text))
            self.assertEqual(h.scrub(h.scrub(text)),h.scrub(text))

    def test_integrity_check_rejects_changed_artifact(self):
        brief=self.prepare();h.install(self.plan,brief)
        (brief['folder']/'handoff.md').write_text('changed')
        with self.assertRaises(ValueError):h.load_latest(self.store)

    def test_prepare_and_install_never_publish(self):
        with mock.patch.object(h,'publish_reviewed') as publish:
            h.install(self.plan,self.prepare())
        publish.assert_not_called()

    def test_publication_requires_supported_repo_and_rejects_tokens(self):
        for receipt,text in (({'repository':'evil.example/owner/repo'},'hello'),({'repository':'owner/repo'},SECRET)):
            with mock.patch.object(h.subprocess,'run') as run:
                with self.assertRaises(ValueError):h.publish_reviewed(receipt,text)
                run.assert_not_called()

    def test_github_publication_only_sends_reviewed_text_to_separate_branch(self):
        receipt=self.prepare()['receipt']; payloads=[]
        replies=[{'default_branch':'main'},{'object':{'sha':'abc'}},None,{},None,{},[],{'html_url':'https://github.com/owner/repo/pull/1'}]
        def api(command,**kw):
            payloads.append((command,json.loads(kw['input']) if kw.get('input') else None))
            reply=replies.pop(0)
            return subprocess.CompletedProcess(command,1 if reply is None else 0,json.dumps(reply),'HTTP 404' if reply is None else '')
        with mock.patch.object(h.subprocess,'run',side_effect=api):
            self.assertEqual(h.publish_reviewed(receipt,'Reviewed public-safe work brief.'),'https://github.com/owner/repo/pull/1')
        self.assertTrue(payloads[-1][1]['draft'])
        self.assertTrue(payloads[-1][1]['head'].startswith('codex/handoff-'))
        self.assertTrue(all('git' not in command[:1] for command,_ in payloads))

    def test_publication_retry_updates_existing_branch_and_reuses_draft(self):
        receipt=self.prepare()['receipt']; calls=[]
        replies=[{'default_branch':'main'},{'object':{'sha':'abc'}},{'object':{'sha':'previous'}},
                 {'sha':'old-file-sha'},{},[{'html_url':'https://github.com/owner/repo/pull/1'}]]
        def api(command,**kw):
            calls.append((command,json.loads(kw['input']) if kw.get('input') else None))
            return subprocess.CompletedProcess(command,0,json.dumps(replies.pop(0)),'')
        with mock.patch.object(h.subprocess,'run',side_effect=api):
            self.assertEqual(h.publish_reviewed(receipt,'Edited and reviewed brief.'),'https://github.com/owner/repo/pull/1')
        self.assertEqual(calls[4][1]['sha'],'old-file-sha')
        self.assertEqual(len(calls),6)

    def test_github_failure_keeps_local_handoff(self):
        brief=self.prepare();h.install(self.plan,brief)
        with mock.patch.object(h.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'',SECRET)):
            with self.assertRaises(ValueError):h.publish_reviewed(brief['receipt'],'reviewed text')
        self.assertEqual(h.load_latest(self.store)[1],SUMMARY+'\n')

if __name__=='__main__':unittest.main()
