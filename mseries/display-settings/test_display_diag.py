import os, sys, unittest
sys.path.insert(0, os.path.dirname(__file__))
import display_diag as d

HP = "[1] apple-dcp: DP2HDMI HPD irq, connected:1"
MS = "[2] apple-dcp: set_digital_out_mode finished:8190"
SW = "[3] apple-dcp: swallowed swap ID 80 as timinsg are not enabled for External Display"


def facts(log, conn="connected", tb=(), gala=None):
    gala = gala if gala is not None else {"HDMI-1": {"modes": [(3840, 2160, 30.0)], "current": (3840, 2160, 30.0), "preferred": (3840, 2160, 30.0)}}
    return {"gala": gala, "drm": {"HDMI-A-1": {"status": conn}, "eDP-1": {"status": "connected"}},
            "thunderbolt": list(tb), "log": log, "dprx_bypass": "Y"}


def titles(f):
    return [x[1] for x in d.diagnose(f)]


class Diag(unittest.TestCase):
    def test_frames_dropped_after_replug(self):
        r = d.diagnose(facts([MS, HP, SW]))
        self.assertTrue(any(x[0] == d.BAD and x[3] == "reapply" for x in r))

    def test_frames_dropped_even_after_a_completed_modeset(self):
        # the black-screen case: modeset finished, then the engine still swallows swaps
        r = d.diagnose(facts([HP, MS, SW]))
        self.assertTrue(any(x[0] == d.BAD and "discarding frames" in x[1] for x in r))
        self.assertFalse(any(x[0] == d.OK for x in r))

    def test_modeset_without_drops_is_not_claimed_as_a_picture(self):
        r = d.diagnose(facts([SW, HP, MS]))
        self.assertFalse(any(x[0] in (d.BAD, d.OK) for x in r if "HDMI-A-1" in x[1]))
        self.assertTrue(any("cannot confirm" in x[2] for x in r))

    def test_hotplug_without_modeset_waits(self):
        r = d.diagnose(facts([MS, HP]))
        self.assertTrue(any(x[0] == d.WARN and "waiting for a video mode" in x[1] for x in r))

    def test_nothing_connected(self):
        r = d.diagnose(facts([], conn="disconnected"))
        self.assertTrue(any("No external display" in x[1] for x in r))

    def test_dock_usb_only(self):
        r = d.diagnose(facts([], conn="disconnected", tb=["WD22TB4 Thunderbolt Dock"]))
        self.assertTrue(any("no video yet" in x[1] for x in r))

    def test_dock_display_engine_timeout(self):
        log = ["x thunderbolt-apple-nhi: 0:5 <-> 1:14 (DP): activating", "x thunderbolt-apple-nhi: DP source preparation failed: -110"]
        r = d.diagnose(facts(log, conn="disconnected", tb=["WD22TB4 Thunderbolt Dock"]))
        self.assertTrue(any(x[0] == d.WARN and "times out" in x[1] for x in r))

    def test_kernel_sees_monitor_desktop_does_not(self):
        r = d.diagnose(facts([HP, MS], gala={}))
        self.assertTrue(any("not in the desktop" in x[1] for x in r))

    def test_4k_30hz_note(self):
        self.assertTrue(any("only offered at 30 Hz" in t for t in titles(facts([MS]))))


if __name__ == "__main__":
    unittest.main()
