use gtk::prelude::*;
use mseries_image_studio::{APP_ID, ui::ImageStudioWindow};
use std::{cell::RefCell, rc::Rc};

fn main() -> gtk::glib::ExitCode {
    if std::env::var_os("GSK_RENDERER").is_none() {
        // GTK reads this during startup. Keep the lightweight cairo renderer as the safe default on Asahi.
        unsafe { std::env::set_var("GSK_RENDERER", "cairo") };
    }
    let application = gtk::Application::builder().application_id(APP_ID).build();
    application.connect_startup(|app| {
        granite::init();
        let quit = gtk::gio::SimpleAction::new("quit", None);
        let app_weak = app.downgrade();
        quit.connect_activate(move |_, _| {
            if let Some(app) = app_weak.upgrade() {
                app.quit();
            }
        });
        app.add_action(&quit);
        app.set_accels_for_action("app.quit", &["<Control>q"]);
        let about = gtk::gio::SimpleAction::new("about", None);
        let app_weak = app.downgrade();
        about.connect_activate(move |_, _| {
            if let Some(app) = app_weak.upgrade() {
                let dialog = gtk::AboutDialog::builder()
                    .application(&app)
                    .program_name("Image Studio")
                    .version(env!("CARGO_PKG_VERSION"))
                    .comments("A native Pantheon image creation workspace for M-Series.")
                    .build();
                dialog.present();
            }
        });
        app.add_action(&about);
    });
    let current_window = Rc::new(RefCell::new(None::<ImageStudioWindow>));
    let window_slot = current_window.clone();
    application.connect_activate(move |app| {
        if let Some(window) = window_slot.borrow().as_ref() {
            window.window().present();
            return;
        }
        let window = ImageStudioWindow::build(app);
        window.window().present();
        *window_slot.borrow_mut() = Some(window);
    });
    application.run()
}
