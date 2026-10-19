import configparser
import unittest
from session_startup import prepare

SOURCE = '''[io.elementary.wingpanel]
args=io.elementary.wingpanel
wait-for-n-panels=1
session-type=desktop
[io.elementary.dock]
args=/guarded/io.elementary.dock
wait-for-n-panels=1
session-type=desktop
[Greeter]
args=io.elementary.greeter
session-type=greeter
'''


class Startup(unittest.TestCase):
    def test_disabled_dock_is_not_a_panel_readiness_dependency(self):
        before = configparser.ConfigParser()
        before.read_string(SOURCE)
        after = configparser.ConfigParser()
        fixed = prepare(SOURCE, True)
        after.read_string(fixed)
        self.assertEqual(after['io.elementary.dock']['wait-for-n-panels'], '0')
        after['io.elementary.dock']['wait-for-n-panels'] = '1'
        self.assertEqual(dict(before['io.elementary.dock']), dict(after['io.elementary.dock']))
        for section in ('io.elementary.wingpanel', 'Greeter'):
            self.assertEqual(dict(before[section]), dict(after[section]))
        self.assertEqual(fixed, prepare(fixed, True))

    def test_enabled_dock_and_custom_no_dock_session_are_untouched(self):
        self.assertEqual(SOURCE, prepare(SOURCE, False))
        self.assertEqual('[Custom]\nargs=custom\n', prepare('[Custom]\nargs=custom\n', True))


if __name__ == '__main__':
    unittest.main()
