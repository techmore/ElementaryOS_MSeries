#!/usr/bin/python3
"""Unicode IBus commits for dictation; no clipboard, key injection or surrounding-text reads."""
import secrets
import time

NAME = 'org.techmore.DictationInput'
PATH = '/org/techmore/DictationInput'
ENGINE = 'mseries-dictation'


def safe_accessible(role, focused, editable, active_window):
    return role in (61, 73, 79, 94, 95) and focused and editable and active_window


def bounded_children(node, count, deadline, clock=time.monotonic):
    children = []
    for index in reversed(range(min(count, 128))):
        if clock() > deadline: break
        children.append(node.get_child_at_index(index))
    return children


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
        # XIM alone cannot establish password/content-purpose information.
        # Do not silently fall back to layout-dependent keys for that client.
        self.target = target if client not in ('fake', 'xim') else None
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
    current = {'engine': None, 'client': None, 'metadata': None}

    class FocusMetadata:
        """Only field role/state/identity and active ancestors; never requests text."""
        def __init__(self):
            gi.require_version('Atspi', '2.0')
            from gi.repository import Atspi
            self.api = Atspi
            Atspi.set_timeout(200, 500)
            self.source = None
            self.listener = Atspi.EventListener.new(self.changed, None)
            self.listener.register('object:state-changed:focused')
            self.listener.register('window:deactivate')

        def identity(self, source):
            return source.get_process_id(), source.path

        def changed(self, event, *_):
            try:
                if event.type.startswith('window:deactivate'):
                    if self.source and event.source.get_process_id() == self.source.get_process_id():
                        self.source = None
                        state.invalidate()
                elif event.detail1:
                    self.source = event.source
                    state.invalidate()
                elif self.source and self.identity(event.source) == self.identity(self.source):
                    self.source = None
                    state.invalidate()
            except Exception:
                self.source = None
                state.invalidate()

        def validate(self):
            try:
                if self.source is None:
                    self.discover_focus()
                source = self.source
                if source is None: raise ValueError('No accessible focused field')
                source.clear_cache()
                states = source.get_state_set()
                role = int(source.get_role())
                focused = states.contains(self.api.StateType.FOCUSED)
                editable = states.contains(self.api.StateType.EDITABLE)
                active = False
                node = source
                for _ in range(24):
                    if node is None: break
                    node.clear_cache()
                    parent = node.get_parent()
                    # Qt's top-level QWidget reports FILLER rather than FRAME.
                    top_level = parent is not None and parent.get_role() == self.api.Role.APPLICATION
                    window_role = node.get_role() in (self.api.Role.FRAME, self.api.Role.DIALOG, self.api.Role.WINDOW)
                    if (window_role or top_level) and node.get_state_set().contains(self.api.StateType.ACTIVE):
                        active = True
                        break
                    node = parent
                if not safe_accessible(role, focused, editable, active):
                    raise ValueError('Focused field is sensitive, inactive or not editable')
                return self.identity(source)
            except Exception:
                raise ValueError('Accessible field metadata unavailable or unsafe') from None

        def discover_focus(self):
            # The service may start after a field already gained focus. Query
            # only active top-levels, with a strict time/node bound; no labels
            # or text are requested and there is no periodic desktop scan.
            deadline = time.monotonic() + .6
            desktop = self.api.get_desktop(0)
            if desktop is None: return
            visited = 0
            for index in range(min(desktop.get_child_count(), 128)):
                if time.monotonic() > deadline: return
                application = desktop.get_child_at_index(index)
                if application is None: continue
                for window_index in range(min(application.get_child_count(), 32)):
                    if time.monotonic() > deadline: return
                    window = application.get_child_at_index(window_index)
                    if window is None: continue
                    window.clear_cache()
                    if not window.get_state_set().contains(self.api.StateType.ACTIVE): continue
                    pending = [window]
                    while pending and visited < 1024 and time.monotonic() <= deadline:
                        node = pending.pop(); visited += 1
                        if node is None: continue
                        states = node.get_state_set()
                        if states.contains(self.api.StateType.FOCUSED):
                            self.source = node
                            return
                        count = min(node.get_child_count(), 128)
                        pending.extend(bounded_children(node, count, deadline))

    try:
        metadata = FocusMetadata()
    except (ImportError, ValueError, GLib.Error):
        metadata = None  # Refuse insertion if reliable field metadata is absent.

    class DictationEngine(IBus.EngineSimple):
        __gtype_name__ = 'MSeriesDictationEngine'

        def __init__(self, **kwargs):
            super().__init__(has_focus_id=True, **kwargs)

        def do_focus_in_id(self, path, client):
            current.update(engine=self, client=client, metadata=None)
            state.focus(self, client)

        def do_focus_out_id(self, path):
            current.update(engine=None, client=None, metadata=None)
            state.focus(None, 'fake')
            IBus.EngineSimple.do_focus_out_id(self, path)

        def do_set_content_type(self, purpose, hints):
            state.content(purpose, hints)

        def do_disable(self):
            current.update(engine=None, client=None, metadata=None)
            state.focus(None, 'fake')
            IBus.EngineSimple.do_disable(self)

        def do_reset(self):
            state.invalidate()
            IBus.EngineSimple.do_reset(self)

        def do_process_key_event(self, keyval, keycode, modifiers):
            if keyval == IBus.KEY_Escape:
                state.invalidate()
            return IBus.EngineSimple.do_process_key_event(self, keyval, keycode, modifiers)

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
                if metadata is None: raise ValueError('Accessible field metadata is required')
                current['metadata'] = metadata.validate()
                state.target = current['engine']
                # IBus suppresses SetContentType when a normal field keeps the
                # default (0, 0); read the engine's cached type as well.
                if state.target is not None:
                    state.content(*state.target.get_content_type())
                invocation.return_value(GLib.Variant('(s)', (state.begin(),)))
            elif method == 'Commit':
                token, text = parameters.unpack()
                if metadata is None or metadata.validate() != current['metadata']:
                    state.invalidate()
                    raise ValueError('Accessible field focus changed')
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
