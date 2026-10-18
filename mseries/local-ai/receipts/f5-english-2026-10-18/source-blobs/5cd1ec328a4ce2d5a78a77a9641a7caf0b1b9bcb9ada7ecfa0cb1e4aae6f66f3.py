import importlib.util, struct, unittest
spec = importlib.util.spec_from_file_location("ane", __file__.replace("test_ane_dictate", "dictation_ane"))
ane = importlib.util.module_from_spec(spec); spec.loader.exec_module(ane)


class Clean(unittest.TestCase):
    def test_trailing_dots_and_stray_tokens(self):
        self.assertEqual(ane.clean("peppered sauce........ Юн Ю"), "peppered sauce.")

    def test_double_dot(self):
        self.assertEqual(ane.clean("with potatoes.."), "with potatoes.")

    def test_normal_text_untouched(self):
        self.assertEqual(ane.clean("Hello, world. Fine."), "Hello, world. Fine.")

    def test_empty_and_only_garbage(self):
        self.assertEqual(ane.clean("... Юн"), "")


class Split(unittest.TestCase):
    def pcm(self, seconds, quiet_at):
        n = int(seconds * 16000)
        v = [0.5] * n
        for i in range(int(quiet_at * 16000), int(quiet_at * 16000) + 3200):
            v[i] = 0.0
        return struct.pack(f"<{n}f", *v)

    def test_short_audio_not_split(self):
        self.assertEqual(ane.split_points(self.pcm(20, 18)), [])

    def test_cut_lands_in_the_quiet_gap(self):
        cuts = ane.split_points(self.pcm(40, 22))
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0] / 4 / 16000, 22, delta=0.2)




class Rolling(unittest.TestCase):
    def test_stable_count_ignores_punctuation_and_case(self):
        self.assertEqual(ane.stable_count("He hoped, there".split(), "he hoped there would".split()), 3)

    def test_stable_count_stops_at_first_difference(self):
        self.assertEqual(ane.stable_count("a b c".split(), "a x c".split()), 1)

    def test_drop_overlap(self):
        tail = ["bruised", "potatoes", "and", "fat"]
        self.assertEqual(ane.drop_overlap(tail, "potatoes and fat mutton".split()), ["mutton"])

    def test_single_word_repeat_kept(self):
        self.assertEqual(ane.drop_overlap(["very"], ["very", "good"]), ["very", "good"])


if __name__ == "__main__":
    unittest.main()
