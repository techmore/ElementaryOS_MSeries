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

#[derive(Clone, Copy, Eq, PartialEq)]
enum LocalAcpPreset {
    Generic,
    DeepSeek,
    MSeries,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct AcpRegistryAgent {
    id: String,
    name: String,
    version: String,
    description: String,
    license: Option<String>,
    website: Option<String>,
    repository: Option<String>,
}

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
    registry_query: gtk::SearchEntry,
    registry_results: gtk::Box,
    registry_status: gtk::Label,
    registry_loaded: Cell<bool>,
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

        let registry = gtk::Expander::new(Some("Add an ACP provider"));
        let registry_content = gtk::Box::new(gtk::Orientation::Vertical, 7);
        let registry_intro = label(
            "Find an agent in the ACP Registry or connect a local ACP command such as DeepSeek Harness or MSeries Assistant. Registry agents are third-party code; review their source and license. The T3 server runs the agent and keeps its credentials.",
            &["caption", "dim-label"],
        );
        registry_intro.set_wrap(true);
        registry_intro.set_ellipsize(pango::EllipsizeMode::None);
        registry_content.append(&registry_intro);
        let registry_controls = gtk::Box::new(gtk::Orientation::Horizontal, 6);
        let registry_query = gtk::SearchEntry::builder().placeholder_text("Search ACP Registry").hexpand(true).build();
        let registry_search = gtk::Button::with_label("Search");
        registry_controls.append(&registry_query);
        registry_controls.append(&registry_search);
        registry_content.append(&registry_controls);

        let local_controls = gtk::Box::new(gtk::Orientation::Horizontal, 6);
        let local_acp = gtk::Button::with_label("Add local command…");
        let deepseek_acp = gtk::Button::with_label("DeepSeek Harness…");
        deepseek_acp.set_tooltip_text(Some("Add DeepSeek Harness as a local ACP command on the T3 server"));
        let mseries_acp = gtk::Button::with_label("MSeries Assistant…");
        mseries_acp.set_tooltip_text(Some("Connect the paired server to its existing MSeries local assistant"));
        local_controls.append(&local_acp);
        local_controls.append(&deepseek_acp);
        local_controls.append(&mseries_acp);
        registry_content.append(&local_controls);
        let registry_status = label("Expand to browse available ACP agents.", &["caption", "dim-label"]);
        registry_status.set_wrap(true);
        registry_status.set_ellipsize(pango::EllipsizeMode::None);
        registry_content.append(&registry_status);
        let registry_results = gtk::Box::new(gtk::Orientation::Vertical, 5);
        let registry_scroll = gtk::ScrolledWindow::builder()
            .child(&registry_results)
            .max_content_height(180)
            .propagate_natural_height(true)
            .build();
        registry_content.append(&registry_scroll);
        registry.set_child(Some(&registry_content));
        root.append(&registry);

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
            registry_query,
            registry_results,
            registry_status,
            registry_loaded: Cell::new(false),
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
        registry_search.connect_clicked(move |_| {
            if let Some(manager) = weak.upgrade() {
                manager.search_registry(manager.registry_query.text().to_string());
            }
        });
        let weak = Rc::downgrade(&manager);
        manager.registry_query.connect_activate(move |entry| {
            if let Some(manager) = weak.upgrade() {
                manager.search_registry(entry.text().to_string());
            }
        });
        let weak = Rc::downgrade(&manager);
        registry.connect_expanded_notify(move |expander| {
            if expander.is_expanded()
                && let Some(manager) = weak.upgrade()
                && !manager.registry_loaded.get()
            {
                manager.search_registry(String::new());
            }
        });
        let weak = Rc::downgrade(&manager);
        local_acp.connect_clicked(move |_| {
            if let Some(manager) = weak.upgrade() {
                manager.add_local_acp_dialog(LocalAcpPreset::Generic);
            }
        });
        let weak = Rc::downgrade(&manager);
        deepseek_acp.connect_clicked(move |_| {
            if let Some(manager) = weak.upgrade() {
                manager.add_local_acp_dialog(LocalAcpPreset::DeepSeek);
            }
        });
        let weak = Rc::downgrade(&manager);
        mseries_acp.connect_clicked(move |_| {
            if let Some(manager) = weak.upgrade() {
                manager.add_local_acp_dialog(LocalAcpPreset::MSeries);
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

    fn search_registry(self: &Rc<Self>, query: String) {
        if query.trim().chars().count() > 120 {
            self.registry_status.set_text("Search terms can be up to 120 characters.");
            return;
        }
        self.registry_loaded.set(true);
        self.registry_status.set_text("Searching the ACP Registry on the T3 server…");
        clear_box(&self.registry_results);
        let manager = self.clone();
        glib::spawn_future_local(async move {
            match manager.rpc.call("server.searchAcpRegistry", json!({"query": query.trim(), "limit": 128})).await {
                Ok(value) => {
                    let agents = value
                        .get("agents")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                        .filter_map(|agent| serde_json::from_value::<AcpRegistryAgent>(agent.clone()).ok())
                        .filter(|agent| !agent.id.is_empty() && !agent.name.is_empty())
                        .collect::<Vec<_>>();
                    let message = if agents.is_empty() {
                        "No compatible ACP agents found. Try another search or add a local command.".into()
                    } else {
                        format!("{} compatible agent(s) found.", agents.len())
                    };
                    manager.registry_status.set_text(&message);
                    for agent in agents {
                        manager.render_registry_agent(agent);
                    }
                }
                Err(error) => {
                    manager.registry_status.set_text(&format!("ACP Registry search failed: {}", error.message()))
                }
            }
        });
    }

    fn render_registry_agent(self: &Rc<Self>, agent: AcpRegistryAgent) {
        let row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        row.add_css_class("provider-registry-row");
        let copy = gtk::Box::new(gtk::Orientation::Vertical, 2);
        copy.set_hexpand(true);
        let title = label(&agent.name, &[]);
        title.set_xalign(0.0);
        title.set_ellipsize(pango::EllipsizeMode::End);
        let mut metadata = vec![format!("v{}", agent.version)];
        if let Some(license) = agent.license.as_deref().filter(|value| !value.trim().is_empty()) {
            metadata.push(license.to_string());
        }
        let metadata = metadata.join(" · ");
        let detail = if agent.description.trim().is_empty() {
            format!("ACP agent · {metadata}")
        } else {
            format!("{} · {metadata}", agent.description)
        };
        let description = label(&detail, &["caption", "dim-label"]);
        description.set_xalign(0.0);
        description.set_wrap(true);
        description.set_ellipsize(pango::EllipsizeMode::End);
        copy.append(&title);
        copy.append(&description);
        row.append(&copy);

        let added = self.providers.borrow().iter().any(|provider| {
            provider.driver == "acpRegistry"
                && provider.display_name.as_deref().is_some_and(|name| name.eq_ignore_ascii_case(&agent.name))
        });
        let add = gtk::Button::with_label(if added { "Added" } else { "Add" });
        add.set_sensitive(!added);
        if let Some(url) = agent.website.as_ref().or(agent.repository.as_ref()) {
            add.set_tooltip_text(Some(&format!("Add {} · {}", agent.name, url)));
        }
        if let Some(url) = agent.repository.as_ref().or(agent.website.as_ref()).filter(|url| safe_registry_url(url)) {
            let source = gtk::LinkButton::with_label(url, "Source");
            source.set_valign(gtk::Align::Center);
            source.set_tooltip_text(Some("Review this third-party agent before adding it"));
            row.append(&source);
        }
        let weak = Rc::downgrade(self);
        add.connect_clicked(move |_| {
            if let Some(manager) = weak.upgrade() {
                manager.prepare_registry_agent(agent.clone());
            }
        });
        row.append(&add);
        self.registry_results.append(&row);
    }

    fn prepare_registry_agent(self: &Rc<Self>, agent: AcpRegistryAgent) {
        self.registry_status.set_text(&format!("Preparing {} on the T3 server…", agent.name));
        let instance_id = self.unique_acp_instance_id(&agent.id);
        let manager = self.clone();
        glib::spawn_future_local(async move {
            if let Err(error) = manager.rpc.call("server.prepareAcpRegistryAgent", json!({"agentId": agent.id})).await {
                manager.registry_status.set_text(&format!("Could not prepare {}: {}", agent.name, error.message()));
                return;
            }
            let config = json!({"source": "registry", "agentId": agent.id, "distribution": "auto"});
            let instance = json!({
                "driver": "acpRegistry",
                "enabled": true,
                "displayName": agent.name,
                "config": config
            });
            let payload = json!({
                "patch": {},
                "providerInstanceMutation": {
                    "operation": "create",
                    "instanceId": instance_id,
                    "instance": instance
                }
            });
            match manager.rpc.call("server.updateSettings", payload).await {
                Ok(_) => {
                    manager.registry_status.set_text(&format!("Added {}. Refreshing provider status…", agent.name));
                    manager.refresh();
                }
                Err(error) => {
                    manager.registry_status.set_text(&format!("Could not add {}: {}", agent.name, error.message()))
                }
            }
        });
    }

    fn unique_acp_instance_id(&self, raw: &str) -> String {
        let slug = raw
            .chars()
            .map(|c| if c.is_ascii_alphanumeric() { c.to_ascii_lowercase() } else { '-' })
            .collect::<String>()
            .split('-')
            .filter(|part| !part.is_empty())
            .collect::<Vec<_>>()
            .join("-");
        let stem = format!("acp-{}", if slug.is_empty() { "agent" } else { &slug });
        let providers = self.providers.borrow();
        for suffix in 1..=999 {
            let candidate = if suffix == 1 { stem.clone() } else { format!("{stem}-{suffix}") };
            let candidate = candidate.chars().take(64).collect::<String>();
            if !providers.iter().any(|provider| provider.instance_id == candidate) {
                return candidate;
            }
        }
        format!("acp-{}", crate::app::new_id().chars().take(16).collect::<String>())
    }

    fn add_local_acp_dialog(self: &Rc<Self>, preset: LocalAcpPreset) {
        let prefill_deepseek = preset == LocalAcpPreset::DeepSeek;
        let prefill_mseries = preset == LocalAcpPreset::MSeries;
        let dialog = gtk::Window::builder()
            .title("Add Local ACP Command")
            .transient_for(&self.window)
            .modal(true)
            .default_width(500)
            .default_height(if prefill_deepseek || prefill_mseries { 440 } else { 360 })
            .build();
        let header = gtk::HeaderBar::builder().show_title_buttons(true).build();
        header.add_css_class(granite::STYLE_CLASS_FLAT);
        dialog.set_titlebar(Some(&header));
        let content = gtk::Box::new(gtk::Orientation::Vertical, 10);
        content.set_margin_top(18);
        content.set_margin_bottom(18);
        content.set_margin_start(20);
        content.set_margin_end(20);
        let intro_text = if prefill_deepseek {
            concat!(
                "DeepSeek Harness is experimental and has not been security-audited. ",
                "It must already be installed on the paired T3 server and can run model-generated commands ",
                "against the workspace T3 gives it. Configure its DeepSeek API key in Harness Settings → Models ",
                "before adding. This fills in the shipped ACP command; it does not install the agent."
            )
        } else if prefill_mseries {
            concat!(
                "This connects the paired server to its existing MSeries local assistant. ",
                "The MSeries assistant tools and supervised local model must already be installed on that server. ",
                "It reuses the local model service, exposes only the scoped MSeries tools, and does not start another model."
            )
        } else {
            "The command runs directly on the paired T3 server. No shell expansion is used."
        };
        let intro = label(intro_text, &["caption", "dim-label"]);
        intro.set_wrap(true);
        content.append(&intro);
        if prefill_deepseek {
            let safety = gtk::LinkButton::with_label(
                "https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md",
                "Read the DeepSeek Harness safety notice",
            );
            safety.set_halign(gtk::Align::Start);
            content.append(&safety);
            let model_setup = gtk::LinkButton::with_label(
                "https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md",
                "Configure a model credential in DeepSeek Harness",
            );
            model_setup.set_halign(gtk::Align::Start);
            content.append(&model_setup);
        }
        let name = gtk::Entry::builder()
            .text(if prefill_deepseek {
                "DeepSeek Harness"
            } else if prefill_mseries {
                "MSeries Assistant"
            } else {
                ""
            })
            .placeholder_text("Provider name, e.g. DeepSeek Harness")
            .build();
        name.update_property(&[gtk::accessible::Property::Label("Provider name")]);
        let command = gtk::Entry::builder()
            .text(if prefill_deepseek {
                "dsh"
            } else if prefill_mseries {
                "mseries-assistant-acp"
            } else {
                ""
            })
            .placeholder_text("Command, e.g. dsh")
            .build();
        command.update_property(&[gtk::accessible::Property::Label("ACP command")]);
        let arguments = gtk::Entry::builder()
            .text(if prefill_deepseek { "--profile acp" } else { "" })
            .placeholder_text("Arguments, e.g. --profile acp")
            .build();
        arguments.update_property(&[gtk::accessible::Property::Label("ACP command arguments")]);
        content.append(&form_row("Name", &name));
        content.append(&form_row("Command", &command));
        content.append(&form_row("Arguments", &arguments));
        let error = label("", &["caption", "error"]);
        error.set_wrap(true);
        content.append(&error);
        let actions = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        actions.set_halign(gtk::Align::End);
        let cancel = gtk::Button::with_label("Cancel");
        let submit = gtk::Button::with_label("Add Provider");
        submit.add_css_class("suggested-action");
        actions.append(&cancel);
        actions.append(&submit);
        content.append(&actions);
        dialog.set_child(Some(&content));
        let dialog_for_cancel = dialog.downgrade();
        cancel.connect_clicked(move |_| {
            if let Some(dialog) = dialog_for_cancel.upgrade() {
                dialog.close();
            }
        });
        let weak = Rc::downgrade(self);
        let dialog_weak = dialog.downgrade();
        let submit_weak = submit.downgrade();
        submit.connect_clicked(move |_| {
            let provider_name = name.text().trim().to_string();
            let command_path = command.text().trim().to_string();
            if provider_name.is_empty() || command_path.is_empty() {
                error.set_text("Enter both a provider name and command.");
                return;
            }
            let command_args = match glib::shell_parse_argv(arguments.text()) {
                Ok(args) => args,
                Err(parse_error) => {
                    error.set_text(&format!("Arguments could not be parsed: {parse_error}"));
                    return;
                }
            };
            let Some(manager) = weak.upgrade() else {
                if let Some(dialog) = dialog_weak.upgrade() {
                    dialog.close();
                }
                return;
            };
            let instance_id = manager.unique_acp_instance_id(&provider_name);
            let instance = json!({
                "driver": "acpRegistry",
                "enabled": true,
                "displayName": provider_name,
                "config": {"source": "local", "commandPath": command_path, "commandArgs": command_args}
            });
            let payload = json!({
                "patch": {},
                "providerInstanceMutation": {
                    "operation": "create",
                    "instanceId": instance_id,
                    "instance": instance
                }
            });
            let rpc = manager.rpc.clone();
            let weak = Rc::downgrade(&manager);
            if let Some(dialog) = dialog_weak.upgrade() {
                dialog.set_sensitive(false);
            }
            if let Some(submit) = submit_weak.upgrade() {
                submit.set_sensitive(false);
            }
            let dialog_weak = dialog_weak.clone();
            let submit_weak = submit_weak.clone();
            let error = error.clone();
            glib::spawn_future_local(async move {
                match rpc.call("server.updateSettings", payload).await {
                    Ok(_) => {
                        if let Some(dialog) = dialog_weak.upgrade() {
                            dialog.close();
                        }
                        if let Some(manager) = weak.upgrade() {
                            manager.registry_status.set_text("Local ACP provider added. Refreshing provider status…");
                            manager.refresh();
                        }
                    }
                    Err(failure) => {
                        if let Some(dialog) = dialog_weak.upgrade() {
                            dialog.set_sensitive(true);
                        }
                        if let Some(submit) = submit_weak.upgrade() {
                            submit.set_sensitive(true);
                        }
                        error.set_text(&format!("Could not add provider: {}", failure.message()));
                    }
                }
            });
        });
        dialog.present();
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

        let is_acp = provider.is_acp_agent();
        let action_label = if is_acp {
            "Remove…"
        } else if provider.ready() {
            "Sign out…"
        } else {
            "Sign in…"
        };
        let action = gtk::Button::with_label(action_label);
        action.set_valign(gtk::Align::Center);
        action.set_sensitive(if is_acp {
            !provider.instance_id.is_empty()
        } else {
            provider.enabled && provider.installed && provider.availability.as_deref() != Some("unavailable")
        });
        action.set_tooltip_text(Some(if is_acp {
            "Remove this agent configuration from the T3 Code server"
        } else if provider.ready() {
            "Sign out on the T3 Code server"
        } else {
            "Start provider sign-in on the T3 Code server"
        }));
        let weak = Rc::downgrade(self);
        let provider = provider.clone();
        action.connect_clicked(move |_| {
            if let Some(manager) = weak.upgrade() {
                if provider.is_acp_agent() {
                    manager.confirm_remove(provider.clone());
                } else if provider.ready() {
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

    fn confirm_remove(self: &Rc<Self>, provider: Provider) {
        let dialog = gtk::AlertDialog::builder()
            .message(format!("Remove {} from T3 Code?", provider.name()))
            .detail(
                "This removes the agent configuration from the T3 Code server. Managed agent files may remain cached.",
            )
            .buttons(["Cancel", "Remove"])
            .default_button(1)
            .cancel_button(0)
            .build();
        let weak = Rc::downgrade(self);
        dialog.choose(Some(&self.window), gio::Cancellable::NONE, move |response| {
            if response != Ok(1) {
                return;
            }
            if let Some(manager) = weak.upgrade() {
                manager.remove_provider(provider.clone());
            }
        });
    }

    fn remove_provider(self: &Rc<Self>, provider: Provider) {
        self.status.set_text(&format!("Removing {}…", provider.name()));
        let manager = self.clone();
        glib::spawn_future_local(async move {
            match manager
                .rpc
                .call(
                    "server.updateSettings",
                    json!({
                        "providerInstanceMutation": {
                            "operation": "remove",
                            "instanceId": provider.instance_id
                        }
                    }),
                )
                .await
            {
                Ok(_) => manager.refresh(),
                Err(error) => manager.status.set_text(&format!("Could not remove agent: {error}")),
            }
        });
    }
}

fn provider_state(provider: &Provider) -> String {
    if provider.ready() {
        if provider.is_acp_agent() { "Agent ready · model checked when you send".into() } else { "Connected".into() }
    } else if provider.is_acp_agent() {
        if !provider.enabled {
            "Agent disabled on the T3 Code server".into()
        } else if !provider.installed {
            "Agent not installed on the T3 Code server".into()
        } else if provider.availability.as_deref() == Some("unavailable") {
            "Agent unavailable on the T3 Code server".into()
        } else {
            match provider.status_text().as_str() {
                "starting" => "Agent starting".into(),
                "error" | "failed" => "Agent startup needs attention".into(),
                _ => "Agent not ready".into(),
            }
        }
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
        let selected = self.method_picker.selected() as usize;
        self.method_picker.set_model(Some(&gtk::StringList::new(&refs)));
        if !names.is_empty() && selected >= names.len() {
            self.method_picker.set_selected(0);
        }
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
        let label_text = state.message.as_deref().unwrap_or(match state.phase.as_str() {
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

fn clear_box(container: &gtk::Box) {
    while let Some(child) = container.first_child() {
        container.remove(&child);
    }
}

fn form_row(title: &str, control: &impl IsA<gtk::Widget>) -> gtk::Box {
    let row = gtk::Box::new(gtk::Orientation::Horizontal, 10);
    row.set_hexpand(true);
    let title_label = label(title, &[]);
    title_label.set_width_chars(12);
    title_label.set_xalign(0.0);
    title_label.set_mnemonic_widget(Some(control));
    control.set_hexpand(true);
    row.append(&title_label);
    row.append(control);
    row
}

fn safe_registry_url(url: &str) -> bool {
    url.strip_prefix("https://").is_some_and(|authority_and_path| {
        let authority = authority_and_path.split('/').next().unwrap_or_default();
        !authority.is_empty()
            && !authority.contains('@')
            && !authority.chars().any(|character| character.is_whitespace() || character.is_control())
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_source_links_require_https_and_a_safe_authority() {
        assert!(safe_registry_url("https://github.com/agent/agent"));
        assert!(!safe_registry_url("http://github.com/agent/agent"));
        assert!(!safe_registry_url("javascript:alert(1)"));
        assert!(!safe_registry_url("https://user@example.com/agent"));
    }

    #[test]
    fn auth_state_decodes_server_advertised_account_methods() {
        let state: AuthState = serde_json::from_value(json!({
            "phase": "idle",
            "methods": [
                {"id": "chatgpt", "name": "Sign in with ChatGPT", "description": "Reconnect account.", "accountEmail": "owner@example.test", "type": "agent"},
                {"id": "chatgpt-change-account", "name": "Use a different ChatGPT account", "description": "Register another account.", "accountEmail": null, "type": "agent"}
            ]
        }))
        .unwrap();

        assert_eq!(state.methods.len(), 2);
        assert_eq!(state.methods[0].id, "chatgpt");
        assert_eq!(state.methods[0].account_email.as_deref(), Some("owner@example.test"));
        assert_eq!(state.methods[1].id, "chatgpt-change-account");
    }

    #[test]
    fn auth_state_accepts_forward_compatible_interactions_and_missing_methods() {
        let state: AuthState = serde_json::from_value(json!({
            "phase": "waiting",
            "flowId": "flow-1",
            "interaction": {"type": "deviceCode", "id": "step-1", "url": "https://example.test/device", "userCode": "ABCD-EFGH", "newServerField": true}
        }))
        .unwrap();

        assert!(state.methods.is_empty());
        assert_eq!(state.flow_id.as_deref(), Some("flow-1"));
        assert_eq!(state.interaction.as_ref().and_then(|v| v.get("type")).and_then(Value::as_str), Some("deviceCode"));
    }
}
