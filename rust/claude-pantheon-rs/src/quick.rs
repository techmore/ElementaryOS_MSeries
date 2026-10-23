//! Compact status window for explicit quick launch. It reads the app's local status snapshot and routes actions back
//! through the same App instance, so opening it never creates another T3 connection.

use gtk::{gio, glib, pango, prelude::*};
use serde::Deserialize;
use std::cell::RefCell;
use std::path::PathBuf;
use std::rc::Rc;

use crate::APP_ID;

#[derive(Clone)]
pub struct Actions {
    pub open_full: Rc<dyn Fn()>,
    pub new_chat: Rc<dyn Fn()>,
    pub open_usage: Rc<dyn Fn()>,
    pub open_settings: Rc<dyn Fn()>,
    pub open_thread: Rc<dyn Fn(String)>,
}

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct Feed {
    connected: bool,
    stale: bool,
    server: String,
    selected_provider_id: String,
    selected_provider: String,
    written_at: String,
    updated_at: String,
    running: Vec<Thread>,
    pending_prompts: Vec<Thread>,
    windows: Vec<UsageWindow>,
}

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct Thread {
    id: String,
    title: String,
    provider: String,
    count: u32,
}

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct UsageWindow {
    instance_id: String,
    provider: String,
    kind: String,
    label: String,
    used_percent: f64,
    resets_at: Option<String>,
}

pub struct QuickPanel {
    pub window: gtk::ApplicationWindow,
    account: gtk::Label,
    connection: gtk::Label,
    usage_title: gtk::Label,
    usage_detail: gtk::Label,
    usage_bar: gtk::LevelBar,
    usage_note: gtk::Label,
    activity: gtk::Box,
    freshness: gtk::Label,
    status_path: PathBuf,
    _monitor: RefCell<Option<gio::FileMonitor>>,
    actions: Actions,
}

impl QuickPanel {
    pub fn new(application: &gtk::Application, actions: Actions) -> Rc<Self> {
        let status_path = crate::status::path();
        let window = gtk::ApplicationWindow::builder()
            .application(application)
            .title("T3-R Pantheon")
            .default_width(390)
            .default_height(590)
            .resizable(false)
            .decorated(false)
            .build();
        window.add_css_class("t3-quick-window");

        let surface = gtk::Box::new(gtk::Orientation::Vertical, 12);
        surface.add_css_class("t3-quick-surface");
        surface.set_margin_top(8);
        surface.set_margin_bottom(8);
        surface.set_margin_start(8);
        surface.set_margin_end(8);
        window.set_child(Some(&surface));

        let header = gtk::Box::new(gtk::Orientation::Horizontal, 10);
        header.add_css_class("t3-quick-header");
        let icon = gtk::Image::from_icon_name(APP_ID);
        icon.set_pixel_size(32);
        let identity = gtk::Box::new(gtk::Orientation::Vertical, 2);
        identity.set_hexpand(true);
        let brand = gtk::Label::new(Some("T3-R Pantheon"));
        brand.add_css_class("title-4");
        brand.set_xalign(0.0);
        let account = gtk::Label::new(Some("No provider selected"));
        account.add_css_class("caption");
        account.add_css_class("dim-label");
        account.set_xalign(0.0);
        account.set_ellipsize(pango::EllipsizeMode::End);
        identity.append(&brand);
        identity.append(&account);
        let close = gtk::Button::from_icon_name("window-close-symbolic");
        close.set_has_frame(false);
        close.set_tooltip_text(Some("Close quick panel"));
        close.update_property(&[gtk::accessible::Property::Label("Close quick panel")]);
        let close_window = window.clone();
        close.connect_clicked(move |_| close_window.set_visible(false));
        header.append(&icon);
        header.append(&identity);
        header.append(&close);
        surface.append(&header);

        let connection = gtk::Label::new(Some("Pair with a T3 server in Settings"));
        connection.add_css_class("t3-quick-connection");
        connection.set_xalign(0.0);
        connection.set_wrap(true);
        surface.append(&connection);

        let usage_card = gtk::Box::new(gtk::Orientation::Vertical, 5);
        usage_card.add_css_class("t3-quick-card");
        let usage_header = gtk::Box::new(gtk::Orientation::Horizontal, 4);
        let usage_label = gtk::Label::new(Some("Usage"));
        usage_label.add_css_class("heading");
        usage_label.set_xalign(0.0);
        usage_label.set_hexpand(true);
        usage_header.append(&usage_label);
        let usage_title = gtk::Label::new(Some("Waiting for usage"));
        usage_title.set_xalign(0.0);
        let usage_detail = gtk::Label::new(Some("Usage windows will appear after the first sync."));
        usage_detail.add_css_class("caption");
        usage_detail.add_css_class("dim-label");
        usage_detail.set_xalign(0.0);
        usage_detail.set_ellipsize(pango::EllipsizeMode::End);
        let usage_bar = gtk::LevelBar::builder().min_value(0.0).max_value(100.0).build();
        usage_bar.add_css_class("t3-quick-gauge");
        usage_bar.add_offset_value("low", 60.0);
        usage_bar.add_offset_value("high", 90.0);
        usage_bar.add_offset_value("full", 100.0);
        let usage_note = gtk::Label::new(None);
        usage_note.add_css_class("caption");
        usage_note.add_css_class("dim-label");
        usage_note.set_xalign(0.0);
        usage_card.append(&usage_header);
        usage_card.append(&usage_title);
        usage_card.append(&usage_detail);
        usage_card.append(&usage_bar);
        usage_card.append(&usage_note);
        surface.append(&usage_card);

        let activity_card = gtk::Box::new(gtk::Orientation::Vertical, 6);
        activity_card.add_css_class("t3-quick-card");
        let activity_title = gtk::Label::new(Some("Activity"));
        activity_title.add_css_class("heading");
        activity_title.set_xalign(0.0);
        activity_card.append(&activity_title);
        let activity = gtk::Box::new(gtk::Orientation::Vertical, 3);
        activity_card.append(&activity);
        surface.append(&activity_card);

        let actions_row = gtk::Box::new(gtk::Orientation::Horizontal, 6);
        let new_chat = gtk::Button::with_label("New chat");
        new_chat.set_hexpand(true);
        new_chat.connect_clicked({
            let action = actions.new_chat.clone();
            move |_| action()
        });
        let usage = gtk::Button::with_label("Usage");
        usage.connect_clicked({
            let action = actions.open_usage.clone();
            move |_| action()
        });
        let settings = gtk::Button::with_label("Settings");
        settings.connect_clicked({
            let action = actions.open_settings.clone();
            move |_| action()
        });
        actions_row.append(&new_chat);
        actions_row.append(&usage);
        actions_row.append(&settings);
        surface.append(&actions_row);

        let freshness = gtk::Label::new(Some("No status snapshot yet"));
        freshness.add_css_class("caption");
        freshness.add_css_class("dim-label");
        freshness.set_xalign(0.0);
        freshness.set_ellipsize(pango::EllipsizeMode::End);
        surface.append(&freshness);

        let open_full = gtk::Button::with_label("Open full chat");
        open_full.add_css_class("suggested-action");
        open_full.set_hexpand(true);
        open_full.connect_clicked({
            let action = actions.open_full.clone();
            move |_| action()
        });
        surface.append(&open_full);

        let panel = Rc::new(Self {
            window,
            account,
            connection,
            usage_title,
            usage_detail,
            usage_bar,
            usage_note,
            activity,
            freshness,
            status_path,
            _monitor: RefCell::new(None),
            actions,
        });
        panel.watch_status();
        panel.reload();

        // Treat this compact window like a popover: it disappears when focus moves to another app.
        let focus = gtk::EventControllerFocus::new();
        focus.connect_leave({
            let weak = Rc::downgrade(&panel);
            move |_| {
                if let Some(panel) = weak.upgrade() {
                    panel.window.set_visible(false);
                }
            }
        });
        panel.window.add_controller(focus);
        panel
    }

    pub fn present(&self) {
        self.reload();
        self.window.present();
    }

    fn watch_status(self: &Rc<Self>) {
        let path = gio::File::for_path(&self.status_path);
        match path.monitor_file(gio::FileMonitorFlags::NONE, gio::Cancellable::NONE) {
            Ok(monitor) => {
                let weak = Rc::downgrade(self);
                monitor.connect_changed(move |_, _, _, _| {
                    if let Some(panel) = weak.upgrade() {
                        panel.reload();
                    }
                });
                *self._monitor.borrow_mut() = Some(monitor);
            }
            Err(error) => eprintln!("status feed monitor: {error}"),
        }
    }

    fn reload(&self) {
        let feed = std::fs::read(&self.status_path)
            .ok()
            .and_then(|bytes| serde_json::from_slice::<Feed>(&bytes).ok())
            .unwrap_or_default();
        self.render(feed);
    }

    fn render(&self, feed: Feed) {
        let provider_id = feed.selected_provider_id.trim();
        let provider_name = feed.selected_provider.trim();
        let has_account = !provider_id.is_empty();
        let account_name = if provider_name.is_empty() { provider_id } else { provider_name };
        let server = feed.server.trim();
        let live = feed.connected && !feed.stale;
        self.account.set_text(if has_account { account_name } else { "No provider selected" });
        let connection = if live {
            if server.is_empty() {
                "Connected · live status".to_string()
            } else {
                format!("Connected to {server} · live status")
            }
        } else if !server.is_empty() {
            format!("Offline · last synced from {server}")
        } else if has_account {
            "Offline · showing last synced status".to_string()
        } else {
            "Pair with a T3 server in Settings".to_string()
        };
        self.connection.set_text(&connection);
        self.connection.remove_css_class("connected");
        self.connection.remove_css_class("stale");
        self.connection.add_css_class(if live { "connected" } else { "stale" });

        let nearest = selected_window(&feed);
        match nearest {
            Some(window) => {
                self.usage_title.set_text(&format!("{} · {}", window.provider, window.label));
                self.usage_detail.set_text(&format!("{:.0}% used", window.used_percent));
                self.usage_bar.set_value(window.used_percent.clamp(0.0, 100.0));
                self.usage_note.set_text(&reset_summary(window.resets_at.as_deref().unwrap_or_default()));
                self.usage_bar.set_visible(true);
                self.usage_detail.set_visible(true);
            }
            None => {
                self.usage_title.set_text("No usage windows reported");
                self.usage_detail.set_text(if live {
                    "T3 has not reported a quota window yet."
                } else {
                    "Usage appears after the first sync."
                });
                self.usage_note.set_text("");
                self.usage_bar.set_visible(false);
                self.usage_detail.set_visible(true);
            }
        }
        clear(&self.activity);
        if !live {
            let known = feed.running.len() + feed.pending_prompts.len();
            let message = if known == 0 {
                "No live activity is available while offline.".to_string()
            } else {
                format!("Last sync showed {known} active item(s). Reconnect to refresh.")
            };
            append_message(&self.activity, &message);
        } else {
            for thread in feed.pending_prompts.iter().take(3) {
                append_thread(&self.activity, thread, true, self.actions.open_thread.clone());
            }
            for thread in feed.running.iter().take(3usize.saturating_sub(feed.pending_prompts.len())) {
                append_thread(&self.activity, thread, false, self.actions.open_thread.clone());
            }
            if feed.pending_prompts.is_empty() && feed.running.is_empty() {
                append_message(&self.activity, "No active work right now.");
            } else if feed.pending_prompts.len() + feed.running.len() > 3 {
                append_message(&self.activity, "More activity is available in the full chat.");
            }
        }

        let timestamp = if live { &feed.updated_at } else { &feed.written_at };
        self.freshness.set_text(&freshness(timestamp));
        self.freshness.set_visible(!timestamp.is_empty());
    }
}

fn clear(box_: &gtk::Box) {
    let mut child = box_.first_child();
    while let Some(widget) = child {
        child = widget.next_sibling();
        box_.remove(&widget);
    }
}

fn selected_window(feed: &Feed) -> Option<&UsageWindow> {
    feed.windows
        .iter()
        .filter(|window| window.instance_id == feed.selected_provider_id)
        .max_by(|a, b| a.used_percent.total_cmp(&b.used_percent))
}

fn append_message(box_: &gtk::Box, text: &str) {
    let label = gtk::Label::new(Some(text));
    label.add_css_class("caption");
    label.add_css_class("dim-label");
    label.set_xalign(0.0);
    label.set_wrap(true);
    box_.append(&label);
}

fn append_thread(box_: &gtk::Box, thread: &Thread, pending: bool, open_thread: Rc<dyn Fn(String)>) {
    let title = if thread.title.trim().is_empty() { "Untitled thread" } else { &thread.title };
    let detail = if pending {
        format!("Needs your approval · {} request(s)", thread.count.max(1))
    } else if thread.provider.trim().is_empty() {
        "Running".to_string()
    } else {
        format!("Running · {}", thread.provider)
    };
    let content = gtk::Box::new(gtk::Orientation::Vertical, 2);
    let primary = gtk::Label::new(Some(title));
    primary.set_xalign(0.0);
    primary.set_ellipsize(pango::EllipsizeMode::End);
    primary.add_css_class("t3-quick-thread-title");
    let secondary = gtk::Label::new(Some(&detail));
    secondary.set_xalign(0.0);
    secondary.set_ellipsize(pango::EllipsizeMode::End);
    secondary.add_css_class("caption");
    secondary.add_css_class(if pending { "warning" } else { "dim-label" });
    content.append(&primary);
    content.append(&secondary);
    let button = gtk::Button::builder().child(&content).hexpand(true).build();
    button.add_css_class("flat");
    button.add_css_class("t3-quick-thread");
    button.set_tooltip_text(Some("Open this thread in the full chat window"));
    let id = thread.id.clone();
    button.connect_clicked(move |_| open_thread(id.clone()));
    box_.append(&button);
}

fn reset_summary(iso: &str) -> String {
    if iso.is_empty() {
        return String::new();
    }
    let Ok(at) = glib::DateTime::from_iso8601(iso, Some(&glib::TimeZone::utc())) else {
        return String::new();
    };
    let Ok(now) = glib::DateTime::now_utc() else {
        return String::new();
    };
    let seconds = at.difference(&now).as_seconds();
    if seconds <= 0 {
        "Resets now".into()
    } else if seconds >= 86_400 {
        format!("Resets in {} d {} h", seconds / 86_400, (seconds % 86_400) / 3_600)
    } else if seconds >= 3_600 {
        format!("Resets in {} h {} min", seconds / 3_600, (seconds % 3_600) / 60)
    } else {
        format!("Resets in {} min", (seconds / 60).max(1))
    }
}

fn freshness(iso: &str) -> String {
    if iso.is_empty() {
        return "No status snapshot yet".into();
    }
    let Ok(at) = glib::DateTime::from_iso8601(iso, Some(&glib::TimeZone::utc())) else {
        return "Status time unavailable".into();
    };
    let Ok(now) = glib::DateTime::now_utc() else {
        return "Status time unavailable".into();
    };
    let seconds = now.difference(&at).as_seconds().max(0);
    if seconds < 60 {
        "Updated just now".into()
    } else if seconds < 3_600 {
        format!("Updated {} min ago", seconds / 60)
    } else {
        format!("Updated {}", at.to_local().ok().and_then(|local| local.format("%H:%M").ok()).unwrap_or_default())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compact_usage_only_shows_the_selected_provider_account() {
        let feed: Feed = serde_json::from_value(serde_json::json!({
            "selectedProviderId": "codex-work",
            "windows": [
                {"instanceId": "claude-personal", "provider": "Claude Personal", "usedPercent": 91.0},
                {"instanceId": "codex-work", "provider": "ChatGPT Work", "usedPercent": 52.0},
                {"instanceId": "codex-work", "provider": "ChatGPT Work", "usedPercent": 64.0, "resetsAt": null}
            ]
        }))
        .unwrap();

        let selected = selected_window(&feed).unwrap();
        assert_eq!(selected.provider, "ChatGPT Work");
        assert_eq!(selected.used_percent, 64.0);
    }

    #[test]
    fn compact_usage_shows_no_other_provider_when_selection_is_empty() {
        let feed: Feed = serde_json::from_value(serde_json::json!({
            "selectedProviderId": "",
            "windows": [
                {"instanceId": "claude-personal", "provider": "Claude Personal", "usedPercent": 91.0}
            ]
        }))
        .unwrap();

        assert!(selected_window(&feed).is_none());
    }
}
