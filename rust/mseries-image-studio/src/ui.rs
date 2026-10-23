use crate::assistant;
use crate::generation_block_reason;
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
            .transition_type(gtk::StackTransitionType::Crossfade)
            .build();
        let recipe_store = RecipeStore::default_store();
        let create = build_create_page();
        let library = build_library_page(&recipe_store);
        stack.add_named(&create.page, Some("create"));
        stack.add_named(&library.page, Some("library"));

        let inspector = build_inspector();
        let main_split = gtk::Paned::builder()
            .orientation(gtk::Orientation::Horizontal)
            .start_child(&stack)
            .end_child(&inspector.panel)
            .position(720)
            .resize_start_child(true)
            .resize_end_child(false)
            .build();
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
            move |class| {
                let (sidebar_width, inspector_width) = match class {
                    mseries_pantheon_kit::LayoutClass::Compact => (176, 260),
                    mseries_pantheon_kit::LayoutClass::Regular => (216, 320),
                };
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
        refresh_hardware(&inspector.hardware, &inspector.engine, &inspector.generate);
        let hardware = inspector.hardware.clone();
        let engine = inspector.engine.clone();
        let generate = inspector.generate.clone();
        glib::timeout_add_seconds_local(5, move || {
            refresh_hardware(&hardware, &engine, &generate);
            glib::ControlFlow::Continue
        });
        load_recipes(&library.recipes, &create, &inspector, &stack, &recipe_store);
        load_generated_images(
            &library.outputs,
            &library.placeholder,
            &library.outputs_heading,
            &library.output_scroll,
            &create, &inspector, &stack,
        );
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
    lora: gtk::Entry,
    lora_weight: gtk::Scale,
    dimensions: gtk::DropDown,
    batch: gtk::SpinButton,
    seed: gtk::SpinButton,
    tags: gtk::Entry,
    generate: gtk::Button,
    save: gtk::Button,
    recipe_status: gtk::Label,
}

fn install_css(window: &gtk::ApplicationWindow) {
    let css = gtk::CssProvider::new();
    css.load_from_string(
        ".mseries-image-studio .studio-sidebar { border-right: 1px solid alpha(currentColor, 0.10); }
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
    for (label, page) in [("Create", "create"), ("Library", "library")] {
        let row = gtk::ListBoxRow::new();
        let contents = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        contents.add_css_class("pantheon-row");
        contents.append(&gtk::Image::from_icon_name(if page == "create" {
            "document-edit-symbolic"
        } else {
            "image-x-generic-symbolic"
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
            } else {
                "library"
            });
        }
    });
    sidebar.append(&navigation);
    let workflows = section_label("Guided workflows");
    sidebar.append(&workflows);
    for (title, subtitle, workflow) in [
        (
            "Model readiness",
            "Check one conservative render",
            "Model readiness",
        ),
        (
            "LoRA comparison",
            "Compare weights with a fixed seed",
            "LoRA comparison",
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
    sidebar.upcast()
}

fn build_create_page() -> CreatePage {
    let page = gtk::Box::new(gtk::Orientation::Vertical, 0);
    mseries_pantheon_kit::set_box_spacing_text_units(&page, 0.8);
    page.add_css_class("pantheon-inset");
    let title = gtk::Label::new(Some("Create"));
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
    preview_center.set_halign(gtk::Align::Center);
    preview_center.set_valign(gtk::Align::Center);
    preview_center.set_vexpand(true);
    let icon = gtk::Image::from_icon_name("image-x-generic-symbolic");
    icon.set_pixel_size(42);
    icon.add_css_class("dim-label");
    let preview_title = gtk::Label::new(Some("Your image preview will appear here"));
    preview_title.add_css_class("title-3");
    let preview_detail = gtk::Label::new(Some(
        "Image generation is waiting for a model runtime qualified on this M-Series device.",
    ));
    preview_detail.set_wrap(true);
    preview_detail.set_justify(gtk::Justification::Center);
    preview_detail.set_max_width_chars(64);
    preview_detail.add_css_class("dim-label");
    preview_center.append(&icon);
    preview_center.append(&preview_title);
    preview_center.append(&preview_detail);
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
    let queue_status = gtk::Label::new(Some("No image jobs queued"));
    queue_status.set_xalign(0.0);
    queue_status.set_hexpand(true);
    queue_row.append(&queue_status);
    page.append(&queue_row);

    CreatePage {
        page: page.upcast(),
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
    panel.set_width_request(270);
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
    panel.append(&model);
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
    let dimensions = gtk::DropDown::from_strings(&["512 × 512", "768 × 768", "1024 × 1024"]);
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
    panel.append(&section_label("Tags"));
    let tags = gtk::Entry::new();
    tags.set_placeholder_text(Some("portrait, streamer, study"));
    tags.update_property(&[gtk::accessible::Property::Label(
        "Comma-separated image tags",
    )]);
    panel.append(&tags);
    let note = gtk::Label::new(Some(
        "These values are saved with the recipe. Model names are notes until a compatible image engine is connected.",
    ));
    note.set_xalign(0.0);
    note.set_wrap(true);
    note.add_css_class("dim-label");
    panel.append(&note);
    let spacer = gtk::Box::new(gtk::Orientation::Vertical, 0);
    spacer.set_vexpand(true);
    panel.append(&spacer);
    let generate = gtk::Button::with_label("Generate preview");
    generate.set_sensitive(false);
    generate.add_css_class("suggested-action");
    generate.set_tooltip_text(Some(
        "Generation is disabled until an image engine/model pair is calibrated on this device.",
    ));
    generate.update_property(&[gtk::accessible::Property::Label(
        "Generate preview, unavailable until engine qualification",
    )]);
    panel.append(&generate);
    let save = gtk::Button::with_label("Save prompt recipe");
    panel.append(&save);
    let recipe_status = gtk::Label::new(Some("Save a prompt recipe to reopen its settings later."));
    recipe_status.set_xalign(0.0);
    recipe_status.set_wrap(true);
    recipe_status.add_css_class("dim-label");
    panel.append(&recipe_status);
    Inspector {
        panel: panel.upcast(),
        hardware,
        engine,
        model,
        lora,
        lora_weight,
        dimensions,
        batch,
        seed,
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
    recipe.lora_id = settings.lora.text().to_string();
    recipe.lora_weight = settings.lora_weight.value();
    recipe.width = match settings.dimensions.selected() {
        1 => 768,
        2 => 1024,
        _ => 512,
    };
    recipe.height = recipe.width;
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
    settings.model.set_text(&recipe.model_id);
    settings.lora.set_text(&recipe.lora_id);
    settings.lora_weight.set_value(recipe.lora_weight);
    settings.dimensions.set_selected(if recipe.width >= 1024 {
        2
    } else if recipe.width >= 768 {
        1
    } else {
        0
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
            format!("Model: {}", recipe.model_id)
        };
        detail.append(&gtk::Label::new(Some(&model_note)));
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
        let benchmark = gtk::Label::new(Some(&format!(
            "Engine: {} · Time: {} · Peak memory: {}",
            recipe.engine_id,
            recipe.elapsed_seconds.map(|v| format!("{v:.1} s")).unwrap_or_else(|| "Not measured".into()),
            recipe.peak_memory_mib.map(|v| format!("{v} MiB")).unwrap_or_else(|| "Not measured".into())
        )));
        benchmark.set_xalign(0.0);
        benchmark.set_wrap(true);
        detail.append(&benchmark);
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
            let viewer = gtk::Window::builder().title("Image Studio · Image")
                .default_width(1100).default_height(760).build();
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
        let reuse = gtk::Button::with_label("Use these settings");
        reuse.set_halign(gtk::Align::Start);
        let saved = recipe.clone();
        let create = create.clone_refs();
        let inspector = inspector.clone_refs();
        let stack = stack.clone();
        reuse.connect_clicked(move |_| {
            load_recipe(&saved, &create, &inspector);
            stack.set_visible_child_name("create");
        });
        detail.append(&reuse);
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

fn refresh_hardware(hardware: &gtk::Label, engine: &gtk::Label, generate: &gtk::Button) {
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
    engine.set_text(&format!("Image engine: not connected\n{}\nStarter target: 512 × 512, batch 1, after model calibration.", host.accelerator_summary()));
    generate.set_tooltip_text(Some(generation_block_reason(
        false,
        host.available_bytes,
        0,
    )));
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
            lora: self.lora.clone(),
            lora_weight: self.lora_weight.clone(),
            dimensions: self.dimensions.clone(),
            batch: self.batch.clone(),
            seed: self.seed.clone(),
            tags: self.tags.clone(),
            generate: self.generate.clone(),
            save: self.save.clone(),
            recipe_status: self.recipe_status.clone(),
        }
    }
}
