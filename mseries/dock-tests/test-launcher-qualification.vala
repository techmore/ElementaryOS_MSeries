// SPDX-License-Identifier: GPL-3.0-or-later
// Production Dock.App/Launcher with a private, recording compositor service.
[DBus (name="org.pantheon.gala.DesktopIntegration")]
class QualificationService : Object {
    public uint version { get { return 1; } }
    private void record (string value) {
        var file = FileStream.open (Environment.get_variable ("QUAL_EVENTS"), "a");
        file.puts (value + "\n");
    }
    public async Dock.DesktopIntegration.Window[] get_windows () throws DBusError, IOError { return {}; }
    public async Dock.DesktopIntegration.RunningApplication[] get_running_applications () throws DBusError, IOError { return {}; }
    public async int get_active_workspace () throws DBusError, IOError { return 0; }
    public async int get_n_workspaces () throws DBusError, IOError { return 1; }
    public async void focus_window (uint64 uid) throws DBusError, IOError { record ("focus:" + uid.to_string ()); }
    public async void show_windows_for (string id) throws DBusError, IOError { record ("show:" + id); }
    public async void move_window_to_workspace (uint64 uid, int workspace) throws DBusError, IOError {}
    public async void activate_workspace (int workspace) throws DBusError, IOError {}
    public async void reorder_workspace (int a, int b) throws DBusError, IOError {}
}
class QualificationWindow : Gtk.Window {
    class construct { set_css_name ("dock-window"); }
}
class QualificationRow : Gtk.Box {
    public QualificationRow () { Object (orientation: Gtk.Orientation.HORIZONTAL, spacing: 14, halign: Gtk.Align.CENTER); }
    class construct { set_css_name ("dock"); }
}
Gtk.Widget? marker (Gtk.Widget w) {
    if (w.has_css_class ("running-indicator")) return w;
    for (var c = w.get_first_child (); c != null; c = c.get_next_sibling ()) {
        var found = marker (c); if (found != null) return found;
    }
    return null;
}
void menu_labels (MenuModel model, StringBuilder text) {
    for (int i=0; i<model.get_n_items (); i++) {
        var label = model.get_item_attribute_value (i, "label", VariantType.STRING);
        if (label != null) text.append (label.get_string () + "\n");
        foreach (var kind in new string[] {"section", "submenu"}) {
            var child = model.get_item_link (i, kind); if (child != null) menu_labels (child, text);
        }
    }
}
void collect_menus (Gtk.Widget w, StringBuilder text) {
    var popover = w as Gtk.PopoverMenu;
    if (popover != null && popover.menu_model != null) menu_labels (popover.menu_model, text);
    for (var c=w.get_first_child (); c!=null; c=c.get_next_sibling ()) collect_menus (c,text);
}
bool popup_mapped (Gtk.Widget w) {
    if (w is Gtk.PopoverMenu && w.get_mapped ()) return true;
    for(var c=w.get_first_child();c!=null;c=c.get_next_sibling()) if(popup_mapped(c)) return true;
    return false;
}
Dock.Window make_window (uint64 uid, string id, bool focused=false) {
    var w = new Dock.Window (uid);
    var p = new HashTable<string,Variant> (str_hash,str_equal);
    p["app-id"] = new Variant.string (id); p["has-focus"] = new Variant.boolean (focused);
    w.update_properties (p); return w;
}
void show_fixture (bool dark) {
    Gtk.Settings.get_default ().gtk_application_prefer_dark_theme = dark;
    Gtk.Settings.get_default ().gtk_icon_theme_name = "elementary";
    var css = new Gtk.CssProvider (); css.load_from_resource ("/io/elementary/dock/Application.css");
    Gtk.StyleContext.add_provider_for_display (Gdk.Display.get_default (),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
    var window = new QualificationWindow () { title="PR343 qualification", decorated=false, default_width=800, default_height=260 };
    window.add_css_class ("taskbar"); if (dark) window.add_css_class ("dark");
    var box = new Gtk.Box (Gtk.Orientation.VERTICAL,20) { margin_top=24, margin_bottom=24, margin_start=24, margin_end=24 };
    var entry = new Gtk.Entry () { placeholder_text="Keyboard focus must survive hover" };
    box.append (entry);
    var row = new QualificationRow (); box.append (row); window.child=box;
    string[] names={"teams","outlook","transient","closed"};
    Dock.Launcher[] launchers={};
    for (int i=0; i<4; i++) {
        string raw = i==0 ? "brave-teams.microsoft.com__v2_-Default" : i==1 ? "brave-outlook.office.com__mail_-Default" : i==2 ? "Uninstalled Qualification Utility" : "ClosedFixture";
        var info=Dock.AppResolver.get_default ().resolve (raw); assert (info!=null);
        if (i<2) assert (info.get_id () == (i==0 ? "TeamsFixture.desktop" : "OutlookFixture.desktop"));
        var app=new Dock.App (info, i!=2);
        var wins=new GenericArray<Dock.Window> ();
        if (i==0) { wins.add(make_window(101,raw)); wins.add(make_window(102,"TeamsFixture.desktop")); }
        if (i==1) { wins.add(make_window(201,raw,true)); wins.add(make_window(202,raw)); }
        if (i==2) wins.add(make_window(301,raw));
        app.update_windows(wins);
        var launcher=new Dock.Launcher(app); launchers+=launcher;
        row.append(launcher);
        var menu=new StringBuilder(); collect_menus(launcher,menu);
        try { FileUtils.set_contents (Path.build_filename(Environment.get_variable("QUAL_OUT"),names[i]+"-menu.txt"),menu.str); } catch(Error e){error("%s",e.message);}
    }

    window.present ();
    entry.changed.connect (()=>{try {FileUtils.set_contents(Environment.get_variable("QUAL_TYPED"),entry.text);}catch(Error e){error("%s",e.message);}});
    Timeout.add (250,()=>{entry.grab_focus();return Source.REMOVE;});
    Timeout.add (100,()=>{
        if (Dock.WindowSystem.get_default().desktop_integration == null) return Source.CONTINUE;
        var data = new Json.Builder (); data.begin_object ();
        double sx,sy;window.get_surface_transform(out sx,out sy);
        data.set_member_name("surface_offset");data.begin_array();data.add_double_value(sx);data.add_double_value(sy);data.end_array();
        Gtk.Widget[] widgets={entry,launchers[0],launchers[1],launchers[2],launchers[3]};
        string[] keys={"entry","teams","outlook","transient","closed"};
        for(int i=0;i<widgets.length;i++) {
            Graphene.Rect rect; assert(widgets[i].compute_bounds(window,out rect));
            data.set_member_name(keys[i]);data.begin_array();data.add_double_value(rect.get_x());data.add_double_value(rect.get_y());data.add_double_value(rect.get_width());data.add_double_value(rect.get_height());data.end_array();
        }
        data.set_member_name("focused_entry");data.add_boolean_value(window.get_focus()!=null && (window.get_focus()==entry || window.get_focus().is_ancestor(entry)));
        data.set_member_name("menus");data.begin_array();foreach(var l in launchers)data.add_boolean_value(popup_mapped(l));data.end_array();
        data.set_member_name("markers");data.begin_array();
        foreach(var launcher in launchers){var m=marker(launcher); assert(m!=null);var r=(Gtk.Revealer)m.get_ancestor(typeof(Gtk.Revealer)); data.begin_object();data.set_member_name("visible");data.add_boolean_value(r.reveal_child);data.set_member_name("focused");data.add_boolean_value(launcher.has_css_class("focused"));data.set_member_name("width");data.add_int_value(m.get_width());data.set_member_name("height");data.add_int_value(m.get_height());data.end_object();}
        data.end_array();data.end_object();var generator=new Json.Generator();generator.set_root(data.get_root());
        try{FileUtils.set_contents(Environment.get_variable("QUAL_STATE"),generator.to_data(null));}catch(Error e){error("%s",e.message);}
        return Source.CONTINUE;
    });
}
int main (string[] args) {
    Gtk.init ();
    var loop = new MainLoop ();
    Bus.own_name (BusType.SESSION,"org.pantheon.gala",BusNameOwnerFlags.NONE,
        (connection)=>{try {connection.register_object("/org/pantheon/gala/DesktopInterface",new QualificationService());}catch(Error e){error("%s",e.message);}},
        ()=>show_fixture(args.length>1 && args[1]=="dark"));
    loop.run (); return 0;
}
