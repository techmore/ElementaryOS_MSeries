//! Per-output frame timing for the native backend.
//!
//! Times are `CLOCK_MONOTONIC` durations so they compare directly with the
//! page-flip timestamp the kernel puts in the vblank event:
//!
//! - render CPU: building elements, `render_frame` and `queue_frame` on the
//!   compositor thread (GPU work runs asynchronously and is not included);
//! - queue→flip: `queue_frame` returned → kernel flip timestamp;
//! - dirty→flip: first client commit or input event that needed this frame →
//!   flip timestamp (roughly commit-to-scanout latency);
//! - late: queue→flip longer than 1.5 refresh periods (a vblank was missed).

use std::time::Duration;

use super::histogram::Histogram;

#[derive(Default)]
pub struct OutputStats {
    pub render_cpu: Histogram,
    pub queue_to_flip: Histogram,
    pub dirty_to_flip: Histogram,
    pub queued: u64,
    pub empty: u64,
    pub late: u64,
    pub flips: u64,
    /// Vblank sequence numbers skipped between consecutive flips while frames
    /// were back to back (the previous flip was answered by this queue).
    pub skipped_vblanks: u64,
    /// Frames completed by the estimated-vblank timer after an empty render.
    pub empty_frame_callbacks: u64,
    /// When the frame now in flight was queued, and the dirty mark it carries.
    in_flight: Option<InFlight>,
    last_flip: Option<(Duration, u32)>,
}

#[derive(Clone, Copy)]
struct InFlight {
    queued_at: Duration,
    dirty_at: Option<Duration>,
    /// Whether this frame was queued in reaction to the previous flip, so a
    /// sequence gap means a missed vblank rather than an idle period.
    follows_flip: bool,
}

/// One output's numbers for a report window.
#[derive(Clone, Debug, PartialEq)]
pub struct OutputWindow {
    pub queued: u64,
    pub empty: u64,
    pub late: u64,
    pub flips: u64,
    pub skipped_vblanks: u64,
    pub empty_frame_callbacks: u64,
    /// Share of render passes that produced no damage, 0.0–1.0.
    pub empty_ratio: f64,
    pub render_cpu_us: [u64; 3],
    pub queue_to_flip_us: [u64; 3],
    pub dirty_to_flip_us: [u64; 3],
    /// Worst render CPU and dirty→flip in the window.
    pub render_cpu_max_us: u64,
    pub dirty_to_flip_max_us: u64,
}

impl OutputStats {
    pub fn record_empty(&mut self) {
        self.empty += 1;
    }

    /// A frame was queued for scanout at `now` after `render_cpu` of work.
    pub fn record_queued(
        &mut self,
        now: Duration,
        render_cpu: Duration,
        dirty_at: Option<Duration>,
    ) {
        self.queued += 1;
        self.render_cpu.record(render_cpu);
        let follows_flip = self
            .last_flip
            .is_some_and(|(flip, _)| now.saturating_sub(flip) < Duration::from_millis(50));
        self.in_flight = Some(InFlight {
            queued_at: now,
            dirty_at,
            follows_flip,
        });
    }

    /// The kernel reported the flip at `flip` (monotonic) with `sequence`.
    /// `refresh` is the mode's frame period, used to classify late frames.
    pub fn record_flip(
        &mut self,
        flip: Duration,
        sequence: Option<u32>,
        refresh: Option<Duration>,
    ) {
        self.flips += 1;
        if let Some(in_flight) = self.in_flight.take() {
            let queue_to_flip = flip.saturating_sub(in_flight.queued_at);
            self.queue_to_flip.record(queue_to_flip);
            if let Some(dirty) = in_flight.dirty_at {
                self.dirty_to_flip.record(flip.saturating_sub(dirty));
            }
            if refresh.is_some_and(|refresh| queue_to_flip > refresh + refresh / 2) {
                self.late += 1;
            }
            if in_flight.follows_flip
                && let (Some(sequence), Some((_, previous))) = (sequence, self.last_flip)
            {
                let gap = sequence.wrapping_sub(previous);
                if (2..1_000).contains(&gap) {
                    self.skipped_vblanks += u64::from(gap - 1);
                }
            }
        }
        if let Some(sequence) = sequence {
            self.last_flip = Some((flip, sequence));
        } else {
            self.last_flip = self.last_flip.map(|(_, sequence)| (flip, sequence));
        }
    }

    /// Last flip time, for estimating the next vblank after an empty frame.
    pub fn last_flip_time(&self) -> Option<Duration> {
        self.last_flip.map(|(time, _)| time)
    }

    /// Take this window's numbers and reset. `None` when the output was idle.
    pub fn take_window(&mut self) -> Option<OutputWindow> {
        if self.queued + self.empty + self.flips + self.empty_frame_callbacks == 0 {
            return None;
        }
        let passes = self.queued + self.empty;
        let window = OutputWindow {
            queued: self.queued,
            empty: self.empty,
            late: self.late,
            flips: self.flips,
            skipped_vblanks: self.skipped_vblanks,
            empty_frame_callbacks: self.empty_frame_callbacks,
            empty_ratio: if passes == 0 {
                0.0
            } else {
                self.empty as f64 / passes as f64
            },
            render_cpu_us: self.render_cpu.summary(),
            queue_to_flip_us: self.queue_to_flip.summary(),
            dirty_to_flip_us: self.dirty_to_flip.summary(),
            render_cpu_max_us: self.render_cpu.max_us(),
            dirty_to_flip_max_us: self.dirty_to_flip.max_us(),
        };
        self.queued = 0;
        self.empty = 0;
        self.late = 0;
        self.flips = 0;
        self.skipped_vblanks = 0;
        self.empty_frame_callbacks = 0;
        self.render_cpu.reset();
        self.queue_to_flip.reset();
        self.dirty_to_flip.reset();
        Some(window)
    }
}

/// Next estimated vblank strictly after `now`, given the last real flip and
/// the frame period. Falls back to `now + refresh` without a previous flip.
pub fn next_vblank_estimate(
    now: Duration,
    last_flip: Option<Duration>,
    refresh: Duration,
) -> Duration {
    if refresh.is_zero() {
        return now;
    }
    match last_flip {
        Some(flip) if flip <= now => {
            let periods = (now - flip).as_nanos() / refresh.as_nanos() + 1;
            flip + Duration::from_nanos((periods * refresh.as_nanos()) as u64)
        }
        Some(flip) => flip,
        None => now + refresh,
    }
}

/// Frame period of a mode refresh in millihertz.
pub fn refresh_period(refresh_mhz: i32) -> Option<Duration> {
    (refresh_mhz > 0).then(|| Duration::from_nanos(1_000_000_000_000 / refresh_mhz as u64))
}

#[cfg(test)]
mod tests {
    use super::*;

    const MS: Duration = Duration::from_millis(1);

    #[test]
    fn queue_and_dirty_to_flip_use_the_kernel_timestamp() {
        let refresh = refresh_period(120_000);
        let mut stats = OutputStats::default();
        stats.record_flip(100 * MS, Some(10), refresh);
        stats.record_queued(101 * MS, Duration::from_micros(700), Some(99 * MS));
        stats.record_flip(108 * MS, Some(11), refresh);
        let window = stats.take_window().unwrap();
        assert_eq!(window.queued, 1);
        assert_eq!(window.flips, 2);
        assert_eq!(window.late, 0);
        assert_eq!(window.skipped_vblanks, 0);
        assert_eq!(window.queue_to_flip_us[0], 7_000);
        assert_eq!(window.dirty_to_flip_us[0], 9_000);
        assert_eq!(window.render_cpu_us[0], 700);
    }

    #[test]
    fn a_missed_vblank_is_late_and_counted() {
        let refresh = refresh_period(120_000); // 8.33 ms
        let mut stats = OutputStats::default();
        stats.record_flip(100 * MS, Some(10), refresh);
        stats.record_queued(101 * MS, MS, None);
        // Flipped two periods later, sequence jumped by 2.
        stats.record_flip(117 * MS, Some(12), refresh);
        let window = stats.take_window().unwrap();
        assert_eq!(window.late, 1);
        assert_eq!(window.skipped_vblanks, 1);
    }

    #[test]
    fn an_idle_gap_is_not_a_skipped_vblank() {
        let refresh = refresh_period(120_000);
        let mut stats = OutputStats::default();
        stats.record_flip(100 * MS, Some(10), refresh);
        // Nothing to draw for a second, then one frame.
        stats.record_queued(1_100 * MS, MS, None);
        stats.record_flip(1_105 * MS, Some(130), refresh);
        let window = stats.take_window().unwrap();
        assert_eq!(window.skipped_vblanks, 0);
        assert_eq!(window.late, 0);
    }

    #[test]
    fn empty_ratio_and_reset() {
        let mut stats = OutputStats::default();
        stats.record_empty();
        stats.record_empty();
        stats.record_empty();
        stats.record_queued(MS, MS, None);
        let window = stats.take_window().unwrap();
        assert!((window.empty_ratio - 0.75).abs() < 1e-9);
        assert_eq!(stats.take_window(), None);
    }

    #[test]
    fn vblank_estimate_steps_whole_periods_from_the_last_flip() {
        let period = Duration::from_micros(8_333);
        let flip = Duration::from_millis(1_000);
        assert_eq!(
            next_vblank_estimate(flip, Some(flip), period),
            flip + period
        );
        assert_eq!(
            next_vblank_estimate(flip + Duration::from_millis(20), Some(flip), period),
            flip + period * 3
        );
        assert_eq!(next_vblank_estimate(flip, None, period), flip + period);
        assert_eq!(
            refresh_period(60_000),
            Some(Duration::from_nanos(16_666_666))
        );
        assert_eq!(refresh_period(0), None);
    }
}
