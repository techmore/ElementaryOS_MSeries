//! Synthetic read-only preview for native screenshot review; no real accounts.
use gtk::gdk;
use gtk::prelude::*;
use msdk::usage::{
    Coverage, Observation, Quota, QuotaUnit, Scope, Snapshot, Source, State, Window,
};
use std::cell::Cell;
use std::rc::Rc;

fn main() {
    let output = std::env::args()
        .nth(1)
        .expect("usage: usage_preview OUTPUT.png");
    let app = gtk::Application::builder()
        .application_id("io.github.techmore.MsdkUsagePreview")
        .flags(gtk::gio::ApplicationFlags::NON_UNIQUE)
        .build();
    let failed = Rc::new(Cell::new(false));
    let outcome = failed.clone();
    app.connect_activate(move |app| {
        let base = Observation {
            scope: Scope {
                provider: "claude".into(),
                source: Source::LocalClient,
                account: Some("fixture-one".into()),
            },
            provider_label: "Claude".into(),
            source_label: "This device".into(),
            account_label: Some("Work account".into()),
            selected: true,
            state: State::Fresh,
            observed_at: Some(100),
            windows: vec![Window {
                key: "week".into(),
                label: "7 day".into(),
                quota: Some(Quota::new(2500, QuotaUnit::Used, 100, None).unwrap()),
            }],
            tokens: None,
        };
        let other = Observation {
            scope: Scope {
                account: Some("fixture-two".into()),
                ..base.scope.clone()
            },
            account_label: Some("Personal account with a longer label".into()),
            selected: false,
            state: State::Stale,
            ..base.clone()
        };
        let snapshot = Snapshot {
            coverage: Coverage::Partial,
            observations: vec![base, other],
        };
        let content = msdk_gtk::usage::render(&snapshot, 150).expect("synthetic snapshot is valid");
        content.set_margin_top(12);
        content.set_margin_bottom(12);
        content.set_margin_start(12);
        content.set_margin_end(12);
        let window = gtk::ApplicationWindow::builder()
            .application(app)
            .title("Usage preview")
            .default_width(480)
            .default_height(500)
            .child(&content)
            .build();
        window.present();
        let app = app.clone();
        let path = output.clone();
        let failed = outcome.clone();
        gtk::glib::timeout_add_local_once(std::time::Duration::from_millis(1500), move || {
            let result = (|| -> Result<(), String> {
                let (width, height) = (window.width(), window.height());
                if width <= 0 || height <= 0 {
                    return Err("window has no size".into());
                }
                let paintable = gtk::WidgetPaintable::new(Some(&window));
                let snapshot = gtk::Snapshot::new();
                paintable.snapshot(
                    snapshot.upcast_ref::<gdk::Snapshot>(),
                    width as f64,
                    height as f64,
                );
                let node = snapshot.to_node().ok_or("nothing to draw")?;
                let renderer = window
                    .native()
                    .and_then(|native| native.renderer())
                    .ok_or("no renderer")?;
                renderer
                    .render_texture(&node, None)
                    .save_to_png(&path)
                    .map_err(|error| error.to_string())
            })();
            if let Err(error) = result {
                eprintln!("preview capture failed: {error}");
                failed.set(true);
            }
            app.quit();
        });
    });
    app.run_with_args::<&str>(&[]);
    if failed.get() {
        std::process::exit(1);
    }
}
