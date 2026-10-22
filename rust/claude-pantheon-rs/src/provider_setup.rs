//! Native provider status and sign-in for the T3 Code server.
//!
//! Provider credentials stay on the server. The client only carries the short-lived
//! interaction replies needed by the server's provider-auth protocol.

use crate::chat::label;
use crate::t3::Rpc;
use crate::t3::model::{Provider, ServerConfig};
use futures_util::StreamExt;
use gtk::{gio, glib, pango, prelude::*};
use serde::Deserialize;
use serde_json::{Map, Value, json};
use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::rc::{Rc, Weak};

const FEATURED: [(&str, &str); 4] =
    [("claudeAgent", "Claude Code"), ("codex", "ChatGPT via Codex"), ("opencode", "OpenCode"), ("grok", "Grok Build")];

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default)]
struct AuthState {
    phase: String,
    #[serde(rename = "flowId")]
    flow_id: Option<String>,
    message: Option<String>,
    interaction: Option<Value>,
    methods: Vec<AuthMethod>,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default)]
struct AuthMethod {
    id: String,
    name: String,
    #[serde(rename = "accountEmail")]
    account_email: Option<String>,
    description: Option<String>,
}

#[derive(Clone)]
pub struct ProviderManager {
    pub window: gtk::Window,
    rows: gtk::Box,
    status: gtk::Label,
    refresh_button: gtk::Button,
    rpc: Rpc,
    providers: Rc<RefCell<Vec<Provider>>>,
    on_changed: Rc<dyn Fn(Vec<Provider>)>,
    auth_window: Rc<RefCell<Option<Rc<AuthWindow>>>>,
}

impl ProviderManager {
    pub fn open(
        parent: &gtk::ApplicationWindow,
        rpc: Rpc,
        providers: Vec<Provider>,
        on_changed: Rc<dyn Fn(Vec<Provider>)>,
    ) -> Rc<Self> {
        let window = gtk::Window::builder()
            .transient_for(parent)
            .title("AI Providers")
            .default_width(640)
            .default_height(560)
            .build();
        let header = gtk::HeaderBar::builder().show_title_buttons(true).build();
        header.add_css_class(granite::STYLE_CLASS_FLAT);
        let refresh_button = gtk::Button::with_label("Refresh");
        refresh_button.set_tooltip_text(Some("Refresh provider availability and sign-in status"));
        header.pack_end(&refresh_button);
        window.set_titlebar(Some(&header));

        let root = gtk::Box::new(gtk::Orientation::Vertical, 12);
        root.set_margin_top(18);
        root.set_margin_bottom(18);
        root.set_margin_start(22);
        root.set_margin_end(22);
        let title = label("AI Providers", &["title-2"]);
        root.append(&title);
        let intro = label(
            "Connect the coding assistants configured on your T3 Code server. ChatGPT uses the Codex provider; provider credentials stay on the server.",
            &["dim-label"],
        );
        intro.set_wrap(true);
        intro.set_ellipsize(pango::EllipsizeMode::None);
        root.append(&intro);

        let rows = gtk::Box::new(gtk::Orientation::Vertical, 8);
        let scroller = gtk::ScrolledWindow::builder().child(&rows).vexpand(true).build();
        root.append(&scroller);
        let status = label("", &["caption", "dim-label"]);
        status.set_wrap(true);
        status.set_ellipsize(pango::EllipsizeMode::None);
        status.set_xalign(0.0);
        root.append(&status);
        window.set_child(Some(&root));

        let manager = Rc::new(Self {
            window,
            rows,
            status,
            refresh_button,
            rpc,
            providers: Rc::new(RefCell::new(providers)),
            on_changed,
            auth_window: Rc::new(RefCell::new(None)),
        });
        manager.render();

        let weak = Rc::downgrade(&manager);
        manager.refresh_button.connect_clicked(move |_| {
            if let Some(manager) = weak.upgrade() {
                manager.refresh();
            }
        });
        let weak = Rc::downgrade(&manager);
        manager.window.connect_close_request(move |_| {
            if let Some(manager) = weak.upgrade() {
                let auth = { manager.auth_window.borrow_mut().take() };
                if let Some(auth) = auth {
                    auth.window.close();
                }
            }
            glib::Propagation::Proceed
        });
        manager.window.present();
        manager
    }

    fn render(self: &Rc<Self>) {
        while let Some(child) = self.rows.first_child() {
            self.rows.remove(&child);
        }

        let providers = self.providers.borrow().clone();
        let mut shown = HashMap::<String, usize>::new();
        for (driver, title) in FEATURED {
            let matching: Vec<Provider> = providers.iter().filter(|p| p.driver == driver).cloned().collect();
            if matching.is_empty() {
                self.rows.append(&self.unconfigured_card(title));
            } else {
                for provider in matching {
                    let index = shown.entry(driver.to_string()).or_default();
                    self.rows.append(&self.provider_card(&provider, title, *index > 0));
                    *index += 1;
                }
            }
        }

        for provider in providers.iter().filter(|p| !FEATURED.iter().any(|(driver, _)| *driver == p.driver)) {
            self.rows.append(&self.provider_card(provider, &provider.name(), false));
        }

        if providers.is_empty() {
            self.status.set_text(
                "No provider instances were returned. Configure providers on the T3 Code server, then refresh.",
            );
        } else {
            let ready = providers.iter().filter(|p| p.ready()).count();
            self.status.set_text(&format!("{ready} of {} provider instances ready", providers.len()));
        }
    }

    fn unconfigured_card(&self, title: &str) -> gtk::Box {
        let card = gtk::Box::new(gtk::Orientation::Horizontal, 12);
        card.add_css_class("card");
        card.set_margin_start(2);
        card.set_margin_end(2);
        card.set_margin_top(2);
        card.set_margin_bottom(2);
        let copy = gtk::Box::new(gtk::Orientation::Vertical, 4);
        copy.set_margin_top(10);
        copy.set_margin_bottom(10);
        copy.set_margin_start(10);
        copy.set_margin_end(4);
        copy.set_hexpand(true);
        let heading = label(title, &["heading"]);
        let detail = label(
            "Not configured on this T3 Code server. Add or enable it there, then refresh.",
            &["caption", "dim-label"],
        );
        detail.set_wrap(true);
        detail.set_ellipsize(pango::EllipsizeMode::None);
        copy.append(&heading);
        copy.append(&detail);
        let state = label("Not configured", &["caption", "dim-label"]);
        state.set_valign(gtk::Align::Center);
        card.append(&copy);
        card.append(&state);
        card
    }

    fn provider_card(self: &Rc<Self>, provider: &Provider, title: &str, extra_instance: bool) -> gtk::Box {
        let card = gtk::Box::new(gtk::Orientation::Horizontal, 12);
        card.add_css_class("card");
        card.set_margin_start(2);
        card.set_margin_end(2);
        card.set_margin_top(2);
        card.set_margin_bottom(2);
        let copy = gtk::Box::new(gtk::Orientation::Vertical, 4);
        copy.set_margin_top(10);
        copy.set_margin_bottom(10);
        copy.set_margin_start(10);
        copy.set_margin_end(4);
        copy.set_hexpand(true);
        let display_title = if extra_instance { format!("{title} · {}", provider.name()) } else { title.to_string() };
        let heading = label(&display_title, &["heading"]);
        heading.set_wrap(true);
        heading.set_ellipsize(pango::EllipsizeMode::None);
        let state = provider_state(provider);
        let status = label(&state, &["caption"]);
        status.set_wrap(true);
        status.set_ellipsize(pango::EllipsizeMode::None);
        copy.append(&heading);
        copy.append(&status);
        if let Some(message) = provider.message.as_deref().filter(|m| !m.trim().is_empty()) {
            let detail = label(message, &["caption", "dim-label"]);
            detail.set_wrap(true);
            detail.set_ellipsize(pango::EllipsizeMode::None);
            copy.append(&detail);
        }
        card.append(&copy);

        let action_label = if provider.ready() { "Sign out…" } else { "Sign in…" };
        let action = gtk::Button::with_label(action_label);
        action.set_valign(gtk::Align::Center);
        action.set_sensitive(
            provider.enabled && provider.installed && provider.availability.as_deref() != Some("unavailable"),
        );
        action.set_tooltip_text(Some(if provider.ready() {
            "Sign out on the T3 Code server"
        } else {
            "Start provider sign-in on the T3 Code server"
        }));
        let weak = Rc::downgrade(self);
        let provider = provider.clone();
        action.connect_clicked(move |_| {
            if let Some(manager) = weak.upgrade() {
                if provider.ready() {
                    manager.confirm_sign_out(provider.clone());
                } else {
                    manager.start_sign_in(provider.clone());
                }
            }
        });
        card.append(&action);
        card
    }

    fn refresh(self: &Rc<Self>) {
        self.refresh_button.set_sensitive(false);
        self.status.set_text("Refreshing provider availability…");
        let manager = self.clone();
        glib::spawn_future_local(async move {
            let refresh_error =
                manager.rpc.call("server.refreshProviders", json!({"fresh": true})).await.err().map(|e| e.to_string());
            match manager.rpc.call("server.getConfig", json!({})).await {
                Ok(value) => match serde_json::from_value::<ServerConfig>(value) {
                    Ok(config) => {
                        *manager.providers.borrow_mut() = config.providers;
                        manager.render();
                        (manager.on_changed)(manager.providers.borrow().clone());
                        if let Some(error) = refresh_error {
                            manager.status.set_text(&format!("Could not refresh provider status: {error}"));
                        }
                    }
                    Err(error) => manager.status.set_text(&format!("Could not read provider status: {error}")),
                },
                Err(error) => manager.status.set_text(&format!("Could not load provider status: {error}")),
            }
            manager.refresh_button.set_sensitive(true);
        });
    }

    fn confirm_sign_out(self: &Rc<Self>, provider: Provider) {
        let dialog = gtk::AlertDialog::builder()
            .message(format!("Sign out of {}?", provider.name()))
            .detail("The T3 Code server will stop active sessions for this provider and clear its sign-in state.")
            .buttons(["Cancel", "Sign out"])
            .default_button(1)
            .cancel_button(0)
            .build();
        let weak = Rc::downgrade(self);
        dialog.choose(Some(&self.window), gio::Cancellable::NONE, move |response| {
            if response != Ok(1) {
                return;
            }
            if let Some(manager) = weak.upgrade() {
                manager.sign_out(provider.clone());
            }
        });
    }

    fn sign_out(self: &Rc<Self>, provider: Provider) {
        self.status.set_text(&format!("Signing out of {}…", provider.name()));
        let manager = self.clone();
        glib::spawn_future_local(async move {
            match manager.rpc.call("provider.auth.logout", json!({"instanceId": provider.instance_id})).await {
                Ok(_) => manager.refresh(),
                Err(error) => manager.status.set_text(&format!("Could not sign out: {error}")),
            }
        });
    }

    fn start_sign_in(self: &Rc<Self>, provider: Provider) {
        if self.auth_window.borrow().is_some() {
            if let Some(auth) = self.auth_window.borrow().as_ref() {
                auth.window.present();
            }
            return;
        }
        let weak_manager: Weak<Self> = Rc::downgrade(self);
        let weak_for_success = weak_manager.clone();
        let weak_for_close = weak_manager.clone();
        let auth = AuthWindow::open(
            &self.window,
            self.rpc.clone(),
            provider,
            Rc::new(move || {
                if let Some(manager) = weak_for_success.upgrade() {
                    manager.refresh();
                }
            }),
            Rc::new(move || {
                // The manager owns the dialog while it is visible. Closing it drops that reference.
                if let Some(manager) = weak_for_close.upgrade() {
                    manager.auth_window.borrow_mut().take();
                }
            }),
        );
        *self.auth_window.borrow_mut() = Some(auth);
    }
}

fn provider_state(provider: &Provider) -> String {
    if provider.ready() {
        "Connected".into()
    } else if !provider.enabled {
        "Disabled on the T3 Code server".into()
    } else if !provider.installed {
        "Not installed on the T3 Code server".into()
    } else if provider.availability.as_deref() == Some("unavailable") {
        "Unavailable on the T3 Code server".into()
    } else {
        match provider.auth_text().as_str() {
            "expired" | "unauthenticated" | "signed-out" | "signedOut" => "Sign-in required".into(),
            "error" | "failed" => "Sign-in needs attention".into(),
            _ => "Not ready".into(),
        }
    }
}

struct AuthWindow {
    window: gtk::Window,
    status: gtk::Label,
    method_row: gtk::Box,
    interaction_box: gtk::Box,
    method_picker: gtk::DropDown,
    start_button: gtk::Button,
    rpc: Rpc,
    provider: Provider,
    methods: RefCell<Vec<AuthMethod>>,
    flow_id: RefCell<Option<String>>,
    subscription_id: RefCell<Option<String>>,
    active: Cell<bool>,
    started: Cell<bool>,
    succeeded: Cell<bool>,
    closed: Cell<bool>,
    interaction_id: RefCell<Option<String>>,
    interaction_type: RefCell<Option<String>>,
    terminal_output: RefCell<Option<gtk::TextView>>,
    cancel_button: gtk::Button,
    on_succeeded: Rc<dyn Fn()>,
    on_closed: Rc<dyn Fn()>,
}

impl AuthWindow {
    fn open(
        parent: &gtk::Window,
        rpc: Rpc,
        provider: Provider,
        on_succeeded: Rc<dyn Fn()>,
        on_closed: Rc<dyn Fn()>,
    ) -> Rc<Self> {
        let title = provider_title(&provider);
        let window = gtk::Window::builder()
            .transient_for(parent)
            .modal(true)
            .title(format!("Sign in to {title}"))
            .default_width(520)
            .default_height(390)
            .build();
        let header = gtk::HeaderBar::builder().show_title_buttons(true).build();
        header.add_css_class(granite::STYLE_CLASS_FLAT);
        window.set_titlebar(Some(&header));

        let root = gtk::Box::new(gtk::Orientation::Vertical, 12);
        root.set_margin_top(18);
        root.set_margin_bottom(18);
        root.set_margin_start(20);
        root.set_margin_end(20);
        let status = label("Starting sign-in…", &["dim-label"]);
        status.set_wrap(true);
        status.set_ellipsize(pango::EllipsizeMode::None);
        status.set_xalign(0.0);
        root.append(&status);
        let method_row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        let method_label = label("Sign-in method", &[]);
        let method_picker = gtk::DropDown::from_strings(&[]);
        method_picker.set_hexpand(true);
        method_picker.update_property(&[gtk::accessible::Property::Label("Sign-in method")]);
        method_row.append(&method_label);
        method_row.append(&method_picker);
        method_row.set_visible(false);
        root.append(&method_row);
        let interaction_box = gtk::Box::new(gtk::Orientation::Vertical, 10);
        root.append(&interaction_box);
        let buttons = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        buttons.set_halign(gtk::Align::End);
        let start_button = gtk::Button::with_label("Loading sign-in methods…");
        start_button.set_sensitive(false);
        buttons.append(&start_button);
        let cancel = gtk::Button::with_label("Cancel");
        buttons.append(&cancel);
        root.append(&buttons);
        window.set_child(Some(&root));

        let auth = Rc::new(Self {
            window,
            status,
            method_row,
            interaction_box,
            method_picker,
            start_button: start_button.clone(),
            rpc,
            provider,
            methods: RefCell::new(Vec::new()),
            flow_id: RefCell::new(None),
            subscription_id: RefCell::new(None),
            active: Cell::new(false),
            started: Cell::new(false),
            succeeded: Cell::new(false),
            closed: Cell::new(false),
            interaction_id: RefCell::new(None),
            interaction_type: RefCell::new(None),
            terminal_output: RefCell::new(None),
            cancel_button: cancel.clone(),
            on_succeeded,
            on_closed,
        });

        let weak = Rc::downgrade(&auth);
        start_button.connect_clicked(move |_| {
            if let Some(auth) = weak.upgrade() {
                auth.begin_sign_in();
            }
        });
        let weak = Rc::downgrade(&auth);
        cancel.connect_clicked(move |_| {
            if let Some(auth) = weak.upgrade() {
                auth.window.close();
            }
        });
        let weak = Rc::downgrade(&auth);
        auth.window.connect_close_request(move |_| {
            if let Some(auth) = weak.upgrade() {
                auth.close_flow();
            }
            glib::Propagation::Proceed
        });
        auth.window.present();
        auth.subscribe();
        auth
    }

    fn subscribe(self: &Rc<Self>) {
        let auth = self.clone();
        let (subscription_id, mut stream) =
            auth.rpc.subscribe("provider.auth.subscribe", json!({"instanceId": auth.provider.instance_id}));
        *auth.subscription_id.borrow_mut() = Some(subscription_id);
        glib::spawn_future_local(async move {
            while let Some(item) = stream.next().await {
                if auth.closed.get() {
                    break;
                }
                match item {
                    Ok(value) => match serde_json::from_value::<AuthState>(value) {
                        Ok(state) if auth.started.get() => auth.render_state(&state),
                        Ok(state) => auth.render_methods(&state),
                        Err(error) => auth.status.set_text(&format!("Could not read sign-in methods: {error}")),
                    },
                    Err(error) => {
                        auth.active.set(false);
                        auth.start_button.set_sensitive(false);
                        auth.status.set_text(&format!("Could not load sign-in methods: {error}"));
                        break;
                    }
                }
            }
        });
    }

    fn render_methods(&self, state: &AuthState) {
        *self.methods.borrow_mut() = state.methods.clone();
        let names: Vec<String> = state
            .methods
            .iter()
            .map(|method| {
                let account = method.account_email.as_deref().map(|email| format!(" — {email}")).unwrap_or_default();
                let description = method.description.as_deref().map(|text| format!(" · {text}")).unwrap_or_default();
                format!("{}{account}{description}", method.name)
            })
            .collect();
        let refs: Vec<&str> = names.iter().map(String::as_str).collect();
        self.method_picker.set_model(Some(&gtk::StringList::new(&refs)));
        self.method_row.set_visible(names.len() > 1);

        let busy = matches!(state.phase.as_str(), "starting" | "waiting" | "verifying");
        self.start_button.set_sensitive(!busy && !state.methods.is_empty());
        self.start_button.set_label(if state.methods.is_empty() { "No sign-in method" } else { "Continue" });
        if let Some(message) = state.message.as_deref().filter(|m| !m.is_empty()) {
            self.status.set_text(message);
        } else if busy {
            self.status.set_text("Sign-in is already in progress in this server session.");
        } else if state.methods.len() == 1 {
            self.status.set_text(&format!("Sign in with {}.", state.methods[0].name));
        } else if state.methods.is_empty() {
            self.status.set_text("No sign-in methods are available from the T3 Code server yet.");
        } else {
            self.status.set_text("Choose a sign-in method to continue.");
        }
    }

    fn begin_sign_in(self: &Rc<Self>) {
        if self.started.replace(true) {
            return;
        }
        self.start_button.set_sensitive(false);
        self.start_button.set_label("Starting…");
        self.method_picker.set_sensitive(false);
        self.status.set_text("Starting sign-in…");

        let selected = self.methods.borrow().get(self.method_picker.selected() as usize).cloned();
        let Some(method) = selected.filter(|method| !method.id.is_empty()) else {
            self.started.set(false);
            self.start_button.set_label("No sign-in method");
            self.status.set_text("The T3 Code server has not provided a sign-in method.");
            return;
        };
        let auth = self.clone();
        glib::spawn_future_local(async move {
            let mut input = json!({"instanceId": auth.provider.instance_id, "callbackMode": "server"});
            input["methodId"] = json!(method.id);
            let value = match auth.rpc.call("provider.auth.start", input).await {
                Ok(value) => value,
                Err(error) => {
                    auth.started.set(false);
                    auth.method_picker.set_sensitive(true);
                    auth.start_button.set_label("Try again");
                    auth.start_button.set_sensitive(true);
                    auth.status.set_text(&format!("Could not start sign-in: {error}"));
                    return;
                }
            };
            let state = match serde_json::from_value::<AuthState>(value) {
                Ok(state) => state,
                Err(error) => {
                    auth.started.set(false);
                    auth.method_picker.set_sensitive(true);
                    auth.start_button.set_label("Try again");
                    auth.start_button.set_sensitive(true);
                    auth.status.set_text(&format!("The server returned an unreadable sign-in state: {error}"));
                    return;
                }
            };
            *auth.flow_id.borrow_mut() = state.flow_id.clone();
            auth.active
                .set(state.flow_id.is_some() && !matches!(state.phase.as_str(), "succeeded" | "failed" | "cancelled"));
            if auth.closed.get() {
                auth.cancel_remote();
                return;
            }
            auth.render_state(&state);
        });
    }

    fn render_state(self: &Rc<Self>, state: &AuthState) {
        if let Some(flow_id) = state.flow_id.as_deref() {
            *self.flow_id.borrow_mut() = Some(flow_id.to_string());
        }
        let label_text = state.message.as_deref().unwrap_or_else(|| match state.phase.as_str() {
            "starting" => "Starting sign-in…",
            "waiting" => "Complete the sign-in step to continue.",
            "verifying" => "Checking provider sign-in…",
            "succeeded" => "Sign-in complete.",
            "failed" => "Sign-in failed.",
            "cancelled" => "Sign-in cancelled.",
            _ => "Waiting for the T3 Code server…",
        });
        self.status.set_text(label_text);

        let finished = matches!(state.phase.as_str(), "succeeded" | "failed" | "cancelled");
        self.active.set(!finished && state.flow_id.is_some());
        self.method_row.set_visible(false);
        self.start_button.set_visible(false);
        self.cancel_button.set_label(if finished { "Close" } else { "Cancel" });
        if state.phase == "succeeded" && !self.succeeded.replace(true) {
            (self.on_succeeded)();
        }

        let Some(interaction) = state.interaction.as_ref() else {
            *self.interaction_id.borrow_mut() = None;
            *self.interaction_type.borrow_mut() = None;
            *self.terminal_output.borrow_mut() = None;
            while let Some(child) = self.interaction_box.first_child() {
                self.interaction_box.remove(&child);
            }
            return;
        };
        let id = interaction.get("id").and_then(Value::as_str).unwrap_or("").to_string();
        let kind = interaction.get("type").and_then(Value::as_str).unwrap_or("").to_string();
        if id.is_empty() || kind.is_empty() {
            self.status.set_text("The server sent a sign-in step this client cannot read.");
            return;
        }

        if self.interaction_id.borrow().as_deref() == Some(id.as_str())
            && self.interaction_type.borrow().as_deref() == Some(kind.as_str())
        {
            if kind == "terminal"
                && let Some(view) = self.terminal_output.borrow().as_ref()
            {
                let output = interaction.get("output").and_then(Value::as_str).unwrap_or("");
                view.buffer().set_text(output);
            }
            return;
        }
        *self.interaction_id.borrow_mut() = Some(id.clone());
        *self.interaction_type.borrow_mut() = Some(kind.clone());
        *self.terminal_output.borrow_mut() = None;
        while let Some(child) = self.interaction_box.first_child() {
            self.interaction_box.remove(&child);
        }

        match kind.as_str() {
            "browser" => self.render_browser(&id, interaction),
            "deviceCode" => self.render_device_code(&id, interaction),
            "terminal" => self.render_terminal(&id, interaction),
            "credentials" => self.render_credentials(&id, interaction),
            _ => {
                let explanation = label(
                    "This sign-in step is not supported by this client version. Cancel and update the client.",
                    &["dim-label"],
                );
                explanation.set_wrap(true);
                explanation.set_ellipsize(pango::EllipsizeMode::None);
                self.interaction_box.append(&explanation);
            }
        }
    }

    fn render_browser(self: &Rc<Self>, interaction_id: &str, interaction: &Value) {
        let needs_consent = interaction.get("requiresConsent").and_then(Value::as_bool).unwrap_or(false);
        let instruction = if needs_consent {
            "The provider requests permission to continue in your browser."
        } else {
            "Continue in your browser to finish signing in."
        };
        let text = label(instruction, &["dim-label"]);
        text.set_wrap(true);
        text.set_ellipsize(pango::EllipsizeMode::None);
        self.interaction_box.append(&text);
        let button =
            gtk::Button::with_label(if needs_consent { "Open browser and continue" } else { "Open sign-in page" });
        button.set_halign(gtk::Align::Start);
        let url = interaction.get("url").and_then(Value::as_str).unwrap_or("").to_string();
        let interaction_id = interaction_id.to_string();
        let weak = Rc::downgrade(self);
        button.connect_clicked(move |_| {
            let Some(auth) = weak.upgrade() else { return };
            if auth.open_uri(&url) && needs_consent {
                auth.respond(&interaction_id, json!({"type": "browser", "action": "accept"}));
            }
        });
        self.interaction_box.append(&button);
    }

    fn render_device_code(self: &Rc<Self>, _interaction_id: &str, interaction: &Value) {
        let instruction = label("Open the provider page and enter this one-time code.", &["dim-label"]);
        instruction.set_wrap(true);
        instruction.set_ellipsize(pango::EllipsizeMode::None);
        self.interaction_box.append(&instruction);
        let code = interaction.get("userCode").and_then(Value::as_str).unwrap_or("").to_string();
        let code_label = label(&code, &["title-2", "monospace"]);
        code_label.set_selectable(true);
        self.interaction_box.append(&code_label);

        let actions = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        let copy = gtk::Button::with_label("Copy code");
        let weak = Rc::downgrade(self);
        let code_to_copy = code.clone();
        copy.connect_clicked(move |_| {
            if let Some(auth) = weak.upgrade() {
                auth.window.clipboard().set_text(&code_to_copy);
                auth.status.set_text("Sign-in code copied. Complete the provider step in your browser.");
            }
        });
        actions.append(&copy);
        let open = gtk::Button::with_label("Open sign-in page");
        let url = interaction.get("url").and_then(Value::as_str).unwrap_or("").to_string();
        let weak = Rc::downgrade(self);
        open.connect_clicked(move |_| {
            if let Some(auth) = weak.upgrade() {
                auth.open_uri(&url);
            }
        });
        actions.append(&open);
        self.interaction_box.append(&actions);
    }

    fn render_terminal(self: &Rc<Self>, interaction_id: &str, interaction: &Value) {
        let output = gtk::TextView::new();
        output.set_editable(false);
        output.set_cursor_visible(false);
        output.set_monospace(true);
        output.set_wrap_mode(gtk::WrapMode::WordChar);
        output.buffer().set_text(interaction.get("output").and_then(Value::as_str).unwrap_or(""));
        let scroll = gtk::ScrolledWindow::builder().child(&output).min_content_height(150).build();
        self.interaction_box.append(&scroll);
        *self.terminal_output.borrow_mut() = Some(output);

        let form = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        let entry =
            gtk::Entry::builder().placeholder_text("Enter the requested code or response").hexpand(true).build();
        entry.update_property(&[gtk::accessible::Property::Label("Provider sign-in response")]);
        let send = gtk::Button::with_label("Send");
        form.append(&entry);
        form.append(&send);
        self.interaction_box.append(&form);
        let id = interaction_id.to_string();
        let weak = Rc::downgrade(self);
        let entry_for_send = entry.clone();
        send.connect_clicked(move |_| {
            let Some(auth) = weak.upgrade() else { return };
            let response = entry_for_send.text().to_string();
            entry_for_send.set_text("");
            auth.respond(&id, json!({"type": "terminal", "data": response, "size": {"cols": 80, "rows": 24}}));
        });
        let id = interaction_id.to_string();
        let weak = Rc::downgrade(self);
        entry.connect_activate(move |entry| {
            let Some(auth) = weak.upgrade() else { return };
            let response = entry.text().to_string();
            entry.set_text("");
            auth.respond(&id, json!({"type": "terminal", "data": response, "size": {"cols": 80, "rows": 24}}));
        });
    }

    fn render_credentials(self: &Rc<Self>, interaction_id: &str, interaction: &Value) {
        let instructions = label(
            "Enter the requested provider credentials. Secret fields are masked and are sent only to the T3 Code server.",
            &["dim-label"],
        );
        instructions.set_wrap(true);
        instructions.set_ellipsize(pango::EllipsizeMode::None);
        self.interaction_box.append(&instructions);
        let form = gtk::Box::new(gtk::Orientation::Vertical, 8);
        let mut entries = Vec::<(String, gtk::Entry)>::new();
        if let Some(fields) = interaction.get("fields").and_then(Value::as_array) {
            for field in fields {
                let id = field.get("name").and_then(Value::as_str).unwrap_or("").to_string();
                let name = field.get("label").and_then(Value::as_str).unwrap_or(&id);
                if id.is_empty() {
                    continue;
                }
                let entry = gtk::Entry::new();
                entry.set_placeholder_text(Some(name));
                entry.set_visibility(!field.get("secret").and_then(Value::as_bool).unwrap_or(false));
                entry.update_property(&[gtk::accessible::Property::Label(name)]);
                form.append(&entry);
                entries.push((id, entry));
            }
        }
        self.interaction_box.append(&form);
        let submit = gtk::Button::with_label("Continue");
        submit.set_halign(gtk::Align::Start);
        let id = interaction_id.to_string();
        let weak = Rc::downgrade(self);
        submit.connect_clicked(move |_| {
            let Some(auth) = weak.upgrade() else { return };
            let mut values = Map::new();
            for (name, entry) in &entries {
                values.insert(name.clone(), Value::String(entry.text().to_string()));
                entry.set_text("");
            }
            auth.respond(&id, json!({"type": "credentials", "values": values}));
        });
        self.interaction_box.append(&submit);
    }

    fn open_uri(&self, uri: &str) -> bool {
        let valid_scheme = uri.split_once("://").is_some_and(|(scheme, host)| {
            matches!(scheme.to_ascii_lowercase().as_str(), "http" | "https") && !host.is_empty()
        });
        if !valid_scheme {
            self.status.set_text("The T3 Code server provided an invalid sign-in URL.");
            return false;
        }
        match gio::AppInfo::launch_default_for_uri(uri, None::<&gio::AppLaunchContext>) {
            Ok(()) => {
                self.status.set_text("Sign-in page opened in your browser.");
                true
            }
            Err(error) => {
                self.status.set_text(&format!("Could not open the browser: {error}"));
                false
            }
        }
    }

    fn respond(self: &Rc<Self>, interaction_id: &str, response: Value) {
        let Some(flow_id) = self.flow_id.borrow().clone() else {
            self.status.set_text("The sign-in flow is no longer active. Start again.");
            return;
        };
        self.status.set_text("Sending sign-in response…");
        let auth = self.clone();
        let interaction_id = interaction_id.to_string();
        glib::spawn_future_local(async move {
            match auth
                .rpc
                .call(
                    "provider.auth.respond",
                    json!({
                        "instanceId": auth.provider.instance_id,
                        "flowId": flow_id,
                        "interactionId": interaction_id,
                        "response": response,
                    }),
                )
                .await
            {
                Ok(value) => match serde_json::from_value::<AuthState>(value) {
                    Ok(state) => auth.render_state(&state),
                    Err(error) => auth.status.set_text(&format!("Could not read sign-in response: {error}")),
                },
                Err(error) => auth.status.set_text(&format!("Could not send sign-in response: {error}")),
            }
        });
    }

    fn close_flow(&self) {
        if self.closed.replace(true) {
            return;
        }
        if let Some(id) = self.subscription_id.borrow_mut().take() {
            self.rpc.interrupt(&id);
        }
        if self.active.get() {
            self.cancel_remote();
        }
        (self.on_closed)();
    }

    fn cancel_remote(&self) {
        let Some(flow_id) = self.flow_id.borrow_mut().take() else { return };
        self.active.set(false);
        let rpc = self.rpc.clone();
        let instance_id = self.provider.instance_id.clone();
        glib::spawn_future_local(async move {
            let _ = rpc.call("provider.auth.cancel", json!({"instanceId": instance_id, "flowId": flow_id})).await;
        });
    }
}

fn provider_title(provider: &Provider) -> String {
    FEATURED
        .iter()
        .find(|(driver, _)| *driver == provider.driver)
        .map(|(_, title)| (*title).to_string())
        .unwrap_or_else(|| provider.name())
}
