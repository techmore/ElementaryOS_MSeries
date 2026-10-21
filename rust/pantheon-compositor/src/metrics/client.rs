//! Per-client surface commit counters.
//!
//! Each Wayland client gets an `Arc<ClientStats>` when it connects, keyed by
//! the peer pid read once from the socket (the old code asked the kernel for
//! `SO_PEERCRED` and took a global mutex on every commit). Several connections
//! from one process share one entry. X11 windows commit through the single
//! Xwayland connection, so their commits are attributed to the X11 client's
//! own pid (`_NET_WM_PID`) through a per-surface cache instead.

use std::{
    collections::HashMap,
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    },
};

/// Attribution key for Xwayland's own surfaces (cursor, unmatched windows).
pub const XWAYLAND_KEY: u32 = 0;

/// What a commit attached, for the shm vs dmabuf split.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BufferKind {
    /// No new buffer in this commit (state-only or frame-callback-only).
    None,
    Shm,
    Dmabuf,
    /// Single-pixel or another buffer type.
    Other,
}

#[derive(Debug)]
pub struct ClientStats {
    pub pid: u32,
    pub name: String,
    commits: AtomicU64,
    shm: AtomicU64,
    dmabuf: AtomicU64,
    damage_px: AtomicU64,
    frame_callbacks: AtomicU64,
}

/// Counters taken (and reset) for one report window.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ClientWindow {
    pub pid: u32,
    pub name: String,
    pub commits: u64,
    pub shm: u64,
    pub dmabuf: u64,
    pub damage_px: u64,
    pub frame_callbacks: u64,
}

impl ClientStats {
    pub fn new(pid: u32, name: impl Into<String>) -> Self {
        Self {
            pid,
            name: name.into(),
            commits: AtomicU64::new(0),
            shm: AtomicU64::new(0),
            dmabuf: AtomicU64::new(0),
            damage_px: AtomicU64::new(0),
            frame_callbacks: AtomicU64::new(0),
        }
    }

    /// Count one commit. Relaxed atomics only: no lock, no syscall.
    pub fn commit(&self, buffer: BufferKind, damage_px: u64, frame_callbacks: u64) {
        self.commits.fetch_add(1, Ordering::Relaxed);
        match buffer {
            BufferKind::Shm => {
                self.shm.fetch_add(1, Ordering::Relaxed);
            }
            BufferKind::Dmabuf => {
                self.dmabuf.fetch_add(1, Ordering::Relaxed);
            }
            BufferKind::None | BufferKind::Other => {}
        }
        if damage_px > 0 {
            self.damage_px.fetch_add(damage_px, Ordering::Relaxed);
        }
        if frame_callbacks > 0 {
            self.frame_callbacks
                .fetch_add(frame_callbacks, Ordering::Relaxed);
        }
    }

    fn take(&self) -> ClientWindow {
        ClientWindow {
            pid: self.pid,
            name: self.name.clone(),
            commits: self.commits.swap(0, Ordering::Relaxed),
            shm: self.shm.swap(0, Ordering::Relaxed),
            dmabuf: self.dmabuf.swap(0, Ordering::Relaxed),
            damage_px: self.damage_px.swap(0, Ordering::Relaxed),
            frame_callbacks: self.frame_callbacks.swap(0, Ordering::Relaxed),
        }
    }
}

/// All known clients, keyed by pid. Touched only at connect, on the first
/// commit of an X11 window, and by the 30 s report.
#[derive(Default)]
pub struct ClientRegistry {
    by_pid: HashMap<u32, Arc<ClientStats>>,
}

impl ClientRegistry {
    /// Stats for `pid`, created on first use. `name` is only called then.
    pub fn get_or_insert(&mut self, pid: u32, name: impl FnOnce() -> String) -> Arc<ClientStats> {
        self.by_pid
            .entry(pid)
            .or_insert_with(|| Arc::new(ClientStats::new(pid, name())))
            .clone()
    }

    /// Stats for a process, named from `/proc/<pid>/comm`.
    pub fn for_pid(&mut self, pid: u32) -> Arc<ClientStats> {
        self.get_or_insert(pid, || process_name(pid))
    }

    /// Stats for Xwayland's own surfaces.
    pub fn xwayland(&mut self) -> Arc<ClientStats> {
        self.get_or_insert(XWAYLAND_KEY, || "Xwayland".into())
    }

    /// Take every client's counters for this window, busiest first, and forget
    /// clients that are gone (no connection or surface holds them) and idle.
    pub fn take_window(&mut self) -> Vec<ClientWindow> {
        let mut windows = Vec::new();
        self.by_pid.retain(|_, stats| {
            let window = stats.take();
            let active = window.commits > 0;
            if active {
                windows.push(window);
            }
            active || Arc::strong_count(stats) > 1
        });
        windows.sort_by(|a, b| b.commits.cmp(&a.commits).then(a.pid.cmp(&b.pid)));
        windows
    }

    #[cfg(test)]
    pub fn len(&self) -> usize {
        self.by_pid.len()
    }
}

/// Who an Xwayland surface's commits belong to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum X11Attribution {
    /// The X11 window's own process (`_NET_WM_PID`); cache it.
    Client(u32),
    /// Xwayland itself, for good: the window has no pid, or the surface never
    /// became a window (Xwayland's cursor). Cache it.
    Xwayland,
    /// No window yet (commits can precede the map); count as Xwayland and
    /// look again on the next commit.
    XwaylandForNow,
}

/// `window_pid` is `None` when no mapped X11 window owns the surface,
/// `Some(None)` when one does but it has no `_NET_WM_PID`. `misses` counts
/// lookups so far, including this one.
pub fn attribute_x11(
    window_pid: Option<Option<u32>>,
    misses: u32,
    max_misses: u32,
) -> X11Attribution {
    match window_pid {
        Some(Some(pid)) => X11Attribution::Client(pid),
        Some(None) => X11Attribution::Xwayland,
        None if misses >= max_misses => X11Attribution::Xwayland,
        None => X11Attribution::XwaylandForNow,
    }
}

pub fn process_name(pid: u32) -> String {
    std::fs::read_to_string(format!("/proc/{pid}/comm"))
        .map(|name| name.trim().to_string())
        .unwrap_or_else(|_| "unknown".into())
}

/// Area of a commit's damage, clipped to the buffer, in buffer pixels.
/// Overlapping rectangles are counted twice; this is a load signal, not an
/// exact region.
pub fn damage_area<I>(rects: I, buffer_w: i32, buffer_h: i32) -> u64
where
    I: IntoIterator<Item = (i32, i32, i32, i32)>,
{
    rects
        .into_iter()
        .map(|(x, y, w, h)| {
            let x0 = x.clamp(0, buffer_w.max(0));
            let y0 = y.clamp(0, buffer_h.max(0));
            let x1 = x.saturating_add(w).clamp(0, buffer_w.max(0));
            let y1 = y.saturating_add(h).clamp(0, buffer_h.max(0));
            u64::from((x1 - x0).max(0) as u32) * u64::from((y1 - y0).max(0) as u32)
        })
        .sum()
}

/// One line for the journal: `name(pid)=commits[/shm|/dmabuf]`, busiest first.
pub fn format_top(windows: &[ClientWindow], limit: usize) -> String {
    windows
        .iter()
        .take(limit)
        .map(|window| {
            let kind = match (window.shm > 0, window.dmabuf > 0) {
                (true, false) => "/shm",
                (false, true) => "/dmabuf",
                (true, true) => "/mixed",
                (false, false) => "",
            };
            format!("{}({})={}{kind}", window.name, window.pid, window.commits)
        })
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn connections_from_one_process_share_stats() {
        let mut registry = ClientRegistry::default();
        let first = registry.get_or_insert(42, || "brave".into());
        let second = registry.get_or_insert(42, || unreachable!("named once"));
        assert!(Arc::ptr_eq(&first, &second));
        first.commit(BufferKind::Shm, 100, 1);
        second.commit(BufferKind::Dmabuf, 50, 0);
        let window = registry.take_window();
        assert_eq!(
            window,
            vec![ClientWindow {
                pid: 42,
                name: "brave".into(),
                commits: 2,
                shm: 1,
                dmabuf: 1,
                damage_px: 150,
                frame_callbacks: 1,
            }]
        );
    }

    #[test]
    fn x11_commits_are_attributed_to_the_x11_client_not_xwayland() {
        // The commit path looks up the X11 window's pid and counts against that
        // entry; Xwayland's own entry only gets surfaces with no X11 window.
        let mut registry = ClientRegistry::default();
        let xwayland = registry.xwayland();
        let chatgpt = registry.get_or_insert(5150, || "chatgpt".into());
        for _ in 0..27 {
            chatgpt.commit(BufferKind::Shm, 10, 1);
        }
        xwayland.commit(BufferKind::None, 0, 0);
        let window = registry.take_window();
        assert_eq!(window[0].name, "chatgpt");
        assert_eq!(window[0].commits, 27);
        assert_eq!(window[1].pid, XWAYLAND_KEY);
        assert_eq!(window[1].commits, 1);
    }

    #[test]
    fn x11_surfaces_resolve_to_the_window_pid_or_xwayland() {
        // ChatGPT (X11) commits through Xwayland's connection; its window pid wins.
        assert_eq!(
            attribute_x11(Some(Some(5150)), 1, 120),
            X11Attribution::Client(5150)
        );
        // A window without _NET_WM_PID stays Xwayland's, decided at once.
        assert_eq!(attribute_x11(Some(None), 1, 120), X11Attribution::Xwayland);
        // Before the window maps: Xwayland for now, ask again next commit...
        assert_eq!(attribute_x11(None, 1, 120), X11Attribution::XwaylandForNow);
        assert_eq!(
            attribute_x11(None, 119, 120),
            X11Attribution::XwaylandForNow
        );
        // ...until it is clearly not a window (the cursor surface).
        assert_eq!(attribute_x11(None, 120, 120), X11Attribution::Xwayland);
        // A late map still wins over earlier misses.
        assert_eq!(
            attribute_x11(Some(Some(7)), 500, 120),
            X11Attribution::Client(7)
        );
    }

    #[test]
    fn take_window_resets_and_forgets_dead_idle_clients() {
        let mut registry = ClientRegistry::default();
        let alive = registry.get_or_insert(1, || "alive".into());
        registry
            .get_or_insert(2, || "gone".into())
            .commit(BufferKind::Shm, 0, 0);
        alive.commit(BufferKind::Shm, 0, 0);

        // Window 1: both active, both reported; the dead one stays for now.
        assert_eq!(registry.take_window().len(), 2);
        assert_eq!(registry.len(), 2);
        // Window 2: nothing happened. The dead, idle one is dropped; the live one stays.
        assert!(registry.take_window().is_empty());
        assert_eq!(registry.len(), 1);
        drop(alive);
        assert!(registry.take_window().is_empty());
        assert_eq!(registry.len(), 0);
    }

    #[test]
    fn damage_is_clipped_to_the_buffer() {
        assert_eq!(damage_area([(0, 0, 10, 10)], 100, 100), 100);
        assert_eq!(damage_area([(-5, -5, 10, 10)], 100, 100), 25);
        assert_eq!(damage_area([(0, 0, i32::MAX, i32::MAX)], 40, 30), 1200);
        assert_eq!(damage_area([(200, 0, 10, 10)], 100, 100), 0);
    }

    #[test]
    fn top_line_names_buffer_kind() {
        let windows = vec![
            ClientWindow {
                pid: 2,
                name: "b".into(),
                commits: 50,
                shm: 50,
                ..Default::default()
            },
            ClientWindow {
                pid: 3,
                name: "c".into(),
                commits: 7,
                dmabuf: 7,
                ..Default::default()
            },
            ClientWindow {
                pid: 1,
                name: "a".into(),
                commits: 5,
                ..Default::default()
            },
        ];
        assert_eq!(format_top(&windows, 2), "b(2)=50/shm c(3)=7/dmabuf");
        assert_eq!(format_top(&windows, 9), "b(2)=50/shm c(3)=7/dmabuf a(1)=5");
    }
}
