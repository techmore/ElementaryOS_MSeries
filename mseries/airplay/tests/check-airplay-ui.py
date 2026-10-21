#!/usr/bin/python3
"""Actual GTK3 window, delayed fake backends; never operates PipeWire."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import subprocess
import threading
import time
import unittest
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

path = Path(__file__).resolve().parents[1] / 'mseries-airplay-outputs'
loader = importlib.machinery.SourceFileLoader('airplay_ui', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
ui = importlib.util.module_from_spec(spec)
loader.exec_module(ui)
ui.FAKE = True
original_dump = ui.pw_dump


def descendants(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descendants(child)


class AirplayUI(unittest.TestCase):
    def test_delayed_loading_toggle_failure_retry_and_close(self):
        main = threading.get_ident()
        state = {'stage': 0, 'ticks': 0, 'failure': False, 'selected': set(), 'calls': 0, 'empty': False, 'long': False}
        paint = {'tag': None, 'frames': 0, 'handler': None}
        errors = []
        def dump():
            self.assertNotEqual(threading.get_ident(), main)
            time.sleep(.2)
            if state['failure']:
                raise RuntimeError('Synthetic backend failure')
            if state['empty']:
                return []
            result = original_dump()
            if state['long']:
                result[0]['info']['props']['node.description'] = 'Synthetic receiver ' + '非常に長い名前' * 20
            return result
        ui.pw_dump = dump
        ui.core.load_state = lambda: state['selected']
        def enabled(key, on):
            self.assertNotEqual(threading.get_ident(), main)
            state['calls'] += 1
            time.sleep(.2)
            (state['selected'].add if on else state['selected'].discard)(key)
        ui.set_enabled = enabled
        def capture_after_frames(window, tag):
            output = os.environ.get('MSERIES_UI_CAPTURE')
            if not output:
                return True
            # Widget values update before GTK allocation/paint. Allow the normal
            # main loop to complete two frames; never nest a loop in tick().
            clock = window.get_frame_clock()
            if paint['tag'] != tag:
                paint.update(tag=tag, frames=0)
                def after_paint(_clock):
                    paint['frames'] += 1
                    if paint['frames'] < 2:
                        window.queue_draw()
                        clock.request_phase(Gdk.FrameClockPhase.PAINT)
                paint['handler'] = clock.connect_after('after-paint', after_paint)
                window.queue_draw()
                clock.request_phase(Gdk.FrameClockPhase.PAINT)
                return False
            if paint['frames'] < 2:
                return False
            clock.disconnect(paint['handler'])
            paint['handler'] = None
            window.get_display().sync()
            Path(output).mkdir(parents=True, exist_ok=True)
            subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'x11grab',
                            '-draw_mouse', '0', '-window_id', str(window.get_window().get_xid()),
                            '-i', os.environ['DISPLAY'], '-frames:v', '1',
                            str(Path(output) / ('airplay-' + tag + '.png'))], check=True, timeout=3)
            return True
        started = time.monotonic()
        def tick():
            try:
                state['ticks'] += 1
                window = next(w for w in Gtk.Window.list_toplevels() if w.get_title() == 'AirPlay Outputs')
                widgets = list(descendants(window))
                refresh = next(w for w in widgets if isinstance(w, Gtk.Button) and w.get_label() == 'Refresh')
                toggles = [w for w in widgets if isinstance(w, Gtk.CheckButton)]
                labels = [w.get_text() for w in widgets if isinstance(w, Gtk.Label)]
                self.assertEqual(window.get_scale_factor(), int(os.environ.get('GDK_SCALE', '1')))
                if time.monotonic() - started > 8:
                    raise AssertionError('Private AirPlay fixture timed out')
                stage = state['stage']
                if stage == 0:
                    self.assertFalse(refresh.get_sensitive())
                    self.assertIn('Finding AirPlay receivers…', labels)
                    state['stage'] = 1
                elif stage == 1 and refresh.get_sensitive():
                    self.assertEqual(len(toggles), 4)
                    self.assertTrue(all(toggle.get_label() for toggle in toggles))
                    self.assertTrue(any('0 selected.' in label for label in labels))
                    self.assertTrue(all(toggle.get_allocation().height > 0 for toggle in toggles))
                    self.assertTrue(all(toggle.get_mapped() for toggle in toggles))
                    if not capture_after_frames(window, 'ready'):
                        return True
                    self.assertGreaterEqual(state['ticks'], 5)
                    toggles[0].set_active(True)
                    self.assertFalse(refresh.get_sensitive())
                    state['stage'] = 2
                elif stage == 2 and refresh.get_sensitive():
                    self.assertEqual(state['calls'], 1)
                    self.assertTrue(toggles[0].get_active())
                    state['failure'] = True
                    refresh.clicked()
                    state['stage'] = 3
                elif stage == 3 and refresh.get_sensitive():
                    self.assertTrue(any('Could not update' in label for label in labels))
                    self.assertTrue(toggles[0].get_active())  # retain last confirmed data
                    if not capture_after_frames(window, 'error'):
                        return True
                    state['failure'] = False
                    refresh.clicked()
                    state['stage'] = 4
                elif stage == 4 and refresh.get_sensitive():
                    self.assertTrue(any('selected' in label for label in labels))
                    state['empty'] = True
                    refresh.clicked()
                    state['stage'] = 5
                elif stage == 5 and refresh.get_sensitive():
                    self.assertEqual(toggles, [])
                    self.assertTrue(any('No AirPlay receivers' in label for label in labels))
                    state['empty'] = False
                    state['long'] = True
                    refresh.clicked()
                    state['stage'] = 6
                elif stage == 6 and refresh.get_sensitive():
                    self.assertEqual(len(toggles), 4)
                    expected = 'Synthetic receiver ' + '非常に長い名前' * 20
                    self.assertIn(expected, [toggle.get_label() for toggle in toggles])
                    self.assertTrue(all(toggle.get_child().get_line_wrap() for toggle in toggles))
                    # Wrap arbitrary network names without growing a narrow window.
                    self.assertLessEqual(window.get_size().width, 360)
                    if not capture_after_frames(window, 'long-name'):
                        return True
                    refresh.clicked()
                    window.destroy()  # pending completion cannot update a closed window
                    state['stage'] = 7
                    return False
            except BaseException as error:
                errors.append(error)
                Gtk.main_quit()
                return False
            return True
        GLib.timeout_add(20, tick)
        ui.gui()
        # Drain the delayed completion after closure, with fatal GTK criticals enabled.
        time.sleep(.3)
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        if errors:
            raise errors[0]
        self.assertEqual(state['stage'], 7)
        self.assertGreater(state['ticks'], 35)


if __name__ == '__main__':
    unittest.main()
