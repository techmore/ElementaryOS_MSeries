#!/usr/bin/python3
"""Smart Reply input method: holds one draft for the focused field; Tab inserts it, Esc discards it.

Reuses the dictation input method's field-safety helpers (password and unknown fields are refused,
accessible focus must be an active editable field). It never sends anything and never reads the
field's text. A draft lives at most 60 seconds, ends on focus change, Esc or any other key, and the
previous input method is restored afterwards. Design: mseries/SMART-REPLY-DESIGN.md.
"""
import importlib.util
import os
import time
from pathlib import Path

NAME = 'org.techmore.SmartReplyInput'
PATH = '/org/techmore/SmartReplyInput'
ENGINE = 'mseries-smart-reply'
HOLD_SECONDS = 60
MAX_TEXT = 1500


def load_dictation_helpers():
    """The dictation input module is the single source of truth for field-safety checks."""
    here = Path(__file__).resolve().parent
    for candidate in (os.environ.get('MSERIES_DICTATION_INPUT'),
                      here.parent / 'dictation' / 'dictation-input.py',
                      Path.home() / '.local/share/mseries/stream/dictation-input.py'):
        if candidate and Path(candidate).is_file():
            spec = importlib.util.spec_from_file_location('dictation_input', candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise SystemExit('The dictation input module is required for field-safety checks')


def valid_offer(text):
    return (isinstance(text, str) and 0 < len(text) <= MAX_TEXT and '\x7f' not in text
            and not any(ord(c) < 32 and c not in '\n\t' for c in text))


class Pending:
    """The one draft being held. Pure state so the Tab/Esc rules are unit-testable."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.text = None
        self.deadline = 0

    def hold(self, text):
        if not valid_offer(text):
            raise ValueError('Invalid draft')
        self.text, self.deadline = text, self.clock() + HOLD_SECONDS

    def active(self):
        return self.text is not None and self.clock() <= self.deadline

    def take(self):
        text, self.text = (self.text if self.active() else None), None
        return text

    def drop(self):
        self.text = None


def classify_key(pending, keyval, tab, escape, released):
    """What to do with a key while a draft is held: 'insert', 'discard-consume', 'discard-pass',
    'swallow' (the release of a key we consumed) or 'ignore'."""
    if not pending.active():
        return 'ignore'
    if released:
        return 'swallow' if keyval in (tab, escape) else 'ignore'
    if keyval == tab:
        return 'insert'
    if keyval == escape:
        return 'discard-consume'
    return 'discard-pass'


def main():
    import gi
    gi.require_version('IBus', '1.0')
    from gi.repository import Gio, GLib, IBus
    dictation = load_dictation_helpers()
    IBus.init()
    bus = IBus.Bus.new()
    if not bus.is_connected():
        raise SystemExit('IBus is unavailable')
    pending = Pending()
    current = {'engine': None}
    lease = {'busy': False, 'previous': None, 'epoch': 0, 'identity': None}
    swallow = set()

    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    Atspi.set_timeout(200, 500)

    class FocusMetadata:
        """Field role/state/identity and active ancestors only; never requests text."""
        def __init__(self):
            self.api = Atspi
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
                        drop()
                elif event.detail1:
                    self.source = event.source
                    if lease['identity'] and self.identity(event.source) != lease['identity']:
                        drop()
                elif self.source and self.identity(event.source) == self.identity(self.source):
                    self.source = None
                    drop()
            except Exception:
                self.source = None
                drop()

        def validate(self):
            try:
                budget = dictation.MetadataBudget()
                if self.source is None:
                    budget.call(self.discover_focus)
                source = self.source
                if source is None:
                    raise ValueError('No accessible focused field')
                budget.call(source.clear_cache)
                states = budget.call(source.get_state_set)
                role = int(budget.call(source.get_role))
                focused = states.contains(self.api.StateType.FOCUSED)
                editable = states.contains(self.api.StateType.EDITABLE)
                active = dictation.active_window_ancestor(source, self.api, budget)
                if not dictation.safe_accessible(role, focused, editable, active):
                    raise ValueError('Focused field is sensitive, inactive or not editable')
                return budget.call(self.identity, source)
            except Exception:
                raise ValueError('Accessible field metadata unavailable or unsafe') from None

        def discover_focus(self):
            deadline = time.monotonic() + .6
            desktop = self.api.get_desktop(0)
            if desktop is None:
                return
            visited = 0
            for index in range(min(desktop.get_child_count(), 128)):
                if time.monotonic() > deadline:
                    return
                application = desktop.get_child_at_index(index)
                if application is None:
                    continue
                for window_index in range(min(application.get_child_count(), 32)):
                    if time.monotonic() > deadline:
                        return
                    window = application.get_child_at_index(window_index)
                    if window is None:
                        continue
                    window.clear_cache()
                    if not window.get_state_set().contains(self.api.StateType.ACTIVE):
                        continue
                    stack = [window]
                    while stack and visited < 1024 and time.monotonic() <= deadline:
                        node = stack.pop()
                        visited += 1
                        if node is None:
                            continue
                        if node.get_state_set().contains(self.api.StateType.FOCUSED):
                            self.source = node
                            return
                        stack.extend(dictation.bounded_children(node, min(node.get_child_count(), 128), deadline))

    metadata = FocusMetadata()

    def hide():
        engine = current['engine']
        if engine is not None:
            engine.hide_auxiliary_text()

    def restore_previous():
        previous = lease['previous']
        lease.update(previous=None, identity=None)
        desc = bus.get_global_engine()
        if previous and previous != ENGINE and desc and desc.get_name() == ENGINE:
            bus.set_global_engine_async(previous, 1500, None, lambda obj, result, *_: obj.set_global_engine_async_finish(result), None)

    def drop():
        had = pending.text is not None
        pending.drop()
        lease['epoch'] += 1
        if had or lease['previous']:
            hide()
            restore_previous()

    class SmartReplyEngine(IBus.EngineSimple):
        __gtype_name__ = 'MSeriesSmartReplyEngine'

        def __init__(self, **kwargs):
            super().__init__(has_focus_id=True, **kwargs)

        def do_focus_in_id(self, path, client):
            current['engine'] = self

        def do_focus_out_id(self, path):
            if current['engine'] is self:
                current['engine'] = None
            if pending.text is not None and not lease['busy']:
                drop()
            IBus.EngineSimple.do_focus_out_id(self, path)

        def do_disable(self):
            current['engine'] = None
            pending.drop()
            IBus.EngineSimple.do_disable(self)

        def do_process_key_event(self, keyval, keycode, modifiers):
            released = bool(modifiers & IBus.ModifierType.RELEASE_MASK)
            if released and keyval in swallow:
                swallow.discard(keyval)
                return True
            action = classify_key(pending, keyval, IBus.KEY_Tab, IBus.KEY_Escape, released)
            if action == 'insert':
                text = pending.take()
                try:
                    if text is None or metadata.validate() != lease['identity']:
                        raise ValueError('Field changed')
                    hide()
                    self.commit_text(IBus.Text.new_from_string(text))
                except ValueError:
                    pass
                swallow.add(keyval)
                drop()
                return True
            if action == 'discard-consume':
                swallow.add(keyval)
                drop()
                return True
            if action == 'discard-pass':
                drop()
            return IBus.EngineSimple.do_process_key_event(self, keyval, keycode, modifiers)

    class Factory(IBus.Factory):
        def __init__(self):
            super().__init__(connection=bus.get_connection(), object_path=IBus.PATH_FACTORY)
            self.engines = []

        def do_create_engine(self, name):
            if name != ENGINE:
                raise ValueError('Unknown engine')
            engine = SmartReplyEngine(connection=bus.get_connection(),
                object_path='/org/freedesktop/IBus/MSeriesSmartReply/Engine' + str(len(self.engines)))
            self.engines.append(engine)
            return engine

    factory = Factory()
    component = IBus.Component.new('org.freedesktop.IBus.MSeriesSmartReply', 'MSeries Smart Reply input',
        '0.1.0', 'MIT', 'ElementaryOS MSeries contributors', 'https://github.com/techmore/ElementaryOS_MSeries', '', '')
    component.add_engine(IBus.EngineDesc.new(ENGINE, 'Smart Reply', 'Holds one drafted reply; Tab inserts it',
        'en', 'MIT', 'ElementaryOS MSeries contributors', 'mail-reply-sender', 'default'))
    bus.register_component(component)

    xml = '''<node><interface name="org.techmore.SmartReplyInput">
      <method name="Offer"><arg type="s" direction="in"/></method>
      <method name="Cancel"/>
      <method name="Ready"><arg type="b" direction="out"/></method>
    </interface></node>'''
    info = Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]

    def offer(invocation, text):
        if lease['busy'] or pending.text is not None:
            drop()
        if not valid_offer(text):
            raise ValueError('Invalid draft')
        identity = metadata.validate()  # Refuse sensitive fields BEFORE switching input methods.
        desc = bus.get_global_engine()
        previous = desc.get_name() if desc else None
        if previous is None:
            settings = Gio.Settings.new('org.gnome.desktop.input-sources')
            previous = dictation.native_engine(settings.get_value('sources').unpack(), settings.get_uint('current'))
        if previous is None:
            raise ValueError('No current or configured native input method')
        lease.update(busy=True, previous=previous, epoch=lease['epoch'] + 1, identity=identity)
        epoch = lease['epoch']
        deadline = time.monotonic() + 2.75

        def fail(message):
            lease['busy'] = False
            restore_previous()
            invocation.return_dbus_error(NAME + '.Unavailable', message)

        def selected(obj, result, *_):
            try:
                if not obj.set_global_engine_async_finish(result):
                    raise ValueError('Could not select the Smart Reply input method')
            except (GLib.Error, ValueError):
                fail('Could not select the Smart Reply input method')
                return
            attempts = [0]

            def settle():
                try:
                    if time.monotonic() > deadline:
                        raise ValueError('Smart Reply startup deadline exceeded')
                    if epoch != lease['epoch']:
                        raise ValueError('Smart Reply was cancelled')
                    if metadata.validate() != identity:
                        raise ValueError('Text-field focus changed')
                    if current['engine'] is None and attempts[0] < 8:
                        attempts[0] += 1
                        return True
                    if current['engine'] is None:
                        raise ValueError('The app did not attach to the Smart Reply input method')
                    pending.hold(text)
                    lease['busy'] = False
                    current['engine'].update_auxiliary_text(
                        IBus.Text.new_from_string('Tab inserts the draft, Esc discards it'), True)

                    def expire():
                        if epoch == lease['epoch'] and pending.text is not None:
                            drop()
                        return False
                    GLib.timeout_add_seconds(HOLD_SECONDS, expire)
                    invocation.return_value(None)
                except ValueError as error:
                    fail(str(error))
                return False
            GLib.timeout_add(25, settle)
        bus.set_global_engine_async(ENGINE, 1500, None, selected, None)

    def call(connection, sender, path, interface, method, parameters, invocation):
        try:
            if method == 'Offer':
                offer(invocation, parameters.unpack()[0])
            elif method == 'Cancel':
                drop()
                invocation.return_value(None)
            elif method == 'Ready':
                invocation.return_value(GLib.Variant('(b)', (True,)))
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
