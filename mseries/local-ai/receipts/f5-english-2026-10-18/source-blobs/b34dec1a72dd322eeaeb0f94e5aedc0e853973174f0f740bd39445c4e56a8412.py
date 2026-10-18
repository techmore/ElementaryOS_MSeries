"""Cross-thread output revocation and provisional leases; no speech/app dependency."""
import importlib.util,sys,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('f5_output_controller',HERE/'stream-dictate.py');s=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'numpy':Mock()}):spec.loader.exec_module(s)

class QueuedOutput(unittest.TestCase):
 def test_cancel_discards_queued_preview_and_commit_before_next_session(self):
  entered=threading.Event();release=threading.Event();calls=[]
  def send(method,token=None,text=None):
   calls.append((method,token,text))
   if text=='blocked':entered.set();release.wait(2)
  with patch.object(s,'OUTPUT','ibus'),patch.object(s,'DRY',False),patch.object(s,'input_call',send):
   t=s.Typer();t.submit('blocked','old');self.assertTrue(entered.wait(1))
   t.preview('stale','old');t.submit('late','old');t.discard();release.set();self.assertTrue(t.drain(2))
   t.preview('new draft','new');t.submit('final','new');t.finish('new');self.assertTrue(t.drain(2))
   self.assertEqual(calls,[('commit','old','blocked'),('preview','new','new draft'),('commit','new','final'),('finish','new',None)])
 def test_no_preedit_is_sent_to_unverified_keyboard_fallback(self):
  with patch.object(s,'input_call') as send:
   t=s.Typer();t.preview('do not type',None);self.assertTrue(t.drain(1));send.assert_not_called()
 def test_focus_invalidation_clears_preview_and_revokes_token(self):
  spec=importlib.util.spec_from_file_location('f5_focus',HERE/'dictation-input.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  f=m.FocusSession();f.focus(object(),'gtk');f.content(0,0);token=f.begin();f.on_invalidate=Mock();f.invalidate();f.on_invalidate.assert_called_once()
  with self.assertRaises(ValueError):f.check(token)

if __name__=='__main__':unittest.main()
