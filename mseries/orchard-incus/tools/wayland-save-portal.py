"""Select an audit-owned destination in a native save portal via AT-SPI.
Matches both the exact dialog title and its unique initial filename.
"""
import gi,sys,time
from pathlib import Path
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
title,initial,destination=sys.argv[1:]
assert Path(destination).is_absolute()

def children(node):
    for i in range(node.get_child_count()):
        child=node.get_child_at_index(i)
        if child:yield child

def walk(node,depth=0):
    yield node
    if depth>=12 or node.get_role_name() in ('list','tree','tree table','table'):return
    for child in children(node):yield from walk(child,depth+1)

def entry_value(node):
    try:
        editable=node.get_editable_text_iface();text=node.get_text_iface()
        if editable and text:return editable,Atspi.Text.get_text(text,0,-1)
    except Exception:pass
    return None,None

deadline=time.monotonic()+12
while time.monotonic()<deadline:
    desktop=Atspi.get_desktop(0)
    for app in children(desktop):
        if app.get_name() not in ('xdg-desktop-portal-gtk','io.elementary.files.xdg-desktop-portal','io.elementary.files','python3'):continue
        for window in children(app):
            if window.get_name()!=title:continue
            widgets=list(walk(window));target=None
            for widget in widgets:
                editable,value=entry_value(widget)
                if value in (initial,destination):target=(widget,editable);break
            if target is None:continue
            node,editable=target
            assert Atspi.EditableText.set_text_contents(editable,destination)
            time.sleep(.35)
            assert Atspi.Text.get_text(node.get_text_iface(),0,-1)==destination
            button=next(x for x in widgets if x.get_role_name() in ('push button','button') and x.get_name().replace('_','').lower()=='save')
            assert Atspi.Action.do_action(button.get_action_iface(),0)
            print('Native save portal accepted audit destination',flush=True)
            sys.exit(0)
    time.sleep(.15)
raise RuntimeError('Audit-owned native save dialog/filename was not found')
