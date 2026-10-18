import importlib.machinery, importlib.util, os, unittest

path = os.path.join(os.path.dirname(__file__), "mseries-display-profiles")
loader = importlib.machinery.SourceFileLoader("dp", path)
spec = importlib.util.spec_from_loader("dp", loader)
dp = importlib.util.module_from_spec(spec)
loader.exec_module(dp)

TV = ("HDMI-1", "INS", "NS65DF710NA21", "0x01010101")


def raw(ext_connector="HDMI-1", with_ext=True, ext_mode="3840x2160@30.000"):
    panel = (("eDP-1", "u", "u", "u"), [("3024x1890@120.000", 3024, 1890, 120.0, 2.0, [1.0],
                                         {"is-current": True, "is-preferred": True})], {})
    mons = [panel]
    logical = [(0, 0, 2.0, 0, True, [("eDP-1", "u", "u", "u")], {})]
    if with_ext:
        tv = ((ext_connector,) + TV[1:], [
            ("3840x2160@30.000", 3840, 2160, 30.0, 1.0, [1.0], {"is-preferred": True, "is-current": ext_mode == "3840x2160@30.000"}),
            ("1920x1080@60.000", 1920, 1080, 60.0, 1.0, [1.0], {"is-current": ext_mode == "1920x1080@60.000"})], {})
        mons.append(tv)
        logical.append((1512, 0, 1.0, 0, False, [(ext_connector, "x", "x", "x")], {}))
    return (1, mons, logical, {})


class Profiles(unittest.TestCase):
    def setUp(self):
        _s, self.mons, self.lms = dp.parse_state(raw())

    def test_key_ignores_connector(self):
        _s, m2, _l = dp.parse_state(raw(ext_connector="DP-2"))
        self.assertEqual(dp.externals(self.mons), dp.externals(m2))

    def test_match_by_attached_set(self):
        prof = {"home": {"match": dp.externals(self.mons), "layout": dp.snapshot(self.mons, self.lms)}}
        self.assertEqual(dp.pick_profile(prof, self.mons), "home")
        _s, none, _l = dp.parse_state(raw(with_ext=False))
        self.assertIsNone(dp.pick_profile(prof, none))

    def test_roundtrip_on_other_connector(self):
        p = {"match": dp.externals(self.mons), "layout": dp.snapshot(self.mons, self.lms)}
        _s, m2, _l = dp.parse_state(raw(ext_connector="DP-2"))
        cfg = dp.build_config(p, m2)
        self.assertEqual([m[0] for lm in cfg for m in lm[5]], ["eDP-1", "DP-2"])
        self.assertEqual(cfg[1][5][0][1], "3840x2160@30.000")
        self.assertEqual(cfg[1][:2], (1512, 0))

    def test_missing_mode_falls_back_to_preferred(self):
        p = {"match": [], "layout": [{"x": 0, "y": 0, "scale": 1.0, "transform": 0, "primary": True,
                                      "monitors": [{"key": dp.externals(self.mons)[0], "mode": "9999x9999@1.000"}]}]}
        self.assertEqual(dp.build_config(p, self.mons)[0][5][0][1], "3840x2160@30.000")

    def test_absent_monitor_dropped_and_primary_kept(self):
        p = {"match": [], "layout": dp.snapshot(self.mons, self.lms)}
        _s, only, _l = dp.parse_state(raw(with_ext=False))
        cfg = dp.build_config(p, only)
        self.assertEqual(len(cfg), 1)
        self.assertTrue(cfg[0][4])

    def test_nudge_uses_a_different_safe_mode(self):
        info = self.mons["HDMI-1"]
        self.assertEqual(dp.nudge_modes(info, "3840x2160@30.000"), "1920x1080@60.000")
        self.assertEqual(dp.nudge_modes(info, "1920x1080@60.000"), "1920x1080@60.000")


if __name__ == "__main__":
    unittest.main()
