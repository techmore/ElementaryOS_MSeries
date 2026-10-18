from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dictation_model import LazyModel, ModelHeadroom


class ModelTests(unittest.TestCase):
    def test_cold_warm_timeout_and_reload(self):
        now = [0]
        factory = Mock(side_effect=[Mock(), Mock()])
        cache = LazyModel(factory, clock=lambda: now[0])
        admit = Mock(return_value=True)
        self.assertFalse(cache.loaded)
        with cache.use(admit) as first:
            self.assertFalse(cache.trim(force=True))
            first.close.assert_not_called()
        now[0] = 59
        self.assertFalse(cache.trim())
        with cache.use(admit) as warm:
            self.assertIs(warm, first)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual([call.args[0] for call in admit.call_args_list], [1024**3, 256 * 1024**2])
        now[0] = 119
        self.assertTrue(cache.trim())
        first.close.assert_called_once()
        with cache.use(admit) as second:
            self.assertIsNot(second, first)
        self.assertEqual(admit.call_args.args[0], 1024**3)

    def test_pressure_releases_without_waiting_for_timeout(self):
        model = Mock()
        cache = LazyModel(lambda: model)
        with cache.use(lambda _: True): pass
        self.assertTrue(cache.trim(force=True))
        self.assertFalse(cache.loaded)
        self.assertFalse(cache.trim(force=True))
        model.close.assert_called_once()

    def test_insufficient_admission_does_not_load(self):
        factory = Mock()
        cache = LazyModel(factory)
        with self.assertRaises(ModelHeadroom):
            with cache.use(lambda _: False): self.fail('Loaded without headroom')
        factory.assert_not_called()
        self.assertFalse(cache.loaded)

    def test_overlapping_use_is_refused_and_active_model_not_closed(self):
        cache = LazyModel(Mock())
        with cache.use(lambda _: True):
            with self.assertRaises(RuntimeError):
                with cache.use(lambda _: True): self.fail('Overlapping model use')
            self.assertFalse(cache.trim(force=True))

    def test_factory_and_consumer_errors_release_exclusive_lease(self):
        model = Mock()
        cache = LazyModel(Mock(side_effect=[ValueError('load failed'), model]))
        with self.assertRaises(ValueError):
            with cache.use(lambda _: True): pass
        with self.assertRaises(RuntimeError):
            with cache.use(lambda _: True): raise RuntimeError('capture failed')
        self.assertTrue(cache.trim(force=True))
        model.close.assert_called_once()


if __name__ == '__main__': unittest.main()
