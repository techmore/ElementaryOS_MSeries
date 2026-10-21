//! Opt-in, bounded timing for native display lifecycle work. No display I/O.
//!
//! PANTHEON_DISPLAY_TRACE=1 enables at most 512 records per monotonic minute.
//! No EDID bytes, monitor serials, window titles, input, or activation tokens
//! are recorded. A pageflip is scanout acknowledgement, not proof of a picture.

use std::sync::{
    Mutex, OnceLock,
    atomic::{AtomicU64, Ordering},
};
use std::time::Instant;

const RECORD_LIMIT: u32 = 512;
static ENABLED: OnceLock<bool> = OnceLock::new();
static EPOCH: OnceLock<Instant> = OnceLock::new();
static NEXT_GENERATION: AtomicU64 = AtomicU64::new(1);
static BUDGET: Mutex<(u128, u32)> = Mutex::new((0, 0));

pub fn enabled() -> bool {
    *ENABLED.get_or_init(|| std::env::var("PANTHEON_DISPLAY_TRACE").is_ok_and(|v| v == "1"))
}

/// Monotonic compositor-local time, not an external-device arrival timestamp.
/// Rate limiting affects diagnostics only; it never changes display work.
pub fn stamp() -> Option<u128> {
    if !enabled() {
        return None;
    }
    let elapsed = EPOCH.get_or_init(Instant::now).elapsed();
    let minute = elapsed.as_secs() as u128 / 60;
    let mut budget = BUDGET.lock().ok()?;
    if budget.0 != minute {
        *budget = (minute, 0);
    }
    budget.1 = budget.1.saturating_add(1);
    if budget.1 == RECORD_LIMIT + 1 {
        tracing::warn!(target: "pantheon_display_lifecycle", monotonic_us = elapsed.as_micros() as u64,
            record_limit = RECORD_LIMIT, "display trace budget exhausted; diagnostics suppressed until next minute");
    }
    (budget.1 <= RECORD_LIMIT).then_some(elapsed.as_micros())
}

/// Every operation gets its own generation. Output markers retain the
/// generation that created/reassigned the output, even across later reconciles.
pub struct Operation {
    pub generation: u64,
    name: &'static str,
    started: Option<Instant>,
}

impl Operation {
    pub fn begin(name: &'static str) -> Self {
        let started = enabled().then(Instant::now);
        let generation = if started.is_some() {
            NEXT_GENERATION.fetch_add(1, Ordering::Relaxed)
        } else {
            0
        };
        if let Some(monotonic_us) = stamp() {
            tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                generation, operation = name, stage = "begin", "display operation");
        }
        Self {
            generation,
            name,
            started,
        }
    }

    pub fn output(&self) -> Option<OutputTrace> {
        OutputTrace::new(self.generation)
    }
}

impl Drop for Operation {
    fn drop(&mut self) {
        if let Some(started) = self.started
            && let Some(monotonic_us) = stamp()
        {
            tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                generation = self.generation, operation = self.name, stage = "end",
                duration_us = started.elapsed().as_micros() as u64,
                "display operation exited (consult transition/error records for outcome)");
        }
    }
}

pub struct OutputTrace {
    generation: u64,
    started: Instant,
    queued: bool,
    submitted: bool,
}

impl OutputTrace {
    pub fn new(generation: u64) -> Option<Self> {
        enabled().then(|| Self {
            generation,
            started: Instant::now(),
            queued: false,
            submitted: false,
        })
    }

    pub fn queued(&mut self, output: &str) {
        if self.queued {
            return;
        }
        self.queued = true;
        if let Some(monotonic_us) = stamp() {
            tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                generation = self.generation, output, stage = "first_queue",
                since_output_marker_us = self.started.elapsed().as_micros() as u64,
                "first damaged frame queued");
        }
    }

    pub fn submitted(&mut self, output: &str) {
        // Ignore unrelated/older vblank events before our first queue.
        if !self.queued || self.submitted {
            return;
        }
        self.submitted = true;
        if let Some(monotonic_us) = stamp() {
            tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                generation = self.generation, output, stage = "first_pageflip",
                since_output_marker_us = self.started.elapsed().as_micros() as u64,
                "first queued frame acknowledged (not a visual confirmation)");
        }
    }
}
