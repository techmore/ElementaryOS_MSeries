//! Pure scheduling decisions for DRM connector reconciliation.
//!
//! The native backend reconciles connectors when a udev `drm` event arrives
//! for its KMS device, once more shortly afterwards (EDID and link training
//! often settle after the first uevent), when a retired Wayland global is due
//! for removal, and on a slow safety poll in case an event was missed. This
//! module holds only the decision logic so it can be unit tested without a
//! display, a udev monitor or an event loop.

use std::time::{Duration, Instant};

/// Delay between the first uevent and the reconcile, coalescing event bursts.
pub const EVENT_DEBOUNCE: Duration = Duration::from_millis(250);
/// One extra reconcile after an event-driven one, for late-settling connectors.
pub const EVENT_RECHECK: Duration = Duration::from_secs(1);
/// Safety poll while the udev monitor is active.
pub const SAFETY_POLL: Duration = Duration::from_secs(30);
/// Fallback poll used only when the udev monitor could not be created.
pub const FALLBACK_POLL: Duration = Duration::from_secs(2);

/// Kind of udev event, mirroring Smithay's `UdevEvent` without its payload.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EventKind {
    Added,
    Changed,
    Removed,
}

/// Whether a udev drm event should schedule a reconcile. Only events for the
/// KMS device this backend drives matter; other GPUs and render nodes do not.
pub fn event_triggers_reconcile(kind: EventKind, event_dev: u64, kms_dev: u64) -> bool {
    // Add, change and remove of our device can all alter connector state.
    let _ = kind;
    event_dev == kms_dev
}

#[derive(Debug)]
pub struct HotplugScheduler {
    safety_interval: Duration,
    /// Earliest instant at which an event-driven reconcile is due.
    due: Option<Instant>,
    /// True once the single follow-up reconcile after an event has been queued.
    followup_queued: bool,
    last_reconcile: Instant,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Tick {
    /// Run `refresh_connectors` now.
    pub reconcile: bool,
    /// Observed due conditions, for diagnostics only.
    pub event_due: bool,
    pub followup_due: bool,
    pub removal_due: bool,
    pub safety_due: bool,
    /// Next instant an event-driven timer must wake (none: let it drop).
    pub next_event_deadline: Option<Instant>,
    /// Next instant the safety poll must wake.
    pub next_safety: Instant,
}

impl HotplugScheduler {
    pub fn new(now: Instant, udev_active: bool) -> Self {
        Self {
            safety_interval: if udev_active {
                SAFETY_POLL
            } else {
                FALLBACK_POLL
            },
            due: None,
            followup_queued: false,
            last_reconcile: now,
        }
    }

    pub fn safety_interval(&self) -> Duration {
        self.safety_interval
    }

    /// Record a relevant uevent. Returns the instant a new one-shot timer must
    /// be armed for, or `None` when an already armed deadline covers it.
    pub fn on_event(&mut self, now: Instant) -> Option<Instant> {
        let wanted = now + EVENT_DEBOUNCE;
        self.followup_queued = false;
        match self.due {
            Some(due) if due <= wanted => None,
            _ => {
                self.due = Some(wanted);
                Some(wanted)
            }
        }
    }

    /// Decide what to do at `now`. `removal_deadline` is the earliest pending
    /// Wayland global removal, which only `refresh_connectors` performs.
    pub fn tick(&mut self, now: Instant, removal_deadline: Option<Instant>) -> Tick {
        let event_due = self.due.is_some_and(|due| due <= now);
        let followup_due = event_due && self.followup_queued;
        let removal_due = removal_deadline.is_some_and(|d| d <= now);
        let safety_due = now >= self.last_reconcile + self.safety_interval;
        let reconcile = event_due || removal_due || safety_due;
        if reconcile {
            self.last_reconcile = now;
            if event_due {
                if self.followup_queued {
                    self.due = None;
                    self.followup_queued = false;
                } else {
                    self.due = Some(now + EVENT_RECHECK);
                    self.followup_queued = true;
                }
            }
        }
        Tick {
            reconcile,
            event_due,
            followup_due,
            removal_due,
            safety_due,
            next_event_deadline: [self.due, removal_deadline].into_iter().flatten().min(),
            next_safety: self.last_reconcile + self.safety_interval,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ms(n: u64) -> Duration {
        Duration::from_millis(n)
    }

    #[test]
    fn only_our_device_triggers() {
        for kind in [EventKind::Added, EventKind::Changed, EventKind::Removed] {
            assert!(event_triggers_reconcile(kind, 226, 226));
            assert!(!event_triggers_reconcile(kind, 227, 226));
        }
    }

    #[test]
    fn idle_does_not_reconcile_before_safety_poll() {
        let t0 = Instant::now();
        let mut s = HotplugScheduler::new(t0, true);
        let tick = s.tick(t0 + Duration::from_secs(29), None);
        assert!(!tick.reconcile);
        assert_eq!(tick.next_event_deadline, None);
        assert!(s.tick(t0 + Duration::from_secs(30), None).reconcile);
    }

    #[test]
    fn fallback_polls_every_two_seconds() {
        let t0 = Instant::now();
        let mut s = HotplugScheduler::new(t0, false);
        assert!(!s.tick(t0 + ms(1999), None).reconcile);
        assert!(s.tick(t0 + ms(2000), None).reconcile);
    }

    #[test]
    fn event_debounces_then_reconciles_then_one_followup() {
        let t0 = Instant::now();
        let mut s = HotplugScheduler::new(t0, true);
        assert_eq!(s.on_event(t0), Some(t0 + EVENT_DEBOUNCE));
        // A burst is coalesced into the already armed deadline.
        assert_eq!(s.on_event(t0 + ms(100)), None);
        assert!(!s.tick(t0 + ms(200), None).reconcile);
        let first = s.tick(t0 + ms(250), None);
        assert!(first.reconcile);
        assert_eq!(
            first.next_event_deadline,
            Some(t0 + ms(250) + EVENT_RECHECK)
        );
        let second = s.tick(t0 + ms(1250), None);
        assert!(second.reconcile);
        assert_eq!(second.next_event_deadline, None);
        assert!(!s.tick(t0 + ms(5000), None).reconcile);
    }

    #[test]
    fn event_during_followup_wait_arms_earlier_timer() {
        let t0 = Instant::now();
        let mut s = HotplugScheduler::new(t0, true);
        s.on_event(t0);
        s.tick(t0 + ms(250), None); // follow-up due at +1250
        let now = t0 + ms(300);
        assert_eq!(s.on_event(now), Some(now + EVENT_DEBOUNCE));
        // The new event restarts the reconcile + single follow-up cycle.
        assert!(s.tick(now + EVENT_DEBOUNCE, None).reconcile);
        assert!(s.tick(now + EVENT_DEBOUNCE + EVENT_RECHECK, None).reconcile);
        assert_eq!(s.tick(now + ms(5000), None).next_event_deadline, None);
    }

    #[test]
    fn pending_global_removal_forces_reconcile_when_due() {
        let t0 = Instant::now();
        let mut s = HotplugScheduler::new(t0, true);
        let deadline = t0 + Duration::from_secs(2);
        let early = s.tick(t0 + ms(500), Some(deadline));
        assert!(!early.reconcile);
        assert_eq!(early.next_event_deadline, Some(deadline));
        assert!(s.tick(deadline, Some(deadline)).reconcile);
    }

    #[test]
    fn safety_poll_is_rescheduled_from_last_reconcile() {
        let t0 = Instant::now();
        let mut s = HotplugScheduler::new(t0, true);
        s.on_event(t0);
        let tick = s.tick(t0 + EVENT_DEBOUNCE, None);
        assert_eq!(tick.next_safety, t0 + EVENT_DEBOUNCE + SAFETY_POLL);
    }
}
