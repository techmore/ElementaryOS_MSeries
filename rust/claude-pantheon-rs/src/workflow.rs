//! The workflow from docs/WORKFLOW.md: pinned GitHub repos, their issue backlog (lane, priority and
//! agent labels), "Start on this" threads, and the runner as T3 scheduled tasks. GitHub is reached
//! through `gh api` (the user is logged in with `gh`); the server owns no GitHub token we can read.

use crate::t3::model::{Provider, pick_provider};
use gtk::{gio, glib};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

pub const LANES: [&str; 3] = ["build", "feature", "maintenance"];
pub const PRIORITIES: [&str; 4] = ["p0", "p1", "p2", "p3"];
pub const RUNNER_INTERVAL_MS: u64 = 5 * 60 * 1000;

/// Labels the workflow uses, with the colours they get when created.
pub const LABELS: [(&str, &str, &str); 11] = [
    ("lane:build", "0e8a16", "Production-grade builds, release pipelines, packaging"),
    ("lane:feature", "1d76db", "Roadmap features"),
    ("lane:maintenance", "fbca04", "Repo maintenance: branches, bumps, hygiene, flaky tests"),
    ("p0", "b60205", "Drop everything"),
    ("p1", "d93f0b", "This week"),
    ("p2", "e99695", "Soon"),
    ("p3", "f9d0c4", "Whenever"),
    ("agent:ready", "5319e7", "Specified well enough for an agent to take unattended"),
    ("agent:running", "0052cc", "An agent thread is working on it"),
    ("agent:done", "006b75", "The agent opened a PR"),
    ("agent:blocked", "000000", "Failed twice; needs a human"),
];

pub fn runner_prompt(repo: &str) -> String {
    format!(
        "List open issues labeled agent:ready in {repo}, highest priority first (p0 before p3), lanes in the order \
build > feature > maintenance. Take the first one not labeled agent:running, label it agent:running, work it to a \
PR that closes it, run the repo's checks, then label it agent:done. If it fails twice, label it agent:blocked and \
comment with the error. Never push to main. One running agent per repo unless the issue is labeled parallel-ok."
    )
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct PinnedRepo {
    /// `owner/name`
    pub repo: String,
    /// Local checkout (a T3 project's workspace root).
    pub path: String,
}

#[derive(Serialize, Deserialize, Default, Clone, Debug)]
pub struct Config {
    pub repos: Vec<PinnedRepo>,
    /// `owner/name#number` → thread id for issues started from the client.
    #[serde(default)]
    pub started: HashMap<String, String>,
    /// `owner/name#number` → thread ids explicitly organized under that issue in the Repos view.
    /// A present empty list intentionally overrides the legacy `started` association.
    #[serde(default)]
    pub issue_chats: HashMap<String, Vec<String>>,
    /// Owner-written issue briefs that have not yet been filed with GitHub.
    #[serde(default)]
    pub issue_drafts: Vec<IssueDraft>,
    /// repo → scheduled task id of its runner.
    #[serde(default)]
    pub runners: HashMap<String, String>,
    /// repo → the webhook task and the GitHub hook that feeds it.
    #[serde(default)]
    pub webhooks: HashMap<String, WebhookInstall>,
}

/// Local issue brief. It describes the problem and acceptance criteria; it deliberately stores no
/// implementation plan or provider selection, which belong to a later execution decision.
#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, Eq)]
pub struct IssueDraft {
    pub id: String,
    pub repo: String,
    pub title: String,
    pub problem: String,
    pub context: String,
    pub success_criteria: String,
    pub constraints: String,
    pub lane: String,
    pub priority: String,
    pub agent_ready: bool,
    pub updated_at: String,
}

impl IssueDraft {
    pub fn validation_error(&self) -> Option<&'static str> {
        if self.title.trim().is_empty() {
            Some("Add an issue title before filing.")
        } else if self.problem.trim().is_empty() {
            Some("Describe the problem or desired change before filing.")
        } else if self.success_criteria.trim().is_empty() {
            Some("Add success criteria so the issue says what done looks like.")
        } else {
            None
        }
    }

    pub fn body(&self) -> String {
        let mut sections = vec![format!("## Problem and desired outcome\n{}", self.problem.trim())];
        for (heading, text) in [
            ("Context and research", self.context.trim()),
            ("Success criteria", self.success_criteria.trim()),
            ("Constraints and non-goals", self.constraints.trim()),
        ] {
            if !text.is_empty() {
                sections.push(format!("## {heading}\n{text}"));
            }
        }
        sections.join("\n\n")
    }

    /// Issue workflow labels are independent of the provider/account selected for execution.
    pub fn labels(&self) -> Vec<String> {
        let mut labels = Vec::new();
        if LANES.contains(&self.lane.as_str()) {
            labels.push(format!("lane:{}", self.lane));
        }
        if PRIORITIES.contains(&self.priority.as_str()) {
            labels.push(self.priority.clone());
        }
        if self.agent_ready {
            labels.push("agent:ready".into());
        }
        labels
    }
}

impl Config {
    /// The chats shown beneath an issue. Newer configs can explicitly replace or clear the
    /// original one-thread association kept in `started` for issue comments and old installs.
    pub fn chats_for_issue(&self, key: &str) -> Vec<String> {
        self.issue_chats.get(key).cloned().unwrap_or_else(|| self.started.get(key).cloned().into_iter().collect())
    }
}

#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, Eq)]
pub struct WebhookInstall {
    pub task_id: String,
    /// The task's webhook URL as the server reported it (None until an endpoint is reachable).
    pub url: Option<String>,
    /// GitHub's hook id once created on the repo.
    pub hook_id: Option<u64>,
}

fn config_path() -> PathBuf {
    let base = std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::var_os("HOME").map(PathBuf::from).unwrap_or_default().join(".config"));
    base.join("claude-pantheon-rs").join("workflow.json")
}

pub fn load_config() -> Config {
    std::fs::read(config_path()).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default()
}

pub fn save_config(c: &Config) -> Result<(), String> {
    let path = config_path();
    let bytes = serde_json::to_vec_pretty(c).map_err(|error| error.to_string())?;
    crate::persistence::atomic_write(&path, &bytes, 0o600).map_err(|error| error.to_string())
}

#[derive(Clone, Debug, Default)]
pub struct Issue {
    pub number: u64,
    pub title: String,
    pub body: String,
    pub url: String,
    /// GitHub lifecycle state: `open` or `closed`.
    pub state: String,
    pub labels: Vec<String>,
    pub updated_at: String,
    pub comments: u64,
}

impl Issue {
    pub fn lane(&self) -> Option<&str> {
        self.labels.iter().find_map(|l| l.strip_prefix("lane:"))
    }
    pub fn priority(&self) -> Option<&str> {
        self.labels.iter().find(|l| PRIORITIES.contains(&l.as_str())).map(String::as_str)
    }
    pub fn agent(&self) -> Option<&str> {
        self.labels.iter().find_map(|l| l.strip_prefix("agent:"))
    }
    /// Sort key: priority first (unlabelled last), then lane order, then number.
    pub fn rank(&self) -> (usize, usize, u64) {
        let p = self.priority().and_then(|p| PRIORITIES.iter().position(|x| *x == p)).unwrap_or(PRIORITIES.len());
        let l = self.lane().and_then(|l| LANES.iter().position(|x| *x == l)).unwrap_or(LANES.len());
        (p, l, self.number)
    }
}

/// Parses `gh api .../issues` output; pull requests (which the issues endpoint also lists) are dropped.
pub fn parse_issues(v: &Value) -> Vec<Issue> {
    let mut out: Vec<Issue> = v
        .as_array()
        .map(|a| a.iter())
        .into_iter()
        .flatten()
        .filter(|i| i.get("pull_request").is_none())
        .map(|i| Issue {
            number: i.get("number").and_then(Value::as_u64).unwrap_or(0),
            title: i.get("title").and_then(Value::as_str).unwrap_or("").to_string(),
            body: i.get("body").and_then(Value::as_str).unwrap_or("").to_string(),
            url: i.get("html_url").and_then(Value::as_str).unwrap_or("").to_string(),
            state: i.get("state").and_then(Value::as_str).unwrap_or("open").to_string(),
            labels: i
                .get("labels")
                .and_then(Value::as_array)
                .map(|ls| ls.iter().filter_map(|l| l.get("name").and_then(Value::as_str).map(str::to_string)).collect())
                .unwrap_or_default(),
            updated_at: i.get("updated_at").and_then(Value::as_str).unwrap_or("").to_string(),
            comments: i.get("comments").and_then(Value::as_u64).unwrap_or(0),
        })
        .collect();
    out.sort_by_key(Issue::rank);
    out
}

/// `owner/name` from a git remote URL.
pub fn repo_from_remote(url: &str) -> Option<String> {
    let url = url.trim().trim_end_matches(".git");
    let rest = url
        .strip_prefix("git@github.com:")
        .or_else(|| url.strip_prefix("https://github.com/"))
        .or_else(|| url.strip_prefix("ssh://git@github.com/"))
        .or_else(|| url.strip_prefix("http://github.com/"))?;
    let mut parts = rest.split('/');
    let owner = parts.next()?;
    let name = parts.next()?;
    (!owner.is_empty() && !name.is_empty()).then(|| format!("{owner}/{name}"))
}

async fn run(argv: &[&str], cwd: Option<&Path>) -> Result<String, String> {
    run_with_input(argv, cwd, None).await
}

/// Runs a command, optionally feeding `input` on stdin (a JSON body for `gh api --input -`).
async fn run_with_input(argv: &[&str], cwd: Option<&Path>, input: Option<&str>) -> Result<String, String> {
    let mut flags = gio::SubprocessFlags::STDOUT_PIPE | gio::SubprocessFlags::STDERR_PIPE;
    if input.is_some() {
        flags |= gio::SubprocessFlags::STDIN_PIPE;
    }
    let launcher = gio::SubprocessLauncher::new(flags);
    if let Some(d) = cwd {
        launcher.set_cwd(d);
    }
    let argv: Vec<&std::ffi::OsStr> = argv.iter().map(std::ffi::OsStr::new).collect();
    let proc = launcher.spawn(&argv).map_err(|e| e.to_string())?;
    let (out, err) = proc.communicate_utf8_future(input.map(str::to_string)).await.map_err(|e| e.to_string())?;
    if proc.has_exited() && proc.exit_status() == 0 {
        Ok(out.map(|s| s.to_string()).unwrap_or_default())
    } else {
        Err(err.map(|s| s.to_string()).unwrap_or_default().trim().to_string())
    }
}

/// The GitHub repo of a local checkout, from its `origin` remote.
pub async fn remote_repo(path: &str) -> Option<String> {
    let out = run(&["git", "remote", "get-url", "origin"], Some(Path::new(path))).await.ok()?;
    repo_from_remote(&out)
}

/// The current branch of a local checkout, with an explicit short revision for detached HEADs.
pub async fn current_branch(path: &str) -> Option<String> {
    let cwd = Some(Path::new(path));
    if let Ok(branch) = run(&["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd).await {
        let branch = branch.trim();
        if !branch.is_empty() {
            return Some(branch.to_string());
        }
    }
    let commit = run(&["git", "rev-parse", "--short", "HEAD"], cwd).await.ok()?;
    let commit = commit.trim();
    (!commit.is_empty()).then(|| format!("detached at {commit}"))
}

pub async fn gh(args: &[&str]) -> Result<Value, String> {
    gh_with_input(args, None).await
}

/// `gh api …` with an optional JSON body on stdin (`--input -`).
pub async fn gh_with_input(args: &[&str], input: Option<&str>) -> Result<Value, String> {
    let mut argv = vec!["gh", "api"];
    argv.extend_from_slice(args);
    let out = run_with_input(&argv, None, input).await?;
    if out.trim().is_empty() {
        return Ok(Value::Null);
    }
    serde_json::from_str(&out).map_err(|e| format!("gh api returned something other than JSON: {e}"))
}

pub async fn issues(repo: &str) -> Result<Vec<Issue>, String> {
    issue_page(repo, "open", 1).await.map(|(issues, _)| issues)
}

/// Loads one bounded GitHub issue page. `has_more` is based on raw API rows so pages containing
/// pull requests still advance even though `parse_issues` removes those rows.
pub async fn issue_page(repo: &str, state: &str, page: u32) -> Result<(Vec<Issue>, bool), String> {
    if !matches!(state, "open" | "closed") {
        return Err("GitHub issue state must be open or closed.".into());
    }
    let endpoint = format!("repos/{repo}/issues?state={state}&per_page=100&page={}", page.max(1));
    let response = gh(&[&endpoint]).await?;
    let has_more = response.as_array().is_some_and(|rows| rows.len() == 100);
    Ok((parse_issues(&response), has_more))
}

/// Files an owner-reviewed issue brief. The request creates an issue only; it does not start an
/// agent. `agent:ready`, when selected by the owner, is a workflow label consumed separately by
/// the repo's runner.
pub async fn create_issue(repo: &str, draft: &IssueDraft) -> Result<Issue, String> {
    let endpoint = format!("repos/{repo}/issues");
    let response =
        gh_with_input(&["-X", "POST", &endpoint, "--input", "-"], Some(&issue_payload(draft).to_string())).await?;
    let Some(number) = response.get("number").and_then(Value::as_u64) else {
        return Err("GitHub created an issue but did not return its number.".into());
    };
    Ok(Issue {
        number,
        title: response.get("title").and_then(Value::as_str).unwrap_or(&draft.title).to_string(),
        body: response.get("body").and_then(Value::as_str).unwrap_or("").to_string(),
        url: response.get("html_url").and_then(Value::as_str).unwrap_or("").to_string(),
        state: "open".into(),
        labels: draft.labels(),
        updated_at: response.get("updated_at").and_then(Value::as_str).unwrap_or("").to_string(),
        comments: 0,
    })
}

pub fn issue_payload(draft: &IssueDraft) -> Value {
    json!({"title": draft.title.trim(), "body": draft.body(), "labels": draft.labels()})
}

/// Prompt for a user-reviewed intake chat. The composer remains unsent until the owner presses Send.
pub fn issue_refinement_prompt(draft: &IssueDraft) -> String {
    format!(
        "Help refine a GitHub issue brief for {}. Research relevant context when available, separate confirmed facts from assumptions, and ask focused questions if the scope or success criteria are unclear. Do not propose an implementation plan, edit files, create the issue, or start work. Return a concise brief with: title, problem and desired outcome, context and research links, measurable success criteria, and constraints/non-goals. Keep the solution open for the future implementation agent.\n\nInitial title: {}\n\nProblem or desired change:\n{}\n\nContext and research:\n{}\n\nSuccess criteria:\n{}\n\nConstraints and non-goals:\n{}",
        draft.repo,
        if draft.title.trim().is_empty() { "(not set)" } else { draft.title.trim() },
        if draft.problem.trim().is_empty() { "(not set)" } else { draft.problem.trim() },
        if draft.context.trim().is_empty() { "(not set)" } else { draft.context.trim() },
        if draft.success_criteria.trim().is_empty() { "(not set)" } else { draft.success_criteria.trim() },
        if draft.constraints.trim().is_empty() { "(not set)" } else { draft.constraints.trim() },
    )
}

/// First pass for a local MSeries Assistant session. Keep it focused on structuring the request;
/// the owner may then switch to a connected hosted provider in the same T3 composer for research.
pub const MAX_LOCAL_ISSUE_INTAKE_CHARS: usize = 16_000;

pub fn issue_local_intake_prompt(draft: &IssueDraft) -> String {
    format!(
        "Help structure an initial GitHub issue brief for {} using only the information below and tools that are already available. This is an intake pass. Do not edit files, run implementation work, create or modify a GitHub issue, choose an implementation, or claim research you did not perform. Preserve material facts and success criteria; label assumptions and additions. Do not repeat clear input verbatim. Return a concise brief of at most 220 words with: problem/outcome; confirmed context and assumptions; observable success criteria; constraints/non-goals; and only questions that materially change scope. Leave the solution open for a later implementation agent.\n\nInitial title: {}\n\nProblem or desired change:\n{}\n\nContext and research:\n{}\n\nSuccess criteria:\n{}\n\nConstraints and non-goals:\n{}",
        draft.repo,
        if draft.title.trim().is_empty() { "(not set)" } else { draft.title.trim() },
        if draft.problem.trim().is_empty() { "(not set)" } else { draft.problem.trim() },
        if draft.context.trim().is_empty() { "(not set)" } else { draft.context.trim() },
        if draft.success_criteria.trim().is_empty() { "(not set)" } else { draft.success_criteria.trim() },
        if draft.constraints.trim().is_empty() { "(not set)" } else { draft.constraints.trim() },
    )
}

pub async fn comments(repo: &str, number: u64) -> Result<Vec<(String, String, String)>, String> {
    let v = gh(&[&format!("repos/{repo}/issues/{number}/comments?per_page=50")]).await?;
    Ok(v.as_array()
        .map(|a| {
            a.iter()
                .map(|c| {
                    (
                        c.get("user").and_then(|u| u.get("login")).and_then(Value::as_str).unwrap_or("").to_string(),
                        c.get("created_at").and_then(Value::as_str).unwrap_or("").to_string(),
                        c.get("body").and_then(Value::as_str).unwrap_or("").to_string(),
                    )
                })
                .collect()
        })
        .unwrap_or_default())
}

/// Creates the workflow labels that are missing in the repo (errors for existing ones are ignored).
pub async fn ensure_labels(repo: &str) {
    let existing: Vec<String> = gh(&[&format!("repos/{repo}/labels?per_page=100")])
        .await
        .ok()
        .and_then(|v| {
            v.as_array()
                .map(|a| a.iter().filter_map(|l| l.get("name").and_then(Value::as_str).map(str::to_string)).collect())
        })
        .unwrap_or_default();
    for (name, color, description) in LABELS {
        if existing.iter().any(|e| e == name) {
            continue;
        }
        let _ = gh(&[
            "-X",
            "POST",
            &format!("repos/{repo}/labels"),
            "-f",
            &format!("name={name}"),
            "-f",
            &format!("color={color}"),
            "-f",
            &format!("description={description}"),
        ])
        .await;
    }
}

pub async fn add_label(repo: &str, number: u64, label: &str) -> Result<(), String> {
    gh(&["-X", "POST", &format!("repos/{repo}/issues/{number}/labels"), "-f", &format!("labels[]={label}")])
        .await
        .map(|_| ())
}

pub async fn remove_label(repo: &str, number: u64, label: &str) -> Result<(), String> {
    gh(&["-X", "DELETE", &format!("repos/{repo}/issues/{number}/labels/{label}")]).await.map(|_| ())
}

pub async fn comment(repo: &str, number: u64, body: &str) -> Result<(), String> {
    gh(&["-X", "POST", &format!("repos/{repo}/issues/{number}/comments"), "-f", &format!("body={body}")])
        .await
        .map(|_| ())
}

/// The first message of a thread started from an issue.
pub fn issue_prompt(repo: &str, issue: &Issue) -> String {
    let mut p = format!(
        "Work GitHub issue #{} in {repo}: {}\n\n{}\n\n",
        issue.number,
        issue.title,
        if issue.body.trim().is_empty() { "(no description)" } else { issue.body.trim() }
    );
    p.push_str(&format!(
        "When done, open a pull request against the repo's development branch whose description closes #{} and \
carries the handoff summary (what was done, what is open, files touched, decisions). Never push to main.",
        issue.number
    ));
    p
}

/// The provider instance and default model for an unattended task.
pub fn runner_selection(providers: &[Provider]) -> Option<(Provider, String, String)> {
    let (p, reason) = pick_provider(providers)?;
    let model =
        p.models.iter().find(|m| m.is_default == Some(true)).or(p.models.first()).map(|m| m.key().to_string())?;
    Some((p.clone(), model, reason))
}

/// The scheduled-task payload for a repo's runner. `runtimeMode` is the provider's supervised mode:
/// full access stays an explicit per-thread choice.
pub fn runner_task(repo: &str, project_id: &str, provider: &Provider, model: &str, existing_id: Option<&str>) -> Value {
    let mut v = json!({
        "title": format!("Runner: {repo}"),
        "prompt": runner_prompt(repo),
        "enabled": true,
        "schedule": {"type": "interval", "everyMs": RUNNER_INTERVAL_MS},
        "projectId": project_id,
        "workspaceStrategy": {"type": "root"},
        "modelSelection": {"instanceId": provider.instance_id, "model": model},
        "runtimeMode": "auto",
        "interactionMode": "default",
        "createdBy": "user",
        "creationSource": "web",
    });
    if let Some(id) = existing_id {
        v["id"] = json!(id);
    }
    v
}

/// The prompt of the webhook task: GitHub's `issues.labeled` payload names the issue.
pub fn webhook_prompt(repo: &str) -> String {
    format!(
        "Issue #{{{{body.issue.number}}}} \"{{{{body.issue.title}}}}\" in {repo} was just labeled agent:ready. If it is not \
labeled agent:running and no other agent is running in that repo (unless it is labeled parallel-ok), label it \
agent:running, work it to a PR that closes it, run the repo's checks, then label it agent:done. If it fails twice, \
label it agent:blocked and comment with the error. Never push to main."
    )
}

/// Whether a task's webhook URL can be reached by GitHub: an absolute URL that is not loopback.
pub fn endpoint_reachable(url: Option<&str>) -> bool {
    let Some(u) = url else { return false };
    let host = u.split("://").nth(1).unwrap_or("").split('/').next().unwrap_or("").split(':').next().unwrap_or("");
    (u.starts_with("https://") || u.starts_with("http://"))
        && !host.is_empty()
        && !matches!(host, "127.0.0.1" | "localhost" | "::1" | "[::1]" | "0.0.0.0")
}

/// The webhook-triggered task for a repo: GitHub's `issues` event, `labeled` action, label
/// `agent:ready`, signed with the shared secret in `X-Hub-Signature-256`. `secret` None keeps the
/// stored one on an update.
pub fn webhook_task(
    repo: &str,
    project_id: &str,
    provider: &Provider,
    model: &str,
    existing_id: Option<&str>,
    secret: Option<&str>,
) -> Value {
    let mut signature = json!({"header": "x-hub-signature-256", "encoding": "hex", "prefix": "sha256="});
    if let Some(s) = secret {
        signature["secret"] = json!(s);
    }
    let mut v = json!({
        "title": format!("Webhook: {repo}"),
        "prompt": webhook_prompt(repo),
        "enabled": true,
        "schedule": {
            "type": "webhook",
            "signature": signature,
            "filters": [
                {"path": "headers.x-github-event", "op": "equals", "value": "issues"},
                {"path": "body.action", "op": "equals", "value": "labeled"},
                {"path": "body.label.name", "op": "equals", "value": "agent:ready"}
            ]
        },
        "projectId": project_id,
        "workspaceStrategy": {"type": "root"},
        "modelSelection": {"instanceId": provider.instance_id, "model": model},
        "runtimeMode": "auto",
        "interactionMode": "default",
        "createdBy": "user",
        "creationSource": "web",
    });
    if let Some(id) = existing_id {
        v["id"] = json!(id);
    }
    v
}

/// A fresh signing secret for a GitHub hook (32 hex characters from GLib's RNG).
pub fn new_secret() -> String {
    (0..8).map(|_| format!("{:08x}", glib::random_int())).collect()
}

/// The GitHub hook body for `POST /repos/{repo}/hooks`: the `issues` event to the task's URL, JSON,
/// signed with `secret`.
pub fn github_hook_body(url: &str, secret: &str) -> Value {
    json!({
        "name": "web",
        "active": true,
        "events": ["issues"],
        "config": {"url": url, "content_type": "json", "secret": secret, "insecure_ssl": "0"}
    })
}

/// Per-run provider rotation: for every runner and webhook task this client installed (titles
/// "Runner: …" / "Webhook: …"), the upsert that moves it to the provider with the most capacity now,
/// when that differs from the one it has. The read model's fields are passed back; the webhook
/// schedule without a secret keeps the stored one.
pub fn rotate_tasks(tasks: &[Value], providers: &[Provider]) -> Vec<(String, Value, String)> {
    let Some((provider, model, reason)) = runner_selection(providers) else { return Vec::new() };
    let mut out = Vec::new();
    for t in tasks {
        let title = t.get("title").and_then(Value::as_str).unwrap_or("");
        if !(title.starts_with("Runner: ") || title.starts_with("Webhook: ")) {
            continue;
        }
        let current = t.get("modelSelection").and_then(|m| m.get("instanceId")).and_then(Value::as_str).unwrap_or("");
        if current == provider.instance_id {
            continue;
        }
        let Some(id) = t.get("id").and_then(Value::as_str) else { continue };
        let mut v = json!({
            "id": id,
            "requireExisting": true,
            "title": title,
            "prompt": t.get("prompt").cloned().unwrap_or(Value::Null),
            "enabled": t.get("enabled").cloned().unwrap_or(json!(true)),
            "schedule": t.get("schedule").cloned().unwrap_or(Value::Null),
            "projectId": t.get("projectId").cloned().unwrap_or(Value::Null),
            "workspaceStrategy": t.get("workspaceStrategy").cloned().unwrap_or(json!({"type": "root"})),
            "modelSelection": {"instanceId": provider.instance_id, "model": model},
            "runtimeMode": t.get("runtimeMode").cloned().unwrap_or(json!("auto")),
            "interactionMode": t.get("interactionMode").cloned().unwrap_or(json!("default")),
        });
        if let Some(thread) = t.get("threadId") {
            v["threadId"] = thread.clone();
        }
        out.push((title.to_string(), v, format!("{} ({reason})", provider.name())));
    }
    out
}

pub fn now_iso() -> String {
    glib::DateTime::now_utc().and_then(|d| d.format_iso8601()).map(|s| s.to_string()).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn remotes_parse() {
        assert_eq!(
            repo_from_remote("git@github.com:techmore/ElementaryOS_MSeries.git").as_deref(),
            Some("techmore/ElementaryOS_MSeries")
        );
        assert_eq!(repo_from_remote("https://github.com/techmore/rupert").as_deref(), Some("techmore/rupert"));
        assert_eq!(repo_from_remote("https://gitlab.com/x/y"), None);
    }

    #[test]
    fn current_branch_reads_the_live_git_head_without_a_shell() {
        use std::process::Command;
        use std::time::{SystemTime, UNIX_EPOCH};

        let nonce = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let path = std::env::temp_dir().join(format!("t3r-current-branch-{}-{nonce}", std::process::id()));
        std::fs::create_dir_all(&path).unwrap();
        let init =
            Command::new("git").args(["init", "-q", "-b", "fresh-checkout"]).current_dir(&path).status().unwrap();
        assert!(init.success(), "git init should create the fixture repository");

        let branch = glib::MainContext::new().block_on(current_branch(path.to_str().unwrap()));
        assert_eq!(branch.as_deref(), Some("fresh-checkout"));
        std::fs::remove_dir_all(path).unwrap();
    }

    #[test]
    fn issue_chat_associations_preserve_legacy_and_explicit_empty() {
        let mut config = Config::default();
        config.started.insert("o/r#7".into(), "legacy-thread".into());
        assert_eq!(config.chats_for_issue("o/r#7"), vec!["legacy-thread"]);

        config.issue_chats.insert("o/r#7".into(), vec!["chat-a".into(), "chat-b".into()]);
        assert_eq!(config.chats_for_issue("o/r#7"), vec!["chat-a", "chat-b"]);
        config.issue_chats.insert("o/r#7".into(), Vec::new());
        assert!(config.chats_for_issue("o/r#7").is_empty());

        let old: Config = serde_json::from_value(json!({"repos": [], "started": {"o/r#7": "legacy-thread"}})).unwrap();
        assert_eq!(old.chats_for_issue("o/r#7"), vec!["legacy-thread"]);
    }

    #[test]
    fn issue_brief_separates_acceptance_contract_from_execution_routing() {
        let mut draft = IssueDraft {
            repo: "o/r".into(),
            title: "Add repo issue intake".into(),
            problem: "Owners need a place to refine a request.".into(),
            context: "Current issues can be read from the Repos page.".into(),
            success_criteria: "A filed issue describes observable outcomes.".into(),
            constraints: "Do not prescribe implementation.".into(),
            lane: "feature".into(),
            priority: "p1".into(),
            agent_ready: false,
            ..Default::default()
        };
        assert!(draft.body().contains("## Success criteria"));
        assert!(!draft.body().contains("implementation plan"));
        assert_eq!(draft.labels(), vec!["lane:feature", "p1"]);
        let payload = issue_payload(&draft);
        assert_eq!(payload["title"], "Add repo issue intake");
        assert_eq!(payload["labels"], json!(["lane:feature", "p1"]));
        assert!(payload.get("modelSelection").is_none());

        draft.agent_ready = true;
        assert_eq!(draft.labels(), vec!["lane:feature", "p1", "agent:ready"]);
        assert!(issue_refinement_prompt(&draft).contains("Keep the solution open"));
    }

    #[test]
    fn local_issue_intake_prompt_is_read_only_and_leaves_solution_open() {
        let draft = IssueDraft {
            repo: "owner/repo".into(),
            title: "Slow startup".into(),
            problem: "The client takes too long to open".into(),
            ..Default::default()
        };
        let prompt = issue_local_intake_prompt(&draft);
        assert!(prompt.contains("owner/repo"));
        assert!(prompt.contains("confirmed context and assumptions"));
        assert!(prompt.contains("Do not edit files"));
        assert!(prompt.contains("Leave the solution open"));
        assert!(prompt.contains("at most 220 words"));
        assert!(prompt.contains("Do not repeat clear input verbatim"));
    }

    #[test]
    fn issue_brief_requires_problem_and_success_before_filing() {
        let mut draft = IssueDraft::default();
        assert_eq!(draft.validation_error(), Some("Add an issue title before filing."));
        draft.title = "A title".into();
        assert_eq!(draft.validation_error(), Some("Describe the problem or desired change before filing."));
        draft.problem = "The problem".into();
        assert_eq!(draft.validation_error(), Some("Add success criteria so the issue says what done looks like."));
        draft.success_criteria = "An observable outcome".into();
        assert_eq!(draft.validation_error(), None);
    }

    #[test]
    fn issues_sort_by_priority_then_lane() {
        let v = json!([
            {"number": 1, "title": "a", "labels": [{"name": "lane:maintenance"}, {"name": "p1"}]},
            {"number": 2, "title": "b", "labels": [{"name": "lane:build"}, {"name": "p1"}]},
            {"number": 3, "title": "pr", "pull_request": {}, "labels": []},
            {"number": 4, "title": "c", "labels": [{"name": "p0"}, {"name": "agent:ready"}]},
            {"number": 5, "title": "d", "labels": []},
        ]);
        let issues = parse_issues(&v);
        assert_eq!(issues.iter().map(|i| i.number).collect::<Vec<_>>(), vec![4, 2, 1, 5]);
        assert_eq!(issues[0].agent(), Some("ready"));
        assert_eq!(issues[1].lane(), Some("build"));
    }

    #[test]
    fn webhook_task_filters_and_rotation() {
        let ready = |driver: &str| Provider {
            instance_id: driver.into(),
            driver: driver.into(),
            enabled: true,
            installed: true,
            auth: json!({"status": "authenticated"}),
            models: vec![crate::t3::model::ProviderModel {
                slug: "m".into(),
                is_default: Some(true),
                ..Default::default()
            }],
            ..Default::default()
        };
        let claude = ready("claudeAgent");
        let t = webhook_task("o/r", "pid", &claude, "m", None, Some("s3cret"));
        assert_eq!(t["schedule"]["type"], "webhook");
        assert_eq!(t["schedule"]["signature"]["header"], "x-hub-signature-256");
        assert_eq!(t["schedule"]["signature"]["secret"], "s3cret");
        let filters = t["schedule"]["filters"].as_array().unwrap();
        assert!(filters.iter().any(|f| f["path"] == "body.label.name" && f["value"] == "agent:ready"));
        assert!(filters.iter().any(|f| f["path"] == "headers.x-github-event" && f["value"] == "issues"));
        assert!(t["prompt"].as_str().unwrap().contains("{{body.issue.number}}"));
        assert!(
            webhook_task("o/r", "pid", &claude, "m", Some("t1"), None)["schedule"]["signature"].get("secret").is_none()
        );
        assert!(endpoint_reachable(Some("https://ser8.tail1234.ts.net:3773/api/webhooks/abc")));
        assert!(!endpoint_reachable(Some("http://127.0.0.1:3773/api/webhooks/abc")));
        assert!(!endpoint_reachable(None));
        assert_eq!(new_secret().len(), 64);
        assert_eq!(github_hook_body("https://x/y", "k")["config"]["secret"], "k");

        // Rotation: only our tasks move, and only when the best provider differs.
        let codex = ready("codex");
        let tasks = vec![
            json!({"id": "t1", "title": "Runner: o/r", "prompt": "p", "enabled": true, "schedule": {"type": "interval", "everyMs": 300000}, "projectId": "pid", "workspaceStrategy": {"type": "root"}, "modelSelection": {"instanceId": "codex", "model": "x"}, "runtimeMode": "auto", "interactionMode": "default", "threadId": null}),
            json!({"id": "t2", "title": "Webhook: o/r", "prompt": "p", "enabled": true, "schedule": {"type": "webhook", "signature": {"header": "x-hub-signature-256", "encoding": "hex", "prefix": "sha256="}, "filters": []}, "projectId": "pid", "workspaceStrategy": {"type": "root"}, "modelSelection": {"instanceId": "claudeAgent", "model": "m"}, "runtimeMode": "auto", "interactionMode": "default"}),
            json!({"id": "t3", "title": "Nightly notes", "modelSelection": {"instanceId": "codex", "model": "x"}}),
        ];
        let moves = rotate_tasks(&tasks, &[claude.clone(), codex.clone()]);
        assert_eq!(moves.len(), 1, "{moves:?}");
        assert_eq!(moves[0].1["id"], "t1");
        assert_eq!(moves[0].1["modelSelection"]["instanceId"], "claudeAgent");
        assert_eq!(moves[0].1["requireExisting"], true);
        assert_eq!(moves[0].1["schedule"]["everyMs"], 300000);
        assert!(rotate_tasks(&tasks, &[]).is_empty());
    }

    #[test]
    fn runner_task_is_supervised() {
        let p = Provider { instance_id: "claudeAgent".into(), driver: "claudeAgent".into(), ..Default::default() };
        let t = runner_task("o/r", "pid", &p, "claude-opus-5-5", None);
        assert_eq!(t["runtimeMode"], "auto");
        assert_eq!(t["schedule"]["everyMs"], 300000);
        assert!(t["prompt"].as_str().unwrap().contains("agent:ready"));
    }
}
