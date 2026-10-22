//! The Repos page (pinned GitHub repos with lane counts and the next issue up) and the Issues panel
//! (live list per repo, filters, "Start on this", runner install). Backed by `workflow.rs`.

use crate::app::{App, new_id};
use crate::chat::label;
use crate::look::{iso_to_unix, now_unix, relative_time};
use crate::skeleton;
use crate::workflow::{self, Config, Issue, PinnedRepo};
use granite::prelude::PlaceholderExt;
use gtk::{gio, glib, pango, prelude::*};
use serde_json::{Value, json};
use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::rc::Rc;

pub struct ReposPage {
    root: gtk::Box,
    repo_list: gtk::Box,
    status: gtk::Label,
    issues_box: gtk::Box,
    issues_title: gtk::Label,
    lane_dd: gtk::DropDown,
    prio_dd: gtk::DropDown,
    agent_dd: gtk::DropDown,
    config: RefCell<Config>,
    issues: RefCell<Vec<Issue>>,
    current_repo: RefCell<Option<PinnedRepo>>,
}

fn pill(text: &str, class: &str) -> gtk::Label {
    let l = label(text, &["caption", "pill", class]);
    l.set_halign(gtk::Align::Start);
    l
}

fn project_matches_repo(project: &crate::t3::model::Project, repo: &PinnedRepo) -> bool {
    if project.deleted_at.is_some() {
        return false;
    }
    if project.workspace_root == repo.path {
        return true;
    }
    let Some(identity) = project.repository_identity.as_ref().and_then(Value::as_object) else { return false };
    if let (Some(owner), Some(name)) =
        (identity.get("owner").and_then(Value::as_str), identity.get("name").and_then(Value::as_str))
        && format!("{owner}/{name}").eq_ignore_ascii_case(&repo.repo)
    {
        return true;
    }
    ["canonicalKey", "repositoryUrl", "remoteUrl", "cloneUrl", "htmlUrl", "url", "sshUrl", "httpsUrl"]
        .iter()
        .filter_map(|key| identity.get(*key).and_then(Value::as_str))
        .any(|candidate| {
            if workflow::repo_from_remote(candidate).is_some_and(|found| found.eq_ignore_ascii_case(&repo.repo)) {
                return true;
            }
            let candidate = candidate
                .trim()
                .trim_start_matches("https://github.com/")
                .trim_start_matches("http://github.com/")
                .trim_start_matches("github.com/")
                .trim_start_matches("github.com:")
                .trim_end_matches('/')
                .trim_end_matches(".git");
            candidate.eq_ignore_ascii_case(&repo.repo)
        })
}

fn thread_title(thread: &crate::t3::model::ThreadShell) -> String {
    if thread.title.trim().is_empty() {
        format!("Untitled chat ({})", thread.id.chars().take(8).collect::<String>())
    } else {
        thread.title.clone()
    }
}

impl ReposPage {
    pub fn new() -> ReposPage {
        let status = label("", &["dim-label"]);
        status.set_margin_start(24);
        status.set_margin_top(12);
        let repo_list = gtk::Box::new(gtk::Orientation::Vertical, 8);
        repo_list.set_margin_start(24);
        repo_list.set_margin_end(24);
        repo_list.set_margin_top(12);

        let issues_title = label("", &["title-4"]);
        issues_title.set_hexpand(true);
        let lane_dd = gtk::DropDown::from_strings(&["All lanes", "build", "feature", "maintenance"]);
        let prio_dd = gtk::DropDown::from_strings(&["All priorities", "p0", "p1", "p2", "p3"]);
        let agent_dd = gtk::DropDown::from_strings(&["Any agent label", "ready", "running", "done", "blocked", "none"]);
        let filters = gtk::Box::new(gtk::Orientation::Horizontal, 6);
        filters.set_margin_start(24);
        filters.set_margin_end(24);
        filters.set_margin_top(12);
        filters.append(&issues_title);
        filters.append(&lane_dd);
        filters.append(&prio_dd);
        filters.append(&agent_dd);
        let issues_box = gtk::Box::new(gtk::Orientation::Vertical, 6);
        issues_box.set_margin_start(24);
        issues_box.set_margin_end(24);
        issues_box.set_margin_top(8);
        issues_box.set_margin_bottom(18);

        let column = gtk::Box::new(gtk::Orientation::Vertical, 0);
        column.append(&status);
        column.append(&repo_list);
        column.append(&filters);
        column.append(&issues_box);
        let scroll = gtk::ScrolledWindow::builder()
            .child(&column)
            .hscrollbar_policy(gtk::PolicyType::Never)
            .vexpand(true)
            .build();
        let root = gtk::Box::new(gtk::Orientation::Vertical, 0);
        root.append(&scroll);
        ReposPage {
            root,
            repo_list,
            status,
            issues_box,
            issues_title,
            lane_dd,
            prio_dd,
            agent_dd,
            config: RefCell::new(workflow::load_config()),
            issues: RefCell::new(Vec::new()),
            current_repo: RefCell::new(None),
        }
    }

    pub fn widget(&self) -> &gtk::Box {
        &self.root
    }

    pub fn config(&self) -> Config {
        self.config.borrow().clone()
    }

    pub fn issue_count(&self) -> usize {
        self.issues.borrow().len()
    }

    /// The issues last loaded, with their repo (for the command palette).
    pub fn cached_issues(&self) -> Vec<(String, Issue)> {
        let repo = self.current_repo.borrow().as_ref().map(|r| r.repo.clone());
        match repo {
            Some(r) => self.issues.borrow().iter().map(|i| (r.clone(), i.clone())).collect(),
            None => Vec::new(),
        }
    }

    fn save(&self, f: impl FnOnce(&mut Config)) {
        let mut c = self.config.borrow_mut();
        f(&mut c);
        workflow::save_config(&c);
    }

    /// The thread started for an issue, if the client started one.
    pub fn thread_for_issue(&self, key: &str) -> Option<String> {
        self.config.borrow().started.get(key).cloned()
    }

    /// All chats shown below an open issue; old installs inherit the client-started thread.
    pub fn chats_for_issue(&self, key: &str) -> Vec<String> {
        self.config.borrow().chats_for_issue(key)
    }

    /// `owner/name#number` for a thread the client started from an issue.
    pub fn issue_for_thread(&self, thread_id: &str) -> Option<String> {
        self.config.borrow().started.iter().find(|(_, t)| *t == thread_id).map(|(k, _)| k.clone())
    }

    /// Lists the server's projects that are GitHub checkouts, with pin toggles, then the pinned repos' backlogs.
    pub fn load(&self, app: Rc<App>) {
        self.status.set_text("Reading repositories…");
        let projects = app.projects();
        let page = app.repos_page_rc();
        glib::spawn_future_local(async move {
            let mut found: Vec<(String, String)> = Vec::new();
            for p in &projects {
                if let Some(repo) = workflow::remote_repo(&p.workspace_root).await {
                    found.push((repo, p.workspace_root.clone()));
                }
            }
            page.render_repos(&app, found).await;
        });
    }

    async fn render_repos(&self, app: &Rc<App>, found: Vec<(String, String)>) {
        while let Some(c) = self.repo_list.first_child() {
            self.repo_list.remove(&c);
        }
        let pinned: Vec<PinnedRepo> = self.config.borrow().repos.clone();
        let mut all: Vec<PinnedRepo> = pinned.clone();
        for (repo, path) in &found {
            if !all.iter().any(|r| r.repo == *repo) {
                all.push(PinnedRepo { repo: repo.clone(), path: path.clone() });
            }
        }
        if all.is_empty() {
            self.status.set_text("");
            let ph = granite::Placeholder::new("No GitHub repos yet");
            ph.set_description("None of the server's projects has a GitHub remote. Import your sessions or add a project with a checkout.");
            ph.set_icon(&gio::ThemedIcon::new("folder-remote-symbolic"));
            let import = ph.append_button(
                &gio::ThemedIcon::new("document-import-symbolic"),
                "Import Sessions",
                "Scan Claude Code and Codex sessions on the server",
            );
            import.set_action_name(Some("win.import"));
            self.repo_list.append(&ph);
            return;
        }
        self.status.set_text(&format!("{} pinned of {} GitHub repos known to the server", pinned.len(), all.len()));
        for r in all {
            let card = gtk::Box::new(gtk::Orientation::Vertical, 6);
            card.add_css_class("card");
            card.add_css_class("repo-card");
            let head = gtk::Box::new(gtk::Orientation::Horizontal, 10);
            let pin = gtk::CheckButton::with_label("Pinned");
            pin.set_active(pinned.iter().any(|p| p.repo == r.repo));
            let name = label(&r.repo, &["title-4"]);
            name.set_hexpand(true);
            head.append(&name);
            head.append(&pin);
            let open = gtk::Button::with_label("Issues");
            head.append(&open);
            let runner = gtk::Button::with_label("Install runner");
            runner.set_tooltip_text(Some("A T3 scheduled task every 5 minutes that takes the next agent:ready issue"));
            head.append(&runner);
            let webhook = gtk::Button::with_label("Webhook");
            webhook.set_tooltip_text(Some(
                "A webhook task that starts on GitHub's issues.labeled agent:ready within seconds; the GitHub hook is created when the server's endpoint is reachable (Tailscale or T3 Connect)",
            ));
            head.append(&webhook);
            card.append(&head);
            let automation = {
                let runner_state = if self.runner_id(&r.repo).is_some() { "installed" } else { "not installed" };
                let hook_state = match self.webhook_install(&r.repo) {
                    Some(w) if w.hook_id.is_some() => "installed, GitHub hook created".to_string(),
                    Some(w) if w.url.is_some() => "task installed, GitHub hook pending".to_string(),
                    Some(_) => "task installed, endpoint not reachable yet".to_string(),
                    None => "not installed".to_string(),
                };
                label(
                    &format!(
                        "runner {runner_state} · webhook {hook_state} · provider re-picked by capacity every 5 min"
                    ),
                    &["caption", "dim-label"],
                )
            };
            card.append(&automation);
            let summary = label(&crate::look::tilde(&r.path), &["caption", "dim-label"]);
            card.append(&summary);
            let counts = label("", &["caption"]);
            card.append(&counts);
            self.repo_list.append(&card);

            let a = app.clone();
            let rr = r.clone();
            pin.connect_toggled(move |b| {
                let active = b.is_active();
                let rr = rr.clone();
                a.repos_page().save(move |c| {
                    c.repos.retain(|p| p.repo != rr.repo);
                    if active {
                        c.repos.push(rr);
                    }
                });
            });
            let a = app.clone();
            let rr = r.clone();
            open.connect_clicked(move |_| a.repos_page().show_issues(&a, rr.clone()));
            let a = app.clone();
            let rr = r.clone();
            runner.connect_clicked(move |_| a.install_runner(rr.clone()));
            let a = app.clone();
            let rr = r.clone();
            webhook.connect_clicked(move |_| a.install_webhook(rr.clone()));

            if pinned.iter().any(|p| p.repo == r.repo) {
                match workflow::issues(&r.repo).await {
                    Ok(issues) => {
                        let lane = |l: &str| issues.iter().filter(|i| i.lane() == Some(l)).count();
                        let ready = issues.iter().filter(|i| i.agent() == Some("ready")).count();
                        let running = issues.iter().filter(|i| i.agent() == Some("running")).count();
                        let next = issues
                            .iter()
                            .find(|i| i.agent() == Some("ready"))
                            .map(|i| format!("next up: #{} {}", i.number, i.title));
                        counts.set_text(&format!(
                            "{} open · build {} · feature {} · maintenance {} · ready {} · running {}{}",
                            issues.len(),
                            lane("build"),
                            lane("feature"),
                            lane("maintenance"),
                            ready,
                            running,
                            next.map(|n| format!(" · {n}")).unwrap_or_default()
                        ));
                    }
                    Err(e) => counts.set_text(&format!("GitHub: {e}")),
                }
            }
        }
    }

    pub fn show_issues(&self, app: &Rc<App>, repo: PinnedRepo) {
        *self.current_repo.borrow_mut() = Some(repo.clone());
        self.issues_title.set_text(&format!("Issues in {}", repo.repo));
        while let Some(c) = self.issues_box.first_child() {
            self.issues_box.remove(&c);
        }
        self.issues_box.append(&skeleton::rows(5));
        let app = app.clone();
        glib::spawn_future_local(async move {
            workflow::ensure_labels(&repo.repo).await;
            match workflow::issues(&repo.repo).await {
                Ok(issues) => {
                    *app.repos_page().issues.borrow_mut() = issues;
                    app.repos_page().render_issues(&app);
                }
                Err(e) => {
                    let page = app.repos_page();
                    while let Some(c) = page.issues_box.first_child() {
                        page.issues_box.remove(&c);
                    }
                    let ph = granite::Placeholder::new("GitHub did not answer");
                    ph.set_description(&format!("GitHub: {e}"));
                    ph.set_icon(&gio::ThemedIcon::new("network-error-symbolic"));
                    let r = repo.clone();
                    let a = app.clone();
                    let retry =
                        ph.append_button(&gio::ThemedIcon::new("view-refresh-symbolic"), "Retry", "Ask GitHub again");
                    retry.connect_clicked(move |_| a.repos_page().show_issues(&a, r.clone()));
                    page.issues_box.append(&ph);
                    let r = repo.clone();
                    app.toast_retry(
                        &format!("GitHub: {e}"),
                        Rc::new(move |a| a.repos_page().show_issues(a, r.clone())),
                    );
                }
            }
        });
    }

    pub fn wire_filters(&self, app: Rc<App>) {
        for dd in [&self.lane_dd, &self.prio_dd, &self.agent_dd] {
            let a = app.clone();
            dd.connect_selected_notify(move |_| a.repos_page().render_issues(&a));
        }
    }

    fn render_issues(&self, app: &Rc<App>) {
        while let Some(c) = self.issues_box.first_child() {
            self.issues_box.remove(&c);
        }
        let Some(repo) = self.current_repo.borrow().clone() else { return };
        let lane = ["", "build", "feature", "maintenance"][self.lane_dd.selected() as usize];
        let prio = ["", "p0", "p1", "p2", "p3"][self.prio_dd.selected() as usize];
        let agent = ["", "ready", "running", "done", "blocked", "none"][self.agent_dd.selected() as usize];
        let now = now_unix();
        let issues = self.issues.borrow();
        let shown: Vec<&Issue> = issues
            .iter()
            .filter(|i| lane.is_empty() || i.lane() == Some(lane))
            .filter(|i| prio.is_empty() || i.priority() == Some(prio))
            .filter(|i| match agent {
                "" => true,
                "none" => i.agent().is_none(),
                a => i.agent() == Some(a),
            })
            .collect();
        let threads_by_id: HashMap<String, crate::t3::model::ThreadShell> =
            app.threads().into_iter().map(|thread| (thread.id.clone(), thread)).collect();
        if shown.is_empty() {
            self.issues_box.append(&skeleton::empty(
                "edit-find-symbolic",
                "No issues match",
                "Label issues lane:*, p0–p3 and agent:ready to feed the runner, or widen the filters.",
            ));
            return;
        }
        for i in shown {
            let issue_card = gtk::Box::new(gtk::Orientation::Vertical, 5);
            issue_card.add_css_class("card");
            issue_card.add_css_class("issue-card");
            issue_card.set_margin_top(3);
            issue_card.set_margin_bottom(3);
            let row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
            row.add_css_class("issue-row");
            let number = label(&format!("#{}", i.number), &["caption", "dim-label"]);
            number.set_width_chars(6);
            row.append(&number);
            let title = label(&i.title, &[]);
            title.set_hexpand(true);
            title.set_tooltip_text(Some(&i.url));
            row.append(&title);
            if let Some(l) = i.lane() {
                row.append(&pill(l, &format!("lane-{l}")));
            }
            if let Some(p) = i.priority() {
                row.append(&pill(p, &format!("prio-{p}")));
            }
            if let Some(a) = i.agent() {
                row.append(&pill(&format!("agent:{a}"), "agent"));
            }
            row.append(&label(&relative_time(iso_to_unix(&i.updated_at), now), &["caption", "dim-label"]));
            let key = format!("{}#{}", repo.repo, i.number);
            match self.thread_for_issue(&key) {
                Some(thread_id) => {
                    let b = gtk::Button::with_label("Open thread");
                    let a = app.clone();
                    b.connect_clicked(move |_| {
                        if !a.select_id(&thread_id) {
                            a.toast("That thread is no longer in the list.");
                        }
                    });
                    row.append(&b);
                }
                None => {
                    let b = gtk::Button::with_label("Start on this");
                    b.add_css_class("suggested-action");
                    let a = app.clone();
                    let issue = i.clone();
                    let rr = repo.clone();
                    b.connect_clicked(move |_| a.start_issue(rr.clone(), issue.clone()));
                    row.append(&b);
                }
            }
            issue_card.append(&row);

            let linked_ids = self.chats_for_issue(&key);
            let chat_header = gtk::Box::new(gtk::Orientation::Horizontal, 8);
            chat_header.set_margin_start(22);
            let linked_title = label(
                &format!("{} {}", linked_ids.len(), if linked_ids.len() == 1 { "chat" } else { "chats" }),
                &["caption", "dim-label"],
            );
            linked_title.set_hexpand(true);
            chat_header.append(&linked_title);
            let organize = gtk::Button::with_label("Organize chats");
            organize.add_css_class("flat");
            let a = app.clone();
            let rr = repo.clone();
            let issue = i.clone();
            organize.connect_clicked(move |_| a.repos_page().organize_issue_chats(&a, &rr, &issue));
            chat_header.append(&organize);
            issue_card.append(&chat_header);

            let linked_box = gtk::Box::new(gtk::Orientation::Vertical, 2);
            linked_box.set_margin_start(34);
            linked_box.set_margin_bottom(4);
            for thread_id in linked_ids {
                let linked_row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
                let (title, available) = match threads_by_id.get(&thread_id) {
                    Some(thread) => (thread_title(thread), true),
                    None => (format!("Unavailable chat ({})", thread_id.chars().take(8).collect::<String>()), false),
                };
                let open_chat = gtk::Button::with_label(&title);
                open_chat.set_halign(gtk::Align::Start);
                open_chat.set_hexpand(true);
                open_chat.add_css_class("flat");
                if available {
                    let a = app.clone();
                    let tid = thread_id.clone();
                    open_chat.connect_clicked(move |_| {
                        if !a.select_id(&tid) {
                            a.toast("That chat is no longer in the list.");
                        }
                    });
                } else {
                    open_chat.set_sensitive(false);
                }
                linked_row.append(&open_chat);
                let remove = gtk::Button::with_label("Remove");
                remove.add_css_class("flat");
                remove.set_tooltip_text(Some("Remove this chat from the issue"));
                let a = app.clone();
                let issue_key = key.clone();
                let tid = thread_id.clone();
                remove.connect_clicked(move |_| {
                    let page = a.repos_page_rc();
                    page.set_issue_chat_link(&issue_key, &tid, false);
                    page.render_issues(&a);
                });
                linked_row.append(&remove);
                linked_box.append(&linked_row);
            }
            if linked_box.first_child().is_none() {
                let empty = label("No chats organized under this issue yet.", &["caption", "dim-label"]);
                empty.set_margin_start(34);
                empty.set_margin_bottom(6);
                issue_card.append(&empty);
            } else {
                issue_card.append(&linked_box);
            }
            self.issues_box.append(&issue_card);
        }
    }

    fn set_issue_chat_link(&self, key: &str, thread_id: &str, linked: bool) {
        let key = key.to_string();
        let thread_id = thread_id.to_string();
        self.save(move |config| {
            let chats = config
                .issue_chats
                .entry(key.clone())
                .or_insert_with(|| config.started.get(&key).cloned().into_iter().collect());
            if linked {
                if !chats.contains(&thread_id) {
                    chats.push(thread_id);
                }
            } else {
                chats.retain(|id| id != &thread_id);
            }
        });
    }

    fn organize_issue_chats(&self, app: &Rc<App>, repo: &PinnedRepo, issue: &Issue) {
        let projects = app.projects();
        let project_ids: HashSet<String> = projects
            .iter()
            .filter(|project| project_matches_repo(project, repo))
            .map(|project| project.id.clone())
            .collect();
        let project_titles: HashMap<String, String> = projects.into_iter().map(|p| (p.id, p.title)).collect();
        let mut threads: Vec<_> =
            app.threads().into_iter().filter(|thread| project_ids.contains(&thread.project_id)).collect();
        threads.sort_by_key(|thread| std::cmp::Reverse(iso_to_unix(&thread.updated_at)));

        if threads.is_empty() {
            app.toast("No chats are available for this repository yet.");
            return;
        }

        let key = format!("{}#{}", repo.repo, issue.number);
        let selected: HashSet<String> = self.chats_for_issue(&key).into_iter().collect();
        let window = gtk::Window::builder()
            .title(format!("Chats for {}#{}", repo.repo, issue.number))
            .transient_for(app.window())
            .modal(true)
            .default_width(500)
            .default_height(560)
            .build();
        let root = gtk::Box::new(gtk::Orientation::Vertical, 10);
        root.set_margin_start(18);
        root.set_margin_end(18);
        root.set_margin_top(16);
        root.set_margin_bottom(16);
        let intro =
            label(&format!("Choose chats to group under #{} while this issue is open.", issue.number), &["dim-label"]);
        intro.set_wrap(true);
        intro.set_xalign(0.0);
        root.append(&intro);

        let list = gtk::Box::new(gtk::Orientation::Vertical, 4);
        let mut checks = Vec::with_capacity(threads.len());
        for thread in threads {
            let check = gtk::CheckButton::new();
            check.set_active(selected.contains(&thread.id));
            let item = gtk::Box::new(gtk::Orientation::Vertical, 2);
            let title = label(&thread_title(&thread), &[]);
            title.set_xalign(0.0);
            let project = project_titles.get(&thread.project_id).map(String::as_str).unwrap_or("Project");
            let context = label(
                &format!("{project} · {}", relative_time(iso_to_unix(&thread.updated_at), now_unix())),
                &["caption", "dim-label"],
            );
            context.set_xalign(0.0);
            item.append(&title);
            item.append(&context);
            check.set_child(Some(&item));
            check.set_margin_top(3);
            check.set_margin_bottom(3);
            list.append(&check);
            checks.push((thread.id, check));
        }
        let scroll =
            gtk::ScrolledWindow::builder().child(&list).hscrollbar_policy(gtk::PolicyType::Never).vexpand(true).build();
        root.append(&scroll);

        let actions = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        actions.set_halign(gtk::Align::End);
        let cancel = gtk::Button::with_label("Cancel");
        let done = gtk::Button::with_label("Done");
        done.add_css_class("suggested-action");
        actions.append(&cancel);
        actions.append(&done);
        root.append(&actions);
        window.set_child(Some(&root));

        let close_window = window.clone();
        cancel.connect_clicked(move |_| close_window.close());
        let a = app.clone();
        let close_window = window.clone();
        done.connect_clicked(move |_| {
            let chats: Vec<String> =
                checks.iter().filter(|(_, check)| check.is_active()).map(|(thread_id, _)| thread_id.clone()).collect();
            let page = a.repos_page_rc();
            let issue_key = key.clone();
            page.save(move |config| {
                config.issue_chats.insert(issue_key, chats);
            });
            page.render_issues(&a);
            close_window.close();
        });
        window.present();
    }

    pub fn remember_started(&self, key: &str, thread_id: &str) {
        let key = key.to_string();
        let thread_id = thread_id.to_string();
        self.save(move |c| {
            c.started.insert(key.clone(), thread_id.clone());
            if let Some(chats) = c.issue_chats.get_mut(&key)
                && !chats.contains(&thread_id)
            {
                chats.push(thread_id);
            }
        });
    }

    pub fn remember_runner(&self, repo: &str, task_id: &str) {
        let repo = repo.to_string();
        let task_id = task_id.to_string();
        self.save(move |c| {
            c.runners.insert(repo, task_id);
        });
    }

    pub fn runner_id(&self, repo: &str) -> Option<String> {
        self.config.borrow().runners.get(repo).cloned()
    }

    pub fn webhook_install(&self, repo: &str) -> Option<workflow::WebhookInstall> {
        self.config.borrow().webhooks.get(repo).cloned()
    }

    pub fn remember_webhook(&self, repo: &str, install: workflow::WebhookInstall) {
        let repo = repo.to_string();
        self.save(move |c| {
            c.webhooks.insert(repo, install);
        });
    }
}

impl Default for ReposPage {
    fn default() -> Self {
        Self::new()
    }
}

/// A collapsed row with an issue's comments, for the top of a thread started from that issue.
pub fn comments_row(key: &str, comments: &[(String, String, String)]) -> gtk::Widget {
    let text = comments
        .iter()
        .map(|(who, when, body)| format!("{who} · {}\n{}", crate::look::clock(when), body.trim()))
        .collect::<Vec<_>>()
        .join("\n\n");
    let shown = if comments.is_empty() { "No comments yet.".to_string() } else { text };
    crate::chat::tool_row("", &format!("Issue {key}: {} comments", comments.len()), shown, None)
}

/// The value the server stores for a started issue thread, kept on the thread as `goal` text.
pub fn issue_goal(repo: &str, issue: &Issue) -> Value {
    json!({"repo": repo, "number": issue.number, "url": issue.url})
}

#[allow(dead_code)]
fn _keep(_: &pango::EllipsizeMode) {}

#[allow(dead_code)]
fn _id() -> String {
    new_id()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::t3::model::Project;

    #[test]
    fn repository_threads_match_by_checkout_or_repository_identity() {
        let repo = PinnedRepo { repo: "techmore/elementaryos_mseries".into(), path: "/src/project".into() };
        let checkout = Project { workspace_root: "/src/project".into(), ..Default::default() };
        assert!(project_matches_repo(&checkout, &repo));

        let other_checkout = Project {
            workspace_root: "/src/worktree".into(),
            repository_identity: Some(json!({"canonicalKey": "https://github.com/techmore/ElementaryOS_MSeries.git"})),
            ..Default::default()
        };
        assert!(project_matches_repo(&other_checkout, &repo));

        let deleted = Project { deleted_at: Some("2026-10-22T00:00:00Z".into()), ..checkout };
        assert!(!project_matches_repo(&deleted, &repo));
    }
}
