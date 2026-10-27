import unittest

import check_frozen as cf

FROZEN = ['rust/msdk', 'mseries/SDK-PARITY.md']


class FrozenTests(unittest.TestCase):
    def test_hits_and_exemptions(self):
        changed = ['rust/msdk/src/lib.rs', 'rust/msdk-gtk/a.rs', 'rust/msdk/FROZEN.md',
                   'mseries/SDK-PARITY.md', 'mseries/ROADMAP.md']
        self.assertEqual(cf.hits(changed, FROZEN),
                         ['mseries/SDK-PARITY.md', 'rust/msdk/src/lib.rs'])

    def test_manifest_paths_exist(self):
        for path in cf.frozen_paths():
            self.assertTrue((cf.ROOT / path).exists(), path)


if __name__ == '__main__':
    unittest.main()
