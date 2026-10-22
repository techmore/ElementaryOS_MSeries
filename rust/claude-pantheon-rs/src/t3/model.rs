//! The parts of the T3 contracts this client reads, decoded leniently: unknown fields and variants are
//! kept as `Value` or skipped so a newer server does not break the client.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{HashMap, HashSet};

fn active_run_status(status: &str) -> bool {
    matches!(status, "preparing" | "queued" | "starting" | "running" | "waiting" | "pending")
}

#[derive(Deserialize, Default, Clone, Debug)]
#[serde(default)]
pub struct ProviderModel {
    pub slug: String,
    pub id: Option<String>,
    pub name: Option<String>,
    pub label: Option<String>,
    pub aliases: Option<Vec<String>>,
    #[serde(rename = "isDefault")]
    pub is_default: Option<bool>,
}

impl ProviderModel {
    /// What `modelSelection.model` takes.
    pub fn key(&self) -> &str {
        if !self.slug.is_empty() { &self.slug } else { self.id.as_deref().unwrap_or("") }
    }

    pub fn display(&self) -> &str {
        self.label.as_deref().or(self.name.as_deref()).unwrap_or_else(|| self.key())
    }
}

#[derive(Deserialize, Default, Clone, Debug)]
#[serde(default)]
pub struct Provider {
    #[serde(rename = "instanceId")]
    pub instance_id: String,
    pub driver: String,
    #[serde(rename = "displayName")]
    pub display_name: Option<String>,
    #[serde(rename = "accentColor")]
    pub accent_color: Option<String>,
    pub enabled: bool,
    pub installed: bool,
    pub version: Option<String>,
    pub status: Value,
    pub auth: Value,
    pub availability: Option<String>,
    pub message: Option<String>,
    pub models: Vec<ProviderModel>,
    #[serde(rename = "supportedRuntimeModes")]
    pub supported_runtime_modes: Option<Vec<String>>,
    #[serde(rename = "nativeSessions")]
    pub native_sessions: Option<Value>,
    #[serde(rename = "usageLimits")]
    pub usage_limits: Option<UsageLimits>,
}

/// One rolling window of a provider's plan: the 5-hour session, the week, or the month.
#[derive(Deserialize, Default, Clone, Debug)]
#[serde(default)]
pub struct UsageWindow {
    pub id: String,
    pub kind: String,
    pub label: String,
    #[serde(rename = "usedPercent")]
    pub used_percent: f64,
    #[serde(rename = "resetsAt")]
    pub resets_at: Option<String>,
    #[serde(rename = "windowDurationMins")]
    pub window_duration_mins: Option<u64>,
}

#[derive(Deserialize, Default, Clone, Debug)]
#[serde(default)]
pub struct UsageLimits {
    #[serde(rename = "checkedAt")]
    pub checked_at: String,
    pub windows: Vec<UsageWindow>,
    pub unavailable: Option<Value>,
    #[serde(rename = "resetCredits")]
    pub reset_credits: Option<Value>,
}

impl Provider {
    pub fn window(&self, kind: &str) -> Option<&UsageWindow> {
        self.usage_limits.as_ref()?.windows.iter().find(|w| w.kind == kind)
    }
}

/// Which provider the next unattended task should use: the lowest session use among the ready
/// providers whose windows are under 90 %, weekly as the tie-break, then the owner's preference
/// (Claude, Codex, Grok, OpenCode) when all are open.
pub fn pick_provider(providers: &[Provider]) -> Option<(&Provider, String)> {
    const PREFERENCE: [&str; 4] = ["claudeAgent", "codex", "grok", "opencode"];
    let rank = |p: &Provider| PREFERENCE.iter().position(|d| *d == p.driver).unwrap_or(PREFERENCE.len());
    let mut open: Vec<&Provider> = providers
        .iter()
        .filter(|p| p.ready())
        .filter(|p| p.usage_limits.as_ref().is_none_or(|u| u.windows.iter().all(|w| w.used_percent < 90.0)))
        .collect();
    if open.is_empty() {
        return None;
    }
    let session = |p: &Provider| p.window("session").map(|w| w.used_percent).unwrap_or(0.0);
    let weekly = |p: &Provider| p.window("weekly").map(|w| w.used_percent).unwrap_or(0.0);
    open.sort_by(|a, b| {
        session(a)
            .partial_cmp(&session(b))
            .unwrap()
            .then(weekly(a).partial_cmp(&weekly(b)).unwrap())
            .then(rank(a).cmp(&rank(b)))
    });
    let best = open[0];
    let busiest = providers
        .iter()
        .filter(|p| p.ready() && p.instance_id != best.instance_id)
        .filter_map(|p| p.window("session").or(p.window("weekly")).map(|w| (p, w)))
        .max_by(|a, b| a.1.used_percent.partial_cmp(&b.1.used_percent).unwrap());
    let reason = match busiest {
        Some((p, w)) => format!(
            "next task → {} ({} {:.0}% session); {} at {:.0}% until {}",
            best.name(),
            if session(best) > 0.0 { "" } else { "no" },
            session(best),
            p.name(),
            w.used_percent,
            crate::look::clock(w.resets_at.as_deref().unwrap_or(""))
        ),
        None => format!("next task → {} ({:.0}% session)", best.name(), session(best)),
    };
    Some((best, reason.replace("( ", "(")))
}

impl Provider {
    pub fn name(&self) -> String {
        self.display_name.clone().unwrap_or_else(|| {
            if self.driver == "claudeAgent" {
                return "Claude".into();
            }
            let mut c = self.driver.chars();
            match c.next() {
                Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
                None => String::new(),
            }
        })
    }

    pub fn status_text(&self) -> String {
        match &self.status {
            Value::String(s) => s.clone(),
            Value::Object(o) => o.get("status").and_then(Value::as_str).unwrap_or("").to_string(),
            _ => String::new(),
        }
    }

    pub fn auth_text(&self) -> String {
        match &self.auth {
            Value::String(s) => s.clone(),
            Value::Object(o) => o
                .get("status")
                .or_else(|| o.get("state"))
                .or_else(|| o.get("kind"))
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            _ => String::new(),
        }
    }

    pub fn is_acp_agent(&self) -> bool {
        self.driver == "acpRegistry"
    }

    /// Authenticated and usable now. ACP agents report readiness from their
    /// successful session handshake rather than an OAuth auth state.
    pub fn ready(&self) -> bool {
        let auth = self.auth_text();
        if !self.enabled || !self.installed || self.availability.as_deref() == Some("unavailable") {
            return false;
        }

        if self.is_acp_agent() {
            return self.status_text() == "ready";
        }

        auth == "authenticated" || auth == "ready" || auth == "ok" || auth == "signed-in"
    }
}

#[derive(Deserialize, Default, Debug)]
#[serde(default)]
pub struct ServerConfig {
    pub cwd: String,
    pub providers: Vec<Provider>,
    pub environment: Value,
    pub settings: Value,
}

#[derive(Deserialize, serde::Serialize, Default, Clone, Debug)]
#[serde(default)]
pub struct Project {
    pub id: String,
    pub title: String,
    #[serde(rename = "workspaceRoot")]
    pub workspace_root: String,
    #[serde(rename = "repositoryIdentity")]
    pub repository_identity: Option<Value>,
    #[serde(rename = "deletedAt")]
    pub deleted_at: Option<String>,
    #[serde(rename = "defaultModelSelection")]
    pub default_model_selection: Option<Value>,
}

#[derive(Deserialize, Default, Clone, Debug)]
#[serde(default)]
pub struct ThreadShell {
    pub id: String,
    #[serde(rename = "projectId")]
    pub project_id: String,
    pub title: String,
    #[serde(rename = "providerInstanceId")]
    pub provider_instance_id: String,
    #[serde(rename = "modelSelection")]
    pub model_selection: Value,
    #[serde(rename = "runtimeMode")]
    pub runtime_mode: String,
    #[serde(rename = "interactionMode")]
    pub interaction_mode: String,
    #[serde(rename = "createdAt")]
    pub created_at: String,
    #[serde(rename = "updatedAt")]
    pub updated_at: String,
    #[serde(rename = "archivedAt")]
    pub archived_at: Option<String>,
    #[serde(rename = "historyOrigin")]
    pub history_origin: Option<Value>,
    #[serde(rename = "activeProviderThreadId")]
    pub active_provider_thread_id: Option<String>,
    /// Everything else the shell row carries (status, pending counts, …).
    #[serde(flatten)]
    pub rest: Value,
}

impl ThreadShell {
    pub fn is_running(&self) -> bool {
        let r = &self.rest;
        r.get("activeRunId").is_some_and(|v| !v.is_null())
            || r.get("status").and_then(Value::as_str).is_some_and(active_run_status)
            || r.get("latestRun").and_then(|v| v.get("status")).and_then(Value::as_str).is_some_and(active_run_status)
    }

    pub fn pending_requests(&self) -> u64 {
        let r = &self.rest;
        r.get("pendingRuntimeRequests")
            .filter(|v| !v.is_null())
            .map(|v| v.as_array().map_or(v.as_u64().unwrap_or(0), |a| a.len() as u64))
            .or_else(|| r.get("pendingRuntimeRequestCount").and_then(Value::as_u64))
            .or_else(|| r.get("pendingRuntimeRequest").filter(|v| !v.is_null()).map(|_| 1))
            .unwrap_or(0)
    }

    /// The native session uuid this thread was imported from, when it came from Claude Code's history.
    pub fn native_session_id(&self) -> Option<String> {
        let h = self.history_origin.as_ref()?;
        h.get("nativeId")
            .or_else(|| h.get("sessionId"))
            .or_else(|| h.get("ref").and_then(|r| r.get("nativeId")))
            .and_then(Value::as_str)
            .map(str::to_string)
    }
}

/// `ThreadId` → `ThreadShell` plus the projects, as the shell snapshot carries them.
#[derive(Deserialize, Default, Debug, Clone)]
pub struct Shell {
    pub projects: Vec<Project>,
    pub threads: Vec<ThreadShell>,
}

impl Shell {
    pub fn from_snapshot(snapshot: &Value) -> Shell {
        let mut shell = Shell::default();
        if let Some(projects) = snapshot.get("projects").and_then(Value::as_array) {
            for p in projects {
                let project = p.get("project").unwrap_or(p);
                if let Ok(mut project) = serde_json::from_value::<Project>(project.clone()) {
                    if project.title.is_empty() {
                        project.title = project.workspace_root.rsplit('/').next().unwrap_or("Project").to_string();
                    }
                    shell.projects.push(project);
                }
            }
        }
        for key in ["threads", "activeThreads", "archivedThreads"] {
            if let Some(threads) = snapshot.get(key).and_then(Value::as_array) {
                for t in threads {
                    let thread = t.get("thread").unwrap_or(t);
                    if let Ok(thread) = serde_json::from_value::<ThreadShell>(thread.clone()) {
                        shell.threads.push(thread);
                    }
                }
            }
        }
        shell
    }

    pub fn upsert_thread(&mut self, thread: ThreadShell) {
        match self.threads.iter_mut().find(|t| t.id == thread.id) {
            Some(slot) => *slot = thread,
            None => self.threads.push(thread),
        }
    }

    pub fn remove_thread(&mut self, id: &str) {
        self.threads.retain(|t| t.id != id);
    }

    pub fn upsert_project(&mut self, project: Project) {
        match self.projects.iter_mut().find(|p| p.id == project.id) {
            Some(slot) => *slot = project,
            None => self.projects.push(project),
        }
    }
}

/// One visible item of a thread, flattened from `visibleTurnItems[].item`.
#[derive(Deserialize, Serialize, Default, Clone, Debug)]
#[serde(default)]
pub struct TurnItem {
    pub id: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub status: String,
    pub text: String,
    pub streaming: bool,
    #[serde(rename = "runId")]
    pub run_id: Option<String>,
    #[serde(rename = "requestId")]
    pub request_id: Option<String>,
    #[serde(rename = "requestKind")]
    pub request_kind: Option<String>,
    pub prompt: Option<String>,
    pub reason: Option<String>,
    pub options: Option<Vec<Value>>,
    pub input: Option<String>,
    pub output: Option<String>,
    #[serde(rename = "exitCode")]
    pub exit_code: Option<i64>,
    #[serde(rename = "fileName")]
    pub file_name: Option<String>,
    pub additions: Option<u64>,
    pub deletions: Option<u64>,
    #[serde(rename = "diffStr")]
    pub diff_str: Option<String>,
    pub markdown: Option<String>,
    pub pattern: Option<String>,
    pub patterns: Option<Vec<String>>,
    pub name: Option<String>,
    pub title: Option<String>,
    pub steps: Option<Vec<Value>>,
    #[serde(rename = "sourceThreadId", skip_serializing_if = "Option::is_none")]
    pub source_thread_id: Option<String>,
    #[serde(rename = "sourceItemId", skip_serializing_if = "Option::is_none")]
    pub source_item_id: Option<String>,
    #[serde(flatten)]
    pub rest: Value,
}

impl TurnItem {
    pub fn is_pending_request(&self) -> bool {
        self.kind == "approval_request" && self.status != "completed" && self.status != "cancelled"
    }

    pub fn identity_key(&self) -> String {
        match (&self.source_thread_id, &self.source_item_id) {
            (Some(thread), Some(item)) => format!("{thread}\0{item}"),
            _ => self.id.clone(),
        }
    }
}

#[derive(Deserialize, Serialize, Default, Debug, Clone)]
pub struct ThreadView {
    pub items: Vec<TurnItem>,
    pub active_run_id: Option<String>,
    pub runs: Vec<Value>,
    /// The thread's checkpoints (restore points), as the projection carries them.
    pub checkpoints: Vec<Value>,
    /// Rebuilt from `items`; avoids a second serialized copy of every item identity.
    #[serde(skip)]
    pub(crate) item_positions: Option<HashMap<String, usize>>,
}

impl ThreadView {
    pub fn from_projection(p: &Value) -> ThreadView {
        let mut view = ThreadView::default();
        let visible = p.get("visibleTurnItems").and_then(Value::as_array);
        if let Some(rows) = visible.filter(|rows| !rows.is_empty()) {
            for row in rows {
                if let Ok(mut item) = serde_json::from_value::<TurnItem>(row.get("item").unwrap_or(row).clone()) {
                    item.source_thread_id = row
                        .get("sourceThreadId")
                        .and_then(Value::as_str)
                        .map(str::to_string)
                        .or_else(|| p.pointer("/thread/id").and_then(Value::as_str).map(str::to_string));
                    item.source_item_id = row
                        .get("sourceItemId")
                        .and_then(Value::as_str)
                        .map(str::to_string)
                        .or_else(|| Some(item.id.clone()));
                    view.items.push(item);
                }
            }
        } else if let Some(raw) = p.get("turnItems").and_then(Value::as_array) {
            for row in raw {
                if let Ok(mut item) = serde_json::from_value::<TurnItem>(row.clone()) {
                    item.source_thread_id = p.pointer("/thread/id").and_then(Value::as_str).map(str::to_string);
                    item.source_item_id = Some(item.id.clone());
                    view.items.push(item);
                }
            }
        }
        if let Some(c) = p.get("checkpoints").and_then(Value::as_array) {
            view.checkpoints = c.clone();
        }
        if let Some(runs) = p.get("runs").and_then(Value::as_array) {
            view.runs = runs.clone();
            view.active_run_id = runs
                .iter()
                .rev()
                .find(|r| r.get("status").and_then(Value::as_str).is_some_and(active_run_status))
                .and_then(|r| r.get("id"))
                .and_then(Value::as_str)
                .map(str::to_string);
        }
        view.rebuild_item_positions();
        view
    }

    pub(crate) fn rebuild_item_positions(&mut self) {
        let mut positions = HashMap::with_capacity(self.items.len());
        for (index, item) in self.items.iter().enumerate() {
            positions.entry(item.identity_key()).or_insert(index);
        }
        self.item_positions = Some(positions);
    }

    fn ensure_item_positions(&mut self) {
        if self.item_positions.is_none() {
            self.rebuild_item_positions();
        }
    }

    pub fn is_running(&self) -> bool {
        self.active_run_id.is_some()
            || self.runs.iter().any(|run| run.get("status").and_then(Value::as_str).is_some_and(active_run_status))
    }

    /// Apply a run projection event while retaining fields omitted by compact updates.
    pub fn upsert_run(&mut self, update: Value) {
        let id = update.get("id").and_then(Value::as_str);
        if let Some(id) = id {
            if let Some(current) = self.runs.iter_mut().find(|run| run.get("id").and_then(Value::as_str) == Some(id)) {
                if let (Some(current), Some(update)) = (current.as_object_mut(), update.as_object()) {
                    current.extend(update.iter().map(|(key, value)| (key.clone(), value.clone())));
                } else {
                    *current = update;
                }
            } else {
                self.runs.push(update);
            }
        }
        self.active_run_id = self
            .runs
            .iter()
            .rev()
            .find(|run| run.get("status").and_then(Value::as_str).is_some_and(active_run_status))
            .and_then(|run| run.get("id"))
            .and_then(Value::as_str)
            .map(str::to_string);
    }

    pub fn upsert(&mut self, item: TurnItem) {
        let key = item.identity_key();
        self.ensure_item_positions();
        let position = self.item_positions.as_ref().and_then(|positions| positions.get(&key)).copied();
        match position.and_then(|index| self.items.get_mut(index)) {
            Some(slot) => *slot = item,
            None => {
                let index = self.items.len();
                self.items.push(item);
                self.item_positions.as_mut().expect("item index initialized").insert(key, index);
            }
        }
    }

    /// Adds one T3 history page ahead of the current projection without replacing live updates.
    pub fn prepend_history(&mut self, mut older: Vec<crate::t3::history::ProjectedTurnItem>) -> usize {
        self.ensure_item_positions();
        older.sort_by_key(|row| row.position);
        let mut page = Vec::with_capacity(older.len());
        let mut page_keys = HashSet::new();
        for row in older {
            let mut item = row.item;
            item.source_thread_id = Some(row.source_thread_id);
            item.source_item_id = Some(row.source_item_id);
            let key = item.identity_key();
            let exists = self.item_positions.as_ref().is_some_and(|positions| positions.contains_key(&key));
            if !exists && page_keys.insert(key) {
                page.push(item);
            }
        }
        let count = page.len();
        if count > 0 {
            page.append(&mut self.items);
            self.items = page;
            self.rebuild_item_positions();
        }
        count
    }
}

// ---- usage ------------------------------------------------------------------------------------------

#[derive(Deserialize, Default, Clone, Debug)]
#[serde(default)]
pub struct UsageTotals {
    #[serde(rename = "uncachedInputTokens")]
    pub uncached_input: u64,
    #[serde(rename = "cachedInputTokens")]
    pub cached_input: Option<u64>,
    #[serde(rename = "cacheCreationTokens")]
    pub cache_creation: Option<u64>,
    #[serde(rename = "outputTokens")]
    pub output: u64,
    #[serde(rename = "reasoningTokens")]
    pub reasoning: u64,
}

impl UsageTotals {
    pub fn add(&mut self, o: &UsageTotals) {
        self.uncached_input += o.uncached_input;
        add_optional(&mut self.cached_input, o.cached_input);
        add_optional(&mut self.cache_creation, o.cache_creation);
        self.output += o.output;
        self.reasoning += o.reasoning;
    }
    pub fn input(&self) -> u64 {
        self.uncached_input + self.cached_input.unwrap_or_default() + self.cache_creation.unwrap_or_default()
    }
    pub fn total(&self) -> u64 {
        self.input() + self.output
    }
}

fn add_optional(total: &mut Option<u64>, value: Option<u64>) {
    if let Some(value) = value {
        *total = Some(total.unwrap_or_default() + value);
    }
}

#[derive(Deserialize, Default, Clone, Debug)]
#[serde(default)]
pub struct UsageBucket {
    pub day: String,
    pub provider: String,
    pub model: String,
    pub totals: UsageTotals,
    #[serde(rename = "costUsd")]
    pub cost_usd: f64,
    #[serde(rename = "cacheSavingsUsd")]
    pub cache_savings_usd: Option<f64>,
    #[serde(rename = "costSource")]
    pub cost_source: String,
    pub records: u64,
    pub sessions: u64,
}

#[derive(Deserialize, Default, Clone, Debug)]
#[serde(default)]
pub struct UsageSource {
    pub fingerprint: Value,
    pub status: String,
    #[serde(rename = "scannedFiles")]
    pub scanned_files: u64,
    #[serde(rename = "distinctSessions")]
    pub distinct_sessions: u64,
    pub message: Option<String>,
}

impl UsageSource {
    pub fn provider(&self) -> String {
        self.fingerprint.get("provider").and_then(Value::as_str).unwrap_or("").to_string()
    }
}

#[derive(Deserialize, Default, Clone, Debug)]
#[serde(default)]
pub struct UsageSummary {
    #[serde(rename = "sinceDay")]
    pub since_day: String,
    #[serde(rename = "untilDay")]
    pub until_day: String,
    pub buckets: Vec<UsageBucket>,
    pub sources: Vec<UsageSource>,
    pub pricing: Value,
    #[serde(rename = "scanDurationMs")]
    pub scan_duration_ms: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lenient_provider_decode() {
        let p: Provider = serde_json::from_value(serde_json::json!({
            "instanceId": "claude", "driver": "claude", "enabled": true, "installed": true, "version": "2.1",
            "status": "ready", "auth": {"status": "authenticated"}, "checkedAt": "x", "models": [{"id": "opus", "label": "Opus"}],
            "slashCommands": [], "skills": [], "somethingNew": {"a": 1}
        }))
        .unwrap();
        assert!(p.ready());
        assert_eq!(p.name(), "Claude");
        assert_eq!(p.models[0].display(), "Opus");
        assert_eq!(p.models[0].key(), "opus");
    }

    #[test]
    fn acp_agent_readiness_uses_session_status_not_oauth_auth() {
        let mut agent: Provider = serde_json::from_value(serde_json::json!({
            "instanceId": "acp-mseries-assistant",
            "driver": "acpRegistry",
            "displayName": "MSeries Assistant",
            "enabled": true,
            "installed": true,
            "status": "ready",
            "auth": "unknown"
        }))
        .unwrap();
        assert!(agent.is_acp_agent());
        assert!(agent.ready());

        agent.status = serde_json::json!("starting");
        assert!(!agent.ready());
        agent.status = serde_json::json!("ready");
        agent.enabled = false;
        assert!(!agent.ready());
        agent.enabled = true;
        agent.installed = false;
        assert!(!agent.ready());
        agent.installed = true;
        agent.availability = Some("unavailable".into());
        assert!(!agent.ready());
    }

    #[test]
    fn run_updates_merge_projection_and_settle_cached_running_state() {
        let mut view = ThreadView::from_projection(&serde_json::json!({
            "runs": [{"id": "run-1", "status": "running", "provider": "codex"}]
        }));
        assert!(view.is_running());
        view.upsert_run(serde_json::json!({"id": "run-1", "status": "completed"}));
        assert!(!view.is_running());
        assert_eq!(view.runs[0]["provider"], "codex");
        assert_eq!(view.runs[0]["status"], "completed");

        view.upsert_run(serde_json::json!({"id": "run-2", "status": "waiting"}));
        assert!(view.is_running());
        assert_eq!(view.active_run_id.as_deref(), Some("run-2"));
    }

    #[test]
    fn history_pages_prepend_in_position_order_and_keep_live_overlap_once() {
        use crate::t3::history::ProjectedTurnItem;

        let projected = |position, source_item_id: &str, text: &str| ProjectedTurnItem {
            position,
            source_thread_id: "thread-a".into(),
            source_item_id: source_item_id.into(),
            item: TurnItem {
                id: source_item_id.into(),
                kind: "assistant_message".into(),
                text: text.into(),
                ..Default::default()
            },
        };
        let mut view = ThreadView::default();
        view.upsert(TurnItem {
            id: "tail".into(),
            kind: "assistant_message".into(),
            text: "latest live text".into(),
            source_thread_id: Some("thread-a".into()),
            source_item_id: Some("tail".into()),
            ..Default::default()
        });

        let added = view.prepend_history(vec![
            projected(3, "older-3", "third"),
            projected(1, "older-1", "first"),
            projected(2, "older-2", "second"),
            projected(2, "older-2", "duplicate within page"),
            projected(4, "tail", "stale overlap"),
        ]);
        assert_eq!(added, 3);
        assert_eq!(
            view.items.iter().map(|item| item.source_item_id.as_deref().unwrap_or("")).collect::<Vec<_>>(),
            ["older-1", "older-2", "older-3", "tail"]
        );
        assert_eq!(view.items[3].text, "latest live text", "history overlap cannot replace a live update");

        let added = view
            .prepend_history(vec![projected(2, "older-2", "duplicate across pages"), projected(0, "oldest", "oldest")]);
        assert_eq!(added, 1);
        assert_eq!(view.items[0].source_item_id.as_deref(), Some("oldest"));
        assert_eq!(view.items.last().unwrap().text, "latest live text");
    }

    #[test]
    fn large_thread_upserts_keep_identity_index_after_cache_round_trip() {
        fn item(index: usize, text: &str) -> TurnItem {
            TurnItem {
                id: format!("item-{index}"),
                kind: "assistant_message".into(),
                text: text.into(),
                source_thread_id: Some("thread-large".into()),
                source_item_id: Some(format!("item-{index}")),
                ..Default::default()
            }
        }

        let mut view = ThreadView::default();
        for index in 0..20_000 {
            view.upsert(item(index, "initial"));
        }
        for index in (0..20_000).rev() {
            view.upsert(item(index, "updated"));
        }
        assert_eq!(view.items.len(), 20_000);
        assert_eq!(view.items[19_999].text, "updated");

        let encoded = serde_json::to_value(&view).unwrap();
        assert!(encoded.get("item_positions").is_none());
        assert!(encoded.get("history_item_keys").is_none());
        let mut legacy_encoded = encoded;
        legacy_encoded["history_item_keys"] = serde_json::json!(["thread-large\0item-0"]);
        let mut restored: ThreadView = serde_json::from_value(legacy_encoded).unwrap();
        assert!(restored.item_positions.is_none(), "the non-serialized index is rebuilt lazily");
        restored.upsert(item(19_999, "after cache"));
        assert_eq!(restored.items.len(), 20_000);
        assert_eq!(restored.items[19_999].text, "after cache");
    }
}

#[cfg(test)]
mod fixture_tests {
    use super::*;

    #[test]
    fn shell_snapshot_decodes() {
        let v: Value = serde_json::from_str(include_str!("../../tests/fixtures/shell-snapshot.json")).unwrap();
        let shell = Shell::from_snapshot(&v["snapshot"]);
        assert_eq!(shell.projects.len(), 1);
        assert_eq!(shell.projects[0].title, "Projects");
        assert_eq!(shell.threads.len(), 3);
        let claude = shell.threads.iter().find(|t| t.id.starts_with("import:claudeAgent:")).unwrap();
        assert_eq!(claude.provider_instance_id, "claudeAgent");
        assert!(!claude.is_running());
        assert_eq!(claude.pending_requests(), 0);
        assert!(!claude.title.is_empty());
    }

    #[test]
    fn enrichment_snapshot_keeps_threads() {
        let v: Value = serde_json::from_str(include_str!("../../tests/fixtures/shell-snapshot.json")).unwrap();
        let mut shell = Shell::from_snapshot(&v["snapshot"]);
        let enrichment = serde_json::json!({"projects": shell.projects.clone().into_iter().map(|p| serde_json::to_value(p).unwrap()).collect::<Vec<_>>(), "threads": [], "archivedThreads": []});
        let fresh = Shell::from_snapshot(&enrichment);
        assert!(fresh.threads.is_empty());
        for p in fresh.projects {
            shell.upsert_project(p);
        }
        assert_eq!(shell.threads.len(), 3);
    }

    #[test]
    fn thread_snapshot_decodes() {
        let v: Value = serde_json::from_str(include_str!("../../tests/fixtures/thread-snapshot.json")).unwrap();
        let view = ThreadView::from_projection(&v["projection"]);
        assert_eq!(view.items.len(), 12);
        assert!(view.items.iter().any(|i| i.kind == "assistant_message"));
        assert!(view.items.iter().all(|i| !i.id.is_empty()));
        assert!(view.active_run_id.is_none());
    }

    #[test]
    fn rotation_prefers_the_emptiest_window() {
        let mk = |driver: &str, session: f64, weekly: f64| Provider {
            instance_id: driver.into(),
            driver: driver.into(),
            enabled: true,
            installed: true,
            auth: serde_json::json!({"status": "authenticated"}),
            usage_limits: Some(UsageLimits {
                windows: vec![
                    UsageWindow {
                        kind: "session".into(),
                        used_percent: session,
                        resets_at: Some("2026-10-22T02:00:00Z".into()),
                        ..Default::default()
                    },
                    UsageWindow { kind: "weekly".into(), used_percent: weekly, ..Default::default() },
                ],
                ..Default::default()
            }),
            ..Default::default()
        };
        let providers = vec![mk("claudeAgent", 94.0, 40.0), mk("codex", 20.0, 45.0), mk("grok", 20.0, 10.0)];
        let (best, reason) = pick_provider(&providers).unwrap();
        assert_eq!(best.driver, "grok", "lowest session, then lowest weekly: {reason}");
        assert!(reason.contains("Claude at 94%"), "{reason}");
        let tied = vec![mk("codex", 10.0, 10.0), mk("claudeAgent", 10.0, 10.0)];
        assert_eq!(pick_provider(&tied).unwrap().0.driver, "claudeAgent", "preference order breaks ties");
        let full = vec![mk("codex", 95.0, 10.0)];
        assert!(pick_provider(&full).is_none());
    }

    #[test]
    fn server_config_decodes() {
        let config: ServerConfig =
            serde_json::from_str(include_str!("../../tests/fixtures/server-config.json")).unwrap();
        assert!(config.providers.len() >= 5);
        let claude = config.providers.iter().find(|p| p.driver == "claudeAgent").unwrap();
        assert_eq!(claude.name(), "Claude");
        assert!(claude.ready());
        assert!(claude.models.iter().any(|m| m.key() == "claude-opus-5-5"));
        let codex = config.providers.iter().find(|p| p.driver == "codex").unwrap();
        assert!(!codex.ready());
        assert_eq!(codex.name(), "Codex");
    }
}
