//! Event sources that replace the compositor's former idle polling timers.
//!
//! Every helper here parks a thread (or the calloop poll itself) until there
//! is real work, so an idle compositor performs no periodic wakeups.

use gio::{
    Settings, SettingsBackend, SettingsSchemaSource,
    glib::{MainContext, MainLoop},
    prelude::SettingsExt,
};
use smithay::reexports::calloop::channel::{self, Channel};
use std::sync::mpsc;

/// Move items from a std channel (whose sender lives in a D-Bus service
/// thread) into a calloop channel. The forwarding thread blocks in `recv`, so
/// the compositor wakes exactly when an item arrives.
pub(crate) fn forward<T: Send + 'static>(name: &str, receiver: mpsc::Receiver<T>) -> Channel<T> {
    let (sender, channel) = channel::channel();
    let spawned = std::thread::Builder::new()
        .name(name.to_owned())
        .spawn(move || {
            while let Ok(item) = receiver.recv() {
                if sender.send(item).is_err() {
                    return;
                }
            }
        });
    if let Err(error) = spawned {
        tracing::warn!(%error, name, "could not start channel forwarding thread");
    }
    channel
}

/// Deliver a `()` whenever any key of the given GSettings schemas changes.
/// Runs a private GLib main context on its own thread (GSettings change
/// notifications require one) so the compositor loop is only woken by changes.
pub(crate) fn watch_settings(schemas: &'static [&'static str]) -> Channel<()> {
    let (sender, channel) = channel::channel();
    let spawned = std::thread::Builder::new()
        .name("gsettings-watch".into())
        .spawn(move || {
            let Some(source) = SettingsSchemaSource::default() else {
                return;
            };
            let context = MainContext::new();
            let _ = context.with_thread_default(|| {
                let mut watched = Vec::new();
                for id in schemas {
                    let Some(schema) = source.lookup(id, true) else {
                        continue;
                    };
                    let settings = Settings::new_full(&schema, None::<&SettingsBackend>, None);
                    let sender = sender.clone();
                    settings.connect_changed(None, move |_, _| {
                        let _ = sender.send(());
                    });
                    watched.push(settings);
                }
                if watched.is_empty() {
                    return;
                }
                MainLoop::new(Some(&context), false).run();
            });
        });
    if let Err(error) = spawned {
        tracing::warn!(%error, "could not start GSettings watcher thread");
    }
    channel
}
