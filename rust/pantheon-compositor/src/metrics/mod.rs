//! Compositor metrics: why it redraws, how long frames take, who commits.
//!
//! Replaces the old `redraw_stats` line. Every 30 s the compositor logs one
//! structured `compositor stats` event (target `pantheon_metrics`) plus one
//! `output frame stats` event per active output, then resets the window.
//! An idle compositor logs nothing. Overhead on the hot paths is a few relaxed
//! atomics per commit and three monotonic clock reads per queued frame.

pub mod client;
pub mod histogram;
#[cfg_attr(not(feature = "native-drm"), allow(dead_code))]
pub mod output;

use std::sync::atomic::{AtomicU64, Ordering};

use client::ClientWindow;
use output::OutputWindow;

/// How often the stats window is reported and reset.
pub const REPORT_INTERVAL: std::time::Duration = std::time::Duration::from_secs(30);
/// Clients named in the summary line.
const TOP_CLIENTS: usize = 5;

static REQUESTS: AtomicU64 = AtomicU64::new(0);
static RENDER_PASSES: AtomicU64 = AtomicU64::new(0);
static VBLANKS: AtomicU64 = AtomicU64::new(0);
/// Never reset; the watchdog status line takes rates from these.
static VBLANKS_TOTAL: AtomicU64 = AtomicU64::new(0);
pub(crate) static COMMITS_TOTAL: AtomicU64 = AtomicU64::new(0);

/// Running totals since start.
#[derive(Clone, Copy, Debug, Default)]
pub struct Totals {
    pub vblanks: u64,
    pub commits: u64,
}

pub fn totals() -> Totals {
    Totals {
        vblanks: VBLANKS_TOTAL.load(Ordering::Relaxed),
        commits: COMMITS_TOTAL.load(Ordering::Relaxed),
    }
}

/// A redraw was requested (before coalescing).
pub fn request() {
    REQUESTS.fetch_add(1, Ordering::Relaxed);
}

/// The coalesced redraw source actually ran a render pass.
#[cfg_attr(not(feature = "native-drm"), allow(dead_code))]
pub fn render_pass() {
    RENDER_PASSES.fetch_add(1, Ordering::Relaxed);
}

#[cfg_attr(not(feature = "native-drm"), allow(dead_code))]
pub fn vblank() {
    VBLANKS.fetch_add(1, Ordering::Relaxed);
    VBLANKS_TOTAL.fetch_add(1, Ordering::Relaxed);
}

/// Global counters for one window.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Counters {
    pub redraw_requests: u64,
    pub render_passes: u64,
    pub vblanks: u64,
}

pub fn take_counters() -> Counters {
    Counters {
        redraw_requests: REQUESTS.swap(0, Ordering::Relaxed),
        render_passes: RENDER_PASSES.swap(0, Ordering::Relaxed),
        vblanks: VBLANKS.swap(0, Ordering::Relaxed),
    }
}

/// Log the window. Returns whether anything was logged.
pub fn report(
    counters: Counters,
    clients: &[ClientWindow],
    outputs: &[(String, OutputWindow)],
) -> bool {
    let commits: u64 = clients.iter().map(|client| client.commits).sum();
    if commits == 0 && counters == Counters::default() && outputs.is_empty() {
        return false;
    }
    let shm: u64 = clients.iter().map(|client| client.shm).sum();
    let dmabuf: u64 = clients.iter().map(|client| client.dmabuf).sum();
    let damage_mpx = clients.iter().map(|client| client.damage_px).sum::<u64>() / 1_000_000;
    let frame_callbacks: u64 = clients.iter().map(|client| client.frame_callbacks).sum();
    let frames_queued: u64 = outputs.iter().map(|(_, output)| output.queued).sum();
    let frames_empty: u64 = outputs.iter().map(|(_, output)| output.empty).sum();
    let top = client::format_top(clients, TOP_CLIENTS);
    let window_s = REPORT_INTERVAL.as_secs();
    tracing::info!(
        target: "pantheon_metrics",
        window_s,
        commits,
        shm_commits = shm,
        dmabuf_commits = dmabuf,
        damage_mpx,
        frame_callbacks_requested = frame_callbacks,
        redraw_requests = counters.redraw_requests,
        render_passes = counters.render_passes,
        vblanks = counters.vblanks,
        frames_queued,
        frames_empty,
        top = %top,
        "compositor stats"
    );
    for (name, output) in outputs {
        let fps = output.flips as f64 / window_s as f64;
        tracing::info!(
            target: "pantheon_metrics",
            output = %name,
            fps = format_args!("{fps:.1}"),
            queued = output.queued,
            empty = output.empty,
            empty_pct = format_args!("{:.0}", output.empty_ratio * 100.0),
            late = output.late,
            skipped_vblanks = output.skipped_vblanks,
            empty_frame_callbacks = output.empty_frame_callbacks,
            render_us = %triple(output.render_cpu_us),
            render_max_us = output.render_cpu_max_us,
            queue_flip_us = %triple(output.queue_to_flip_us),
            dirty_flip_us = %triple(output.dirty_to_flip_us),
            dirty_flip_max_us = output.dirty_to_flip_max_us,
            "output frame stats"
        );
    }
    true
}

/// `p50/p95/p99`.
fn triple([p50, p95, p99]: [u64; 3]) -> String {
    format!("{p50}/{p95}/{p99}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn idle_window_logs_nothing() {
        assert!(!report(Counters::default(), &[], &[]));
    }

    #[test]
    fn counters_are_taken() {
        request();
        request();
        assert!(take_counters().redraw_requests >= 2);
    }

    #[test]
    fn triple_formats_percentiles() {
        assert_eq!(triple([1, 22, 333]), "1/22/333");
    }
}
