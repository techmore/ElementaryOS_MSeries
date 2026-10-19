#!/usr/bin/python3
"""Review only local assistant drafts; Open in Mail starts the normal composer."""
import os
from pathlib import Path
import subprocess
import sys

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from app_adapters import read_draft, draft_id


def main():
    root = Path(os.environ.get('MSERIES_ASSISTANT_WORKSPACE', Path.home() / 'Documents/Assistant Workspace')).resolve()
    window = Gtk.Window(title='Assistant Mail Drafts'); window.set_default_size(680, 440)
    window.connect('destroy', Gtk.main_quit)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=16); window.add(box)
    label = Gtk.Label(label='Local unsent drafts. Review a draft, then open it in Mail.', xalign=0); box.pack_start(label, False, False, 0)
    selector = Gtk.ComboBoxText(); box.pack_start(selector, False, False, 0)
    view = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    scroll = Gtk.ScrolledWindow(); scroll.add(view); box.pack_start(scroll, True, True, 0)
    button = Gtk.Button(label='Open in Mail'); button.set_sensitive(False); box.pack_start(button, False, False, 0)
    directory = root / 'Mail Drafts'
    if directory.exists() and not directory.is_symlink():
        for path in sorted(directory.glob('*.json')):
            try:
                identifier = draft_id(path.stem); value = read_draft(root, identifier)
                selector.append(identifier, value['subject'])
            except (OSError, ValueError, KeyError): continue
    def selected(_combo):
        identifier = selector.get_active_id()
        if not identifier: return
        try:
            value = read_draft(root, identifier)
            view.get_buffer().set_text('To: ' + value['to'] + '\nSubject: ' + value['subject'] + '\n\n' + value['body'])
            button.set_sensitive(True)
        except (OSError, ValueError, KeyError):
            view.get_buffer().set_text('Draft changed; review the local file.'); button.set_sensitive(False)
    selector.connect('changed', selected)
    def review(_button):
        subprocess.Popen(['/usr/bin/python3', str(Path(__file__).with_name('app_adapters.py')), 'review-mail', selector.get_active_id()])
    button.connect('clicked', review)
    selector.set_active(0); window.show_all(); Gtk.main()


if __name__ == '__main__': main()
