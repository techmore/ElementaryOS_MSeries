import unittest
from unittest.mock import patch
import dictation_resources as r
class QuietBoundary(unittest.TestCase):
 def test_exact_quiet_boundary_refuses_speech_only(self):
  policy=dict(r.DEFAULT_POLICY)
  for fan,temp in [(2700,40),(2500,63)]:
   sample={'fans_rpm':{'f':fan},'temperatures_c':{'t':temp}}
   with patch.object(r,'violations',return_value=[]):self.assertTrue(r.reasons(policy,sample=sample))
 def test_just_below_boundary_uses_shared_reserve(self):
  sample={'fans_rpm':{'f':2699},'temperatures_c':{'t':62.9}}
  with patch.object(r,'violations',return_value=['memory']) as shared:
   self.assertEqual(r.reasons(dict(r.DEFAULT_POLICY),7,sample),['memory']);self.assertEqual(shared.call_args.args[2],7)
if __name__=='__main__':unittest.main()
