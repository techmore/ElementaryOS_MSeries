// Minimal application services for exercising the production activation method.
namespace Gtk {
    public class Window : Object {
        public static int presentations = 0;
        public void present () { presentations++; }
    }

    public class Application : Object {
        public string application_id { get; construct; }
        public Window? active_window { get; set; }
        private List<weak Window> windows;
        protected virtual void startup () {}
        protected virtual void activate () {}
        public virtual bool dbus_register (DBusConnection connection, string path) throws Error { return true; }
        public void add_window (Window window) {
            windows.append (window);
            active_window = window;
        }
        public unowned List<weak Window>? get_windows () { return windows; }
        public int run (string[] args) { return 0; }
        public void trigger_activate () { activate (); }
    }
}

namespace Granite { public void init () {} }

namespace Dock {
    public class MainWindow : Gtk.Window {}
    public class ShellKeyGrabber : Object { public static void init () {} }
    public class GalaDBus : Object { public static async void init () {} }
    public class AppSystem : Object {
        private static Once<AppSystem> instance;
        public static unowned AppSystem get_default () {
            return instance.once (() => new AppSystem ());
        }
    }
    public class Unity : Object {
        private static Once<Unity> instance;
        public static unowned Unity get_default () {
            return instance.once (() => new Unity ());
        }
        public void add_client (AppSystem client) {}
    }
    [DBus (name = "org.techmore.DockActivationTest")]
    public class ItemInterface : Object { public void ping () throws Error {} }
}

public class ActivationTest {
    public static int main () {
        var app = new Dock.Application ();
        app.trigger_activate ();
        var window = app.active_window;
        assert (window != null);
        assert (Gtk.Window.presentations == 1);
        for (int i = 0; i < 5; i++) {
            app.trigger_activate ();
        }
        assert (app.get_windows ().length () == 1);
        assert (Gtk.Window.presentations == 1);
        // A panel can exist without being the keyboard's active window.
        app.active_window = null;
        app.trigger_activate ();
        assert (app.get_windows ().length () == 1);
        assert (Gtk.Window.presentations == 1);
        print ("PASS: repeated activation neither presents nor recreates the dock\n");
        return 0;
    }
}
