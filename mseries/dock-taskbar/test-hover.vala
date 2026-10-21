int main () {
 Gtk.init ();
 var window = new Gtk.Window () { default_width = 500, default_height = 120 };
 var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
 var entry = new Gtk.Entry ();
 row.append (entry);
 var item = new Dock.TaskbarCodexBar ();
 row.append (item); window.child = row; window.present ();
 var button = (Gtk.Button) item.get_first_child ();
 Gtk.Popover? popup = null;
 for (var child = button.get_first_child (); child != null; child = child.get_next_sibling ())
   if (child is Gtk.Popover) popup = (Gtk.Popover) child;
 assert (popup != null);
 Gtk.EventControllerMotion? motion = null;
 var controllers = button.observe_controllers ();
 for (uint i = 0; i < controllers.get_n_items (); i++)
   if (controllers.get_item (i) is Gtk.EventControllerMotion) motion = (Gtk.EventControllerMotion) controllers.get_item (i);
 assert (motion != null);
 var loop = new MainLoop ();
 Timeout.add (200, () => { entry.grab_focus (); motion.enter (1,1); return Source.REMOVE; });
 Timeout.add (600, () => {
   assert (popup.visible); assert (!popup.autohide);
   assert (window.get_focus ().is_ancestor (entry) || window.get_focus () == entry);
   button.clicked (); assert (popup.visible); assert (popup.autohide);
   button.clicked (); assert (!popup.visible);
   motion.enter (1,1); return Source.REMOVE;
 });
 Timeout.add (1000, () => { assert (popup.visible); motion.leave (); return Source.REMOVE; });
 Timeout.add (1600, () => {
   assert (!popup.visible);
   button.clicked (); assert (popup.visible); assert (popup.autohide);
   button.clicked (); assert (!popup.visible);
   print ("PASS hover opens, preserves typing focus, leave closes, click pins and toggles\n");
   loop.quit (); return Source.REMOVE;
 });
 loop.run (); window.close (); return 0;
}
