public class MainWindow : Gtk.ApplicationWindow {
    private Gtk.TextView prompt_view;
    private Gtk.DropDown intent_picker;
    private Gtk.Label assistant_status;
    private Gtk.Label hardware_status;
    private Gtk.Label engine_status;
    private Gtk.Label recipe_status;
    private Gtk.Button generate_button;
    private Gtk.Stack content_stack;
    private Gtk.ListBox saved_recipes;
    private Gtk.ListBox generated_outputs;
    private Gtk.ScrolledWindow output_scroll;
    private Granite.Placeholder images_placeholder;
    private Gtk.Label outputs_heading;
    private PromptAssistant assistant = new PromptAssistant ();
    private string selected_workflow = "Freeform";

    private const string[] INTENTS = { "Portrait", "Streamer scene", "Product photo", "Illustration", "Graphic or poster" };

    public MainWindow (Gtk.Application app) {
        Object (application: app, title: "Image Studio", default_width: 1380, default_height: 900 );
        add_css_class ("mseries-image-studio");

        var style = new Gtk.CssProvider ();
        style.load_from_string ("""
            .mseries-image-studio .studio-sidebar { border-right: 1px solid alpha(currentColor, 0.10); }
            .mseries-image-studio .section-heading { font-size: 0.78em; font-weight: 700; letter-spacing: 0.05em; opacity: 0.62; }
            .mseries-image-studio .preview-stage { background: alpha(currentColor, 0.035); border-radius: 14px; }
            .mseries-image-studio .preview-icon { opacity: 0.35; }
            .mseries-image-studio .status-card { padding: 12px; border-radius: 10px; background: alpha(currentColor, 0.04); }
            .mseries-image-studio .small-copy { font-size: 0.9em; opacity: 0.74; }
            .mseries-image-studio .prompt-editor { padding: 10px; border-radius: 8px; }
            .mseries-image-studio .queue-row { padding: 8px 10px; border-radius: 8px; background: alpha(currentColor, 0.04); }
        """);
        Gtk.StyleContext.add_provider_for_display (get_display (), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);

        var header = new Gtk.HeaderBar () { show_title_buttons = false };
        header.add_css_class (Granite.STYLE_CLASS_FLAT);
        header.pack_start (new Gtk.WindowControls (Gtk.PackType.START));
        header.title_widget = new Gtk.Label ("Image Studio");
        var menu_button = new Gtk.MenuButton () { icon_name = "open-menu-symbolic", tooltip_text = "Application menu" };
        menu_button.update_property (Gtk.AccessibleProperty.LABEL, "Application menu", -1);
        var app_menu = new GLib.Menu ();
        app_menu.append ("About Image Studio", "app.about");
        app_menu.append ("Quit", "app.quit");
        menu_button.menu_model = app_menu;
        header.pack_end (menu_button);

        var sidebar = build_sidebar ();
        content_stack = new Gtk.Stack () { hexpand = true, vexpand = true, transition_type = Gtk.StackTransitionType.CROSSFADE };
        content_stack.add_named (build_create_page (), "create");
        content_stack.add_named (build_library_page (), "library");

        var inspector = build_inspector ();
        var main_pane = new Gtk.Paned (Gtk.Orientation.HORIZONTAL) {
            start_child = content_stack,
            end_child = inspector,
            position = 720,
            resize_start_child = true,
            resize_end_child = false,
            shrink_start_child = true,
            shrink_end_child = true
        };
        var shell = new Gtk.Paned (Gtk.Orientation.HORIZONTAL) {
            start_child = sidebar,
            end_child = main_pane,
            position = 200,
            resize_start_child = false,
            resize_end_child = true,
            shrink_start_child = true,
            shrink_end_child = true
        };
        var overlay = new Gtk.Overlay () { child = shell };
        var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        root.append (header);
        root.append (overlay);
        child = root;

        refresh_hardware_status ();
        load_saved_recipes ();
        arm_test_hooks ();
    }

    private Gtk.Widget build_sidebar () {
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { width_request = 200, margin_top = 16, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        box.add_css_class ("studio-sidebar");
        var title = new Gtk.Label ("WORKSPACE") { xalign = 0, margin_start = 8, margin_bottom = 4 };
        title.add_css_class ("section-heading");
        box.append (title);

        var create = new Gtk.Button.with_label ("Create") { halign = Gtk.Align.FILL };
        create.add_css_class ("flat");
        create.clicked.connect (() => { content_stack.visible_child_name = "create"; });
        create.update_property (Gtk.AccessibleProperty.LABEL, "Create an image", -1);
        box.append (create);
        var library = new Gtk.Button.with_label ("Library") { halign = Gtk.Align.FILL };
        library.add_css_class ("flat");
        library.clicked.connect (() => { content_stack.visible_child_name = "library"; });
        library.update_property (Gtk.AccessibleProperty.LABEL, "Open image library", -1);
        box.append (library);

        var workflows = new Gtk.Label ("GUIDED WORKFLOWS") { xalign = 0, margin_start = 8, margin_top = 20, margin_bottom = 4 };
        workflows.add_css_class ("section-heading");
        box.append (workflows);
        add_workflow_button (box, "Model readiness", "Check one conservative render", "Model readiness");
        add_workflow_button (box, "LoRA comparison", "Compare weights with a fixed seed", "LoRA comparison");
        add_workflow_button (box, "Prompt type study", "Compare three prompt structures", "Prompt type study");

        var spacer = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { vexpand = true };
        box.append (spacer);
        var device_heading = new Gtk.Label ("THIS DEVICE") { xalign = 0, margin_start = 8, margin_bottom = 4 };
        device_heading.add_css_class ("section-heading");
        box.append (device_heading);
        hardware_status = new Gtk.Label ("") { xalign = 0, wrap = true, margin_start = 8, margin_end = 8 };
        hardware_status.add_css_class ("small-copy");
        box.append (hardware_status);
        return box;
    }

    private void add_workflow_button (Gtk.Box parent, string title, string subtitle, string workflow) {
        var button = new Gtk.Button () { halign = Gtk.Align.FILL };
        button.add_css_class ("flat");
        var contents = new Gtk.Box (Gtk.Orientation.VERTICAL, 2) { margin_top = 5, margin_bottom = 5, margin_start = 6, margin_end = 6 };
        var heading = new Gtk.Label (title) { xalign = 0, wrap = true };
        heading.add_css_class ("heading");
        var detail = new Gtk.Label (subtitle) { xalign = 0, wrap = true };
        detail.add_css_class ("dim-label");
        contents.append (heading);
        contents.append (detail);
        button.child = contents;
        button.update_property (Gtk.AccessibleProperty.LABEL, "%s: %s".printf (title, subtitle), -1);
        button.clicked.connect (() => select_workflow (workflow));
        parent.append (button);
    }

    private Gtk.Widget build_create_page () {
        var page = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        var heading = new Gtk.Label ("Create") { xalign = 0 };
        heading.add_css_class ("title-2");
        page.append (heading);

        var preview = new Gtk.Box (Gtk.Orientation.VERTICAL, 10) { hexpand = true, vexpand = true, halign = Gtk.Align.FILL, valign = Gtk.Align.FILL };
        preview.add_css_class ("preview-stage");
        preview.set_size_request (-1, 250);
        var preview_content = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { halign = Gtk.Align.CENTER, valign = Gtk.Align.CENTER, vexpand = true };
        var image_icon = new Gtk.Image.from_icon_name ("image-x-generic-symbolic") { pixel_size = 42 };
        image_icon.add_css_class ("preview-icon");
        var empty_title = new Gtk.Label ("Your image preview will appear here") { wrap = true, justify = Gtk.Justification.CENTER };
        empty_title.add_css_class ("title-3");
        var empty_detail = new Gtk.Label ("Image generation is waiting for a model runtime qualified on this M-Series device.") { wrap = true, justify = Gtk.Justification.CENTER, max_width_chars = 64 };
        empty_detail.add_css_class ("dim-label");
        preview_content.append (image_icon);
        preview_content.append (empty_title);
        preview_content.append (empty_detail);
        preview.append (preview_content);
        page.append (preview);

        var prompt_header = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var prompt_title = new Gtk.Label ("Prompt") { xalign = 0, hexpand = true };
        prompt_title.add_css_class ("title-4");
        intent_picker = new Gtk.DropDown.from_strings (INTENTS);
        intent_picker.update_property (Gtk.AccessibleProperty.LABEL, "Prompt type", -1);
        var assistant_button = new Gtk.Button.with_label ("Help shape this prompt") { tooltip_text = "Ask the already-running M-Series local assistant for an editable suggestion" };
        assistant_button.update_property (Gtk.AccessibleProperty.LABEL, "Help shape this prompt", -1);
        assistant_button.clicked.connect (() => { request_suggestion.begin (); });
        prompt_header.append (prompt_title);
        prompt_header.append (intent_picker);
        prompt_header.append (assistant_button);
        page.append (prompt_header);

        prompt_view = new Gtk.TextView () { wrap_mode = Gtk.WrapMode.WORD_CHAR, height_request = 120, left_margin = 8, right_margin = 8, top_margin = 8, bottom_margin = 8 };
        prompt_view.add_css_class ("prompt-editor");
        prompt_view.buffer.text = "A warm, candid portrait in a modern creator studio, soft daylight, thoughtful composition, natural color.";
        prompt_view.update_property (Gtk.AccessibleProperty.LABEL, "Image prompt", -1);
        var prompt_scroll = new Gtk.ScrolledWindow () { child = prompt_view, min_content_height = 120, max_content_height = 180, hscrollbar_policy = Gtk.PolicyType.NEVER };
        prompt_scroll.add_css_class ("card");
        page.append (prompt_scroll);
        assistant_status = new Gtk.Label ("Prompt help uses the existing local assistant at 127.0.0.1:8766; it will not start or replace a worker.") { xalign = 0, wrap = true };
        assistant_status.add_css_class ("dim-label");
        page.append (assistant_status);

        var queue_heading = new Gtk.Label ("Queue") { xalign = 0, margin_top = 2 };
        queue_heading.add_css_class ("title-4");
        page.append (queue_heading);
        var queue_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10) { margin_top = 4, margin_bottom = 4, margin_start = 8, margin_end = 8 };
        queue_row.add_css_class ("queue-row");
        var queue_icon = new Gtk.Image.from_icon_name ("content-loading-symbolic");
        var queue_text = new Gtk.Label ("No image jobs queued") { xalign = 0, hexpand = true };
        recipe_status = new Gtk.Label ("Save a prompt recipe to reopen its settings later.") { xalign = 1, wrap = true };
        recipe_status.add_css_class ("dim-label");
        queue_row.append (queue_icon);
        queue_row.append (queue_text);
        queue_row.append (recipe_status);
        page.append (queue_row);
        return page;
    }

    private Gtk.Widget build_library_page () {
        var page = new Gtk.Box (Gtk.Orientation.VERTICAL, 10) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        var heading = new Gtk.Label ("Library") { xalign = 0 };
        heading.add_css_class ("title-2");
        page.append (heading);
        var explanation = new Gtk.Label ("Generated images keep their prompt, model, LoRAs and tags beside the image. New renders will appear here when a local engine is qualified.") { xalign = 0, wrap = true, max_width_chars = 90 };
        explanation.add_css_class ("dim-label");
        page.append (explanation);
        images_placeholder = new Granite.Placeholder ("No generated images yet") {
            description = "Save a recipe now; generated outputs will join it once a local image engine is qualified."
        };
        images_placeholder.hexpand = true;
        images_placeholder.vexpand = true;
        images_placeholder.set_size_request (-1, 220);
        page.append (images_placeholder);
        outputs_heading = new Gtk.Label ("Generated images") { xalign = 0 };
        outputs_heading.add_css_class ("title-4");
        outputs_heading.visible = false;
        page.append (outputs_heading);
        generated_outputs = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.NONE, visible = false };
        generated_outputs.add_css_class ("boxed-list");
        output_scroll = new Gtk.ScrolledWindow () {
            child = generated_outputs,
            min_content_height = 220,
            max_content_height = 380,
            vexpand = true,
            visible = false
        };
        page.append (output_scroll);
        var recipe_heading = new Gtk.Label ("Saved recipes") { xalign = 0 };
        recipe_heading.add_css_class ("title-4");
        page.append (recipe_heading);
        saved_recipes = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.NONE };
        saved_recipes.add_css_class ("boxed-list");
        saved_recipes.set_placeholder (new Gtk.Label ("No saved recipes yet."));
        var recipe_scroll = new Gtk.ScrolledWindow () {
            child = saved_recipes,
            min_content_height = 120,
            max_content_height = 220,
            vexpand = true
        };
        page.append (recipe_scroll);
        return page;
    }

    private Gtk.Widget build_inspector () {
        var panel = new Gtk.Box (Gtk.Orientation.VERTICAL, 10) { width_request = 270, margin_top = 18, margin_bottom = 18, margin_start = 14, margin_end = 14 };
        var heading = new Gtk.Label ("Generation settings") { xalign = 0 };
        heading.add_css_class ("title-3");
        panel.append (heading);

        var device_card = new Gtk.Box (Gtk.Orientation.VERTICAL, 5) { margin_top = 4, margin_bottom = 4, margin_start = 8, margin_end = 8 };
        device_card.add_css_class ("status-card");
        var device_label = new Gtk.Label ("M-Series device check") { xalign = 0 };
        device_label.add_css_class ("heading");
        var device_detail = new Gtk.Label ("Hardware is observed, not guessed. Model and image-size recommendations appear after a successful calibration.") { xalign = 0, wrap = true };
        device_detail.add_css_class ("small-copy");
        device_card.append (device_label);
        device_card.append (device_detail);
        panel.append (device_card);

        engine_status = new Gtk.Label ("Image engine: not configured\nCompatibility: unverified") { xalign = 0, wrap = true };
        engine_status.add_css_class ("status-card");
        panel.append (engine_status);

        append_section_label (panel, "MODEL");
        var model = new Gtk.Entry () { placeholder_text = "No qualified model installed", editable = false };
        model.update_property (Gtk.AccessibleProperty.LABEL, "Image model", -1);
        panel.append (model);

        append_section_label (panel, "LORA");
        var lora = new Gtk.Entry () { placeholder_text = "Choose a compatible LoRA", editable = false };
        lora.update_property (Gtk.AccessibleProperty.LABEL, "LoRA model", -1);
        panel.append (lora);
        var weight_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var weight_title = new Gtk.Label ("LoRA strength") { xalign = 0, hexpand = true };
        var weight = new Gtk.Scale.with_range (Gtk.Orientation.HORIZONTAL, 0.0, 1.5, 0.05) { width_request = 100, draw_value = true, digits = 2, sensitive = false };
        weight.set_value (1.0);
        weight.update_property (Gtk.AccessibleProperty.LABEL, "LoRA strength", -1);
        weight_row.append (weight_title);
        weight_row.append (weight);
        panel.append (weight_row);

        append_section_label (panel, "OUTPUT");
        var dimensions = new Gtk.DropDown.from_strings ({ "512 × 512", "768 × 768", "1024 × 1024" }) { sensitive = false };
        dimensions.update_property (Gtk.AccessibleProperty.LABEL, "Image dimensions", -1);
        panel.append (dimensions);
        var batch_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var batch_title = new Gtk.Label ("Images in this run") { xalign = 0, hexpand = true };
        var batch = new Gtk.SpinButton.with_range (1, 8, 1) { value = 1, numeric = true, sensitive = false };
        batch.update_property (Gtk.AccessibleProperty.LABEL, "Number of images", -1);
        batch_row.append (batch_title);
        batch_row.append (batch);
        panel.append (batch_row);

        var spacer = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { vexpand = true };
        panel.append (spacer);
        generate_button = new Gtk.Button.with_label ("Generate preview") { sensitive = false };
        generate_button.add_css_class (Granite.CssClass.SUGGESTED);
        generate_button.tooltip_text = "Generation is disabled until a model/runtime pair is calibrated on this device.";
        generate_button.update_property (Gtk.AccessibleProperty.LABEL, "Generate preview, unavailable until engine qualification", -1);
        panel.append (generate_button);
        var save = new Gtk.Button.with_label ("Save prompt recipe") { halign = Gtk.Align.FILL };
        save.clicked.connect (save_current_recipe);
        panel.append (save);
        return panel;
    }

    private void append_section_label (Gtk.Box parent, string label) {
        var heading = new Gtk.Label (label) { xalign = 0, margin_top = 8 };
        heading.add_css_class ("section-heading");
        parent.append (heading);
    }

    private void select_workflow (string workflow) {
        content_stack.visible_child_name = "create";
        selected_workflow = workflow;
        if (workflow == "Model readiness") {
            engine_status.label = "Model readiness\nWaiting for a qualified image engine and model.";
            assistant_status.label = "This workflow will load one model and render one conservative image after an engine is qualified.";
        } else if (workflow == "LoRA comparison") {
            engine_status.label = "LoRA comparison\nWaiting for a qualified base model and compatible LoRA.";
            assistant_status.label = "This workflow will compare LoRA off/on or selected weights with the same prompt and seed.";
        } else {
            engine_status.label = "Prompt type study\nWaiting for a qualified image engine.";
            assistant_status.label = "This workflow will compare three editable prompt structures while holding subject and seed steady.";
            intent_picker.selected = 1;
        }
        generate_button.tooltip_text = GenerationGate.explain (false, HostCapabilities.capture ().available_bytes, 0);
    }

    private GenerationRecipe current_recipe () {
        var recipe = new GenerationRecipe ();
        recipe.prompt = prompt_view.buffer.text;
        var selected = intent_picker.selected;
        recipe.intent = selected < INTENTS.length ? INTENTS[selected] : "Portrait";
        recipe.workflow = selected_workflow;
        recipe.engine_id = "unconfigured";
        recipe.tags = { "mseries-image-studio", recipe.intent.down ().replace (" ", "-") };
        return recipe;
    }

    private void save_current_recipe () {
        try {
            var recipe = current_recipe ();
            RecipeStore.save (recipe);
            recipe_status.label = "Recipe saved to Library.";
            var row = new Gtk.ListBoxRow ();
            var label = new Gtk.Label ("%s\n%s".printf (recipe.intent, recipe.prompt)) { xalign = 0, wrap = true, margin_top = 8, margin_bottom = 8, margin_start = 12, margin_end = 12 };
            row.child = label;
            saved_recipes.prepend (row);
        } catch (Error e) {
            recipe_status.label = "Recipe could not be saved: %s".printf (e.message);
        }
    }

    private async void request_suggestion () {
        var original = prompt_view.buffer.text.strip ();
        if (original == "") {
            assistant_status.label = "Add a subject or idea first, then ask for prompt help.";
            return;
        }
        assistant_status.label = "Asking the already-running M-Series local assistant…";
        try {
            var selected = intent_picker.selected;
            var intent = selected < INTENTS.length ? INTENTS[selected] : "Portrait";
            var suggestion = yield assistant.suggest (intent, original);
            show_suggestion (suggestion);
            assistant_status.label = "Suggestion ready. Review it before replacing your prompt.";
        } catch (Error e) {
            assistant_status.label = "Prompt help unavailable: %s".printf (e.message);
        }
    }

    private void show_suggestion (string suggestion) {
        var dialog = new Gtk.Window () { title = "Review prompt suggestion", transient_for = this, modal = true, default_width = 520, default_height = 360 };
        var body = new Gtk.Box (Gtk.Orientation.VERTICAL, 10) { margin_top = 16, margin_bottom = 16, margin_start = 16, margin_end = 16 };
        body.append (new Gtk.Label ("Your original prompt is unchanged until you accept this suggestion.") { xalign = 0, wrap = true });
        var proposal = new Gtk.TextView () { editable = false, cursor_visible = false, wrap_mode = Gtk.WrapMode.WORD_CHAR, height_request = 150 };
        proposal.buffer.text = suggestion;
        var scroll = new Gtk.ScrolledWindow () { child = proposal, min_content_height = 150 };
        body.append (scroll);
        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) { halign = Gtk.Align.END };
        var keep = new Gtk.Button.with_label ("Keep original");
        var accept = new Gtk.Button.with_label ("Use suggestion");
        accept.add_css_class (Granite.CssClass.SUGGESTED);
        keep.clicked.connect (() => dialog.destroy ());
        accept.clicked.connect (() => {
            prompt_view.buffer.text = suggestion;
            dialog.destroy ();
        });
        actions.append (keep);
        actions.append (accept);
        body.append (actions);
        dialog.child = body;
        dialog.present ();
    }

    private void refresh_hardware_status () {
        var host = HostCapabilities.capture ();
        hardware_status.label = "%s\n%s\n%s".printf (
            host.memory_summary (),
            host.desktop_reserve_met () ? "6 GiB desktop reserve: met" : "6 GiB desktop reserve: not met",
            host.has_render_node ? "Render node detected" : "No render node detected");
        engine_status.label = "Image engine: not configured\n%s".printf (host.accelerator_summary ());
    }

    private void load_saved_recipes () {
        try {
            foreach (var recipe in RecipeStore.load_recent ()) {
                var row = new Gtk.ListBoxRow ();
                var label = new Gtk.Label ("%s\n%s".printf (recipe.intent, recipe.prompt)) {
                    xalign = 0,
                    wrap = true,
                    margin_top = 8,
                    margin_bottom = 8,
                    margin_start = 12,
                    margin_end = 12
                };
                row.child = label;
                saved_recipes.append (row);
            }
            load_saved_outputs ();
        } catch (Error e) {
            warning ("Could not load saved image recipes: %s", e.message);
        }
    }

    private void load_saved_outputs () throws Error {
        foreach (var recipe in GenerationOutputStore.load_recent ()) {
            var row = new Gtk.ListBoxRow ();
            var contents = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12) {
                margin_top = 10,
                margin_bottom = 10,
                margin_start = 12,
                margin_end = 12
            };
            Gdk.Texture texture;
            try {
                var thumbnail = new Gdk.Pixbuf.from_file_at_scale (recipe.image_path, 320, 240, true);
                uint8[] thumbnail_bytes;
                thumbnail.save_to_buffer (out thumbnail_bytes, "png");
                texture = Gdk.Texture.from_bytes (new Bytes (thumbnail_bytes));
            } catch (Error e) {
                warning ("Could not create a thumbnail for %s: %s", recipe.image_path, e.message);
                continue;
            }
            var picture = new Gtk.Picture.for_paintable (texture) {
                content_fit = Gtk.ContentFit.CONTAIN,
                width_request = 210,
                height_request = 150
            };
            var detail = new Gtk.Box (Gtk.Orientation.VERTICAL, 5) { hexpand = true, valign = Gtk.Align.CENTER };
            var title = new Gtk.Label ("%s · %dx%d".printf (recipe.intent, recipe.width, recipe.height)) { xalign = 0, wrap = true };
            title.add_css_class ("heading");
            detail.append (title);
            detail.append (new Gtk.Label (recipe.prompt) { xalign = 0, wrap = true, max_width_chars = 64 });
            var model_info = recipe.model_id == "" ? "Model not recorded" : "Model: %s".printf (recipe.model_id);
            detail.append (new Gtk.Label (model_info) { xalign = 0, wrap = true });
            if (recipe.lora_id != "") detail.append (new Gtk.Label ("LoRA: %s · %.2f".printf (recipe.lora_id, recipe.lora_weight)) { xalign = 0, wrap = true });
            if (recipe.tags.length > 0) detail.append (new Gtk.Label ("Tags: %s".printf (string.joinv (", ", recipe.tags))) { xalign = 0, wrap = true });
            contents.append (picture);
            contents.append (detail);
            row.child = contents;
            generated_outputs.append (row);
        }
        var has_outputs = generated_outputs.get_first_child () != null;
        images_placeholder.visible = !has_outputs;
        outputs_heading.visible = has_outputs;
        generated_outputs.visible = has_outputs;
        output_scroll.visible = has_outputs;
    }

    private void arm_test_hooks () {
        var prompt = Environment.get_variable ("M_SERIES_IMAGE_STUDIO_TEST_PROMPT");
        if (prompt != null) prompt_view.buffer.text = prompt;

        var workflow = Environment.get_variable ("M_SERIES_IMAGE_STUDIO_TEST_WORKFLOW");
        if (workflow != null && (workflow == "Model readiness" || workflow == "LoRA comparison" || workflow == "Prompt type study")) {
            select_workflow (workflow);
        }
        if (Environment.get_variable ("M_SERIES_IMAGE_STUDIO_TEST_PAGE") == "library") {
            content_stack.visible_child_name = "library";
        }

        var screenshot = Environment.get_variable ("M_SERIES_IMAGE_STUDIO_SCREENSHOT");
        if (screenshot != null) {
            Timeout.add (1600, () => {
                var paintable = new Gtk.WidgetPaintable (this);
                var snapshot = new Gtk.Snapshot ();
                paintable.snapshot (snapshot, get_width (), get_height ());
                var node = snapshot.free_to_node ();
                if (node != null) {
                    var texture = get_renderer ().render_texture (node, null);
                    if (!texture.save_to_png (screenshot)) warning ("Screenshot could not be saved: %s", screenshot);
                }
                return Source.REMOVE;
            });
        }
        var save_recipe = Environment.get_variable ("M_SERIES_IMAGE_STUDIO_TEST_SAVE_RECIPE");
        if (save_recipe == "1") save_current_recipe ();

        var exit_after = Environment.get_variable ("M_SERIES_IMAGE_STUDIO_EXIT_AFTER");
        if (exit_after != null) {
            int seconds = 3;
            int.try_parse (exit_after, out seconds);
            Timeout.add_seconds ((uint) int.max (1, seconds), () => {
                ((Gtk.Application) application).quit ();
                return Source.REMOVE;
            });
        }
    }
}
