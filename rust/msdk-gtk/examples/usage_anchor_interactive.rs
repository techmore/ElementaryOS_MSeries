//! Private-session anchor fixture. It does not install a desktop status host.
use gtk::prelude::*;
use msdk::usage::{Coverage, Snapshot};

fn main() -> gtk::glib::ExitCode {
    let executable = std::env::args_os()
        .nth(1)
        .expect("synthetic executable path");
    let app = gtk::Application::builder()
        .application_id("io.github.techmore.MsdkUsageAnchorTest")
        .flags(gtk::gio::ApplicationFlags::NON_UNIQUE)
        .build();
    let quit = gtk::gio::SimpleAction::new("quit", None);
    let weak_app = app.downgrade();
    quit.connect_activate(move |_, _| {
        if let Some(app) = weak_app.upgrade() {
            app.quit();
        }
    });
    app.add_action(&quit);
    app.set_accels_for_action("app.quit", &["<Primary>q"]);
    app.connect_activate(move |app| {
        let snapshot = Snapshot {
            coverage: Coverage::Unknown,
            observations: vec![],
        };
        let anchor = msdk_gtk::usage_anchor::UsageAnchor::new(
            &snapshot,
            0,
            executable.clone().into(),
            u64::MAX,
            gtk::PositionType::Top,
        )
        .unwrap();
        let column = gtk::Box::new(gtk::Orientation::Vertical, 8);
        let spacer = gtk::Box::new(gtk::Orientation::Vertical, 0);
        spacer.set_vexpand(true);
        column.append(&spacer);
        let row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        row.set_halign(gtk::Align::End);
        row.set_margin_end(12);
        row.set_margin_bottom(12);
        row.append(&gtk::Button::with_label("Outside"));
        row.append(anchor.button());
        column.append(&row);
        let window = gtk::ApplicationWindow::builder()
            .application(app)
            .title("Usage status anchor test")
            .default_width(480)
            .default_height(500)
            .child(&column)
            .build();
        window.connect_close_request(move |_| {
            let _keep_alive = &anchor;
            gtk::glib::Propagation::Proceed
        });
        window.present();
    });
    app.run_with_args::<&str>(&[])
}
