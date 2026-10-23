use crate::assistant;
use crate::host::HostCapabilities;
use crate::recipe::{Recipe, RecipeStore, load_outputs};
use granite::prelude::PlaceholderExt;
use gtk::prelude::*;
use gtk::{gio, glib};
use std::cell::RefCell;
use std::path::Path;
use std::rc::Rc;
use std::sync::mpsc::{self, TryRecvError};
use std::time::Duration;

const INTENTS: &[&str] = &[
    "Portrait",
    "Streamer scene",
    "Product photo",
    "Illustration",
    "Graphic or poster",
];
const SAMPLE_SERIES: &str = "Three-image editorial series featuring Alexandra Daddario portrayed as a 22-year-old adult college student and modern streamer personality: (1) hosting a relaxed gaming stream, (2) recording a campus-day vlog, (3) editing a video in a bright campus cafe. Casual everyday clothing, friendly expression, natural light, consistent adult identity and visual style, no sexualization.";

pub struct ImageStudioWindow {
    window: gtk::ApplicationWindow,
}

impl ImageStudioWindow {
    pub fn build(application: &gtk::Application) -> Self {
        let window = gtk::ApplicationWindow::builder()
            .application(application)
            .title("Image Studio")
            .default_width(1380)
            .default_height(900)
            .build();
        window.add_css_class("mseries-image-studio");
        install_css(&window);

        let header = gtk::HeaderBar::builder().show_title_buttons(true).build();
        header.add_css_class(granite::STYLE_CLASS_FLAT);
        let title = gtk::Label::new(Some("Image Studio"));
        header.set_title_widget(Some(&title));
        let menu = gio::Menu::new();
        menu.append(Some("About Image Studio"), Some("app.about"));
        menu.append(Some("Quit"), Some("app.quit"));
        let menu_button = gtk::MenuButton::builder()
            .icon_name("open-menu-symbolic")
            .menu_model(&menu)
            .build();
        menu_button.update_property(&[gtk::accessible::Property::Label("Application menu")]);
        header.pack_end(&menu_button);

        let stack = gtk::Stack::builder()
            .hexpand(true)
            .vexpand(true)
            .hhomogeneous(false)
            .vhomogeneous(false)
            .transition_type(gtk::StackTransitionType::Crossfade)
            .build();
        let recipe_store = RecipeStore::default_store();
        let create = build_create_page();
        let library = build_library_page(&recipe_store);
        stack.add_named(&create.page, Some("create"));
        stack.add_named(
            &crate::logs::page(glib::user_data_dir().join("mseries-image-studio")),
            Some("logs"),
        );
        stack.add_named(&library.page, Some("library"));

        let inspector = build_inspector();
        let next_run = gtk::Box::new(gtk::Orientation::Vertical, 6);
        next_run.add_css_class("pantheon-surface");
        next_run.add_css_class("pantheon-inset");
        let next_title = gtk::Label::new(Some("Next run · Model and settings"));
        next_title.set_xalign(0.0);
        next_title.add_css_class("heading");
        next_run.append(&next_title);
        next_run.append(&inspector.model_picker);
        let summary = gtk::Label::new(None);
        summary.set_xalign(0.0);
        summary.set_wrap(true);
        summary.set_selectable(true);
        next_run.append(&summary);
        if let Some(page) = create.page.downcast_ref::<gtk::Box>() {
            page.prepend(&next_run);
        }
        let settings = inspector.clone_refs();
        let weak_summary = summary.downgrade();
        glib::timeout_add_local(Duration::from_millis(250), move || {
            let Some(summary) = weak_summary.upgrade() else {
                return glib::ControlFlow::Break;
            };
            let sizes = [
                "512 × 512",
                "768 × 768",
                "1024 × 1024",
                "512 × 768",
                "768 × 512",
                "768 × 1024",
                "1024 × 768",
            ];
            summary.set_text(&format!(
                "{} · VAE: {}\n{} / {} · {} steps · CFG {:.1} · {} · Seed {}",
                short_model_name(settings.model.text().as_str()),
                format!(
                    "{} ({})",
                    short_model_name(settings.vae.text().as_str()),
                    if settings.vae_on_cpu.is_active() {
                        "CPU"
                    } else {
                        "GPU"
                    }
                ),
                ["Euler", "Euler ancestral", "DPM++ 2M", "DPM++ 2M SDE"]
                    .get(settings.sampler.selected() as usize)
                    .unwrap_or(&"Unknown sampler"),
                if settings.scheduler.selected() == 1 {
                    "Karras"
                } else {
                    "Discrete"
                },
                settings.steps.value_as_int(),
                settings.cfg.value(),
                sizes
                    .get(settings.dimensions.selected() as usize)
                    .unwrap_or(&"Unknown size"),
                if settings.seed.value_as_int() < 0 {
                    "Random".into()
                } else {
                    settings.seed.value_as_int().to_string()
                }
            ));
            let reference = settings.reference_image.text();
            let reference_label = if reference.is_empty() {
                "Reference: none · prompt only".into()
            } else {
                format!(
                    "Reference: {} · strength {:.2}",
                    Path::new(reference.as_str())
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy(),
                    settings.reference_strength.value()
                )
            };
            summary.set_text(&format!(
                "{}\n{} · tiles {} · {} CPU threads",
                summary.text(),
                reference_label,
                settings.vae_tile_size.value_as_int(),
                settings.cpu_threads.value_as_int()
            ));
            summary.set_text(&format!(
                "{} · weights {} · GPU budget {:.1} GiB",
                summary.text(),
                ["disk", "cpu", "auto"]
                    .get(settings.params_backend.selected() as usize)
                    .unwrap_or(&"disk"),
                settings.max_vram_gib.value()
            ));
            summary.set_tooltip_text(Some(&format!(
                "Model: {}\nVAE: {}",
                settings.model.text(),
                settings.vae.text()
            )));
            glib::ControlFlow::Continue
        });
        let reuse: Rc<dyn Fn(&Recipe)> = {
            let create = create.clone_refs();
            let inspector = inspector.clone_refs();
            let stack = stack.clone();
            Rc::new(move |recipe| {
                load_recipe(recipe, &create, &inspector);
                stack.set_visible_child_name("create");
            })
        };
        let snapshot: Rc<dyn Fn() -> Recipe> = {
            let create = create.clone_refs();
            let inspector = inspector.clone_refs();
            Rc::new(move || current_recipe(&create, &inspector))
        };
        stack.add_named(&crate::study::review(reuse.clone()), Some("review"));
        stack.add_named(&crate::study::compare(snapshot, reuse), Some("compare"));
        let select_model: Rc<dyn Fn(&str)> = {
            let create = create.clone_refs();
            let inspector = inspector.clone_refs();
            let stack = stack.clone();
            Rc::new(move |path| {
                if path.contains("Qwen3VL") {
                    stack.set_visible_child_name("review");
                    return;
                }
                inspector.model.set_text(path);
                inspector.dimensions.set_selected(0);
                inspector.batch.set_value(1.0);
                inspector.seed.set_value(424242.0);
                inspector.lora.set_text("");
                let turbo = path.contains("turbo");
                inspector.steps.set_value(if turbo { 4.0 } else { 20.0 });
                inspector.cfg.set_value(if turbo { 1.0 } else { 7.0 });
                inspector.sampler.set_selected(if turbo { 1 } else { 0 });
                if path.contains("Realistic") {
                    inspector.steps.set_value(30.0);
                    inspector.cfg.set_value(5.0);
                    inspector.dimensions.set_selected(3);
                    inspector.sampler.set_selected(2);
                    inspector.scheduler.set_selected(1);
                }
                if turbo {
                    set_text(&create.negative, "");
                }
                inspector.recipe_status.set_text("Selected model and starter settings loaded. Local memory admission still applies.");
                stack.set_visible_child_name("create");
            })
        };
        stack.add_named(&crate::models::page(select_model), Some("models"));

        stack.add_named(
            &build_model_guide(&create, &inspector, &stack),
            Some("guide"),
        );
        let reload = gtk::Button::with_label("Reload recipe");
        reload.set_tooltip_text(Some(
            "Load the active or last completed generation recipe into Create",
        ));
        let reload_create = create.clone_refs();
        let reload_inspector = inspector.clone_refs();
        let reload_stack = stack.clone();
        reload.connect_clicked(move |_| {
            let path = gtk::glib::user_data_dir().join("mseries-image-studio/current-job.json");
            let result = std::fs::read(path)
                .ok()
                .and_then(|raw| serde_json::from_slice::<serde_json::Value>(&raw).ok())
                .and_then(|job| job["recipe_path"].as_str().map(str::to_owned))
                .and_then(|path| std::fs::read(path).ok())
                .and_then(|raw| serde_json::from_slice::<Recipe>(&raw).ok());
            if let Some(recipe) = result {
                load_recipe(&recipe, &reload_create, &reload_inspector);
                reload_stack.set_visible_child_name("create");
            } else {
                reload_inspector
                    .recipe_status
                    .set_text("No readable generation recipe is available yet.");
            }
        });
        header.pack_start(&reload);
        let run = gtk::Button::with_label("Run");
        run.add_css_class("suggested-action");
        run.set_tooltip_text(Some(
            "Run the local image recipe; readiness or memory errors appear in the preview",
        ));
        let action = inspector.generate.clone();
        let run_action = gio::SimpleAction::new("run", None);
        run_action.connect_activate(move |_, _| action.emit_clicked());
        application.add_action(&run_action);
        application.set_accels_for_action("app.run", &["<Control>Return"]);
        run.set_action_name(Some("app.run"));
        header.pack_end(&run);
        let stop = gtk::Button::with_label("Stop");
        stop.set_tooltip_text(Some(
            "Cancel the current image, review or remaining sweep queue",
        ));
        stop.connect_clicked(move |_| {
            let base = glib::user_data_dir().join("mseries-image-studio");
            let _ = std::fs::create_dir_all(&base);
            if let Err(error) = std::fs::write(base.join("cancel.request"), "cancel") {
                eprintln!("Could not request cancellation: {error}");
            }
        });
        header.pack_end(&stop);
        let settings_popover = gtk::Popover::new();
        settings_popover.set_size_request(320, 520);
        let settings_button = gtk::MenuButton::builder()
            .label("Settings")
            .popover(&settings_popover)
            .build();
        settings_button.set_visible(false);
        settings_button.update_property(&[gtk::accessible::Property::Label("Generation settings")]);
        header.pack_end(&settings_button);
        let main_split = gtk::Paned::builder()
            .orientation(gtk::Orientation::Horizontal)
            .start_child(&stack)
            .end_child(&inspector.panel)
            .position(720)
            .resize_start_child(true)
            .resize_end_child(false)
            .build();
        let visible_settings = inspector.panel.clone();
        let compact_settings_button = settings_button.clone();
        let settings_window = window.downgrade();
        let header_run = run.clone();
        stack.connect_visible_child_name_notify(move |stack| {
            header_run.set_visible(stack.visible_child_name().as_deref() == Some("create"));
            let compact = settings_window
                .upgrade()
                .is_some_and(|w| w.has_css_class("pantheon-compact"));
            compact_settings_button
                .set_visible(compact && stack.visible_child_name().as_deref() == Some("create"));
            visible_settings.set_visible(stack.visible_child_name().as_deref() == Some("create"));
        });
        let sidebar = build_sidebar(&stack, &create, &inspector);
        let split = gtk::Paned::builder()
            .orientation(gtk::Orientation::Horizontal)
            .start_child(&sidebar)
            .end_child(&main_split)
            .position(200)
            .resize_start_child(false)
            .resize_end_child(true)
            .build();
        window.set_titlebar(Some(&header));
        window.set_child(Some(&split));
        mseries_pantheon_kit::watch_responsive_width(&window, 64.0, {
            let split = split.clone();
            let main_split = main_split.clone();
            let sidebar = sidebar.clone();
            let inspector = inspector.panel.clone();
            let settings_button = settings_button.clone();
            let settings_popover = settings_popover.clone();
            let stack = stack.clone();
            move |class| {
                let (sidebar_width, inspector_width) = match class {
                    mseries_pantheon_kit::LayoutClass::Compact => (216, 320),
                    mseries_pantheon_kit::LayoutClass::Regular => (216, 320),
                };
                let compact = matches!(class, mseries_pantheon_kit::LayoutClass::Compact);
                if compact && main_split.end_child().is_some() {
                    main_split.set_end_child(None::<&gtk::Widget>);
                    settings_popover.set_child(Some(&inspector));
                } else if !compact && main_split.end_child().is_none() {
                    settings_popover.popdown();
                    settings_popover.set_child(None::<&gtk::Widget>);
                    main_split.set_end_child(Some(&inspector));
                }
                settings_button.set_visible(
                    compact && stack.visible_child_name().as_deref() == Some("create"),
                );
                sidebar.set_width_request(sidebar_width);
                inspector.set_width_request(inspector_width);
                if split.width() > 0 {
                    split.set_position(sidebar_width);
                }
                if main_split.width() > 0 {
                    main_split.set_position((main_split.width() - inspector_width).max(420));
                }
            }
        });

        wire_actions(
            application,
            &window,
            &stack,
            &create,
            &library,
            &inspector,
            &recipe_store,
        );
        refresh_hardware(
            &inspector.hardware,
            &inspector.engine,
            &inspector.generate,
            &inspector.model,
        );
        let hardware = inspector.hardware.clone();
        let engine = inspector.engine.clone();
        let generate = inspector.generate.clone();
        let selected_model = inspector.model.clone();
        glib::timeout_add_seconds_local(5, move || {
            refresh_hardware(&hardware, &engine, &generate, &selected_model);
            glib::ControlFlow::Continue
        });
        load_recipes(&library.recipes, &create, &inspector, &stack, &recipe_store);
        load_generated_images(
            &library.outputs,
            &library.placeholder,
            &library.outputs_heading,
            &library.output_scroll,
            &create,
            &inspector,
            &stack,
        );
        let outputs = library.outputs.clone();
        let placeholder = library.placeholder.clone();
        let heading = library.outputs_heading.clone();
        let scroll = library.output_scroll.clone();
        let result_create = create.clone_refs();
        let result_inspector = inspector.clone_refs();
        let result_stack = stack.clone();
        let mut previous_job = String::new();
        glib::timeout_add_seconds_local(1, move || {
            if outputs.root().is_none() {
                return glib::ControlFlow::Break;
            }
            let path = glib::user_data_dir().join("mseries-image-studio/current-job.json");
            if let Ok(raw) = std::fs::read_to_string(path) {
                if raw != previous_job {
                    if let Ok(job) = serde_json::from_str::<serde_json::Value>(&raw) {
                        if job["running"].as_bool() == Some(false)
                            && job["status"]
                                .as_str()
                                .is_some_and(|s| s.starts_with("Complete"))
                        {
                            load_generated_images(
                                &outputs,
                                &placeholder,
                                &heading,
                                &scroll,
                                &result_create,
                                &result_inspector,
                                &result_stack,
                            );
                        }
                    }
                    previous_job = raw;
                }
            }
            glib::ControlFlow::Continue
        });
        if std::env::var_os("M_SERIES_IMAGE_STUDIO_TEST_WORKFLOW").is_none() {
            reload.emit_clicked();
        }
        test_hooks(
            application,
            &window,
            &stack,
            &create,
            &library,
            &inspector,
            &recipe_store,
        );

        Self { window }
    }

    pub fn window(&self) -> &gtk::ApplicationWindow {
        &self.window
    }
}

struct CreatePage {
    page: gtk::Widget,
    prompt: gtk::TextView,
    negative: gtk::TextView,
    intent: gtk::DropDown,
    assistant_status: gtk::Label,
    workflow_status: gtk::Label,
    queue_status: gtk::Label,
    workflow: Rc<RefCell<String>>,
}

struct LibraryPage {
    page: gtk::Widget,
    recipes: gtk::ListBox,
    outputs: gtk::ListBox,
    placeholder: granite::Placeholder,
    output_scroll: gtk::ScrolledWindow,
    outputs_heading: gtk::Label,
}

struct Inspector {
    panel: gtk::Widget,
    hardware: gtk::Label,
    engine: gtk::Label,
    model: gtk::Entry,
    model_picker: gtk::DropDown,
    lora: gtk::Entry,
    lora_weight: gtk::Scale,
    dimensions: gtk::DropDown,
    batch: gtk::SpinButton,
    seed: gtk::SpinButton,
    steps: gtk::SpinButton,
    cfg: gtk::SpinButton,
    sampler: gtk::DropDown,
    vae: gtk::Entry,
    vae_on_cpu: gtk::CheckButton,
    reference_image: gtk::Entry,
    reference_strength: gtk::SpinButton,
    vae_tile_size: gtk::SpinButton,
    cpu_threads: gtk::SpinButton,
    params_backend: gtk::DropDown,
    max_vram_gib: gtk::SpinButton,
    scheduler: gtk::DropDown,
    tags: gtk::Entry,
    generate: gtk::Button,
    save: gtk::Button,
    recipe_status: gtk::Label,
}

fn short_model_name(value: &str) -> String {
    if value.is_empty() {
        return "Checkpoint default".into();
    }
    let file = Path::new(value)
        .file_stem()
        .unwrap_or_default()
        .to_string_lossy();
    if file.contains("Realistic_Vision") {
        "Realistic Vision 6.0 · FP16".into()
    } else if file.contains("vae-ft-mse") {
        "MSE 840000".into()
    } else {
        file.replace('_', " ")
    }
}

fn install_css(window: &gtk::ApplicationWindow) {
    let css = gtk::CssProvider::new();
    css.load_from_string(
        ".mseries-image-studio { font-size: 1.15em; }
         .mseries-image-studio .preview-stage picture { min-height: 320px; }
         .mseries-image-studio.pantheon-compact .preview-stage picture { min-height: 220px; }
         .mseries-image-studio .studio-sidebar { border-right: 1px solid alpha(currentColor, 0.10); }
         .mseries-image-studio .preview-stage { background: @theme_base_color; border: 1px solid alpha(currentColor, 0.08); }
         .mseries-image-studio .status-card, .mseries-image-studio .queue-row { background: @theme_base_color; }",
    );
    let display = gtk::prelude::RootExt::display(window);
    gtk::style_context_add_provider_for_display(
        &display,
        &css,
        gtk::STYLE_PROVIDER_PRIORITY_APPLICATION,
    );
}

fn build_sidebar(stack: &gtk::Stack, create: &CreatePage, inspector: &Inspector) -> gtk::Widget {
    let sidebar = gtk::Box::new(gtk::Orientation::Vertical, 0);
    sidebar.set_width_request(200);
    sidebar.add_css_class("studio-sidebar");
    sidebar.add_css_class(granite::STYLE_CLASS_SIDEBAR);
    sidebar.add_css_class("pantheon-inset");
    mseries_pantheon_kit::set_box_spacing_text_units(&sidebar, 0.6);
    sidebar.append(&section_label("Workspace"));
    let navigation = gtk::ListBox::builder()
        .css_classes(["navigation-sidebar"])
        .selection_mode(gtk::SelectionMode::Single)
        .activate_on_single_click(true)
        .build();
    mseries_pantheon_kit::set_accessible_label(&navigation, "Image Studio pages");
    for (label, page) in [
        ("Create", "create"),
        ("Library", "library"),
        ("Models", "models"),
        ("Model guide", "guide"),
        ("Compare", "compare"),
        ("Review", "review"),
        ("Run logs", "logs"),
    ] {
        let row = gtk::ListBoxRow::new();
        let contents = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        contents.add_css_class("pantheon-row");
        contents.append(&gtk::Image::from_icon_name(match page {
            "create" => "document-edit-symbolic",
            "library" => "image-x-generic-symbolic",
            "models" => "drive-harddisk-symbolic",
            "compare" => "view-grid-symbolic",
            "review" => "emblem-ok-symbolic",
            "logs" => "utilities-terminal-symbolic",
            _ => "help-browser-symbolic",
        }));
        let row_label = gtk::Label::new(Some(label));
        row_label.set_xalign(0.0);
        row_label.set_hexpand(true);
        contents.append(&row_label);
        row.set_child(Some(&contents));
        navigation.append(&row);
        if page == "create" {
            navigation.select_row(Some(&row));
        }
    }
    let stack_for_navigation = stack.clone();
    navigation.connect_row_selected(move |_, row| {
        if let Some(row) = row {
            stack_for_navigation.set_visible_child_name(if row.index() == 0 {
                "create"
            } else if row.index() == 1 {
                "library"
            } else if row.index() == 2 {
                "models"
            } else if row.index() == 3 {
                "guide"
            } else if row.index() == 4 {
                "compare"
            } else if row.index() == 5 {
                "review"
            } else {
                "logs"
            });
        }
    });
    let navigation_weak = navigation.downgrade();
    stack.connect_visible_child_name_notify(move |stack| {
        if let Some(navigation) = navigation_weak.upgrade() {
            let index = match stack.visible_child_name().as_deref() {
                Some("library") => 1,
                Some("models") => 2,
                Some("guide") => 3,
                Some("compare") => 4,
                Some("review") => 5,
                Some("logs") => 6,
                _ => 0,
            };
            navigation.select_row(navigation.row_at_index(index).as_ref());
        }
    });
    sidebar.append(&navigation);
    sidebar.append(&crate::models::storage_label());
    let workflows = section_label("Guided workflows");
    sidebar.append(&workflows);
    for (title, subtitle, workflow) in [
        (
            "Model readiness",
            "Check one conservative render",
            "Model readiness",
        ),
        (
            "Prompt type study",
            "Compare prompt structures",
            "Prompt type study",
        ),
    ] {
        let button = gtk::Button::new();
        button.add_css_class("flat");
        let contents = gtk::Box::new(gtk::Orientation::Vertical, 2);
        for (text, class) in [(title, "heading"), (subtitle, "dim-label")] {
            let label = gtk::Label::new(Some(text));
            label.set_xalign(0.0);
            label.set_wrap(true);
            label.add_css_class(class);
            contents.append(&label);
        }
        button.set_child(Some(&contents));
        button.update_property(&[gtk::accessible::Property::Label(title)]);
        let page = create.clone_refs();
        let settings = inspector.clone_refs();
        let stack = stack.clone();
        button.connect_clicked(move |_| {
            stack.set_visible_child_name("create");
            apply_workflow(workflow, &page, &settings);
        });
        sidebar.append(&button);
    }
    let spacer = gtk::Box::new(gtk::Orientation::Vertical, 0);
    spacer.set_vexpand(true);
    sidebar.append(&spacer);
    let device_header = section_label("This device");
    sidebar.append(&device_header);
    let hardware = gtk::Label::new(None);
    hardware.set_xalign(0.0);
    hardware.set_wrap(true);
    hardware.set_margin_start(8);
    hardware.set_margin_end(8);
    hardware.add_css_class("pantheon-caption");
    let host = HostCapabilities::capture();
    hardware.set_text(&format!(
        "{}\n6 GiB desktop reserve: {}\n{}",
        host.memory_summary(),
        if host.reserve_met() { "met" } else { "not met" },
        if host.has_render_node {
            "Render node detected"
        } else {
            "No render node detected"
        }
    ));
    // Refresh the inspector and sidebar labels from the same current host sample.
    let panel_status = inspector.hardware.clone();
    let hardware_copy = hardware.clone();
    glib::timeout_add_seconds_local(5, move || {
        hardware_copy.set_text(panel_status.text().as_str());
        glib::ControlFlow::Continue
    });
    sidebar.append(&hardware);
    gtk::ScrolledWindow::builder()
        .child(&sidebar)
        .hscrollbar_policy(gtk::PolicyType::Never)
        .min_content_width(190)
        .build()
        .upcast()
}

fn build_create_page() -> CreatePage {
    let queue_status = gtk::Label::new(Some("No local image jobs queued"));
    let page = gtk::Box::new(gtk::Orientation::Vertical, 0);
    mseries_pantheon_kit::set_box_spacing_text_units(&page, 0.8);
    page.add_css_class("pantheon-inset");
    let title = gtk::Label::new(Some("Image workspace"));
    title.set_xalign(0.0);
    title.add_css_class("title-2");
    page.append(&title);

    let preview = gtk::Box::new(gtk::Orientation::Vertical, 10);
    preview.add_css_class("preview-stage");
    preview.add_css_class("pantheon-surface");
    preview.add_css_class("pantheon-inset");
    mseries_pantheon_kit::set_box_spacing_text_units(&preview, 0.5);
    preview.set_size_request(-1, 220);
    preview.set_hexpand(true);
    preview.set_vexpand(true);
    let preview_center = gtk::Box::new(gtk::Orientation::Vertical, 8);
    preview_center.set_halign(gtk::Align::Fill);
    preview_center.set_hexpand(true);
    preview_center.set_margin_start(16);
    preview_center.set_margin_end(16);
    preview_center.set_margin_top(16);
    preview_center.set_margin_bottom(16);
    preview_center.set_valign(gtk::Align::Center);
    preview_center.set_vexpand(true);
    let icon = gtk::Image::from_icon_name("image-x-generic-symbolic");
    icon.set_pixel_size(42);
    icon.add_css_class("dim-label");
    let preview_title = gtk::Label::new(Some("Your image preview will appear here"));
    preview_title.add_css_class("title-3");
    let preview_detail = gtk::Label::new(Some(
        "Choose an installed model, describe your image, and press Run. Live denoising previews appear here.",
    ));
    preview_detail.set_wrap(true);
    preview_detail.set_justify(gtk::Justification::Center);
    preview_detail.set_max_width_chars(64);
    preview_detail.set_lines(3);
    preview_detail.set_ellipsize(gtk::pango::EllipsizeMode::End);
    preview_detail.add_css_class("dim-label");
    preview_center.append(&icon);
    preview_center.append(&preview_title);
    preview_center.append(&preview_detail);
    let live_image = gtk::Picture::new();
    live_image.set_content_fit(gtk::ContentFit::Contain);
    live_image.set_can_shrink(true);
    live_image.set_size_request(-1, 0);
    live_image.set_hexpand(true);
    live_image.set_vexpand(true);
    live_image.set_visible(false);
    preview_center.append(&live_image);
    let spinner = gtk::Spinner::new();
    preview_center.append(&spinner);
    let progress = gtk::ProgressBar::new();
    progress.set_show_text(true);
    progress.set_text(Some("Ready to generate"));
    preview_center.append(&progress);
    let run_details = gtk::Label::new(None);
    run_details.set_xalign(0.0);
    run_details.set_wrap(true);
    run_details.set_selectable(true);
    run_details.add_css_class("caption");
    preview_center.append(&run_details);
    let job_path = gtk::glib::user_data_dir().join("mseries-image-studio/current-job.json");
    let mut last_job = String::new();
    let active_queue = queue_status.clone();
    gtk::glib::timeout_add_seconds_local(1, move || {
        if preview_title.root().is_none() {
            return gtk::glib::ControlFlow::Break;
        }
        if let Ok(raw) = std::fs::read_to_string(&job_path) {
            if raw != last_job {
                if let Ok(job) = serde_json::from_str::<serde_json::Value>(&raw) {
                    preview_title.set_text(
                        job["status"]
                            .as_str()
                            .unwrap_or("Generation status unavailable"),
                    );
                    active_queue.set_text(job["status"].as_str().unwrap_or("Status unavailable"));
                    preview_detail.set_text(&format!(
                        "{}\n{}",
                        job["engine"].as_str().unwrap_or("Engine unavailable"),
                        job["prompt"].as_str().unwrap_or("")
                    ));
                    let path = job["image_path"].as_str().unwrap_or("");
                    if !path.is_empty() {
                        live_image.set_filename(Some(path));
                        live_image.set_visible(true);
                    } else {
                        live_image.set_visible(false);
                    }
                    let running = job["running"].as_bool().unwrap_or(false);
                    spinner.set_spinning(running);
                    let step = job["step"].as_f64().unwrap_or(0.0);
                    let steps = job["steps"].as_f64().unwrap_or(0.0);
                    if steps > 0.0 {
                        progress.set_fraction((step / steps).clamp(0.0, 1.0));
                    } else if running {
                        progress.pulse();
                    } else {
                        progress.set_fraction(if path.is_empty() { 0.0 } else { 1.0 });
                    }
                    progress.set_text(Some(job["status"].as_str().unwrap_or("Ready")));
                    let detail = [
                        "model",
                        "sampler",
                        "scheduler",
                        "elapsed_seconds",
                        "preview_count",
                    ]
                    .iter()
                    .filter_map(|key| {
                        job.get(*key).map(|value| {
                            let display = if *key == "model" {
                                short_model_name(value.as_str().unwrap_or(""))
                            } else {
                                value.to_string()
                            };
                            format!("{}: {}", key.replace('_', " "), display)
                        })
                    })
                    .collect::<Vec<_>>()
                    .join(" · ");
                    run_details.set_text(&format!("Active / last image · {detail}"));
                    icon.set_visible(false);
                }
                last_job = raw;
            }
        }
        gtk::glib::ControlFlow::Continue
    });
    preview.append(&preview_center);
    page.append(&preview);

    let header = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    let prompt_title = gtk::Label::new(Some("Prompt"));
    prompt_title.set_xalign(0.0);
    prompt_title.set_hexpand(true);
    prompt_title.add_css_class("title-4");
    let intent = gtk::DropDown::from_strings(INTENTS);
    intent.set_selected(1);
    intent.update_property(&[gtk::accessible::Property::Label("Prompt type")]);
    header.append(&prompt_title);
    header.append(&intent);
    page.append(&header);

    let actions = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    let suggest_type = gtk::Button::with_label("Suggest type");
    suggest_type.set_tooltip_text(Some(
        "Ask the already-running M-Series local assistant to recommend a prompt type",
    ));
    let help_prompt = gtk::Button::with_label("Help shape this prompt");
    help_prompt.set_tooltip_text(Some(
        "Ask the already-running local assistant for an editable prompt suggestion",
    ));
    actions.append(&suggest_type);
    actions.append(&help_prompt);
    page.append(&actions);

    let prompt = gtk::TextView::new();
    prompt.set_wrap_mode(gtk::WrapMode::WordChar);
    prompt.set_size_request(-1, 110);
    prompt.set_left_margin(8);
    prompt.set_right_margin(8);
    prompt.set_top_margin(8);
    prompt.set_bottom_margin(8);
    prompt.buffer().set_text(SAMPLE_SERIES);
    prompt.update_property(&[gtk::accessible::Property::Label("Image prompt")]);
    let prompt_scroll = gtk::ScrolledWindow::builder()
        .child(&prompt)
        .min_content_height(110)
        .max_content_height(180)
        .hscrollbar_policy(gtk::PolicyType::Never)
        .build();
    prompt_scroll.add_css_class("card");
    prompt_scroll.add_css_class("pantheon-surface");
    page.append(&prompt_scroll);

    let negative_title = gtk::Label::new(Some("Negative prompt (optional)"));
    negative_title.set_xalign(0.0);
    negative_title.add_css_class("dim-label");
    page.append(&negative_title);
    let negative = gtk::TextView::new();
    negative.set_wrap_mode(gtk::WrapMode::WordChar);
    negative.set_size_request(-1, 52);
    negative.set_left_margin(8);
    negative.set_right_margin(8);
    negative.set_top_margin(6);
    negative.set_bottom_margin(6);
    negative
        .buffer()
        .set_text("text, watermark, logo, extra fingers, inconsistent person, sexualized styling");
    negative.update_property(&[gtk::accessible::Property::Label("Negative prompt")]);
    page.append(
        &gtk::ScrolledWindow::builder()
            .child(&negative)
            .min_content_height(52)
            .max_content_height(76)
            .hscrollbar_policy(gtk::PolicyType::Never)
            .build(),
    );

    let assistant_status = gtk::Label::new(Some(
        "Prompt help uses the already-running local assistant at 127.0.0.1:8766; the app will not start or replace a worker.",
    ));
    assistant_status.set_xalign(0.0);
    assistant_status.set_wrap(true);
    assistant_status.add_css_class("dim-label");
    page.append(&assistant_status);
    let workflow_status = gtk::Label::new(Some(
        "Prompt type study · compare prompt structures while holding the subject and seed steady.",
    ));
    workflow_status.set_xalign(0.0);
    workflow_status.set_wrap(true);
    workflow_status.add_css_class("pantheon-caption");
    page.append(&workflow_status);

    let queue_heading = gtk::Label::new(Some("Queue"));
    queue_heading.set_xalign(0.0);
    queue_heading.add_css_class("title-4");
    page.append(&queue_heading);
    let queue_row = gtk::Box::new(gtk::Orientation::Horizontal, 10);
    queue_row.add_css_class("queue-row");
    queue_row.add_css_class("pantheon-surface");
    queue_row.add_css_class("pantheon-row");
    queue_row.append(&gtk::Image::from_icon_name("content-loading-symbolic"));

    queue_status.set_xalign(0.0);
    queue_status.set_hexpand(true);
    queue_row.append(&queue_status);
    page.append(&queue_row);

    CreatePage {
        page: gtk::ScrolledWindow::builder()
            .child(&page)
            .hscrollbar_policy(gtk::PolicyType::Never)
            .build()
            .upcast(),
        prompt,
        negative,
        intent,
        assistant_status,
        workflow_status,
        queue_status,
        workflow: Rc::new(RefCell::new("Prompt type study".into())),
    }
}

fn build_library_page(store: &RecipeStore) -> LibraryPage {
    let page = gtk::Box::new(gtk::Orientation::Vertical, 0);
    mseries_pantheon_kit::set_box_spacing_text_units(&page, 0.75);
    page.add_css_class("pantheon-inset");
    let title = gtk::Label::new(Some("Library"));
    title.set_xalign(0.0);
    title.add_css_class("title-2");
    page.append(&title);
    let explainer = gtk::Label::new(Some(
        "Generated images keep their prompt, model, LoRAs and tags beside the image. Saved recipes can be loaded into Create.",
    ));
    explainer.set_xalign(0.0);
    explainer.set_wrap(true);
    explainer.add_css_class("dim-label");
    page.append(&explainer);
    let placeholder = granite::Placeholder::new("No generated images yet");
    placeholder.set_description("Save a recipe now; generated outputs will join it after a local image engine is qualified.");
    placeholder.set_hexpand(true);
    placeholder.set_vexpand(true);
    placeholder.set_size_request(-1, 220);
    page.append(&placeholder);
    let outputs_heading = gtk::Label::new(Some("Generated images"));
    outputs_heading.set_xalign(0.0);
    outputs_heading.add_css_class("title-4");
    outputs_heading.set_visible(false);
    page.append(&outputs_heading);
    let outputs = gtk::ListBox::new();
    outputs.set_selection_mode(gtk::SelectionMode::None);
    outputs.add_css_class("boxed-list");
    let output_scroll = gtk::ScrolledWindow::builder()
        .child(&outputs)
        .min_content_height(220)
        .max_content_height(380)
        .vexpand(true)
        .build();
    output_scroll.set_visible(false);
    page.append(&output_scroll);
    let recipe_heading = gtk::Label::new(Some("Saved recipes"));
    recipe_heading.set_xalign(0.0);
    recipe_heading.add_css_class("title-4");
    page.append(&recipe_heading);
    let recipes = gtk::ListBox::new();
    recipes.set_selection_mode(gtk::SelectionMode::None);
    recipes.add_css_class("boxed-list");
    recipes.set_placeholder(Some(&gtk::Label::new(Some("No saved recipes yet."))));
    let recipe_scroll = gtk::ScrolledWindow::builder()
        .child(&recipes)
        .min_content_height(120)
        .max_content_height(220)
        .vexpand(true)
        .build();
    page.append(&recipe_scroll);
    let _ = store; // Store is passed in so page construction stays close to its library widgets.
    LibraryPage {
        page: page.upcast(),
        recipes,
        outputs,
        placeholder,
        output_scroll,
        outputs_heading,
    }
}

fn build_inspector() -> Inspector {
    let panel = gtk::Box::new(gtk::Orientation::Vertical, 0);
    panel.set_width_request(300);
    mseries_pantheon_kit::set_box_spacing_text_units(&panel, 0.65);
    panel.add_css_class("pantheon-inset");
    let title = gtk::Label::new(Some("Generation settings"));
    title.set_xalign(0.0);
    title.add_css_class("title-3");
    panel.append(&title);
    let device_card = gtk::Box::new(gtk::Orientation::Vertical, 0);
    mseries_pantheon_kit::set_box_spacing_text_units(&device_card, 0.35);
    device_card.add_css_class("status-card");
    device_card.add_css_class("pantheon-surface");
    device_card.add_css_class("pantheon-inset");
    let device_title = gtk::Label::new(Some("M-Series device check"));
    device_title.set_xalign(0.0);
    device_title.add_css_class("heading");
    let device_detail = gtk::Label::new(Some(
        "Hardware is observed, not guessed. Model and image-size recommendations appear after successful calibration.",
    ));
    device_detail.set_xalign(0.0);
    device_detail.set_wrap(true);
    device_detail.add_css_class("pantheon-caption");
    device_card.append(&device_title);
    device_card.append(&device_detail);
    panel.append(&device_card);
    let hardware = gtk::Label::new(None);
    hardware.set_xalign(0.0);
    hardware.set_wrap(true);
    hardware.add_css_class("pantheon-caption");
    panel.append(&hardware);
    let engine = gtk::Label::new(Some(
        "Image engine: not connected\nCompatibility: unverified",
    ));
    engine.set_xalign(0.0);
    engine.set_wrap(true);
    engine.add_css_class("status-card");
    engine.add_css_class("pantheon-surface");
    engine.add_css_class("pantheon-inset");
    panel.append(&engine);

    panel.append(&section_label("Model"));
    let model = gtk::Entry::new();
    model.set_placeholder_text(Some("Model name or checkpoint"));
    model.update_property(&[gtk::accessible::Property::Label(
        "Model name or checkpoint for recipe",
    )]);
    let installed = gtk::glib::user_data_dir()
        .join("mseries-image-studio/models/stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf");
    if installed.is_file() {
        model.set_text(&installed.to_string_lossy());
    }
    let installed_models = gtk::DropDown::from_strings(&[]);
    installed_models.set_hexpand(true);
    installed_models.set_tooltip_text(Some(
        "Installed image checkpoints. Full paths are available under Model file.",
    ));
    installed_models.update_property(&[gtk::accessible::Property::Label("Installed image model")]);
    let directory = gtk::glib::user_data_dir().join("mseries-image-studio/models");
    let mut files: Vec<_> = std::fs::read_dir(directory)
        .into_iter()
        .flatten()
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| {
            let name = path
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .to_lowercase();
            path.is_file()
                && (name.ends_with(".gguf") || name.ends_with(".safetensors"))
                && !name.contains("qwen")
                && !name.contains("mmproj")
                && !name.starts_with("vae")
        })
        .collect();
    files.sort_by_key(|path| (!path.to_string_lossy().contains("Realistic"), path.clone()));
    let names: Vec<String> = files
        .iter()
        .map(|path| short_model_name(&path.to_string_lossy()))
        .collect();
    let labels: Vec<&str> = names.iter().map(String::as_str).collect();
    installed_models.set_model(Some(&gtk::StringList::new(&labels)));
    let files = Rc::new(files);
    let paths = files.clone();
    let current_model = model.clone();
    installed_models.connect_selected_notify(move |choice| {
        if let Some(path) = paths.get(choice.selected() as usize) {
            if current_model.text().as_str() != path.to_string_lossy() {
                current_model.set_text(&path.to_string_lossy());
            }
        }
    });
    let choices = installed_models.downgrade();
    let paths = files.clone();
    model.connect_changed(move |entry| {
        if let Some(choices) = choices.upgrade() {
            let index = paths
                .iter()
                .position(|path| path.to_string_lossy() == entry.text().as_str())
                .map(|index| index as u32)
                .unwrap_or(gtk::INVALID_LIST_POSITION);
            if choices.selected() != index {
                choices.set_selected(index);
            }
        }
    });
    if let Some(path) = files.first() {
        model.set_text(&path.to_string_lossy());
    }

    let model_file = gtk::Expander::new(Some("Model file"));
    model_file.set_child(Some(&model));
    panel.append(&model_file);
    panel.append(&section_label("VAE decoder"));
    let vae = gtk::Entry::new();
    vae.set_placeholder_text(Some("Built into checkpoint, or VAE file path"));
    vae.update_property(&[gtk::accessible::Property::Label("VAE decoder file")]);
    let installed_vae = gtk::glib::user_data_dir()
        .join("mseries-image-studio/models/vae-ft-mse-840000-ema-pruned.safetensors");
    if installed_vae.is_file() {
        vae.set_text(&installed_vae.to_string_lossy());
    }
    let vae_file = gtk::Expander::new(Some("VAE file · advanced"));
    let vae_settings = gtk::Box::new(gtk::Orientation::Vertical, 6);
    vae_settings.append(&vae);
    let vae_on_cpu = gtk::CheckButton::with_label("Decode VAE on CPU (lower GPU use)");
    vae_on_cpu.set_active(true);
    vae_on_cpu.set_tooltip_text(Some("CPU decoding uses less GPU memory. Disable to try faster GPU decoding when memory allows. Saved with each recipe."));
    vae_settings.append(&vae_on_cpu);
    let vae_tile_size = gtk::SpinButton::with_range(64.0, 512.0, 64.0);
    vae_tile_size.set_value(256.0);
    let cpu_threads = gtk::SpinButton::with_range(1.0, 16.0, 1.0);
    cpu_threads.set_value(4.0);
    for (title, control) in [
        ("Decoder tile size", &vae_tile_size),
        ("CPU threads", &cpu_threads),
    ] {
        control.update_property(&[gtk::accessible::Property::Label(title)]);
        let row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        let label = gtk::Label::new(Some(title));
        label.set_xalign(0.0);
        label.set_hexpand(true);
        row.append(&label);
        row.append(control);
        vae_settings.append(&row);
    }
    let params_backend =
        gtk::DropDown::from_strings(&["Disk · lower memory", "CPU memory", "Automatic"]);
    params_backend.update_property(&[gtk::accessible::Property::Label(
        "Model weights storage backend",
    )]);
    vae_settings.append(&gtk::Label::new(Some("Model weights storage")));
    vae_settings.append(&params_backend);
    let max_vram_gib = gtk::SpinButton::with_range(2.0, 8.0, 0.5);
    max_vram_gib.set_value(3.0);
    max_vram_gib.update_property(&[gtk::accessible::Property::Label("GPU memory budget in GiB")]);
    vae_settings.append(&gtk::Label::new(Some("GPU memory budget · GiB")));
    vae_settings.append(&max_vram_gib);
    vae_file.set_child(Some(&vae_settings));
    panel.append(&vae_file);
    panel.append(&section_label("Reference image"));
    let reference_image = gtk::Entry::new();
    reference_image.set_placeholder_text(Some("No reference · prompt only"));
    reference_image.update_property(&[gtk::accessible::Property::Label("Reference image path")]);
    let reference_row = gtk::Box::new(gtk::Orientation::Horizontal, 6);
    let choose_reference = gtk::Button::with_label("Choose image…");
    let clear_reference = gtk::Button::with_label("Clear");
    reference_row.append(&choose_reference);
    reference_row.append(&clear_reference);
    let reference = reference_image.clone();
    choose_reference.connect_clicked(move |button| {
        let parent = button.root().and_downcast::<gtk::Window>();
        let chooser = gtk::FileDialog::builder()
            .title("Choose reference image")
            .accept_label("Use reference")
            .build();
        let filter = gtk::FileFilter::new();
        filter.set_name(Some("PNG and JPEG images"));
        filter.add_mime_type("image/png");
        filter.add_mime_type("image/jpeg");
        let filters = gio::ListStore::new::<gtk::FileFilter>();
        filters.append(&filter);
        chooser.set_filters(Some(&filters));
        let reference = reference.clone();
        chooser.open(parent.as_ref(), None::<&gio::Cancellable>, move |result| {
            if let Ok(file) = result {
                if let Some(path) = file.path() {
                    reference.set_text(&path.to_string_lossy());
                }
            }
        });
    });
    let reference = reference_image.clone();
    clear_reference.connect_clicked(move |_| reference.set_text(""));
    panel.append(&reference_row);
    let reference_path = gtk::Expander::new(Some("Reference file"));
    reference_path.set_child(Some(&reference_image));
    panel.append(&reference_path);
    let reference_strength = gtk::SpinButton::with_range(0.0, 2.0, 0.05);
    reference_strength.set_digits(2);
    reference_strength.set_value(0.8);
    reference_strength
        .update_property(&[gtk::accessible::Property::Label("Reference image strength")]);
    panel.append(&gtk::Label::new(Some("Reference strength")));
    panel.append(&reference_strength);
    panel.append(&section_label("LoRA"));
    let lora = gtk::Entry::new();
    lora.set_placeholder_text(Some("LoRA name (optional)"));
    lora.update_property(&[gtk::accessible::Property::Label("LoRA name for recipe")]);
    panel.append(&lora);
    let weight_row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    let weight_title = gtk::Label::new(Some("LoRA strength"));
    weight_title.set_xalign(0.0);
    weight_title.set_hexpand(true);
    let lora_weight = gtk::Scale::with_range(gtk::Orientation::Horizontal, 0.0, 1.5, 0.05);
    lora_weight.set_width_request(100);
    lora_weight.set_draw_value(true);
    lora_weight.set_digits(2);
    lora_weight.set_value(1.0);
    lora_weight.update_property(&[gtk::accessible::Property::Label("LoRA strength")]);
    weight_row.append(&weight_title);
    weight_row.append(&lora_weight);
    panel.append(&weight_row);

    panel.append(&section_label("Output"));
    let dimensions = gtk::DropDown::from_strings(&[
        "512 × 512 · square",
        "768 × 768 · square",
        "1024 × 1024 · square",
        "512 × 768 · portrait",
        "768 × 512 · landscape",
        "768 × 1024 · portrait",
        "1024 × 768 · landscape",
    ]);
    dimensions.update_property(&[gtk::accessible::Property::Label(
        "Image dimensions for recipe",
    )]);
    panel.append(&dimensions);
    let batch_row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    let batch_title = gtk::Label::new(Some("Images in this run"));
    batch_title.set_xalign(0.0);
    batch_title.set_hexpand(true);
    let batch = gtk::SpinButton::with_range(1.0, 8.0, 1.0);
    batch.set_numeric(true);
    batch.update_property(&[gtk::accessible::Property::Label(
        "Number of images in recipe",
    )]);
    batch_row.append(&batch_title);
    batch_row.append(&batch);
    panel.append(&batch_row);
    panel.append(&section_label("Seed"));
    let seed = gtk::SpinButton::with_range(-1.0, 2_147_483_647.0, 1.0);
    seed.set_numeric(true);
    seed.set_value(-1.0);
    seed.update_property(&[gtk::accessible::Property::Label(
        "Seed, minus one means random",
    )]);
    panel.append(&seed);
    panel.append(&section_label("Sampling"));
    let sampler =
        gtk::DropDown::from_strings(&["Euler", "Euler ancestral", "DPM++ 2M", "DPM++ 2M SDE"]);
    sampler.update_property(&[gtk::accessible::Property::Label("Sampler")]);
    panel.append(&sampler);
    let scheduler = gtk::DropDown::from_strings(&["Discrete", "Karras"]);
    scheduler.update_property(&[gtk::accessible::Property::Label("Noise scheduler")]);
    panel.append(&scheduler);
    let steps = gtk::SpinButton::with_range(1.0, 50.0, 1.0);
    steps.set_value(20.0);
    steps.set_tooltip_text(Some("Denoising steps"));
    steps.update_property(&[gtk::accessible::Property::Label("Denoising steps")]);
    let steps_row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    let steps_label = gtk::Label::new(Some("Steps"));
    steps_label.set_hexpand(true);
    steps_label.set_xalign(0.0);
    steps_row.append(&steps_label);
    steps_row.append(&steps);
    panel.append(&steps_row);
    let cfg = gtk::SpinButton::with_range(0.0, 15.0, 0.5);
    cfg.set_value(7.0);
    cfg.set_tooltip_text(Some("Prompt guidance strength (CFG)"));
    cfg.update_property(&[gtk::accessible::Property::Label("Prompt guidance CFG")]);
    let cfg_row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    let cfg_label = gtk::Label::new(Some("Prompt guidance"));
    cfg_label.set_hexpand(true);
    cfg_label.set_xalign(0.0);
    cfg_row.append(&cfg_label);
    cfg_row.append(&cfg);
    panel.append(&cfg_row);
    panel.append(&section_label("Tags"));
    let tags = gtk::Entry::new();
    tags.set_placeholder_text(Some("portrait, streamer, study"));
    tags.update_property(&[gtk::accessible::Property::Label(
        "Comma-separated image tags",
    )]);
    panel.append(&tags);
    if model.text().contains("Realistic") {
        dimensions.set_selected(3);
        steps.set_value(30.0);
        cfg.set_value(5.0);
        sampler.set_selected(2);
        scheduler.set_selected(1);
    }
    let note = gtk::Label::new(Some(
        "Every run saves the prompt, model, seed and settings beside its image. Reload recipe restores an editable copy.",
    ));
    note.set_xalign(0.0);
    note.set_wrap(true);
    note.add_css_class("dim-label");
    panel.append(&note);
    let spacer = gtk::Box::new(gtk::Orientation::Vertical, 0);
    spacer.set_vexpand(true);
    panel.append(&spacer);
    let generate = gtk::Button::with_label("Run image generation");
    generate.set_sensitive(false);
    generate.add_css_class("suggested-action");
    generate.set_tooltip_text(Some(
        "Generation is disabled until an image engine/model pair is calibrated on this device.",
    ));
    generate.update_property(&[gtk::accessible::Property::Label("Run image generation")]);
    panel.append(&generate);
    let save = gtk::Button::with_label("Save prompt recipe");
    panel.append(&save);
    let recipe_status = gtk::Label::new(Some("Save a prompt recipe to reopen its settings later."));
    recipe_status.set_xalign(0.0);
    recipe_status.set_wrap(true);
    recipe_status.add_css_class("dim-label");
    panel.append(&recipe_status);
    Inspector {
        panel: gtk::ScrolledWindow::builder()
            .child(&panel)
            .hscrollbar_policy(gtk::PolicyType::Never)
            .min_content_width(315)
            .build()
            .upcast(),
        hardware,
        engine,
        model,
        model_picker: installed_models,
        lora,
        lora_weight,
        dimensions,
        batch,
        seed,
        steps,
        cfg,
        sampler,
        vae,
        vae_on_cpu,
        reference_image,
        reference_strength,
        vae_tile_size,
        cpu_threads,
        params_backend,
        max_vram_gib,
        scheduler,
        tags,
        generate,
        save,
        recipe_status,
    }
}

fn section_label(text: &str) -> granite::HeaderLabel {
    granite::HeaderLabel::new(text)
}

fn apply_workflow(workflow: &str, page: &CreatePage, settings: &Inspector) {
    *page.workflow.borrow_mut() = workflow.into();
    settings.steps.set_value(if workflow == "Model readiness" {
        8.0
    } else {
        20.0
    });
    settings.cfg.set_value(7.0);
    settings.sampler.set_selected(0);
    match workflow {
        "Model readiness" => {
            set_text(
                &page.prompt,
                "Editorial portrait of Alexandra Daddario portrayed as a 22-year-old adult college student and modern livestream creator, relaxed at a tidy desk with a webcam and headphones, friendly confident expression, soft daylight, natural color, realistic photography, shoulders-up composition.",
            );
            set_text(
                &page.negative,
                "text, watermark, logo, extra fingers, distorted hands, blurry face",
            );
            settings.dimensions.set_selected(0);
            settings.batch.set_value(1.0);
            settings.seed.set_value(424242.0);
            page.workflow_status.set_text("Model readiness · one conservative 512 × 512 image, batch 1, fixed seed. Save the recipe while the image runtime is being qualified.");
            page.assistant_status.set_text("Start with one model and one image. The app will not send a job until the runtime is connected and this size has a measured memory budget.");
        }
        "LoRA comparison" => {
            set_text(
                &page.prompt,
                "Editorial scene of Alexandra Daddario portrayed as a 22-year-old adult college student hosting a relaxed gaming livestream from a small modern dorm study nook, headphones, webcam, natural window light, candid documentary photography, consistent adult identity.",
            );
            set_text(
                &page.negative,
                "text, watermark, logo, extra fingers, distorted hands, sexualized styling",
            );
            settings.dimensions.set_selected(0);
            settings.batch.set_value(1.0);
            settings.seed.set_value(424242.0);
            page.workflow_status.set_text("LoRA comparison · save the same prompt and seed with LoRA strength 0, then save again with the chosen weight after a compatible LoRA is available.");
            page.assistant_status.set_text("Keep the base model, prompt, dimensions and seed fixed; change only LoRA strength between recipe copies. The LoRA name and weight are saved as notes.");
        }
        _ => {
            set_text(&page.prompt, SAMPLE_SERIES);
            set_text(
                &page.negative,
                "text, watermark, logo, extra fingers, inconsistent person, sexualized styling",
            );
            settings.dimensions.set_selected(0);
            settings.batch.set_value(1.0);
            settings.seed.set_value(424242.0);
            page.intent.set_selected(1);
            page.workflow_status.set_text("Prompt type study · ask the local assistant to recommend a type, review prompt wording, and save variants with the same subject and seed.");
            page.assistant_status.set_text("This recipe describes a three-scene series. A connected image engine will need a qualified multi-image workflow before it can render the set.");
        }
    }
}

fn wire_actions(
    application: &gtk::Application,
    window: &gtk::ApplicationWindow,
    stack: &gtk::Stack,
    create: &CreatePage,
    library: &LibraryPage,
    inspector: &Inspector,
    store: &RecipeStore,
) {
    let generation_page = create.clone_refs();
    let generation_settings = inspector.clone_refs();
    inspector.generate.connect_clicked(move |_| {
        let base = gtk::glib::user_data_dir().join("mseries-image-studio");
        if base.join("batch.lock").exists() || base.join("generation.lock").exists() {
            generation_settings.recipe_status.set_text(
                "A local workflow is active. Stop it or wait before starting another run.",
            );
            return;
        }
        let recipe = current_recipe(&generation_page, &generation_settings);
        let base = gtk::glib::user_data_dir().join("mseries-image-studio");
        let _ = std::fs::remove_file(base.join("cancel.request"));
        generation_settings
            .recipe_status
            .set_text("Submitting supervised local calibration…");
        std::thread::spawn(move || {
            let result = std::process::Command::new("python3")
                .arg("-c")
                .arg(include_str!("local_generation.py"))
                .arg(base)
                .arg(serde_json::to_string(&recipe).unwrap())
                .output();
            if let Err(error) = result {
                eprintln!("Generation worker could not start: {error}");
            }
        });
    });
    let page = create.clone_refs();
    let settings = inspector.clone_refs();
    let library_list = library.recipes.clone();
    let store = store.clone();
    let stack_for_save = stack.clone();
    inspector.save.connect_clicked(move |_| {
        let recipe = current_recipe(&page, &settings);
        match store.save(&recipe) {
            Ok(_) => {
                settings.recipe_status.set_text("Recipe saved to Library.");
                add_recipe_row(
                    &library_list,
                    recipe,
                    &page,
                    &settings,
                    &stack_for_save,
                    true,
                );
            }
            Err(error) => settings
                .recipe_status
                .set_text(&format!("Recipe could not be saved: {error}")),
        }
    });

    // Prompt help buttons are direct children of the create page action row. Find them once by label.
    let (suggest_type, help_prompt) = find_prompt_buttons(&create.page);
    let page = create.clone_refs();
    let status = create.assistant_status.clone();
    let intent = create.intent.clone();
    let type_dialog_parent = window.clone();
    suggest_type.connect_clicked(move |_| {
        let prompt = text_of(&page.prompt).trim().to_string();
        if prompt.is_empty() {
            status.set_text("Add a subject or idea first, then ask for a prompt-type suggestion.");
            return;
        }
        status.set_text(
            "Asking the already-running M-Series local assistant to recommend a prompt type…",
        );
        let status_done = status.clone();
        let intent = intent.clone();
        let window = type_dialog_parent.clone();
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = tx.send(assistant::suggest_intent(&prompt));
        });
        glib::timeout_add_local(Duration::from_millis(80), move || match rx.try_recv() {
            Ok(Ok(suggestion)) => {
                status_done.set_text(
                    "Prompt type suggestion ready. Review it before changing the selection.",
                );
                show_intent_dialog(&window, &intent, &suggestion);
                glib::ControlFlow::Break
            }
            Ok(Err(error)) => {
                status_done.set_text(&format!("Prompt-type help unavailable: {error}"));
                glib::ControlFlow::Break
            }
            Err(TryRecvError::Empty) => glib::ControlFlow::Continue,
            Err(TryRecvError::Disconnected) => {
                status_done.set_text("Prompt-type helper stopped unexpectedly.");
                glib::ControlFlow::Break
            }
        });
    });

    let page = create.clone_refs();
    let status = create.assistant_status.clone();
    let intent = create.intent.clone();
    let prompt_dialog_parent = window.clone();
    help_prompt.connect_clicked(move |_| {
        let prompt = text_of(&page.prompt).trim().to_string();
        if prompt.is_empty() {
            status.set_text("Add a subject or idea first, then ask for prompt help.");
            return;
        }
        let index = intent.selected() as usize;
        let intent_name = INTENTS
            .get(index)
            .copied()
            .unwrap_or("Portrait")
            .to_string();
        status.set_text("Asking the already-running M-Series local assistant…");
        let status_done = status.clone();
        let prompt_view = page.prompt.clone();
        let window = prompt_dialog_parent.clone();
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = tx.send(assistant::suggest_prompt(&intent_name, &prompt));
        });
        glib::timeout_add_local(Duration::from_millis(80), move || match rx.try_recv() {
            Ok(Ok(suggestion)) => {
                status_done.set_text("Suggestion ready. Review it before replacing your prompt.");
                show_prompt_dialog(&window, &prompt_view, &suggestion);
                glib::ControlFlow::Break
            }
            Ok(Err(error)) => {
                status_done.set_text(&format!("Prompt help unavailable: {error}"));
                glib::ControlFlow::Break
            }
            Err(TryRecvError::Empty) => glib::ControlFlow::Continue,
            Err(TryRecvError::Disconnected) => {
                status_done.set_text("Prompt helper stopped unexpectedly.");
                glib::ControlFlow::Break
            }
        });
    });
    let _ = stack;
    let _ = application;
}

fn find_prompt_buttons(page: &gtk::Widget) -> (gtk::Button, gtk::Button) {
    let mut buttons = Vec::new();
    walk(page, &mut |widget| {
        if let Some(button) = widget.downcast_ref::<gtk::Button>() {
            if let Some(label) = button.label() {
                buttons.push((label.to_string(), button.clone()));
            }
        }
    });
    let find = |name: &str| {
        buttons
            .iter()
            .find(|(label, _)| label == name)
            .map(|(_, button)| button.clone())
            .expect("prompt action button")
    };
    (find("Suggest type"), find("Help shape this prompt"))
}

fn current_recipe(page: &CreatePage, settings: &Inspector) -> Recipe {
    let mut recipe = Recipe::default();
    recipe.prompt = text_of(&page.prompt);
    recipe.negative_prompt = text_of(&page.negative);
    recipe.intent = INTENTS
        .get(page.intent.selected() as usize)
        .copied()
        .unwrap_or("Portrait")
        .into();
    recipe.workflow = page.workflow.borrow().clone();
    recipe.model_id = settings.model.text().to_string();
    recipe.steps = settings.steps.value_as_int() as u32;
    recipe.cfg_scale = settings.cfg.value();
    recipe.sampler = ["euler", "euler_a", "dpm++2m", "dpm++2m_sde"]
        .get(settings.sampler.selected() as usize)
        .unwrap_or(&"euler")
        .to_string();
    recipe.vae_path = settings.vae.text().to_string();
    recipe.vae_on_cpu = settings.vae_on_cpu.is_active();
    recipe.reference_image = settings.reference_image.text().to_string();
    recipe.reference_strength = settings.reference_strength.value();
    recipe.vae_tile_size = settings.vae_tile_size.value_as_int() as u32;
    recipe.cpu_threads = settings.cpu_threads.value_as_int() as u32;
    recipe.params_backend = ["disk", "cpu", "auto"]
        .get(settings.params_backend.selected() as usize)
        .unwrap_or(&"disk")
        .to_string();
    recipe.max_vram_gib = settings.max_vram_gib.value();
    recipe.scheduler = if settings.scheduler.selected() == 1 {
        "karras"
    } else {
        "discrete"
    }
    .into();
    recipe.lora_id = settings.lora.text().to_string();
    recipe.lora_weight = settings.lora_weight.value();
    (recipe.width, recipe.height) = match settings.dimensions.selected() {
        1 => (768, 768),
        2 => (1024, 1024),
        3 => (512, 768),
        4 => (768, 512),
        5 => (768, 1024),
        6 => (1024, 768),
        _ => (512, 512),
    };
    recipe.batch_size = settings.batch.value_as_int().clamp(1, 8) as u32;
    recipe.seed = settings.seed.value_as_int() as i64;
    recipe.tags = settings
        .tags
        .text()
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .collect();
    if recipe.tags.is_empty() {
        recipe.tags = vec![
            "mseries-image-studio".into(),
            recipe.intent.to_lowercase().replace(' ', "-"),
        ];
    }
    recipe
}

fn load_recipe(recipe: &Recipe, page: &CreatePage, settings: &Inspector) {
    set_text(&page.prompt, &recipe.prompt);
    set_text(&page.negative, &recipe.negative_prompt);
    *page.workflow.borrow_mut() = recipe.workflow.clone();
    page.workflow_status.set_text(&format!(
        "Loaded {} · editing this copy will not change the saved recipe.",
        recipe.workflow
    ));
    if let Some(index) = INTENTS.iter().position(|intent| *intent == recipe.intent) {
        page.intent.set_selected(index as u32);
    }
    let installed = gtk::glib::user_data_dir()
        .join("mseries-image-studio/models/stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf");
    if recipe.engine_id.contains("hosted") && installed.is_file() {
        settings.model.set_text(&installed.to_string_lossy());
    } else {
        settings.model.set_text(&recipe.model_id);
    }
    settings.steps.set_value(recipe.steps as f64);
    settings.cfg.set_value(recipe.cfg_scale);
    settings.sampler.set_selected(
        ["euler", "euler_a", "dpm++2m", "dpm++2m_sde"]
            .iter()
            .position(|sampler| *sampler == recipe.sampler)
            .unwrap_or(0) as u32,
    );
    settings.vae.set_text(&recipe.vae_path);
    settings.vae_on_cpu.set_active(recipe.vae_on_cpu);
    settings.reference_image.set_text(&recipe.reference_image);
    settings
        .reference_strength
        .set_value(recipe.reference_strength);
    settings
        .vae_tile_size
        .set_value(recipe.vae_tile_size as f64);
    settings.cpu_threads.set_value(recipe.cpu_threads as f64);
    settings.params_backend.set_selected(
        ["disk", "cpu", "auto"]
            .iter()
            .position(|backend| *backend == recipe.params_backend)
            .unwrap_or(0) as u32,
    );
    settings.max_vram_gib.set_value(recipe.max_vram_gib);
    settings
        .scheduler
        .set_selected(if recipe.scheduler == "karras" { 1 } else { 0 });
    settings.lora.set_text(&recipe.lora_id);
    settings.lora_weight.set_value(recipe.lora_weight);
    settings
        .dimensions
        .set_selected(match (recipe.width, recipe.height) {
            (512, 768) => 3,
            (768, 512) => 4,
            (768, 1024) => 5,
            (1024, 768) => 6,
            (768, 768) => 1,
            (1024, 1024) => 2,
            _ => 0,
        });
    settings
        .batch
        .set_value(recipe.batch_size.clamp(1, 8) as f64);
    settings
        .seed
        .set_value(recipe.seed.clamp(-1, i32::MAX as i64) as f64);
    settings.tags.set_text(&recipe.tags.join(", "));
    settings
        .recipe_status
        .set_text("Recipe loaded from Library.");
}

fn add_recipe_row(
    list: &gtk::ListBox,
    recipe: Recipe,
    page: &CreatePage,
    settings: &Inspector,
    stack: &gtk::Stack,
    newest: bool,
) {
    let row = gtk::ListBoxRow::new();
    let content = gtk::Box::new(gtk::Orientation::Horizontal, 10);
    for margin in [8] {
        content.set_margin_top(margin);
        content.set_margin_bottom(margin);
        content.set_margin_start(12);
        content.set_margin_end(8);
    }
    let label = gtk::Label::new(Some(&format!(
        "{} · {}×{} · {}\n{}",
        recipe.intent, recipe.width, recipe.height, recipe.workflow, recipe.prompt
    )));
    label.set_xalign(0.0);
    label.set_wrap(true);
    label.set_hexpand(true);
    label.set_max_width_chars(72);
    let load = gtk::Button::with_label("Load");
    load.set_valign(gtk::Align::Center);
    let page = page.clone_refs();
    let settings = settings.clone_refs();
    let stack = stack.clone();
    load.connect_clicked(move |_| {
        load_recipe(&recipe, &page, &settings);
        stack.set_visible_child_name("create");
    });
    content.append(&label);
    content.append(&load);
    row.set_child(Some(&content));
    if newest {
        list.prepend(&row);
    } else {
        list.append(&row);
    }
}

fn load_recipes(
    list: &gtk::ListBox,
    page: &CreatePage,
    settings: &Inspector,
    stack: &gtk::Stack,
    store: &RecipeStore,
) {
    match store.load_recent(100) {
        Ok(recipes) => {
            for recipe in recipes {
                add_recipe_row(list, recipe, page, settings, stack, false);
            }
        }
        Err(error) => eprintln!("Could not load image recipes: {error}"),
    }
}

fn load_generated_images(
    list: &gtk::ListBox,
    placeholder: &granite::Placeholder,
    heading: &gtk::Label,
    scroll: &gtk::ScrolledWindow,
    create: &CreatePage,
    inspector: &Inspector,
    stack: &gtk::Stack,
) {
    let directory = gtk::glib::user_data_dir()
        .join("mseries-image-studio")
        .join("images");
    while let Some(child) = list.first_child() {
        list.remove(&child);
    }
    let outputs = load_outputs(&directory, 100).unwrap_or_else(|error| {
        eprintln!("Could not load image metadata: {error}");
        vec![]
    });
    for recipe in &outputs {
        let row = gtk::ListBoxRow::new();
        let content = gtk::Box::new(gtk::Orientation::Horizontal, 12);
        content.set_margin_top(10);
        content.set_margin_bottom(10);
        content.set_margin_start(12);
        content.set_margin_end(12);
        let picture = gtk::Picture::for_filename(&recipe.image_path);
        picture.set_content_fit(gtk::ContentFit::Contain);
        picture.set_size_request(210, 150);
        let detail = gtk::Box::new(gtk::Orientation::Vertical, 5);
        detail.set_hexpand(true);
        detail.set_valign(gtk::Align::Center);
        let title = gtk::Label::new(Some(&format!(
            "{} · {}×{}",
            recipe.intent, recipe.width, recipe.height
        )));
        title.set_xalign(0.0);
        title.add_css_class("heading");
        detail.append(&title);
        let prompt = gtk::Label::new(Some(&recipe.prompt));
        prompt.set_xalign(0.0);
        prompt.set_wrap(true);
        prompt.set_max_width_chars(64);
        detail.append(&prompt);
        let model_note = if recipe.model_id.is_empty() {
            "Model not recorded".to_string()
        } else {
            format!("Model: {}", short_model_name(&recipe.model_id))
        };
        detail.append(&gtk::Label::new(Some(&model_note)));
        let notes = gtk::Expander::new(Some("My model notes and rating"));
        notes.set_child(Some(&crate::model_notes::model_notes_editor(
            gtk::glib::user_data_dir().join("mseries-image-studio"),
            recipe.model_id.clone(),
        )));
        detail.append(&notes);
        if !recipe.lora_id.is_empty() {
            detail.append(&gtk::Label::new(Some(&format!(
                "LoRA: {} · {:.2}",
                recipe.lora_id, recipe.lora_weight
            ))));
        }
        if !recipe.tags.is_empty() {
            detail.append(&gtk::Label::new(Some(&format!(
                "Tags: {}",
                recipe.tags.join(", ")
            ))));
        }
        let settings_expander = gtk::Expander::new(Some("Generation settings"));
        let settings_text = gtk::Label::new(Some(&format!(
            "Sampler: {} · Steps: {} · Guidance: {:.1} · Seed: {}\nNegative prompt: {}\nFirst preview: {} · Preview frames: {}\n{}",
            recipe.sampler,
            recipe.steps,
            recipe.cfg_scale,
            recipe.seed,
            recipe.negative_prompt,
            recipe
                .time_to_first_preview_seconds
                .map(|v| format!("{v:.1} s"))
                .unwrap_or_else(|| "Not measured".into()),
            recipe.preview_count,
            if recipe.engine_id.contains("hosted") {
                "Hosted model and inference settings were not exposed; sampler and steps above are editable local starter defaults."
            } else {
                "Peak memory below reports process RSS, excluding GPU memory."
            }
        )));
        settings_text.set_xalign(0.0);
        settings_text.set_wrap(true);
        settings_text.set_max_width_chars(64);
        settings_expander.set_child(Some(&settings_text));
        detail.append(&settings_expander);
        let benchmark = gtk::Label::new(Some(&format!(
            "Engine: {} · Time: {} · Peak memory: {}",
            recipe.engine_id,
            recipe
                .elapsed_seconds
                .map(|v| format!("{v:.1} s"))
                .unwrap_or_else(|| "Not measured".into()),
            recipe
                .peak_memory_mib
                .map(|v| format!("{v} MiB"))
                .unwrap_or_else(|| "Not measured".into())
        )));
        benchmark.set_xalign(0.0);
        benchmark.set_wrap(true);
        detail.append(&benchmark);
        let conditioning = gtk::Label::new(Some(&format!(
            "Reference: {} · strength {:.2} · VAE {} · tiles {} · {} CPU threads",
            if recipe.reference_image.is_empty() {
                "None".into()
            } else {
                Path::new(&recipe.reference_image)
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string()
            },
            recipe.reference_strength,
            if recipe.vae_on_cpu { "CPU" } else { "GPU" },
            recipe.vae_tile_size,
            recipe.cpu_threads
        )));
        conditioning.set_wrap(true);
        conditioning.set_xalign(0.0);
        detail.append(&conditioning);
        if !recipe.settings_note.is_empty() {
            let note = gtk::Label::new(Some(&recipe.settings_note));
            note.set_wrap(true);
            note.set_xalign(0.0);
            detail.append(&note);
        }
        let view = gtk::Button::with_label("View image");
        view.set_halign(gtk::Align::Start);
        let image_path = recipe.image_path.clone();
        view.connect_clicked(move |button| {
            let viewer = gtk::Window::builder()
                .title("Image Studio · Image")
                .default_width(1100)
                .default_height(760)
                .build();
            if let Some(parent) = button.root().and_downcast::<gtk::Window>() {
                viewer.set_transient_for(Some(&parent));
            }
            let image = gtk::Picture::for_filename(&image_path);
            image.set_content_fit(gtk::ContentFit::Contain);
            image.set_can_shrink(true);
            viewer.set_child(Some(&image));
            viewer.present();
        });
        detail.append(&view);
        let actions = gtk::Box::new(gtk::Orientation::Horizontal, 6);
        actions.set_homogeneous(false);
        for (label, new_seed) in [("Repeat exactly", false), ("Try new seed", true)] {
            let reuse = gtk::Button::with_label(label);
            reuse.set_tooltip_text(Some(if new_seed {
                "Load this recipe with a fresh random seed. Press Run when ready."
            } else {
                "Load this recipe and its saved seed. Press Run when ready."
            }));
            if !new_seed && recipe.engine_id.contains("hosted") {
                reuse.set_sensitive(false);
                reuse.set_tooltip_text(Some("Exact repeat is unavailable: the hosted provider did not expose its model and inference settings."));
            }
            let mut saved = recipe.clone();
            if new_seed {
                saved.seed = -1;
            }
            let create = create.clone_refs();
            let inspector = inspector.clone_refs();
            let stack = stack.clone();
            reuse.connect_clicked(move |_| {
                load_recipe(&saved, &create, &inspector);
                stack.set_visible_child_name("create");
            });
            actions.append(&reuse);
        }
        detail.append(&actions);
        content.append(&picture);
        content.append(&detail);
        row.set_child(Some(&content));
        list.append(&row);
    }
    let has_outputs = !outputs.is_empty();
    placeholder.set_visible(!has_outputs);
    heading.set_visible(has_outputs);
    scroll.set_visible(has_outputs);
}

fn refresh_hardware(
    hardware: &gtk::Label,
    engine: &gtk::Label,
    generate: &gtk::Button,
    selected_model: &gtk::Entry,
) {
    let host = HostCapabilities::capture();
    hardware.set_text(&format!(
        "{}\n6 GiB desktop reserve: {}\n{}",
        host.memory_summary(),
        if host.reserve_met() { "met" } else { "not met" },
        if host.has_render_node {
            "Render node detected"
        } else {
            "No render node detected"
        }
    ));
    let base = gtk::glib::user_data_dir().join("mseries-image-studio");
    let connected = base.join("engine/sd-cli").is_file();
    let selected = selected_model.text().to_string();
    let name = Path::new(&selected)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    let required = match name {
        "stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf" => 9.0,
        "stable-diffusion-v1-5-pruned-emaonly-Q8_0.gguf" => 9.5,
        "sd_xl_turbo_1.0_fp16.safetensors" => 12.0,
        "Realistic_Vision_V6.0_NV_B1_fp16.safetensors" => 10.25,
        _ => f64::INFINITY,
    };
    let model = Path::new(&selected).is_file() && required.is_finite();
    let busy = base.join("generation.lock").exists() || base.join("batch.lock").exists();
    engine.set_text(&if !connected { "Install the local image engine in Models. Hosted samples have no intermediate frames.".into() }
        else if !model { "Local engine installed. Select a downloaded model in Models and load its starter settings.".into() }
        else { format!("Local engine installed. Selected model needs {required:.1} GiB available, including the desktop reserve. Runs are supervised calibration until qualified.") });
    generate.set_sensitive(connected && model && !busy && host.available_gib() >= required);
    generate.set_label(if busy {
        "Workflow active…"
    } else {
        "Render local preview"
    });
    generate.set_tooltip_text(Some(
        "Run the selected local recipe. Memory or configuration errors appear in the preview.",
    ));
}

fn show_intent_dialog(parent: &gtk::ApplicationWindow, dropdown: &gtk::DropDown, suggestion: &str) {
    let dialog = gtk::Window::builder()
        .title("Review prompt type")
        .transient_for(parent)
        .modal(true)
        .default_width(420)
        .default_height(180)
        .build();
    let body = dialog_body();
    for text in [
        format!("The local assistant recommends: {suggestion}"),
        "Your prompt will stay unchanged. Choose whether to use this type.".into(),
    ] {
        let label = gtk::Label::new(Some(&text));
        label.set_xalign(0.0);
        label.set_wrap(true);
        body.append(&label);
    }
    let actions = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    actions.set_halign(gtk::Align::End);
    let keep = gtk::Button::with_label("Keep current type");
    let accept = gtk::Button::with_label("Use suggested type");
    accept.add_css_class("suggested-action");
    let close = dialog.clone();
    keep.connect_clicked(move |_| close.close());
    let close = dialog.clone();
    let dropdown = dropdown.clone();
    let suggestion = suggestion.to_string();
    accept.connect_clicked(move |_| {
        if let Some(index) = INTENTS.iter().position(|intent| *intent == suggestion) {
            dropdown.set_selected(index as u32);
        }
        close.close();
    });
    actions.append(&keep);
    actions.append(&accept);
    body.append(&actions);
    dialog.set_child(Some(&body));
    dialog.present();
}

fn show_prompt_dialog(parent: &gtk::ApplicationWindow, prompt: &gtk::TextView, suggestion: &str) {
    let dialog = gtk::Window::builder()
        .title("Review prompt suggestion")
        .transient_for(parent)
        .modal(true)
        .default_width(520)
        .default_height(360)
        .build();
    let body = dialog_body();
    let original = gtk::Label::new(Some(
        "Your original prompt stays unchanged until you accept this suggestion.",
    ));
    original.set_xalign(0.0);
    original.set_wrap(true);
    body.append(&original);
    let proposal = gtk::TextView::new();
    proposal.set_editable(false);
    proposal.set_cursor_visible(false);
    proposal.set_wrap_mode(gtk::WrapMode::WordChar);
    proposal.buffer().set_text(suggestion);
    body.append(
        &gtk::ScrolledWindow::builder()
            .child(&proposal)
            .min_content_height(150)
            .build(),
    );
    let actions = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    actions.set_halign(gtk::Align::End);
    let keep = gtk::Button::with_label("Keep original");
    let accept = gtk::Button::with_label("Use suggestion");
    accept.add_css_class("suggested-action");
    let close = dialog.clone();
    keep.connect_clicked(move |_| close.close());
    let close = dialog.clone();
    let prompt = prompt.clone();
    let suggestion = suggestion.to_string();
    accept.connect_clicked(move |_| {
        set_text(&prompt, &suggestion);
        close.close();
    });
    actions.append(&keep);
    actions.append(&accept);
    body.append(&actions);
    dialog.set_child(Some(&body));
    dialog.present();
}

fn dialog_body() -> gtk::Box {
    let body = gtk::Box::new(gtk::Orientation::Vertical, 10);
    body.set_margin_top(16);
    body.set_margin_bottom(16);
    body.set_margin_start(16);
    body.set_margin_end(16);
    body
}

fn set_text(view: &gtk::TextView, text: &str) {
    view.buffer().set_text(text);
}

fn text_of(view: &gtk::TextView) -> String {
    let buffer = view.buffer();
    buffer
        .text(&buffer.start_iter(), &buffer.end_iter(), true)
        .to_string()
}

fn walk(widget: &gtk::Widget, visit: &mut dyn FnMut(&gtk::Widget)) {
    visit(widget);
    let mut child = widget.first_child();
    while let Some(item) = child {
        walk(&item, visit);
        child = item.next_sibling();
    }
}

fn test_hooks(
    application: &gtk::Application,
    window: &gtk::ApplicationWindow,
    stack: &gtk::Stack,
    create: &CreatePage,
    library: &LibraryPage,
    inspector: &Inspector,
    store: &RecipeStore,
) {
    if let Ok(workflow) = std::env::var("M_SERIES_IMAGE_STUDIO_TEST_WORKFLOW") {
        if ["Model readiness", "LoRA comparison", "Prompt type study"].contains(&workflow.as_str())
        {
            apply_workflow(&workflow, create, inspector);
        }
    }
    if let Ok(prompt) = std::env::var("M_SERIES_IMAGE_STUDIO_TEST_PROMPT") {
        set_text(&create.prompt, &prompt);
    }
    if std::env::var("M_SERIES_IMAGE_STUDIO_TEST_PAGE")
        .ok()
        .as_deref()
        == Some("library")
    {
        stack.set_visible_child_name("library");
    }
    if std::env::var("M_SERIES_IMAGE_STUDIO_TEST_SAVE_RECIPE")
        .ok()
        .as_deref()
        == Some("1")
    {
        let recipe = current_recipe(create, inspector);
        match store.save(&recipe) {
            Ok(_) => {
                inspector.recipe_status.set_text("Recipe saved to Library.");
                add_recipe_row(&library.recipes, recipe, create, inspector, stack, true);
            }
            Err(error) => inspector
                .recipe_status
                .set_text(&format!("Recipe could not be saved: {error}")),
        }
    }
    if let Ok(screenshot) = std::env::var("M_SERIES_IMAGE_STUDIO_SCREENSHOT") {
        let window = window.clone();
        glib::timeout_add_local_once(Duration::from_millis(1600), move || {
            save_window_png(&window, Path::new(&screenshot))
        });
    }
    if let Ok(seconds) = std::env::var("M_SERIES_IMAGE_STUDIO_EXIT_AFTER") {
        let seconds = seconds.parse::<u32>().unwrap_or(3).max(1);
        let application = application.clone();
        glib::timeout_add_seconds_local(seconds, move || {
            application.quit();
            glib::ControlFlow::Break
        });
    }
}

fn save_window_png(window: &gtk::ApplicationWindow, path: &Path) {
    let paintable = gtk::WidgetPaintable::new(Some(window));
    let snapshot = gtk::Snapshot::new();
    paintable.snapshot(
        &snapshot,
        f64::from(window.width()),
        f64::from(window.height()),
    );
    if let Some(node) = snapshot.to_node() {
        if let Some(renderer) = window.native().and_then(|native| native.renderer()) {
            if let Err(error) = renderer.render_texture(&node, None).save_to_png(path) {
                eprintln!("Could not save screenshot: {error}");
            }
        }
    }
}

impl CreatePage {
    fn clone_refs(&self) -> Self {
        Self {
            page: self.page.clone(),
            prompt: self.prompt.clone(),
            negative: self.negative.clone(),
            intent: self.intent.clone(),
            assistant_status: self.assistant_status.clone(),
            workflow_status: self.workflow_status.clone(),
            queue_status: self.queue_status.clone(),
            workflow: self.workflow.clone(),
        }
    }
}

impl Inspector {
    fn clone_refs(&self) -> Self {
        Self {
            panel: self.panel.clone(),
            hardware: self.hardware.clone(),
            engine: self.engine.clone(),
            model: self.model.clone(),
            model_picker: self.model_picker.clone(),
            lora: self.lora.clone(),
            lora_weight: self.lora_weight.clone(),
            dimensions: self.dimensions.clone(),
            batch: self.batch.clone(),
            seed: self.seed.clone(),
            steps: self.steps.clone(),
            cfg: self.cfg.clone(),
            sampler: self.sampler.clone(),
            vae: self.vae.clone(),
            vae_on_cpu: self.vae_on_cpu.clone(),
            reference_image: self.reference_image.clone(),
            reference_strength: self.reference_strength.clone(),
            vae_tile_size: self.vae_tile_size.clone(),
            cpu_threads: self.cpu_threads.clone(),
            params_backend: self.params_backend.clone(),
            max_vram_gib: self.max_vram_gib.clone(),
            scheduler: self.scheduler.clone(),
            tags: self.tags.clone(),
            generate: self.generate.clone(),
            save: self.save.clone(),
            recipe_status: self.recipe_status.clone(),
        }
    }
}

fn build_model_guide(
    create: &CreatePage,
    inspector: &Inspector,
    stack: &gtk::Stack,
) -> gtk::Widget {
    let page = gtk::Box::new(gtk::Orientation::Vertical, 16);
    page.add_css_class("pantheon-inset");
    let title = gtk::Label::new(Some("Choose a model for your project"));
    title.add_css_class("title-2");
    title.set_xalign(0.0);
    page.append(&title);
    let intro = gtk::Label::new(Some(
        "A short list for Apple Silicon running Linux. Download size is not inference memory. Author guidance and engine support are distinguished from local qualification.",
    ));
    intro.set_wrap(true);
    intro.set_xalign(0.0);
    page.append(&intro);
    let grid = gtk::Grid::builder()
        .column_spacing(16)
        .row_spacing(12)
        .build();
    for (r, cells) in [
        [
            "Model",
            "Best starting use",
            "Settings / dependencies",
            "App qualification",
        ],
        [
            "Realistic Vision 6.0 FP16",
            "Photographic portraits and fashion",
            "512 × 768 · DPM++ 2M · Karras · 30 steps · CFG 5 · external vae-ft-mse-840000-ema-pruned",
            "Installed; quality test pending",
        ],
        [
            "SD 1.5 Q4 / Q8",
            "Small portrait and fashion studies",
            "512² · Euler · 20 steps · CFG 7 · seed 424242 · batch 1",
            "Q4: supervised local calibration",
        ],
        [
            "SDXL Turbo FP16",
            "Fast composition experiments",
            "512² · 1–4 steps · engine CFG 1 (Diffusers guidance 0); no negative prompt",
            "Download candidate; local render not qualified",
        ],
        [
            "Qwen3-VL 2B Q4",
            "Review images against a rubric",
            "Model + matching Q8 vision projector · run after generation unloads",
            "CPU review adapter; download model + projector",
        ],
        [
            "LoRA adapters",
            "Style or subject conditioning",
            "Must match base family; start weight 0.7; keep seed fixed",
            "Not qualified in this app",
        ],
        [
            "IP-Adapter / inpainting",
            "Reference identity / masked edits",
            "Matching vision encoder or inpainting checkpoint required",
            "Engine capability; app controls pending",
        ],
    ]
    .iter()
    .enumerate()
    {
        for (c, text) in cells.iter().enumerate() {
            let label = gtk::Label::new(Some(text));
            label.set_wrap(true);
            label.set_max_width_chars(25);
            label.set_xalign(0.0);
            label.set_valign(gtk::Align::Start);
            if r == 0 {
                label.add_css_class("heading");
            }
            grid.attach(&label, c as i32, r as i32, 1, 1);
        }
    }
    page.append(&grid);
    for (label, steps, cfg) in [
        ("Use portrait defaults · 20 steps", 20.0, 7.0),
        ("Use speed test · 8 steps · reduced quality", 8.0, 7.0),
    ] {
        let button = gtk::Button::with_label(label);
        button.set_halign(gtk::Align::Start);
        let create = create.clone_refs();
        let inspector = inspector.clone_refs();
        let stack = stack.clone();
        button.connect_clicked(move |_|{inspector.steps.set_value(steps);inspector.cfg.set_value(cfg);inspector.seed.set_value(424242.0);inspector.batch.set_value(1.0);inspector.dimensions.set_selected(0);inspector.lora.set_text("");inspector.model.set_text(&gtk::glib::user_data_dir().join("mseries-image-studio/models/stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf").to_string_lossy());create.workflow.replace("SD 1.5 starter".into());inspector.recipe_status.set_text("Starter defaults loaded. Local calibration and memory admission still apply.");stack.set_visible_child_name("create");});
        page.append(&button);
    }
    let review = gtk::Label::new(Some(
        "Compare fairly: keep seed, dimensions and steps fixed; change one prompt phrase or model at a time. A vision grade should store the rubric, evaluator identity, explanations and run settings. It is advisory, not a guarantee of likeness or commercial image quality.",
    ));
    review.set_wrap(true);
    review.set_xalign(0.0);
    page.append(&review);
    for (label, url) in [
        (
            "SD 1.5 quantized model files and license",
            "https://huggingface.co/second-state/stable-diffusion-v1-5-GGUF",
        ),
        (
            "SDXL Turbo author settings and license",
            "https://huggingface.co/stabilityai/sdxl-turbo",
        ),
        (
            "Qwen3-VL model and projector instructions",
            "https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF",
        ),
        (
            "Vulkan engine support",
            "https://github.com/leejet/stable-diffusion.cpp",
        ),
    ] {
        page.append(&gtk::LinkButton::with_label(url, label));
    }
    gtk::ScrolledWindow::builder()
        .child(&page)
        .hscrollbar_policy(gtk::PolicyType::Automatic)
        .build()
        .upcast()
}
