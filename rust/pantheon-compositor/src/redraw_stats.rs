//! Low-overhead counters that explain why the compositor keeps redrawing.
//!
//! Every 30 s `report` returns a one-line summary (and resets the counters) so
//! the journal shows whether idle CPU comes from client commits, our own
//! redraw requests, vblank events, or frames that were actually queued.

use std::{
    collections::HashMap,
    sync::{
        Mutex,
        atomic::{AtomicU64, Ordering},
    },
};

static REQUESTS: AtomicU64 = AtomicU64::new(0);
static VBLANKS: AtomicU64 = AtomicU64::new(0);
static QUEUED: AtomicU64 = AtomicU64::new(0);
static EMPTY: AtomicU64 = AtomicU64::new(0);
static COMMITS: Mutex<Option<Commits>> = Mutex::new(None);

#[derive(Default)]
struct Commits {
    by_pid: HashMap<u32, u64>,
    names: HashMap<u32, String>,
}

pub fn request() {
    REQUESTS.fetch_add(1, Ordering::Relaxed);
}

#[cfg_attr(not(feature = "native-drm"), allow(dead_code))]
pub fn vblank() {
    VBLANKS.fetch_add(1, Ordering::Relaxed);
}

#[cfg_attr(not(feature = "native-drm"), allow(dead_code))]
pub fn frame_queued() {
    QUEUED.fetch_add(1, Ordering::Relaxed);
}

#[cfg_attr(not(feature = "native-drm"), allow(dead_code))]
pub fn frame_empty() {
    EMPTY.fetch_add(1, Ordering::Relaxed);
}

/// Count one surface commit from the client process `pid` (if known).
pub fn commit(pid: Option<u32>) {
    let pid = pid.unwrap_or(0);
    if let Ok(mut guard) = COMMITS.lock() {
        let commits = guard.get_or_insert_with(Commits::default);
        *commits.by_pid.entry(pid).or_insert(0) += 1;
        commits.names.entry(pid).or_insert_with(|| {
            std::fs::read_to_string(format!("/proc/{pid}/comm"))
                .map(|name| name.trim().to_string())
                .unwrap_or_else(|_| "unknown".into())
        });
    }
}

/// Summarise and reset. `None` when nothing happened (an idle compositor
/// logs nothing).
pub fn report() -> Option<String> {
    let requests = REQUESTS.swap(0, Ordering::Relaxed);
    let vblanks = VBLANKS.swap(0, Ordering::Relaxed);
    let queued = QUEUED.swap(0, Ordering::Relaxed);
    let empty = EMPTY.swap(0, Ordering::Relaxed);
    let commits = COMMITS.lock().ok().and_then(|mut guard| guard.take());
    let total_commits = commits
        .as_ref()
        .map_or(0, |commits| commits.by_pid.values().sum::<u64>());
    if requests + vblanks + queued + empty + total_commits == 0 {
        return None;
    }
    Some(format_report(
        requests,
        vblanks,
        queued,
        empty,
        commits.as_ref(),
    ))
}

fn format_report(
    requests: u64,
    vblanks: u64,
    queued: u64,
    empty: u64,
    commits: Option<&Commits>,
) -> String {
    let mut top: Vec<(u64, String)> = commits
        .map(|commits| {
            commits
                .by_pid
                .iter()
                .map(|(pid, count)| {
                    let name = commits.names.get(pid).map_or("unknown", String::as_str);
                    (*count, format!("{name}({pid})={count}"))
                })
                .collect()
        })
        .unwrap_or_default();
    top.sort_by_key(|entry| std::cmp::Reverse(entry.0));
    let total: u64 = top.iter().map(|(count, _)| count).sum();
    let top = top
        .into_iter()
        .take(4)
        .map(|(_, text)| text)
        .collect::<Vec<_>>()
        .join(" ");
    format!(
        "redraw stats /30s: commits={total} [{top}] redraw_requests={requests} vblanks={vblanks} frames_queued={queued} frames_empty={empty}"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn top_clients_are_sorted_and_limited() {
        let mut commits = Commits::default();
        for (pid, count, name) in [
            (1, 5, "a"),
            (2, 50, "b"),
            (3, 7, "c"),
            (4, 1, "d"),
            (5, 2, "e"),
        ] {
            commits.by_pid.insert(pid, count);
            commits.names.insert(pid, name.into());
        }
        let line = format_report(9, 8, 7, 6, Some(&commits));
        assert!(
            line.contains("commits=65 [b(2)=50 c(3)=7 a(1)=5 e(5)=2]"),
            "{line}"
        );
        assert!(line.contains("redraw_requests=9 vblanks=8 frames_queued=7 frames_empty=6"));
    }

    #[test]
    fn empty_window_reports_nothing() {
        // Drain whatever other tests in this process counted, then expect silence.
        let _ = report();
        assert_eq!(report(), None);
    }
}
