//! Drives the real Pantheon window through its save/load path under Xvfb.

use gtk::glib;
use gtk::prelude::*;
use mseries_image_studio::{Recipe, RecipeStore, recipe::save_png, ui::ImageStudioWindow};
use std::path::PathBuf;
use std::time::{Duration, Instant};

fn scratch() -> PathBuf {
    std::env::temp_dir().join(format!("image-studio-render-{}", std::process::id()))
}

fn pump(duration: Duration) {
    let end = Instant::now() + duration;
    let context = glib::MainContext::default();
    while Instant::now() < end {
        while context.iteration(false) {}
        std::thread::sleep(Duration::from_millis(5));
    }
}

fn walk(widget: &gtk::Widget, visit: &mut dyn FnMut(&gtk::Widget)) {
    visit(widget);
    let mut child = widget.first_child();
    while let Some(item) = child {
        walk(&item, visit);
        child = item.next_sibling();
    }
}

fn button(window: &gtk::ApplicationWindow, name: &str) -> gtk::Button {
    let mut found = None;
    walk(window.upcast_ref(), &mut |widget| {
        if let Some(button) = widget.downcast_ref::<gtk::Button>() {
            if button.label().is_some_and(|label| label == name) {
                found = Some(button.clone());
            }
        }
    });
    found.unwrap_or_else(|| panic!("missing button {name}"))
}

fn mapped_text(window: &gtk::ApplicationWindow) -> Vec<String> {
    let mut values = vec![];
    walk(window.upcast_ref(), &mut |widget| {
        if !widget.is_mapped() {
            return;
        }
        if let Some(label) = widget.downcast_ref::<gtk::Label>() {
            values.push(label.text().to_string());
        }
        if let Some(view) = widget.downcast_ref::<gtk::TextView>() {
            let buffer = view.buffer();
            values.push(
                buffer
                    .text(&buffer.start_iter(), &buffer.end_iter(), true)
                    .to_string(),
            );
        }
    });
    values
}

fn save_screenshot(window: &gtk::ApplicationWindow, name: &str) {
    let Some(directory) = std::env::var_os("MSERIES_IMAGE_STUDIO_SHOTS").map(PathBuf::from) else {
        return;
    };
    std::fs::create_dir_all(&directory).unwrap();
    let paintable = gtk::WidgetPaintable::new(Some(window));
    let snapshot = gtk::Snapshot::new();
    paintable.snapshot(
        &snapshot,
        f64::from(window.width()),
        f64::from(window.height()),
    );
    let node = snapshot.to_node().expect("mapped app window paint node");
    let renderer = window
        .native()
        .and_then(|native| native.renderer())
        .expect("window renderer");
    renderer
        .render_texture(&node, None)
        .save_to_png(directory.join(name))
        .unwrap();
}

fn main() {
    let data_home = scratch().join("xdg");
    let _ = std::fs::remove_dir_all(scratch());
    std::fs::create_dir_all(&data_home).unwrap();
    // These process-local values are set before GTK/GLib read user paths.
    unsafe {
        std::env::set_var("XDG_DATA_HOME", &data_home);
        std::env::set_var("M_SERIES_IMAGE_STUDIO_TEST_WORKFLOW", "Prompt type study");
        std::env::set_var("M_SERIES_IMAGE_STUDIO_TEST_SAVE_RECIPE", "1");
        std::env::remove_var("M_SERIES_IMAGE_STUDIO_TEST_PAGE");
    }
    let mut generated = Recipe::default();
    generated.prompt = "Test output image with recorded prompt metadata".into();
    generated.intent = "Streamer scene".into();
    generated.model_id = "fixture-model".into();
    generated.tags = vec!["fixture".into(), "metadata".into()];
    let images = data_home.join("mseries-image-studio").join("images");
    save_png(include_bytes!("fixtures/tiny.png"), &mut generated, &images).unwrap();

    gtk::init().expect("GTK display; run under xvfb-run");
    granite::init();
    let application = gtk::Application::builder()
        .application_id("org.elementary.mseries.ImageStudio.RenderTest")
        .build();
    application
        .register(gtk::gio::Cancellable::NONE)
        .expect("register app");
    let ui = ImageStudioWindow::build(&application);
    let window = ui.window();
    window.present();
    pump(Duration::from_millis(350));
    assert!(mapped_text(window).iter().any(|text| text == "Create"));
    save_screenshot(window, "image-studio-create.png");

    let recipes = RecipeStore::default_store().load_recent(10).unwrap();
    assert_eq!(recipes.len(), 1);
    assert_eq!(recipes[0].intent, "Streamer scene");
    assert_eq!(recipes[0].workflow, "Prompt type study");
    assert_eq!(
        (
            recipes[0].width,
            recipes[0].height,
            recipes[0].batch_size,
            recipes[0].seed
        ),
        (512, 512, 1, 424242)
    );
    assert!(recipes[0].prompt.contains("Alexandra Daddario"));
    assert!(recipes[0].prompt.contains("22-year-old adult"));

    button(window, "Library").emit_clicked();
    pump(Duration::from_millis(100));
    assert!(mapped_text(window).iter().any(|text| text == "Library"));
    let library_text = mapped_text(window);
    assert!(library_text.iter().any(|text| text == "Generated images"));
    assert!(
        library_text
            .iter()
            .any(|text| text.contains("Test output image with recorded prompt metadata"))
    );
    save_screenshot(window, "image-studio-library.png");
    button(window, "Load").emit_clicked();
    pump(Duration::from_millis(100));
    let visible = mapped_text(window);
    assert!(visible.iter().any(|text| text == "Create"));
    assert!(
        visible
            .iter()
            .any(|text| text.contains("Alexandra Daddario")
                && text.contains("Three-image editorial series"))
    );
}
