//! The local, at-a-glance cache shared by the Dock quick surface and optional Wingpanel indicator:
//! running threads, pending permission prompts, and provider usage windows. The quick surface reads
//! this file with a file monitor; it never opens a second T3 connection or polls the server.

use crate::t3::model::{Provider, ThreadShell};
use serde_json::{Value, json};
use std::path::PathBuf;

pub fn path() -> PathBuf {
    crate::index::cache_dir().join("status.json")
}

pub fn build(
    connected: bool,
    label: &str,
    selected_provider_id: &str,
    providers: &[Provider],
    threads: &[ThreadShell],
) -> Value {
    let now = crate::workflow::now_iso();
    let running: Vec<Value> = threads
        .iter()
        .filter(|t| t.is_running() && t.pending_requests() == 0)
        .map(|t| {
            let provider = providers
                .iter()
                .find(|p| p.instance_id == t.provider_instance_id)
                .map(Provider::name)
                .unwrap_or_else(|| t.provider_instance_id.clone());
            json!({"id": t.id, "title": t.title, "provider": provider})
        })
        .collect();
    let pending: Vec<Value> = threads
        .iter()
        .filter(|t| t.pending_requests() > 0)
        .map(|t| json!({"id": t.id, "title": t.title, "count": t.pending_requests()}))
        .collect();
    let windows: Vec<Value> = providers
        .iter()
        .filter(|p| p.ready())
        .flat_map(|p| {
            let name = p.name();
            p.usage_limits
                .iter()
                .flat_map(|u| u.windows.iter())
                .map(move |w| {
                    json!({
                        "instanceId": p.instance_id, "provider": name, "kind": w.kind, "label": w.label,
                        "usedPercent": w.used_percent, "resetsAt": w.resets_at,
                    })
                })
                .collect::<Vec<_>>()
        })
        .collect();
    let next =
        crate::t3::model::pick_provider(providers).map(|(p, reason)| json!({"provider": p.name(), "reason": reason}));
    let selected_provider = providers
        .iter()
        .find(|provider| provider.instance_id == selected_provider_id)
        .map(Provider::name)
        .unwrap_or_default();
    json!({
        "schemaVersion": 1,
        "writtenAt": now,
        "updatedAt": now,
        "connected": connected,
        "stale": !connected,
        "server": label,
        "selectedProviderId": selected_provider_id,
        "selectedProvider": selected_provider,
        "running": running,
        "pendingPrompts": pending,
        "windows": windows,
        "nextTask": next,
    })
}

pub fn write(v: &Value) {
    let p = path();
    let payload = if v.get("connected").and_then(Value::as_bool) == Some(false) {
        std::fs::read(&p)
            .ok()
            .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
            .filter(|previous| previous.get("schemaVersion").and_then(Value::as_u64) == Some(1))
            .map(|previous| preserve_last_known(&previous, v))
            .unwrap_or_else(|| v.clone())
    } else {
        v.clone()
    };
    write_payload(&p, &payload);
}

/// Persist the last connection as stale when the client exits normally. The panel can then keep its
/// last-known account and usage without presenting old approvals or running work as live.
pub fn mark_stale() {
    let p = path();
    let Ok(bytes) = std::fs::read(&p) else { return };
    let Ok(previous) = serde_json::from_slice::<Value>(&bytes) else { return };
    if previous.get("schemaVersion").and_then(Value::as_u64) != Some(1) {
        return;
    }
    let stale = stale_after_shutdown(&previous, &crate::workflow::now_iso());
    write_payload(&p, &stale);
}

fn write_payload(p: &PathBuf, payload: &Value) {
    if let Some(dir) = p.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let tmp = p.with_extension("json.tmp");
    let Ok(bytes) = serde_json::to_vec_pretty(payload) else { return };
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    if let Ok(mut file) = options.open(&tmp)
        && std::io::Write::write_all(&mut file, &bytes).is_ok()
    {
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o600));
        }
        let _ = std::fs::rename(&tmp, p);
    }
}

/// Keep the previous account and data visible as explicitly stale when the transport drops.
/// Pending prompts and running threads are still carried for a useful last-known summary; consumers
/// must disable live actions until `connected` becomes true again.
fn preserve_last_known(previous: &Value, disconnected: &Value) -> Value {
    preserve_last_known_at(previous, disconnected, &crate::workflow::now_iso())
}

fn preserve_last_known_at(previous: &Value, disconnected: &Value, now: &str) -> Value {
    let mut next = disconnected.clone();
    for key in [
        "server",
        "selectedProviderId",
        "selectedProvider",
        "running",
        "pendingPrompts",
        "windows",
        "nextTask",
        "writtenAt",
    ] {
        if let Some(value) = previous.get(key) {
            next[key] = value.clone();
        }
    }
    next["connected"] = Value::Bool(false);
    next["stale"] = Value::Bool(true);
    next["updatedAt"] = Value::String(now.to_string());
    next
}

fn stale_after_shutdown(previous: &Value, now: &str) -> Value {
    let disconnected = json!({
        "schemaVersion": 1,
        "writtenAt": now,
        "updatedAt": now,
        "connected": false,
        "stale": true,
    });
    preserve_last_known_at(previous, &disconnected, now)
}

/// Remove the cached account and activity after an explicit unpair.
pub fn clear() {
    let p = path();
    let _ = std::fs::remove_file(&p);
    let _ = std::fs::remove_file(p.with_extension("json.tmp"));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn feed_lists_running_and_windows() {
        let threads = vec![ThreadShell {
            id: "t1".into(),
            title: "Build".into(),
            rest: json!({"activeRunId": "r1", "pendingRuntimeRequestCount": 1}),
            ..Default::default()
        }];
        let v = build(true, "eos", "", &[], &threads);
        assert!(v["running"].as_array().unwrap().is_empty());
        assert_eq!(v["pendingPrompts"][0]["count"], 1);
        assert!(v["windows"].as_array().unwrap().is_empty());
    }

    #[test]
    fn feed_names_running_provider_and_keeps_approval_rows_distinct() {
        let provider: Provider = serde_json::from_value(json!({
            "instanceId": "codex-work",
            "driver": "codex",
            "displayName": "ChatGPT Work",
            "enabled": true,
            "installed": true,
            "auth": "ready"
        }))
        .unwrap();
        let threads = vec![
            ThreadShell {
                id: "running".into(),
                title: "Build".into(),
                provider_instance_id: "codex-work".into(),
                rest: json!({"activeRunId": "run-1"}),
                ..Default::default()
            },
            ThreadShell {
                id: "approval".into(),
                title: "Review".into(),
                provider_instance_id: "codex-work".into(),
                rest: json!({"activeRunId": "run-2", "pendingRuntimeRequestCount": 1}),
                ..Default::default()
            },
        ];
        let v = build(true, "eos", "codex-work", &[provider], &threads);

        assert_eq!(v["running"].as_array().unwrap().len(), 1);
        assert_eq!(v["running"][0]["provider"], "ChatGPT Work");
        assert_eq!(v["selectedProvider"], "ChatGPT Work");
        assert_eq!(v["pendingPrompts"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn offline_feed_keeps_last_known_data_and_marks_it_stale() {
        let previous = json!({
            "schemaVersion": 1,
            "writtenAt": "2026-10-22T12:00:00Z",
            "connected": true,
            "stale": false,
            "server": "workstation",
            "selectedProvider": "ChatGPT Work",
            "running": [{"id": "thread-1"}],
            "pendingPrompts": [{"id": "thread-2", "count": 1}],
            "windows": [{"provider": "Codex", "usedPercent": 48.0}],
            "nextTask": {"provider": "Codex", "reason": "ready"}
        });
        let offline = stale_after_shutdown(&previous, "2026-10-22T12:30:00Z");

        assert_eq!(offline["connected"], false);
        assert_eq!(offline["stale"], true);
        assert_eq!(offline["server"], "workstation");
        assert_eq!(offline["selectedProvider"], "ChatGPT Work");
        assert_eq!(offline["writtenAt"], "2026-10-22T12:00:00Z");
        assert_eq!(offline["updatedAt"], "2026-10-22T12:30:00Z");
        assert_eq!(offline["running"][0]["id"], "thread-1");
        assert_eq!(offline["pendingPrompts"][0]["count"], 1);
        assert_eq!(offline["windows"][0]["provider"], "Codex");
    }
}
