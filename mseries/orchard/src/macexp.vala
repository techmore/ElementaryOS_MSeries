/* Read-only preparation checks for the experimental Linux/KVM macOS lane. */
using Gtk;

public class MacExperiment : Gtk.Box {
    private Gtk.Box steps_box;
    private Gtk.TextView log_view;
    private Gtk.Button run_button;
    private Gtk.Label verdict_title;
    private Gtk.Label verdict_text;
    private Gtk.Box verdict_card;
    private bool running = false;

    private struct Step {
        public string title;
        public string detail;
        public string[] argv;
        public string pass_when;   // "ok" = command exits 0, "fail" = failing is the expected finding, "info" = always shown
    }

    public MacExperiment () {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 0);
    }

    construct {
        hexpand = true;
        var header = new Gtk.HeaderBar ();
        header.add_css_class ("flat");
        header.decoration_layout = ":maximize";
        header.title_widget = new Gtk.Label ("");
        var handle = new Gtk.WindowHandle ();
        handle.child = header;
        append (handle);

        var scroller = new Gtk.ScrolledWindow ();
        scroller.vexpand = true;
        scroller.hscrollbar_policy = Gtk.PolicyType.NEVER;
        append (scroller);

        var clamp = new Gtk.Box (Gtk.Orientation.VERTICAL, 18);
        clamp.margin_start = 32;
        clamp.margin_end = 32;
        clamp.margin_bottom = 28;
        clamp.width_request = 480;
        scroller.child = clamp;

        var hero = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 18);
        var icon = new Gtk.Image.from_icon_name ("computer");
        icon.pixel_size = 64;
        icon.add_css_class ("ml-hero-icon");
        icon.add_css_class ("ml-c-6");
        icon.valign = Gtk.Align.START;
        hero.append (icon);
        var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
        text.hexpand = true;
        text.valign = Gtk.Align.CENTER;
        var title = new Gtk.Label ("macOS (experimental)");
        title.add_css_class ("title-1");
        title.xalign = 0;
        text.append (title);
        var sub = new Gtk.Label ("Check this machine and the files needed for an experimental macOS guest. No VM is started.");
        sub.wrap = true;
        sub.xalign = 0;
        sub.add_css_class ("dim-label");
        text.append (sub);
        hero.append (text);
        clamp.append (hero);

        steps_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        steps_box.add_css_class ("ml-card");
        clamp.append (steps_box);

        run_button = new Gtk.Button.with_label ("Check readiness");
        run_button.add_css_class ("suggested-action");
        run_button.halign = Gtk.Align.END;
        run_button.clicked.connect (() => run.begin ());
        clamp.append (run_button);

        verdict_card = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        verdict_card.add_css_class ("ml-note");
        verdict_card.visible = false;
        verdict_title = new Gtk.Label ("");
        verdict_title.xalign = 0;
        verdict_title.add_css_class ("title-4");
        verdict_text = new Gtk.Label ("");
        verdict_text.xalign = 0;
        verdict_text.wrap = true;
        verdict_card.append (verdict_title);
        verdict_card.append (verdict_text);
        clamp.append (verdict_card);

        var out_label = new Gtk.Label ("Command output");
        out_label.xalign = 0;
        out_label.add_css_class ("ml-sidebar-title");
        out_label.margin_start = 0;
        clamp.append (out_label);
        log_view = new Gtk.TextView ();
        log_view.editable = false;
        log_view.monospace = true;
        log_view.wrap_mode = Gtk.WrapMode.WORD_CHAR;
        log_view.top_margin = 12;
        log_view.bottom_margin = 12;
        log_view.left_margin = 14;
        log_view.right_margin = 14;
        log_view.add_css_class ("ml-console");
        var frame = new Gtk.ScrolledWindow ();
        frame.add_css_class ("ml-console-frame");
        frame.min_content_height = 220;
        frame.child = log_view;
        clamp.append (frame);

        build_rows ();
    }

    private Step[] steps () {
        var helper = Environment.find_program_in_path ("machine-lab-macos-check");
        if (helper == null) {
            helper = Config.MACOS_CHECK_SOURCE;
        }
        return {
            Step () { title = "Linux ARM64 host", detail = "Check the host architecture.", argv = { "python3", helper, "--check", "host" } },
            Step () { title = "Hardware virtualization", detail = "Check access to /dev/kvm.", argv = { "python3", helper, "--check", "kvm" } },
            Step () { title = "VMApple machine", detail = "Check QEMU_VMAPPLE, or the system QEMU.", argv = { "python3", helper, "--check", "qemu" } },
            Step () { title = "Apple boot firmware", detail = "Check MACOS_DIR, or ~/vms/macos.", argv = { "python3", helper, "--check", "firmware" } },
            Step () { title = "Provisioned macOS guest", detail = "Disk, AUX and vm.json from the same VM are required.", argv = { "python3", helper, "--check", "guest" } },
            Step () { title = "Hardware qualification", detail = "M1 Pro/Aurora boot and save/restore are not verified.", argv = { "python3", helper, "--check", "qualification" }, pass_when = "info" }
        };
    }

    private Gtk.Label[] marks = {};
    private Gtk.Label[] details = {};

    private void build_rows () {
        var all = steps ();
        for (int i = 0; i < all.length; i++) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 14);
            row.add_css_class ("ml-form-row");
            if (i < all.length) row.add_css_class ("ml-form-sep");
            var mark = new Gtk.Label ("•");
            mark.add_css_class ("ml-step-skip");
            mark.width_request = 22;
            mark.valign = Gtk.Align.START;
            marks += mark;
            row.append (mark);
            var t = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
            t.hexpand = true;
            var tl = new Gtk.Label (all[i].title);
            tl.xalign = 0;
            tl.add_css_class ("ml-spec-value");
            var dl = new Gtk.Label (all[i].detail);
            dl.xalign = 0;
            dl.wrap = true;
            dl.add_css_class ("ml-spec-label");
            details += dl;
            t.append (tl);
            t.append (dl);
            row.append (t);
            steps_box.append (row);
        }
    }

    private void log (string text) {
        Gtk.TextIter end;
        log_view.buffer.get_end_iter (out end);
        log_view.buffer.insert (ref end, text, -1);
    }

    private async void run () {
        if (running) {
            return;
        }
        running = true;
        run_button.sensitive = false;
        log_view.buffer.text = "";
        verdict_card.visible = false;
        var all = steps ();
        int blocked = 0;
        for (int i = 0; i < all.length; i++) {
            marks[i].label = "…";
            marks[i].remove_css_class ("ml-step-ok");
            marks[i].remove_css_class ("ml-step-fail");
            log ("$ %s\n".printf (string.joinv (" ", all[i].argv)));
            string output = "";
            int code = -1;
            try {
                var p = new Subprocess.newv (all[i].argv, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
                uint kill = Timeout.add_seconds (8, () => { p.force_exit (); return Source.REMOVE; });
                string? so;
                string? se;
                yield p.communicate_utf8_async (null, null, out so, out se);
                Source.remove (kill);
                output = so ?? "";
                code = p.get_if_exited () ? p.get_exit_status () : -1;
            } catch (Error e) {
                output = e.message;
            }
            log (output.strip () + "\n[exit %d]\n\n".printf (code));
            bool ok = code == 0;
            if (all[i].pass_when == "info") {
                marks[i].label = "i";
                marks[i].add_css_class ("ml-step-skip");
            } else if (!ok) {
                marks[i].label = "✗";
                marks[i].add_css_class ("ml-step-fail");
                blocked++;
                var first = output.strip ().split ("\n")[0];
                details[i].label = first.length > 0 ? first : details[i].label;
            } else {
                marks[i].label = "✓";
                marks[i].add_css_class ("ml-step-ok");
            }
            yield sleep_ms (350);
        }
        verdict_title.label = blocked > 0 ? "More preparation is needed" : "Files present; guest boot remains unverified";
        verdict_text.label = "An upstream experiment reached Ventura Setup Assistant on an M2 Pro using patched Linux KVM, QEMU and Reims graphics. This M1 Pro/Aurora configuration is not qualified. Prepare the matching guest files during a macOS visit; keep the working host kernel in place. Dock-controlled save/restore and iMessage still need separate tests.";
        verdict_card.visible = true;
        run_button.label = "Check again";
        run_button.sensitive = true;
        running = false;
    }

    private async void sleep_ms (uint ms) {
        Timeout.add (ms, () => { sleep_ms.callback (); return Source.REMOVE; });
        yield;
    }
}
