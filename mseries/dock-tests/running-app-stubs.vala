// Controlled services around the real production AppSystem and AppResolver.
public interface Dock.UnityClient : Object {}
public class Dock.Window : Object {
    public string app_id { get; set; default = ""; }
    public Window (string id) { app_id = id; }
}
public class Dock.WindowSystem : Object {
    private static WindowSystem? instance;
    public static WindowSystem get_default () {
        if (instance == null) { instance = new WindowSystem (); }
        return instance;
    }
    public GenericArray<Window> windows { get; set; default = new GenericArray<Window> (); }
}
public class Dock.App : Object {
    public signal void removed ();
    public DesktopAppInfo app_info { get; construct; }
    public bool pinned { get; set; default = false; }
    public GenericArray<Window> windows { get; private set; default = new GenericArray<Window> (); }
    public bool running { get { return windows.length > 0; } }
    public App (DesktopAppInfo info, bool pin) { Object (app_info: info, pinned: pin); }
    public void update_windows (GenericArray<Window>? next) {
        windows = next ?? new GenericArray<Window> ();
        if (!pinned && !running) { removed (); }
    }
    public void perform_unity_update (VariantIter iter) {}
    public void remove_launcher_entry () {}
}

namespace RunningTest {
    void check_resolve (string raw, string expected) {
        var info = Dock.AppResolver.get_default ().resolve (raw);
        assert_nonnull (info);
        assert_cmpstr (info.get_id (), CompareOperator.EQ, expected);
    }
    void resolution () {
        check_resolve ("io.elementary.appcenter", "io.elementary.appcenter.desktop");
        check_resolve ("io.elementary.appcenter.desktop", "io.elementary.appcenter.desktop");
        check_resolve ("Chatgpt", "chatgpt.desktop");
        check_resolve ("brave-teams.microsoft.com__v2_-Default", "org.techmore.mseries.TeamsWeb.desktop");
        check_resolve ("brave-outlook.office.com__mail_-Default", "org.techmore.mseries.OutlookWeb.desktop");
        check_resolve ("legacy-exec", "odd-name.desktop");
    }
    void unknown () {
        var info = Dock.AppResolver.get_default ().resolve ("Uninstalled App\nExec=/bin/evil");
        assert_nonnull (info);
        assert_true (info.get_boolean ("X-MSeries-Transient"));
        assert_cmpstr (info.get_commandline (), CompareOperator.EQ, "/usr/bin/false");
        assert_true (info.get_filename ().has_prefix (Environment.get_user_runtime_dir ()));
        var again = Dock.AppResolver.get_default ().resolve ("Uninstalled App\nExec=/bin/evil");
        assert_cmpstr (info.get_id (), CompareOperator.EQ, again.get_id ());
        var ambiguous = Dock.AppResolver.get_default ().resolve ("flatpak");
        assert_true (ambiguous.get_boolean ("X-MSeries-Transient"));
    }
    void ambiguous_aliases () {
        check_resolve ("CaseAlias", "CaseAlias.desktop");
        check_resolve ("casealias.desktop", "casealias.desktop");
        check_resolve ("class-one", "class-one.desktop");
        foreach (var raw in new string[] {"SharedApplication", "sharedapplication", "CASEALIAS"}) {
            var info = Dock.AppResolver.get_default ().resolve (raw);
            assert_nonnull (info);
            assert_true (info.get_boolean ("X-MSeries-Transient"));
            assert_cmpstr (info.get_commandline (), CompareOperator.EQ, "/usr/bin/false");
        }
    }
    void activation_identity () {
        var windows = new GenericArray<Dock.Window> ();
        assert_null (Dock.AppResolver.shared_window_id (windows));
        windows.add (new Dock.Window ("Chatgpt"));
        windows.add (new Dock.Window ("Chatgpt"));
        assert_cmpstr (Dock.AppResolver.shared_window_id (windows), CompareOperator.EQ, "Chatgpt");
        windows.add (new Dock.Window ("chatgpt.desktop"));
        assert_null (Dock.AppResolver.shared_window_id (windows));
    }
    void sync () {
        var loop = new MainLoop ();
        Dock.AppSystem.get_default ().sync_windows.begin (() => loop.quit ());
        loop.run ();
    }
    void running_lifecycle () {
        var settings = new Settings ("io.elementary.dock");
        settings.set_strv ("launchers", {"missing.desktop", "org.techmore.mseries.TeamsWeb.desktop"});
        var loop = new MainLoop ();
        var system = Dock.AppSystem.get_default ();
        system.load.begin (() => loop.quit ());
        loop.run ();
        assert_cmpuint (system.apps.get_n_items (), CompareOperator.EQ, 1);
        var windows = new GenericArray<Dock.Window> ();
        windows.add (new Dock.Window ("brave-teams.microsoft.com__v2_-Default"));
        windows.add (new Dock.Window ("brave-teams.microsoft.com__v2_-Default"));
        windows.add (new Dock.Window ("io.elementary.appcenter"));
        windows.add (new Dock.Window ("Uninstalled Utility"));
        Dock.WindowSystem.get_default ().windows = windows;
        sync ();
        assert_cmpuint (system.apps.get_n_items (), CompareOperator.EQ, 3);
        var teams = system.get_app ("org.techmore.mseries.TeamsWeb.desktop");
        assert_true (teams.running);
        assert_cmpuint (teams.windows.length, CompareOperator.EQ, 2);
        assert_true (system.get_app ("io.elementary.appcenter.desktop").running);
        Dock.WindowSystem.get_default ().windows = new GenericArray<Dock.Window> ();
        sync ();
        assert_cmpuint (system.apps.get_n_items (), CompareOperator.EQ, 1);
        assert_false (teams.running);
        assert_true (teams.pinned);
    }
    int main (string[] args) {
        Test.init (ref args);
        Test.add_func ("/dock/desktop-and-browser-identities", resolution);
        Test.add_func ("/dock/unknown-and-ambiguous-identities", unknown);
        Test.add_func ("/dock/running-open-close-and-grouping", running_lifecycle);
        Test.add_func ("/dock/ambiguous-classes-and-case-sensitive-ids", ambiguous_aliases);
        Test.add_func ("/dock/activation-uses-complete-raw-identity", activation_identity);
        return Test.run ();
    }
}
