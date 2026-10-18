#!/usr/bin/python3
"""Small system-Python IBus bridge client; transcript travels on stdin, not argv."""
import sys
from gi.repository import Gio, GLib


def main():
    if sys.argv[1] in ('select', 'repair-native'):
        import gi
        gi.require_version('IBus', '1.0')
        from gi.repository import IBus
        IBus.init(); bus = IBus.Bus.new()
        name = sys.argv[2] if len(sys.argv) > 2 else 'mseries-dictation'
        if sys.argv[1] == 'repair-native':
            if not bus.is_connected():raise SystemExit('IBus is unavailable')
            if bus.get_global_engine() is not None:return
            # Removing any dynamic component can clear even a static global
            # engine in IBus. Repair only an empty selection, from native prefs.
            import importlib.util
            from pathlib import Path
            spec=importlib.util.spec_from_file_location('dictation_native',Path(__file__).with_name('dictation-input.py'))
            native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
            settings=Gio.Settings.new('org.gnome.desktop.input-sources')
            name=native.native_engine(settings.get_value('sources').unpack(),settings.get_uint('current'))
            if name is None:return  # Preserve an unknown/empty configuration.

        if not bus.is_connected() or not bus.set_global_engine(name):
            raise SystemExit('Could not select the dictation input method')
        current = bus.get_global_engine()
        if current is None or current.get_name() != name:
            raise SystemExit('Input method selection did not remain active')
        return
    method = {'begin': 'Begin', 'commit': 'Commit', 'preview': 'Preview', 'check': 'Check', 'cancel': 'Cancel', 'finish': 'Finish', 'ready': 'Ready'}[sys.argv[1]]
    args = None
    if method in ('Commit', 'Preview'):
        text = sys.stdin.read(4001)
        if len(text) > 4000:
            raise SystemExit('Dictation chunk too long')
        args = GLib.Variant('(ss)', (sys.argv[2], text))
    if method in ('Finish', 'Check'): args = GLib.Variant('(s)', (sys.argv[2],))
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    try:
        result = connection.call_sync('org.techmore.DictationInput', '/org/techmore/DictationInput',
            'org.techmore.DictationInput', method, args, None, Gio.DBusCallFlags.NO_AUTO_START, 4000, None)
    except GLib.Error as error:
        # The only refusal an unfocused/inaccessible app can cause is "no accessible field": say so
        # distinctly so the controller may fall back to typing. Anything else stays a hard refusal.
        if method == 'Begin' and 'No accessible focused field' in str(error):
            raise SystemExit('UNVERIFIED-FIELD: no accessible focused field')
        raise SystemExit('Dictation input unavailable, sensitive, cancelled or focus changed')
    if method == 'Ready' and not result.unpack()[0]: raise SystemExit('Dictation input is not ready')
    if method == 'Begin':
        print(result.unpack()[0])


if __name__ == '__main__':
    main()
