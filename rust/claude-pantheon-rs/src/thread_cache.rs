//! A small, private cache of settled T3 thread projections and their replay cursor.
//!
//! The projection and sequence are one record: the client must never resume after a cursor whose
//! events are not represented in the cached view. Active turns stay in memory and are saved only
//! after a settled snapshot or completion. The cache is scoped by environment and thread, bounded,
//! and disposable if its schema or contents do not validate.

use crate::t3::model::ThreadView;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

const SCHEMA_VERSION: u32 = 3;
const MAX_RECORD_BYTES: u64 = 8 * 1024 * 1024;
const MAX_ENV_ENTRIES: usize = 32;
const MAX_ENV_BYTES: u64 = 64 * 1024 * 1024;
static NEXT_TEMP: AtomicU64 = AtomicU64::new(1);

/// A replay event is applied only once and only when it advances the paired projection cursor.
pub fn event_is_new(current_sequence: Option<u64>, incoming_sequence: u64) -> bool {
    current_sequence.is_none_or(|current| incoming_sequence > current)
}

/// A same-sequence snapshot may refresh the identical high-water projection; an older one may not
/// replace data that the cache already represents.
pub fn snapshot_is_current(current_sequence: Option<u64>, incoming_sequence: u64) -> bool {
    current_sequence.is_none_or(|current| incoming_sequence >= current)
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CachedThread {
    schema_version: u32,
    environment_id: String,
    thread_id: String,
    pub sequence: u64,
    pub view: ThreadView,
    pub history_cursor: Option<String>,
    pub has_more_history: bool,
}

impl CachedThread {
    pub fn new(
        environment_id: &str,
        thread_id: &str,
        sequence: u64,
        view: &ThreadView,
        history_cursor: Option<&str>,
        has_more_history: bool,
    ) -> Self {
        Self {
            schema_version: SCHEMA_VERSION,
            environment_id: environment_id.to_string(),
            thread_id: thread_id.to_string(),
            sequence,
            view: cache_view(view),
            history_cursor: history_cursor.map(str::to_string),
            has_more_history,
        }
    }

    fn matches(&self, environment_id: &str, thread_id: &str) -> bool {
        self.schema_version == SCHEMA_VERSION && self.environment_id == environment_id && self.thread_id == thread_id
    }
}

fn cache_view(view: &ThreadView) -> ThreadView {
    let first_run = view.runs.len().saturating_sub(100);
    let first_checkpoint = view.checkpoints.len().saturating_sub(100);
    let items = view.items.clone();
    let history_item_keys = items.iter().map(|item| item.identity_key()).collect();
    ThreadView {
        items,
        active_run_id: view.active_run_id.clone(),
        runs: view.runs[first_run..].to_vec(),
        checkpoints: view.checkpoints[first_checkpoint..].to_vec(),
        history_item_keys,
    }
}

fn root() -> PathBuf {
    crate::index::cache_dir().join("threads")
}

fn encoded_component(value: &str) -> Option<String> {
    // T3 ids are short; keeping the full value encoded makes paths traversal-safe and avoids
    // relying on a hash collision not to mix two environments or threads.
    if value.is_empty() || value.len() > 100 {
        return None;
    }
    Some(value.as_bytes().iter().map(|byte| format!("{byte:02x}")).collect())
}

fn environment_dir(root: &Path, environment_id: &str) -> Option<PathBuf> {
    Some(root.join(encoded_component(environment_id)?))
}

fn record_path(root: &Path, environment_id: &str, thread_id: &str) -> Option<PathBuf> {
    Some(environment_dir(root, environment_id)?.join(format!("{}.json", encoded_component(thread_id)?)))
}

pub fn load(environment_id: &str, thread_id: &str) -> Option<CachedThread> {
    load_from(&root(), environment_id, thread_id)
}

fn load_from(root: &Path, environment_id: &str, thread_id: &str) -> Option<CachedThread> {
    let path = record_path(root, environment_id, thread_id)?;
    prune_environment(root, environment_id, &path);
    let metadata = std::fs::metadata(&path).ok()?;
    if metadata.len() > MAX_RECORD_BYTES {
        let _ = std::fs::remove_file(path);
        return None;
    }
    let bytes = std::fs::read(&path).ok()?;
    let decoded = serde_json::from_slice::<CachedThread>(&bytes).ok();
    match decoded {
        Some(record) if record.matches(environment_id, thread_id) => Some(record),
        _ => {
            let _ = std::fs::remove_file(path);
            None
        }
    }
}

pub fn save(record: &CachedThread) -> Result<(), String> {
    save_to(&root(), record)
}

fn save_to(root: &Path, record: &CachedThread) -> Result<(), String> {
    if record.schema_version != SCHEMA_VERSION {
        return Err("invalid T3 thread cache scope".into());
    }
    let path = record_path(root, &record.environment_id, &record.thread_id)
        .ok_or_else(|| "environment or thread id is too long to cache".to_string())?;
    let dir = path.parent().ok_or_else(|| "thread cache has no parent directory".to_string())?;
    std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    set_dir_mode(dir)?;

    let bytes = serde_json::to_vec(record).map_err(|e| e.to_string())?;
    if bytes.len() as u64 > MAX_RECORD_BYTES {
        return Err(format!("thread cache record exceeds {} MiB", MAX_RECORD_BYTES / 1024 / 1024));
    }

    // Never replace a newer record with a delayed or stale writer.
    if let Some(existing) = load_from(root, &record.environment_id, &record.thread_id)
        && existing.sequence > record.sequence
    {
        return Ok(());
    }

    let tmp = path.with_extension(format!("tmp.{}.{}", std::process::id(), NEXT_TEMP.fetch_add(1, Ordering::Relaxed)));
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&tmp).map_err(|e| e.to_string())?;
    use std::io::Write;
    file.write_all(&bytes).map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())?;
    set_file_mode(&tmp)?;
    std::fs::rename(&tmp, &path).map_err(|e| e.to_string())?;
    if let Ok(dir) = std::fs::File::open(dir) {
        let _ = dir.sync_all();
    }
    prune_environment(root, &record.environment_id, &path);
    Ok(())
}

fn prune_environment(root: &Path, environment_id: &str, keep: &Path) {
    let Some(dir) = environment_dir(root, environment_id) else { return };
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    let mut records: Vec<(PathBuf, u64, std::time::SystemTime)> = entries
        .flatten()
        .filter_map(|entry| {
            let path = entry.path();
            let metadata = entry.metadata().ok()?;
            if !metadata.is_file() {
                return None;
            }
            if path.extension().is_none_or(|ext| ext != "json") {
                let _ = std::fs::remove_file(path);
                return None;
            }
            Some((path, metadata.len(), metadata.modified().unwrap_or(std::time::UNIX_EPOCH)))
        })
        .collect();
    records.sort_by_key(|entry| std::cmp::Reverse(entry.2));
    let mut count = 0usize;
    let mut total = 0u64;
    for (path, size, _) in records {
        if path == keep || (count < MAX_ENV_ENTRIES && total.saturating_add(size) <= MAX_ENV_BYTES) {
            count += 1;
            total = total.saturating_add(size);
        } else {
            let _ = std::fs::remove_file(path);
        }
    }
}

pub fn remove(environment_id: &str, thread_id: &str) {
    if let Some(path) = record_path(&root(), environment_id, thread_id) {
        let _ = std::fs::remove_file(path);
    }
}

pub fn clear_environment(environment_id: &str) {
    if let Some(dir) = environment_dir(&root(), environment_id) {
        let _ = std::fs::remove_dir_all(dir);
    }
}

#[cfg(unix)]
fn set_dir_mode(path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700)).map_err(|e| e.to_string())
}

#[cfg(not(unix))]
fn set_dir_mode(_path: &Path) -> Result<(), String> {
    Ok(())
}

#[cfg(unix)]
fn set_file_mode(path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600)).map_err(|e| e.to_string())
}

#[cfg(not(unix))]
fn set_file_mode(_path: &Path) -> Result<(), String> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::t3::model::TurnItem;

    fn temp_root() -> PathBuf {
        let nonce = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        std::env::temp_dir().join(format!("t3-thread-cache-{}-{nonce}", std::process::id()))
    }

    #[test]
    fn round_trips_a_scoped_snapshot_and_cursor_atomically() {
        let root = temp_root();
        let mut view = ThreadView::default();
        view.items.push(TurnItem {
            id: "item-1".into(),
            kind: "assistant_message".into(),
            text: "cached reply".into(),
            ..Default::default()
        });
        let record = CachedThread::new("env-a", "thread-a", 42, &view, Some("opaque-page-cursor"), true);
        save_to(&root, &record).unwrap();

        let loaded = load_from(&root, "env-a", "thread-a").unwrap();
        assert_eq!(loaded.sequence, 42);
        assert_eq!(loaded.view.items[0].text, "cached reply");
        assert_eq!(loaded.history_cursor.as_deref(), Some("opaque-page-cursor"));
        assert!(loaded.has_more_history);
        assert!(load_from(&root, "env-b", "thread-a").is_none());
        assert!(load_from(&root, "env-a", "thread-b").is_none());

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let path = record_path(&root, "env-a", "thread-a").unwrap();
            assert_eq!(std::fs::metadata(path).unwrap().permissions().mode() & 0o777, 0o600);
        }
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn rejects_corrupt_wrong_scope_oversized_and_stale_writes() {
        let root = temp_root();
        let path = record_path(&root, "env-a", "thread-a").unwrap();
        let dir = path.parent().unwrap();
        std::fs::create_dir_all(dir).unwrap();
        std::fs::write(&path, b"not-json").unwrap();
        assert!(load_from(&root, "env-a", "thread-a").is_none());
        assert!(!path.exists());

        let view = ThreadView::default();
        save_to(&root, &CachedThread::new("env-a", "thread-a", 42, &view, None, false)).unwrap();
        save_to(&root, &CachedThread::new("env-a", "thread-a", 40, &view, None, false)).unwrap();
        assert_eq!(load_from(&root, "env-a", "thread-a").unwrap().sequence, 42);

        std::fs::write(&path, vec![b'x'; MAX_RECORD_BYTES as usize + 1]).unwrap();
        assert!(load_from(&root, "env-a", "thread-a").is_none());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn cached_history_keeps_items_and_bounds_runs_and_checkpoints() {
        let view = ThreadView {
            items: (0..501).map(|i| TurnItem { id: format!("item-{i}"), ..Default::default() }).collect(),
            runs: (0..101).map(|i| serde_json::json!({"id": i})).collect(),
            checkpoints: (0..101).map(|i| serde_json::json!({"id": i})).collect(),
            ..Default::default()
        };
        let cached = CachedThread::new("env-a", "thread-a", 1, &view, Some("cursor"), true);
        assert_eq!(cached.view.items.len(), 501);
        assert_eq!(cached.view.items[0].id, "item-0");
        assert_eq!(cached.view.runs.len(), 100);
        assert_eq!(cached.view.checkpoints.len(), 100);
        assert!(cached.has_more_history);
        assert_eq!(cached.history_cursor.as_deref(), Some("cursor"));
    }

    #[test]
    fn replay_cursor_only_moves_forward_after_applied_events() {
        assert!(event_is_new(None, 0));
        assert!(event_is_new(Some(42), 43));
        assert!(!event_is_new(Some(42), 42));
        assert!(!event_is_new(Some(42), 41));
        assert!(snapshot_is_current(Some(42), 42));
        assert!(!snapshot_is_current(Some(42), 41));
    }
}
