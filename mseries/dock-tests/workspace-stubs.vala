// Controlled asynchronous desktop services around the production WorkspaceSystem.
namespace Dock {
    public class Window : Object {
        public int workspace_index = 0;
        public int64 time_appeared_on_workspace = 0;
    }
    public class Workspace : Object {
        public int index = 0;
        public void update_windows (GenericArray<Window> windows) {}
        public void update_active_workspace () {}
    }
    public class DesktopIntegration : Object {
        public int queries = 0;
        public async int get_n_workspaces () throws Error { queries++; return 3; }
        public async void reorder_workspace (int old_index, int new_index) throws Error {}
    }
    public class WindowSystem : Object {
        private static Once<WindowSystem> instance;
        public static unowned WindowSystem get_default () {
            return instance.once (() => new WindowSystem ());
        }
        public DesktopIntegration? desktop_integration { get; set; }
        public GenericArray<Window> windows { get; set; default = new GenericArray<Window> (); }
        public int active_workspace { get; set; default = 0; }
        public signal void workspace_removed (int index);
    }
}

public class WorkspaceTest {
    private static void drain () {
        var context = MainContext.default ();
        while (context.pending ()) { context.iteration (false); }
    }

    public static int main () {
        unowned var system = Dock.WindowSystem.get_default ();
        unowned var workspaces = Dock.WorkspaceSystem.get_default ();
        workspaces.load.begin ();
        drain ();
        assert (workspaces.workspaces.get_n_items () == 0);
        var integration = new Dock.DesktopIntegration ();
        system.desktop_integration = integration;
        assert (integration.queries == 0);
        system.windows = new GenericArray<Dock.Window> ();
        drain ();
        assert (integration.queries == 1);
        assert (workspaces.workspaces.get_n_items () == 2);
        foreach (var invalid in new int[] { -1, 3, 999 }) {
            system.workspace_removed (invalid);
            drain ();
            assert (workspaces.workspaces.get_n_items () == 2);
        }
        system.workspace_removed (1);
        drain ();
        assert (workspaces.workspaces.get_n_items () == 1);
        print ("PASS: delayed Gala readiness and stale workspace removal\n");
        return 0;
    }
}
