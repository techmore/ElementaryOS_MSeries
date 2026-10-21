//! Reconnect schedule: exponential with a cap and deterministic jitter input,
//! so both the Rust viewer client and tests share one policy. The phone web
//! client implements the same schedule (`web/app.js`).

use std::time::Duration;

#[derive(Debug, Clone, Copy)]
pub struct Backoff {
    pub base: Duration,
    pub cap: Duration,
    /// Give up after this many consecutive failures (None = never).
    pub max_attempts: Option<u32>,
}

impl Default for Backoff {
    fn default() -> Self {
        Self {
            base: Duration::from_millis(500),
            cap: Duration::from_secs(15),
            max_attempts: Some(8),
        }
    }
}

impl Backoff {
    /// Delay before retry number `attempt` (0-based). `jitter` is in 0.0..=1.0
    /// and scales the delay between 50% and 100% so reconnect storms spread out.
    /// Returns `None` when the attempt budget is exhausted.
    pub fn delay(&self, attempt: u32, jitter: f64) -> Option<Duration> {
        if self.max_attempts.is_some_and(|m| attempt >= m) {
            return None;
        }
        let exp = self.base.saturating_mul(1u32.checked_shl(attempt.min(16)).unwrap_or(u32::MAX));
        let capped = exp.min(self.cap);
        let j = 0.5 + 0.5 * jitter.clamp(0.0, 1.0);
        Some(capped.mul_f64(j))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn grows_caps_and_gives_up() {
        let b = Backoff::default();
        assert_eq!(b.delay(0, 1.0), Some(Duration::from_millis(500)));
        assert_eq!(b.delay(1, 1.0), Some(Duration::from_secs(1)));
        assert_eq!(b.delay(2, 0.0), Some(Duration::from_secs(1)));
        assert_eq!(b.delay(7, 1.0), Some(Duration::from_secs(15)));
        assert_eq!(b.delay(8, 1.0), None);
    }

    #[test]
    fn unbounded_attempts_never_overflow() {
        let b = Backoff { max_attempts: None, ..Backoff::default() };
        assert_eq!(b.delay(u32::MAX, 1.0), Some(Duration::from_secs(15)));
    }
}
