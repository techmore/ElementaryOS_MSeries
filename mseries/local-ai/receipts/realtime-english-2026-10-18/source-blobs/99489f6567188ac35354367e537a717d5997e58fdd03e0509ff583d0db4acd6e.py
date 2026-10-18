import unittest
from dictation_live import LiveEnglishReview


class LiveTests(unittest.TestCase):
    def setUp(self):self.live=LiveEnglishReview()
    def observe(self,text,now=0,capturing=True,eligible=True,enabled=True,previews=True):
        self.live.observe(text,enabled,previews,capturing,eligible,now)
    def test_latest_only_and_prefix_suggestions(self):
        self.observe('we was');r=self.live.take(0)
        self.observe('we was late',1);self.assertIsNone(self.live.take(10))
        self.assertEqual(self.live.finish(r,'We were'),('We were',False))
        self.assertEqual(self.live.take(3).source,'we was late')
    def test_replacement_or_disabling_discards_answer(self):
        for change in [dict(text='new'),dict(text='we was',enabled=False)]:
            self.setUp();self.observe('we was');r=self.live.take(0);self.observe(**change)
            self.assertIsNone(self.live.finish(r,'stale'))
    def test_other_apps_and_idle_typing_never_start_review(self):
        self.observe('old text',capturing=False);self.assertIsNone(self.live.take(20))
        self.observe('another app',eligible=False);self.assertIsNone(self.live.take(20))
    def test_final_cached_source_is_not_reviewed_twice(self):
        self.observe('we was late');r=self.live.take(0);self.live.finish(r,'We were late.')
        self.observe('we was late',now=4,capturing=False)
        self.assertIsNone(self.live.take(4));self.assertTrue(self.live.finalized)
    def test_default_final_only_waits_until_speech_ends(self):
        self.observe('we was late',previews=False);self.assertIsNone(self.live.take(5))
        self.observe('we was late',now=6,capturing=False,previews=False);r=self.live.take(6)
        self.assertEqual(self.live.finish(r,'We were late.'),('We were late.',True))
    def test_final_settles_and_unchanged_failure_does_not_spin(self):
        self.observe('one');self.observe('one two',now=1,capturing=False)
        self.assertIsNone(self.live.take(1.2));r=self.live.take(2)
        self.live.finish(r,error='waiting');self.assertIsNone(self.live.take(10))
        self.observe('one two three',now=11,capturing=False);self.assertIsNotNone(self.live.take(12))
    def test_empty_or_oversize_never_autoruns(self):
        for source in ['', 'a'*4001]:
            self.observe(source);self.assertIsNone(self.live.take(20))


if __name__=='__main__':unittest.main()
