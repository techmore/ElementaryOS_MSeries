//! systemd watchdog and status line.
//!
//! With `WatchdogSec=` set, systemd passes `WATCHDOG_USEC`; an event-loop
//! timer then sends `WATCHDOG=1` every third of that, so the pings stop only
//! when the loop itself stops turning (a hang) and systemd restarts the
//! service. Each ping also updates `STATUS=` (flip rate, commit rate, busiest
//! client, any stuck page flip) for `systemctl --user status`. A page flip that
//! never completes is logged and shown, but pings continue: the output can
//! recover (hotplug, link retrain) without killing every Wayland client.

use std::time::{Duration, Instant};

use smithay::reexports::calloop::timer::{TimeoutAction, Timer};

use crate::PantheonCompositor;

/// A flip pending longer than this is reported as stuck.
#[cfg_attr(not(feature = "native-drm"), allow(dead_code))]
pub const STUCK_FLIP: Duration = Duration::from_secs(1);

/// Ping interval for `WATCHDOG_USEC` (a third of it), or `None` when the
/// watchdog is off or meant for another process (`WATCHDOG_PID`).
pub fn interval(usec: Option<&str>, pid: Option<&str>, own_pid: u32) -> Option<Duration> {
    let usec = usec?.trim().parse::<u64>().ok().filter(|usec| *usec > 0)?;
    if let Some(pid) = pid
        && pid.trim().parse::<u32>().ok() != Some(own_pid)
    {
        return None;
    }
    Some(Duration::from_micros(usec / 3).max(Duration::from_millis(100)))
}

/// One-line service status, e.g.
/// `58 flips/s, 114 commits/s, busiest brave(1234); flip stuck on eDP-1 for 3.2 s`.
pub fn status(
    flips_per_s: f64,
    commits_per_s: f64,
    busiest: Option<&str>,
    stuck: &[(String, Duration)],
) -> String {
    let mut line = format!("{flips_per_s:.0} flips/s, {commits_per_s:.0} commits/s");
    if let Some(busiest) = busiest {
        line.push_str(", busiest ");
        line.push_str(busiest);
    }
    for (output, age) in stuck {
        line.push_str(&format!(
            "; flip stuck on {output} for {:.1} s",
            age.as_secs_f64()
        ));
    }
    line
}

/// Arm the watchdog timer if systemd asked for one. Call once, after READY=1.
pub fn start(state: &mut PantheonCompositor) {
    let Some(every) = interval(
        std::env::var("WATCHDOG_USEC").ok().as_deref(),
        std::env::var("WATCHDOG_PID").ok().as_deref(),
        std::process::id(),
    ) else {
        return;
    };
    tracing::info!(
        interval_ms = every.as_millis() as u64,
        "systemd watchdog enabled"
    );
    let mut last = (Instant::now(), crate::metrics::totals());
    let timer = Timer::immediate();
    let armed = state.loop_handle.insert_source(timer, move |_, _, state| {
        let now = Instant::now();
        let totals = crate::metrics::totals();
        let seconds = now.duration_since(last.0).as_secs_f64().max(0.001);
        let flips = totals.vblanks.saturating_sub(last.1.vblanks) as f64 / seconds;
        let commits = totals.commits.saturating_sub(last.1.commits) as f64 / seconds;
        last = (now, totals);
        let stuck = state.stuck_flips();
        for (output, age) in &stuck {
            tracing::warn!(
                output,
                pending_ms = age.as_millis() as u64,
                "page flip has not completed"
            );
        }
        let line = status(
            flips,
            commits,
            state.client_registry.busiest().as_deref(),
            &stuck,
        );
        if let Err(error) = crate::notify_systemd(&format!("WATCHDOG=1\nSTATUS={line}")) {
            tracing::warn!(?error, "could not ping the systemd watchdog");
        }
        TimeoutAction::ToDuration(every)
    });
    if let Err(error) = armed {
        tracing::error!(?error, "could not arm the systemd watchdog timer");
    }
}

impl PantheonCompositor {
    /// Outputs whose queued page flip has been pending longer than `STUCK_FLIP`.
    fn stuck_flips(&self) -> Vec<(String, Duration)> {
        #[cfg(feature = "native-drm")]
        if let Some(backend) = self.native_backend.as_ref() {
            return backend
                .kms
                .stuck_flips(self.monotonic_clock.now().into(), STUCK_FLIP);
        }
        Vec::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interval_is_a_third_of_watchdog_usec_for_us_only() {
        assert_eq!(
            interval(Some("30000000"), None, 7),
            Some(Duration::from_secs(10))
        );
        assert_eq!(
            interval(Some("30000000"), Some("7"), 7),
            Some(Duration::from_secs(10))
        );
        assert_eq!(interval(Some("30000000"), Some("8"), 7), None);
        assert_eq!(interval(Some("0"), None, 7), None);
        assert_eq!(interval(Some("junk"), None, 7), None);
        assert_eq!(interval(None, None, 7), None);
        assert_eq!(
            interval(Some("90"), None, 7),
            Some(Duration::from_millis(100))
        );
    }

    #[test]
    fn status_names_busiest_client_and_stuck_outputs() {
        assert_eq!(status(58.4, 113.6, None, &[]), "58 flips/s, 114 commits/s");
        assert_eq!(
            status(
                0.0,
                3.0,
                Some("brave(1234)"),
                &[("eDP-1".into(), Duration::from_millis(3_200))]
            ),
            "0 flips/s, 3 commits/s, busiest brave(1234); flip stuck on eDP-1 for 3.2 s"
        );
    }
}
