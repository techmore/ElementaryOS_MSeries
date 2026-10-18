#!/usr/bin/python3
"""Unicode IBus commits for dictation; no clipboard, key injection or surrounding-text reads."""
import secrets
import time

NAME = 'org.techmore.DictationInput'
PATH = '/org/techmore/DictationInput'
ENGINE = 'mseries-dictation'


class FocusSession:
    """A transcript belongs to one uninterrupted, non-sensitive input focus."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.target = None
        self.purpose = None
        self.hints = 0
        self.token = None
        self.characters = 0

    def invalidate(self):
        self.token = None

    def focus(self, target, client):
        self.invalidate()
        self.target = target if client != 'fake' else None
        self.purpose = None
        self.hints = 0

    def content(self, purpose, hints):
        if (purpose, hints) != (self.purpose, self.hints):
            self.invalidate()
        self.purpose, self.hints = purpose, hints

    def begin(self):
        if self.target is None or self.purpose is None or self.purpose in (8, 9) or self.hints & 2048:
            raise ValueError('Select a normal text field with the Dictation input method')
        self.token = secrets.token_urlsafe(24)
        self.deadline = self.clock() + 120
        self.characters = 0
        return self.token

    def accept(self, token, text):
        if not self.token or not secrets.compare_digest(token, self.token) or self.clock() > self.deadline:
            raise ValueError('Dictation focus changed, was cancelled or expired')
        if not isinstance(text, str) or not text or len(text) > 4000 or self.characters + len(text) > 16000:
            raise ValueError('Dictation text exceeds the session bound')
        if any(ord(c) < 32 and c not in '\n\t' for c in text) or '\x7f' in text:
            raise ValueError('Control characters are not dictation text')
        self.characters += len(text)


def main():
    import gi
    gi.require_version('IBus', '1.0')
    from gi.repository import Gio, GLib, IBus
    IBus.init()
    bus = IBus.Bus.new()
    if not bus.is_connected():
        raise SystemExit('IBus is unavailable')
    state = FocusSession()

    class DictationEngine(IBus.Engine):
        __gtype_name__ = 'MSeriesDictationEngine'

        def __init__(self, **kwargs):
            super().__init__(has_focus_id=True, **kwargs)

        def do_focus_in_id(self, path, client):
            state.focus(self, client)

        def do_focus_out_id(self, path):
            state.focus(None, 'fake')

        def do_set_content_type(self, purpose, hints):
            state.content(purpose, hints)

        def do_disable(self):
            state.focus(None, 'fake')

        def do_reset(self):
            state.invalidate()

        def do_process_key_event(self, keyval, keycode, modifiers):
            if keyval == IBus.KEY_Escape:
                state.invalidate()
            return False

    class DictationFactory(IBus.Factory):
        def __init__(self):
            super().__init__(connection=bus.get_connection(), object_path=IBus.PATH_FACTORY)
            self.engines = []

        def do_create_engine(self, name):
            if name != ENGINE:
                raise ValueError('Unknown dictation engine')
            engine = DictationEngine(connection=bus.get_connection(),
                object_path='/org/freedesktop/IBus/MSeriesDictation/Engine' + str(len(self.engines)))
            self.engines.append(engine)
            return engine

    factory = DictationFactory()
    component = IBus.Component.new('org.freedesktop.IBus.MSeriesDictation',
        'MSeries dictation input', '0.1.0', 'MIT', 'ElementaryOS MSeries contributors',
        'https://github.com/techmore/ElementaryOS_MSeries', '', '')
    component.add_engine(IBus.EngineDesc.new(ENGINE, 'Dictation',
        'Unicode dictation; ordinary keys pass through', 'en', 'MIT',
        'ElementaryOS MSeries contributors', 'audio-input-microphone', 'default'))
    bus.register_component(component)
    xml = '''<node><interface name="org.techmore.DictationInput">
      <method name="Begin"><arg type="s" direction="out"/></method>
      <method name="Commit"><arg type="s" direction="in"/><arg type="s" direction="in"/></method>
      <method name="Cancel"/>
    </interface></node>'''
    info = Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]

    def call(connection, sender, path, interface, method, parameters, invocation):
        try:
            if method == 'Begin':
                # IBus suppresses SetContentType when a normal field keeps the
                # default (0, 0); read the engine's cached type as well.
                if state.target is not None:
                    state.content(*state.target.get_content_type())
                invocation.return_value(GLib.Variant('(s)', (state.begin(),)))
            elif method == 'Commit':
                token, text = parameters.unpack()
                state.accept(token, text)
                state.target.commit_text(IBus.Text.new_from_string(text))
                invocation.return_value(None)
            elif method == 'Cancel':
                state.invalidate()
                invocation.return_value(None)
        except ValueError as error:
            invocation.return_dbus_error(NAME + '.Unavailable', str(error))

    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    connection.register_object(PATH, info, call, None, None)
    owner = Gio.bus_own_name_on_connection(connection, NAME, Gio.BusNameOwnerFlags.NONE, None, None)
    loop = GLib.MainLoop()
    bus.connect('disconnected', lambda *_: loop.quit())
    loop.run()
    Gio.bus_unown_name(owner)


if __name__ == '__main__':
    main()
