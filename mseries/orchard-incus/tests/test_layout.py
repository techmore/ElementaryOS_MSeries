"""Layout regressions that need GTK. Skipped without a display; run headless with:
xvfb-run -a env -u DBUS_SESSION_BUS_ADDRESS GSK_RENDERER=cairo GDK_BACKEND=x11 python3 -m unittest tests.test_layout -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Granite", "7.0")
    from gi.repository import Gtk
    HAVE = Gtk.init_check()
except Exception:  # noqa: BLE001
    HAVE = False

H = None
if HAVE:
    H = Gtk.Orientation.HORIZONTAL


@unittest.skipUnless(HAVE, "needs a display (use xvfb-run)")
class Layout(unittest.TestCase):
    def test_tiles_fit_a_narrow_pane_by_wrapping(self):
        from orchard_incus.ui import TileRow, card, lbl
        row = TileRow()
        for t in ("Memory", "CPU", "Disk", "Processes"):
            row.add(card(lbl(t, "dim"), lbl("10.4 MiB", "stat-val")))
        minimum = row.measure(H, -1)[0]
        # FlowBoxChild padding varies with GTK/theme (GTK 4.22 adds 12px for
        # two children here). Check the actual 780px window's detail budget.
        available = 780 - 240 - 2 * 20  # window minus sidebar and detail margins
        self.assertLessEqual(minimum, available, "two tile columns must fit the narrow detail pane")

    def test_action_row_can_shrink(self):
        from orchard_incus.ui import pill_button
        fb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=12)
        for t in ("Stop", "Restart", "Pause", "Shell", "Snapshot"):
            fb.append(pill_button(t, "media-playback-stop-symbolic"))
        self.assertLess(fb.measure(H, -1)[0], 200)


if __name__ == "__main__":
    unittest.main()
