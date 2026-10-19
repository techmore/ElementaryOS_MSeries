import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from dictation_pipeline import transform
from dictation_review import ReviewUnavailable


class PipelineTests(unittest.TestCase):
    def test_two_stages_keep_translation_and_use_the_same_reviewer(self):
        reviewer=Mock(side_effect=['translation','polished'])
        result=transform('original','translate-polish','French',reviewer)
        self.assertEqual(result.proposal,'polished');self.assertEqual(result.translation,'translation')
        self.assertEqual(reviewer.call_args_list[0].args,('original','translate','French'))
        self.assertEqual(reviewer.call_args_list[1].args,('translation','grammar','French'))

    def test_polish_unavailable_retains_translation_and_explicit_warning(self):
        reviewer=Mock(side_effect=['translation',ReviewUnavailable('waiting')])
        result=transform('original','translate-polish','French',reviewer)
        self.assertEqual(result.proposal,'translation');self.assertIsNotNone(result.warning)
        self.assertEqual(reviewer.call_count,2)

    def test_translation_failure_does_not_run_polish(self):
        reviewer=Mock(side_effect=ReviewUnavailable('waiting'))
        with self.assertRaises(ReviewUnavailable):transform('original','translate-polish','French',reviewer)
        self.assertEqual(reviewer.call_count,1)

    def test_single_mode_does_not_add_a_model_request(self):
        reviewer=Mock(return_value='proposed')
        self.assertEqual(transform('original','grammar','English',reviewer).proposal,'proposed')
        self.assertEqual(reviewer.call_count,1)


if __name__=='__main__':unittest.main()
