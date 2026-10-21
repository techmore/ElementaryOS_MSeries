//! Input gating: view-only enforcement, rate limiting and the sink trait the
//! platform backends implement. The gate is the only path from the network to
//! a sink, and it never lets an event through unless the consent machine says
//! control is currently granted.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};

use crate::clock::Millis;
use crate::protocol::InputEvent;

#[derive(Debug, thiserror::Error, PartialEq, Eq, Clone)]
pub enum InputError {
    /// Screen locked or session inactive: injecting would type into a lock screen.
    #[error("desktop locked or inactive")]
    Locked,
    #[error("input backend unavailable: {0}")]
    Unavailable(String),
    #[error("input backend error: {0}")]
    Backend(String),
}

/// Platform injection backend (Mutter RemoteDesktop on Pantheon/Wayland).
pub trait InputSink: Send {
    fn apply(&mut self, event: &InputEvent) -> Result<(), InputError>;
    /// Release any held buttons/keys. Called when control ends or the viewer drops.
    fn release_all(&mut self);
}

/// Token bucket: `rate` events/s sustained, `burst` at once.
pub struct RateLimiter {
    rate: f64,
    burst: f64,
    tokens: f64,
    last_ms: Millis,
}

impl RateLimiter {
    pub fn new(rate_per_s: f64, burst: f64, now: Millis) -> Self {
        Self { rate: rate_per_s, burst, tokens: burst, last_ms: now }
    }

    pub fn allow(&mut self, now: Millis) -> bool {
        let dt = now.saturating_sub(self.last_ms) as f64 / 1000.0;
        self.last_ms = now;
        self.tokens = (self.tokens + dt * self.rate).min(self.burst);
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Outcome {
    Applied,
    Rejected(&'static str),
}

pub struct InputGate {
    sink: Box<dyn InputSink>,
    limiter: RateLimiter,
    /// Held-down button state so a drop mid-drag releases cleanly.
    dirty: bool,
}

impl InputGate {
    pub fn new(sink: Box<dyn InputSink>, now: Millis) -> Self {
        Self { sink, limiter: RateLimiter::new(240.0, 60.0, now), dirty: false }
    }

    /// `control` is the consent machine's current answer, evaluated per event so
    /// a mid-session downgrade takes effect on the very next event.
    pub fn handle(&mut self, event: &InputEvent, control: bool, now: Millis) -> Outcome {
        if matches!(event, InputEvent::Ping { .. }) {
            return Outcome::Applied;
        }
        if !control {
            if self.dirty {
                self.release_all();
            }
            return Outcome::Rejected("view_only");
        }
        if !self.limiter.allow(now) {
            return Outcome::Rejected("rate_limited");
        }
        match self.sink.apply(event) {
            Ok(()) => {
                self.dirty = matches!(event, InputEvent::Button { down: true, .. });
                Outcome::Applied
            }
            Err(InputError::Locked) => Outcome::Rejected("desktop_locked"),
            Err(e) => {
                tracing::warn!("input backend: {e}");
                Outcome::Rejected("input_unavailable")
            }
        }
    }

    pub fn release_all(&mut self) {
        self.dirty = false;
        self.sink.release_all();
    }
}

impl Drop for InputGate {
    fn drop(&mut self) {
        self.sink.release_all();
    }
}

/// Test sink that records what reached the platform layer.
#[derive(Clone, Default)]
pub struct RecordingSink {
    pub events: Arc<Mutex<Vec<InputEvent>>>,
    pub releases: Arc<AtomicUsize>,
    pub locked: Arc<std::sync::atomic::AtomicBool>,
}

impl InputSink for RecordingSink {
    fn apply(&mut self, event: &InputEvent) -> Result<(), InputError> {
        if self.locked.load(Ordering::SeqCst) {
            return Err(InputError::Locked);
        }
        self.events.lock().unwrap().push(event.clone());
        Ok(())
    }

    fn release_all(&mut self) {
        self.releases.fetch_add(1, Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::Button;

    fn gate() -> (InputGate, RecordingSink) {
        let sink = RecordingSink::default();
        (InputGate::new(Box::new(sink.clone()), 0), sink)
    }

    #[test]
    fn view_only_drops_everything_but_ping() {
        let (mut g, s) = gate();
        let mv = InputEvent::Move { dx: 1.0, dy: 1.0 };
        assert_eq!(g.handle(&mv, false, 0), Outcome::Rejected("view_only"));
        assert_eq!(g.handle(&InputEvent::Ping { t: 1 }, false, 0), Outcome::Applied);
        assert!(s.events.lock().unwrap().is_empty());
    }

    #[test]
    fn downgrade_takes_effect_on_the_next_event_and_releases_buttons() {
        let (mut g, s) = gate();
        let down = InputEvent::Button { button: Button::Left, down: true };
        assert_eq!(g.handle(&down, true, 0), Outcome::Applied);
        assert_eq!(g.handle(&InputEvent::Move { dx: 1.0, dy: 0.0 }, false, 1), Outcome::Rejected("view_only"));
        assert_eq!(s.releases.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn rate_limit_applies_and_recovers() {
        let (mut g, s) = gate();
        let mv = InputEvent::Move { dx: 1.0, dy: 0.0 };
        let applied = (0..200).filter(|_| g.handle(&mv, true, 0) == Outcome::Applied).count();
        assert_eq!(applied, 60);
        assert_eq!(g.handle(&mv, true, 0), Outcome::Rejected("rate_limited"));
        assert_eq!(g.handle(&mv, true, 500), Outcome::Applied);
        assert!(s.events.lock().unwrap().len() > 60);
    }

    #[test]
    fn locked_desktop_is_reported_not_typed() {
        let (mut g, s) = gate();
        s.locked.store(true, Ordering::SeqCst);
        let k = InputEvent::Text { text: "hunter2".into() };
        assert_eq!(g.handle(&k, true, 0), Outcome::Rejected("desktop_locked"));
        assert!(s.events.lock().unwrap().is_empty());
    }

    #[test]
    fn dropping_the_gate_releases_held_input() {
        let (g, s) = gate();
        drop(g);
        assert_eq!(s.releases.load(Ordering::SeqCst), 1);
    }
}
