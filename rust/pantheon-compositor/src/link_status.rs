//! Policy for answering a DRM `link-status = Bad` connector property.
//!
//! The Apple DCP driver sets `link-status` to Bad when its display pipeline has
//! lost the mode (a dock route moved, a sink re-trained) and documents that
//! "userspace needs to trigger a flush, or the CRTC gets no signal". Plane-only
//! page flips never retrain the link, so the compositor must write `Good` back,
//! which the atomic core turns into a full modeset on that connector's CRTC.
//! This module only decides *when* to do that so the loop stays bounded.

use std::time::{Duration, Instant};

/// Raw values of the `link-status` enum property.
pub const LINK_STATUS_GOOD: u64 = 0;
pub const LINK_STATUS_BAD: u64 = 1;

/// Minimum time between two reset attempts on one connector.
pub const MIN_RETRY_INTERVAL: Duration = Duration::from_secs(5);
/// Attempts per bad episode before giving up until the link reads Good again
/// or the connector is replugged.
pub const MAX_ATTEMPTS: u32 = 3;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ResetState {
    attempts: u32,
    last_attempt: Instant,
}

impl ResetState {
    /// Current bounded attempt count, exposed for lifecycle diagnostics only.
    pub fn attempts(&self) -> u32 {
        self.attempts
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Action {
    /// Nothing to do (link is good, waiting for the retry interval, or gave up).
    Wait,
    /// Write `Good` to the property now.
    Reset,
}

/// Decide what to do for one connector given its current raw `link-status`.
/// `state` is the per-connector memory; it is cleared when the link is Good.
pub fn decide(state: &mut Option<ResetState>, raw_value: u64, now: Instant) -> Action {
    if raw_value != LINK_STATUS_BAD {
        *state = None;
        return Action::Wait;
    }
    match state {
        None => {
            *state = Some(ResetState {
                attempts: 1,
                last_attempt: now,
            });
            Action::Reset
        }
        Some(memory) => {
            if memory.attempts >= MAX_ATTEMPTS
                || now.duration_since(memory.last_attempt) < MIN_RETRY_INTERVAL
            {
                return Action::Wait;
            }
            memory.attempts += 1;
            memory.last_attempt = now;
            Action::Reset
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn secs(n: u64) -> Duration {
        Duration::from_secs(n)
    }

    #[test]
    fn good_link_does_nothing_and_clears_memory() {
        let t0 = Instant::now();
        let mut state = None;
        assert_eq!(decide(&mut state, LINK_STATUS_BAD, t0), Action::Reset);
        assert!(state.is_some());
        assert_eq!(
            decide(&mut state, LINK_STATUS_GOOD, t0 + secs(1)),
            Action::Wait
        );
        assert!(state.is_none());
    }

    #[test]
    fn bad_link_resets_immediately_then_waits_for_the_interval() {
        let t0 = Instant::now();
        let mut state = None;
        assert_eq!(decide(&mut state, LINK_STATUS_BAD, t0), Action::Reset);
        assert_eq!(
            decide(&mut state, LINK_STATUS_BAD, t0 + secs(2)),
            Action::Wait
        );
        assert_eq!(
            decide(&mut state, LINK_STATUS_BAD, t0 + secs(5)),
            Action::Reset
        );
    }

    #[test]
    fn gives_up_after_the_attempt_budget() {
        let t0 = Instant::now();
        let mut state = None;
        let mut resets = 0;
        for step in 0..10 {
            if decide(&mut state, LINK_STATUS_BAD, t0 + secs(step * 6)) == Action::Reset {
                resets += 1;
            }
        }
        assert_eq!(resets, MAX_ATTEMPTS);
    }

    #[test]
    fn a_new_bad_episode_after_good_gets_a_fresh_budget() {
        let t0 = Instant::now();
        let mut state = None;
        for step in 0..4 {
            decide(&mut state, LINK_STATUS_BAD, t0 + secs(step * 6));
        }
        decide(&mut state, LINK_STATUS_GOOD, t0 + secs(30));
        assert_eq!(
            decide(&mut state, LINK_STATUS_BAD, t0 + secs(31)),
            Action::Reset
        );
    }
}
