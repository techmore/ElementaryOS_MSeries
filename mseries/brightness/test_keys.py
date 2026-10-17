import importlib.machinery
import importlib.util
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

PATH = Path(__file__).parents[2] / 'mkosi.images/apple-silicon/mkosi.extra/usr/libexec/mseries-brightness'
loader = importlib.machinery.SourceFileLoader('keys', str(PATH))
spec = importlib.util.spec_from_loader('keys', loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class CurveTests(unittest.TestCase):
    max = 500

    def test_ends_of_the_scale(self):
        self.assertEqual(module.level_to_nits(0, self.max), module.FLOOR)
        self.assertEqual(module.level_to_nits(1, self.max), self.max)

    def test_curve_round_trips(self):
        for nits in (2, 3, 5, 10, 30, 120, 500):
            level = module.nits_to_level(nits, self.max)
            self.assertAlmostEqual(module.level_to_nits(level, self.max), nits, places=6)

    def test_ladder_is_distinct_sorted_and_fine_at_the_dim_end(self):
        steps = module.ladder(self.max)
        self.assertEqual(steps, sorted(set(steps)))
        self.assertEqual((steps[0], steps[-1]), (module.FLOOR, self.max))
        self.assertGreaterEqual(len([n for n in steps if n <= 30]), 5)
        # Each key press must look even: no step may raise the light by more than 1.5x
        # (integer nits cannot always do better, e.g. 2 -> 3).
        for low, high in zip(steps, steps[1:]):
            self.assertLessEqual(high / low, 1.5, (low, high))

    def test_keys_stop_at_the_ends(self):
        self.assertEqual(module.key_target(module.FLOOR, -1, self.max), module.FLOOR)
        self.assertEqual(module.key_target(self.max, 1, self.max), self.max)

    def test_keys_walk_from_an_arbitrary_value(self):
        up = module.key_target(30, 1, self.max)
        down = module.key_target(30, -1, self.max)
        self.assertGreater(up, 30)
        self.assertLess(down, 30)
        self.assertGreater(down, module.FLOOR)  # the old 5% key stepped 30 straight to 5

    def test_keys_reach_the_hardware_floor_and_never_go_off(self):
        value = 30
        for _ in range(40):
            value = module.key_target(value, -1, self.max)
        self.assertEqual(value, module.FLOOR)

    def test_tiny_panel_range_does_not_break(self):
        steps = module.ladder(10)
        self.assertEqual(steps[0], module.FLOOR)
        self.assertEqual(module.key_target(10, 1, 10), 10)


class SubFloorTests(unittest.TestCase):
    max = 500

    def test_sub_floor_ladder_continues_below_the_hardware_floor(self):
        value = 5
        seen = []
        for _ in range(12):
            value = module.key_target(value, -1, self.max, sub_floor=True)
            seen.append(value)
        self.assertEqual(seen[:3], [4, 3, 2])
        self.assertAlmostEqual(seen[-1], module.FLOOR * min(module.SUB_FLOOR))
        self.assertLess(seen[-1], module.FLOOR)

    def test_sub_floor_steps_are_ignored_without_the_dim_layer(self):
        self.assertEqual(module.key_target(2, -1, self.max, sub_floor=False), module.FLOOR)

    def test_keys_climb_back_out_of_the_dim_layer(self):
        low = module.FLOOR * min(module.SUB_FLOOR)
        value = low
        for _ in range(4):
            value = module.key_target(value, 1, self.max, sub_floor=True)
        self.assertEqual(value, module.FLOOR)
        self.assertEqual(module.key_target(value, 1, self.max, sub_floor=True), 3)

    def test_alpha_is_zero_at_the_floor_and_capped_far_below_it(self):
        self.assertEqual(module.dim_alpha(2, ), 0.0)
        self.assertEqual(module.dim_alpha(5), 0.0)
        self.assertEqual(module.dim_alpha(0), module.MAX_DIM_ALPHA)
        alphas = [module.dim_alpha(module.FLOOR * f) for f in module.SUB_FLOOR]
        self.assertEqual(alphas, sorted(alphas))
        self.assertTrue(all(0 < a < module.MAX_DIM_ALPHA for a in alphas))

    def test_alpha_round_trips_to_virtual_nits(self):
        for factor in module.SUB_FLOOR:
            nits = module.FLOOR * factor
            self.assertAlmostEqual(module.alpha_to_nits(module.dim_alpha(nits)), nits, places=6)

    def test_dim_file_is_written_atomically_and_cleared(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {'XDG_RUNTIME_DIR': directory}):
            module.write_dim(0)  # nothing to clear: must not create the file
            self.assertFalse(os.path.exists(os.path.join(directory, 'mseries-dim')))
            module.write_dim(0.4)
            self.assertAlmostEqual(module.read_dim(), 0.4)
            self.assertEqual(os.listdir(directory), ['mseries-dim'])
            module.write_dim(0)
            self.assertEqual(module.read_dim(), 0.0)

    def test_bad_dim_files_read_as_no_dim(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {'XDG_RUNTIME_DIR': directory}):
            path = os.path.join(directory, 'mseries-dim')
            for text in ('', 'abc', 'nan', '-1', '7'):
                with open(path, 'w') as handle:
                    handle.write(text)
                self.assertEqual(module.read_dim(), 0.0, text)

    def test_dim_support_requires_a_live_gala(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {'XDG_RUNTIME_DIR': directory}):
            self.assertFalse(module.dim_supported())
            with open(os.path.join(directory, 'mseries-dim.gala'), 'w') as handle:
                handle.write(f'{os.getpid()}\n')  # a live process, but not named gala
            self.assertFalse(module.dim_supported())
            with open(os.path.join(directory, 'mseries-dim.gala'), 'w') as handle:
                handle.write('999999999\n')  # a stale pid
            self.assertFalse(module.dim_supported())


class DocumentationTests(unittest.TestCase):
    """BRIGHTNESS.md quotes the ladder and the dim alphas; keep it honest."""

    text = (Path(__file__).parents[1] / 'BRIGHTNESS.md').read_text()

    def test_documented_ladder_matches_the_code(self):
        ladder = ', '.join(str(n) for n in module.ladder(500))
        self.assertIn(f'`{ladder}`', self.text)

    def test_documented_dim_alphas_match_the_code(self):
        for factor in module.SUB_FLOOR:
            virtual = module.FLOOR * factor
            self.assertIn(f'| {virtual:.1f} | {module.dim_alpha(virtual):.3f} |', self.text)

    def test_documented_constants_match_the_code(self):
        self.assertIn(f'capped at {module.MAX_DIM_ALPHA}', self.text)
        self.assertIn(f'more than {module.MAX_STEP_RATIO}x', self.text)


if __name__ == '__main__':
    unittest.main()
