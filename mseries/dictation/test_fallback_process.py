"""A cancelled fallback retires its own blocked CPU child without another utterance."""
import importlib.util,subprocess,sys,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('fallback_control',Path(__file__).with_name('stream-dictate.py'));m=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'numpy':Mock()}):spec.loader.exec_module(m)
class FallbackProcess(unittest.TestCase):
 def test_cancel_during_blocked_native_process_reaps_it(self):
  children=[];real=subprocess.Popen;start=time.monotonic()
  def create(*args,**kwargs):
   child=real([sys.executable,'-c','import time;time.sleep(20)'],**kwargs);children.append(child);return child
  with patch.object(m.subprocess,'Popen',create):
   self.assertEqual(m.whisper_fallback(bytes(320),cancelled=lambda:time.monotonic()-start>.1),'')
  self.assertLess(time.monotonic()-start,2);self.assertIsNotNone(children[0].poll())
 def test_already_cancelled_never_starts_fallback(self):
  with patch.object(m.subprocess,'Popen') as spawn:
   self.assertEqual(m.whisper_fallback(bytes(320),cancelled=lambda:True),'');spawn.assert_not_called()
if __name__=='__main__':unittest.main()
