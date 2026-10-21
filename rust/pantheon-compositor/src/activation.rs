//! Policy for xdg-activation requests, i.e. what happens when an application
//! calls GTK's `present()` (or any toolkit's equivalent) on its window.
//!
//! A toolkit asks the compositor for an activation token, commits it with the
//! serial of the last input event the application saw, and then activates its
//! surface with that token. An application that has not just received input
//! (a launcher script, a second instance, a notification handler) has no recent
//! serial, so a strict compositor drops the request and the window stays where
//! it was. That is correct but surprising for a desktop whose owner expects
//! `present()` to bring the window forward.
//!
//! `Raise` keeps the strict path for tokens with a valid recent serial and also
//! honours tokens without one, with one guard against focus stealing: while the
//! user is typing, the raise waits until they pause, so a window can never take
//! the keyboard in the middle of a word or a password.
//!
//! Set `PANTHEON_ACTIVATION_POLICY=strict` to restore the previous behaviour.

use std::time::Duration;

/// Tokens older than this are never acted on, whatever the policy.
pub const TOKEN_MAX_AGE: Duration = Duration::from_secs(10);
/// The user counts as typing for this long after their last key press.
pub const TYPING_IDLE: Duration = Duration::from_millis(1200);
/// A deferred activation is dropped if the user never pauses this long.
pub const DEFER_LIMIT: Duration = Duration::from_secs(8);
/// How often a deferred activation re-checks whether the user paused.
pub const DEFER_POLL: Duration = Duration::from_millis(250);
/// Upper bound on activations waiting for the user to stop typing.
pub const MAX_DEFERRED: usize = 8;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActivationPolicy {
    /// Only tokens carrying a valid recent input serial activate a window.
    Strict,
    /// Also activate on tokens without one, unless the user is typing.
    Raise,
}

impl ActivationPolicy {
    /// `PANTHEON_ACTIVATION_POLICY`; anything but `strict` selects `Raise`.
    pub fn from_env_value(value: Option<&str>) -> Self {
        match value.map(|v| v.trim().to_ascii_lowercase()).as_deref() {
            Some("strict") => Self::Strict,
            _ => Self::Raise,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    Ignore,
    ActivateNow,
    ActivateWhenIdle,
}

#[derive(Debug, Clone, Copy)]
pub struct Request {
    /// The token carried a serial no older than the last keyboard enter.
    pub serial_trusted: bool,
    pub token_age: Duration,
    pub session_locked: bool,
    /// Time since the last key press, if any was seen.
    pub since_last_key: Option<Duration>,
}

/// Whether a freshly created token should be kept so it can be activated later.
pub fn accepts_token(policy: ActivationPolicy, serial_trusted: bool) -> bool {
    serial_trusted || policy == ActivationPolicy::Raise
}

pub fn is_typing(since_last_key: Option<Duration>) -> bool {
    since_last_key.is_some_and(|since| since < TYPING_IDLE)
}

pub fn verdict(policy: ActivationPolicy, request: Request) -> Verdict {
    if request.session_locked || request.token_age > TOKEN_MAX_AGE {
        return Verdict::Ignore;
    }
    if request.serial_trusted {
        return Verdict::ActivateNow;
    }
    match policy {
        ActivationPolicy::Strict => Verdict::Ignore,
        ActivationPolicy::Raise if is_typing(request.since_last_key) => Verdict::ActivateWhenIdle,
        ActivationPolicy::Raise => Verdict::ActivateNow,
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeferStep {
    Wait,
    Go,
    GiveUp,
}

/// One tick of a deferred activation.
pub fn defer_step(waited: Duration, since_last_key: Option<Duration>) -> DeferStep {
    if waited >= DEFER_LIMIT {
        DeferStep::GiveUp
    } else if is_typing(since_last_key) {
        DeferStep::Wait
    } else {
        DeferStep::Go
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(trusted: bool) -> Request {
        Request {
            serial_trusted: trusted,
            token_age: Duration::from_millis(50),
            session_locked: false,
            since_last_key: None,
        }
    }

    #[test]
    fn env_value_defaults_to_raise_and_only_strict_restores_old_behaviour() {
        assert_eq!(
            ActivationPolicy::from_env_value(None),
            ActivationPolicy::Raise
        );
        assert_eq!(
            ActivationPolicy::from_env_value(Some("raise")),
            ActivationPolicy::Raise
        );
        assert_eq!(
            ActivationPolicy::from_env_value(Some("")),
            ActivationPolicy::Raise
        );
        assert_eq!(
            ActivationPolicy::from_env_value(Some("nonsense")),
            ActivationPolicy::Raise
        );
        assert_eq!(
            ActivationPolicy::from_env_value(Some(" Strict ")),
            ActivationPolicy::Strict
        );
    }

    #[test]
    fn strict_policy_keeps_only_trusted_tokens() {
        assert!(accepts_token(ActivationPolicy::Strict, true));
        assert!(!accepts_token(ActivationPolicy::Strict, false));
        assert!(accepts_token(ActivationPolicy::Raise, true));
        assert!(accepts_token(ActivationPolicy::Raise, false));
    }

    #[test]
    fn trusted_tokens_activate_immediately_even_while_typing() {
        // The user's own click or key press asked for this window.
        let mut r = request(true);
        r.since_last_key = Some(Duration::from_millis(10));
        for policy in [ActivationPolicy::Strict, ActivationPolicy::Raise] {
            assert_eq!(verdict(policy, r), Verdict::ActivateNow);
        }
    }

    #[test]
    fn untrusted_token_is_ignored_when_strict_and_raises_when_idle() {
        assert_eq!(
            verdict(ActivationPolicy::Strict, request(false)),
            Verdict::Ignore
        );
        assert_eq!(
            verdict(ActivationPolicy::Raise, request(false)),
            Verdict::ActivateNow
        );
        let mut r = request(false);
        r.since_last_key = Some(Duration::from_secs(30));
        assert_eq!(verdict(ActivationPolicy::Raise, r), Verdict::ActivateNow);
    }

    #[test]
    fn untrusted_token_waits_while_the_user_is_typing() {
        let mut r = request(false);
        r.since_last_key = Some(Duration::from_millis(300));
        assert_eq!(
            verdict(ActivationPolicy::Raise, r),
            Verdict::ActivateWhenIdle
        );
        r.since_last_key = Some(TYPING_IDLE);
        assert_eq!(verdict(ActivationPolicy::Raise, r), Verdict::ActivateNow);
    }

    #[test]
    fn locked_session_and_stale_tokens_are_never_activated() {
        for trusted in [true, false] {
            let mut r = request(trusted);
            r.session_locked = true;
            assert_eq!(verdict(ActivationPolicy::Raise, r), Verdict::Ignore);
            let mut r = request(trusted);
            r.token_age = TOKEN_MAX_AGE + Duration::from_millis(1);
            assert_eq!(verdict(ActivationPolicy::Raise, r), Verdict::Ignore);
        }
        let mut r = request(true);
        r.token_age = TOKEN_MAX_AGE;
        assert_eq!(
            verdict(ActivationPolicy::Raise, r),
            Verdict::ActivateNow,
            "exactly at the limit still counts"
        );
    }

    #[test]
    fn deferred_activation_waits_for_a_pause_then_goes_or_gives_up() {
        let typing = Some(Duration::from_millis(100));
        let paused = Some(Duration::from_secs(2));
        assert_eq!(
            defer_step(Duration::from_millis(250), typing),
            DeferStep::Wait
        );
        assert_eq!(
            defer_step(Duration::from_millis(250), paused),
            DeferStep::Go
        );
        assert_eq!(defer_step(Duration::from_millis(250), None), DeferStep::Go);
        assert_eq!(defer_step(DEFER_LIMIT, paused), DeferStep::GiveUp);
        assert_eq!(
            defer_step(DEFER_LIMIT + DEFER_POLL, typing),
            DeferStep::GiveUp,
            "never waits forever"
        );
    }

    #[test]
    fn typing_window_boundaries() {
        assert!(!is_typing(None));
        assert!(is_typing(Some(Duration::ZERO)));
        assert!(is_typing(Some(TYPING_IDLE - Duration::from_millis(1))));
        assert!(!is_typing(Some(TYPING_IDLE)));
    }
}
