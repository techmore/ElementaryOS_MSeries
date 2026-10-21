//! The consent state machine: nothing is streamed until the person at the
//! desktop says yes, view-only is the default, control is a separate yes, and
//! the owner can end or downgrade a session at any moment.
//!
//! ```text
//!   Idle ──request(invite)──▶ Pending ──Allow──▶ Active ◀──attach(resume)── Grace
//!    ▲          │  Deny/timeout                    │ detach (viewer lost)      │
//!    └──────────┴──────────── end / expiry ◀───────┴───────────────────────────┘
//! ```
//!
//! One viewer at a time. The machine is pure: time comes from a [`Clock`] and
//! effects are returned as [`Event`]s for the daemon to deliver.

use std::sync::Arc;

use serde::Serialize;

use crate::audit::{AuditEvent, AuditSink};
use crate::auth::{AuthError, Claims, InviteStore, TokenKey};
use crate::clock::{Clock, Millis};

#[derive(Debug, Clone, Copy)]
pub struct Policy {
    /// How long the owner has to answer a request.
    pub consent_timeout_ms: Millis,
    /// How long a dropped viewer may re-attach without asking again.
    pub grace_ms: Millis,
    /// Hard session length cap.
    pub max_session_ms: Millis,
    /// End the session after this long without any viewer activity.
    pub idle_timeout_ms: Millis,
    pub invite_ttl_ms: Millis,
    pub max_pending_invites: usize,
}

impl Default for Policy {
    fn default() -> Self {
        Self {
            consent_timeout_ms: 60_000,
            grace_ms: 30_000,
            max_session_ms: 8 * 3600 * 1000,
            idle_timeout_ms: 30 * 60 * 1000,
            invite_ttl_ms: 5 * 60 * 1000,
            max_pending_invites: 4,
        }
    }
}

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum ConsentError {
    #[error("another request or session is in progress")]
    Busy,
    #[error("no such pending request")]
    NoSuchRequest,
    #[error("no active session")]
    NoSession,
    #[error("this invite does not permit remote control")]
    ControlNotPermitted,
    #[error(transparent)]
    Auth(#[from] AuthError),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Decision {
    Allow { control: bool },
    Deny,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PendingRequest {
    pub id: String,
    pub device: String,
    /// The invite allows the owner to grant control.
    pub control_offered: bool,
    pub requested_ms: Millis,
    pub expires_ms: Millis,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SessionInfo {
    pub id: String,
    pub device: String,
    pub control: bool,
    pub control_permitted: bool,
    pub started_ms: Millis,
    pub connected: bool,
}

/// What the viewer receives on approval.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Grant {
    pub session: SessionInfo,
    pub resume_token: String,
    pub grace_ms: Millis,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Idle,
    Pending,
    Active,
    Grace,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Status {
    pub phase: Phase,
    pub pending: Option<PendingRequest>,
    pub session: Option<SessionInfo>,
    pub grace_until_ms: Option<Millis>,
    pub invites_pending: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Event {
    Requested(PendingRequest),
    Granted(SessionInfo),
    Denied { request_id: String, reason: String },
    Attached { session_id: String },
    Detached { session_id: String },
    ModeChanged { session_id: String, control: bool },
    Ended { session_id: String, reason: String },
}

enum State {
    Idle,
    Pending {
        req: PendingRequest,
    },
    Active {
        session: SessionInfo,
        last_activity: Millis,
    },
    Grace {
        session: SessionInfo,
        until: Millis,
        last_activity: Millis,
    },
}

pub struct ConsentManager {
    policy: Policy,
    clock: Arc<dyn Clock>,
    audit: Box<dyn AuditSink>,
    key: TokenKey,
    invites: InviteStore,
    state: State,
    events: Vec<Event>,
}

fn random_id() -> String {
    use base64::Engine;
    base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(rand::random::<[u8; 9]>())
}

impl ConsentManager {
    pub fn new(policy: Policy, clock: Arc<dyn Clock>, audit: Box<dyn AuditSink>) -> Self {
        Self {
            invites: InviteStore::new(policy.invite_ttl_ms, policy.max_pending_invites),
            policy,
            clock,
            audit,
            key: TokenKey::random(),
            state: State::Idle,
            events: Vec::new(),
        }
    }

    fn log(&mut self, event: &str, session: Option<&str>, device: Option<&str>, detail: Option<&str>) {
        let ev = AuditEvent {
            ts_ms: self.clock.now_ms(),
            event: event.into(),
            session: session.map(Into::into),
            device: device.map(Into::into),
            detail: detail.map(Into::into),
        };
        self.audit.record(&ev);
    }

    pub fn take_events(&mut self) -> Vec<Event> {
        std::mem::take(&mut self.events)
    }

    pub fn policy(&self) -> &Policy {
        &self.policy
    }

    /// Owner action: make a link/QR secret for a phone.
    pub fn create_invite(&mut self, allow_control: bool) -> Result<String, ConsentError> {
        self.tick();
        if !matches!(self.state, State::Idle) {
            return Err(ConsentError::Busy);
        }
        let now = self.clock.now_ms();
        let token = self.invites.create(now, allow_control)?;
        self.log("invite_created", None, None, Some(if allow_control { "control_offered" } else { "view_only" }));
        Ok(token)
    }

    /// Viewer presented an invite: ask the owner. The invite is consumed only
    /// when the machine is idle, so a busy host does not burn a valid invite.
    pub fn request(&mut self, invite: &str, device: &str) -> Result<PendingRequest, ConsentError> {
        self.tick();
        if !matches!(self.state, State::Idle) {
            return Err(ConsentError::Busy);
        }
        let now = self.clock.now_ms();
        let grant = match self.invites.redeem(now, invite) {
            Ok(g) => g,
            Err(e) => {
                self.log("invite_rejected", None, Some(device), Some(&e.to_string()));
                return Err(e.into());
            }
        };
        let req = PendingRequest {
            id: random_id(),
            device: device.to_string(),
            control_offered: grant.allow_control,
            requested_ms: now,
            expires_ms: now + self.policy.consent_timeout_ms,
        };
        self.log("consent_requested", None, Some(device), None);
        self.events.push(Event::Requested(req.clone()));
        self.state = State::Pending { req: req.clone() };
        Ok(req)
    }

    /// Owner answered. `Allow { control: true }` needs the invite to have
    /// offered control; otherwise the owner can only grant view-only.
    pub fn decide(&mut self, request_id: &str, decision: Decision) -> Result<Option<Grant>, ConsentError> {
        self.tick();
        let req = match &self.state {
            State::Pending { req } if req.id == request_id => req.clone(),
            _ => return Err(ConsentError::NoSuchRequest),
        };
        let now = self.clock.now_ms();
        match decision {
            Decision::Deny => {
                self.state = State::Idle;
                self.log("consent_denied", None, Some(&req.device), Some("owner"));
                self.events.push(Event::Denied {
                    request_id: req.id,
                    reason: "The owner declined.".into(),
                });
                Ok(None)
            }
            Decision::Allow { control } => {
                if control && !req.control_offered {
                    return Err(ConsentError::ControlNotPermitted);
                }
                let session = SessionInfo {
                    id: random_id(),
                    device: req.device.clone(),
                    control,
                    control_permitted: req.control_offered,
                    started_ms: now,
                    connected: false,
                };
                let resume_token = self.key.issue(&Claims {
                    sid: session.id.clone(),
                    exp: now + self.policy.max_session_ms,
                });
                self.log(
                    "consent_granted",
                    Some(&session.id),
                    Some(&session.device),
                    Some(if control { "control" } else { "view_only" }),
                );
                self.events.push(Event::Granted(session.clone()));
                // A freshly granted session is treated as detached until the
                // viewer attaches, so an abandoned approval still expires.
                self.state = State::Grace {
                    session: session.clone(),
                    until: now + self.policy.grace_ms,
                    last_activity: now,
                };
                Ok(Some(Grant {
                    session,
                    resume_token,
                    grace_ms: self.policy.grace_ms,
                }))
            }
        }
    }

    /// The viewer (re)connects its signalling socket with a resume token.
    pub fn attach(&mut self, resume_token: &str) -> Result<SessionInfo, ConsentError> {
        self.tick();
        let now = self.clock.now_ms();
        let claims = self.key.verify(resume_token, now)?;
        let (mut session, last_activity, was_grace) = match &self.state {
            State::Active { session, last_activity } if session.id == claims.sid => {
                (session.clone(), *last_activity, false)
            }
            State::Grace { session, last_activity, .. } if session.id == claims.sid => {
                (session.clone(), *last_activity, true)
            }
            _ => return Err(ConsentError::NoSession),
        };
        session.connected = true;
        self.state = State::Active {
            session: session.clone(),
            last_activity: last_activity.max(now),
        };
        self.log(if was_grace { "session_attached" } else { "session_reattached" }, Some(&session.id), Some(&session.device), None);
        self.events.push(Event::Attached { session_id: session.id.clone() });
        Ok(session)
    }

    /// The viewer's connection dropped; keep the session for the grace period.
    pub fn detach(&mut self) {
        let now = self.clock.now_ms();
        if let State::Active { session, last_activity } = &self.state {
            let mut session = session.clone();
            session.connected = false;
            let until = now + self.policy.grace_ms;
            let last_activity = *last_activity;
            self.log("session_detached", Some(&session.id), Some(&session.device), None);
            self.events.push(Event::Detached { session_id: session.id.clone() });
            self.state = State::Grace { session, until, last_activity };
        }
    }

    /// Owner toggles control during a session (downgrade is always allowed;
    /// upgrade only if the invite offered control).
    pub fn set_control(&mut self, control: bool) -> Result<(), ConsentError> {
        self.tick();
        let session = match &mut self.state {
            State::Active { session, .. } | State::Grace { session, .. } => session,
            _ => return Err(ConsentError::NoSession),
        };
        if control && !session.control_permitted {
            return Err(ConsentError::ControlNotPermitted);
        }
        if session.control == control {
            return Ok(());
        }
        session.control = control;
        let (sid, device) = (session.id.clone(), session.device.clone());
        self.log("mode_changed", Some(&sid), Some(&device), Some(if control { "control" } else { "view_only" }));
        self.events.push(Event::ModeChanged { session_id: sid, control });
        Ok(())
    }

    /// Record viewer activity (keeps the idle timer from firing).
    pub fn note_activity(&mut self) {
        let now = self.clock.now_ms();
        if let State::Active { last_activity, .. } = &mut self.state {
            *last_activity = now;
        }
    }

    /// Revoke every outstanding invite without touching a live session.
    pub fn cancel_invites(&mut self) {
        self.invites.clear();
        self.log("invites_cancelled", None, None, None);
    }

    /// Owner stop / revoke. Idempotent. Also cancels a pending request.
    pub fn end(&mut self, reason: &str) {
        match std::mem::replace(&mut self.state, State::Idle) {
            State::Idle => {}
            State::Pending { req } => {
                self.log("consent_cancelled", None, Some(&req.device), Some(reason));
                self.events.push(Event::Denied { request_id: req.id, reason: reason.into() });
            }
            State::Active { session, .. } | State::Grace { session, .. } => {
                self.log("session_ended", Some(&session.id), Some(&session.device), Some(reason));
                self.events.push(Event::Ended { session_id: session.id, reason: reason.into() });
            }
        }
    }

    /// Advance timers. Cheap; called by every entry point and by the daemon's
    /// periodic tick.
    pub fn tick(&mut self) {
        let now = self.clock.now_ms();
        match &self.state {
            State::Pending { req } if now >= req.expires_ms => {
                let req = req.clone();
                self.state = State::Idle;
                self.log("consent_timeout", None, Some(&req.device), None);
                self.events.push(Event::Denied {
                    request_id: req.id,
                    reason: "Nobody answered in time.".into(),
                });
            }
            State::Grace { session, until, .. } if now >= *until => {
                let id = session.id.clone();
                let _ = id;
                self.end("viewer did not return");
            }
            State::Active { session, last_activity } => {
                if now.saturating_sub(session.started_ms) >= self.policy.max_session_ms {
                    self.end("session length limit reached");
                } else if now.saturating_sub(*last_activity) >= self.policy.idle_timeout_ms {
                    self.end("idle timeout");
                }
            }
            _ => {}
        }
    }

    pub fn can_control(&self) -> bool {
        matches!(&self.state, State::Active { session, .. } if session.control)
    }

    pub fn status(&mut self) -> Status {
        self.tick();
        let now = self.clock.now_ms();
        let invites_pending = self.invites.pending(now);
        match &self.state {
            State::Idle => Status { phase: Phase::Idle, pending: None, session: None, grace_until_ms: None, invites_pending },
            State::Pending { req } => Status { phase: Phase::Pending, pending: Some(req.clone()), session: None, grace_until_ms: None, invites_pending },
            State::Active { session, .. } => Status { phase: Phase::Active, pending: None, session: Some(session.clone()), grace_until_ms: None, invites_pending },
            State::Grace { session, until, .. } => Status { phase: Phase::Grace, pending: None, session: Some(session.clone()), grace_until_ms: Some(*until), invites_pending },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audit::MemoryAudit;
    use crate::clock::ManualClock;

    fn manager() -> (ConsentManager, ManualClock, MemoryAudit) {
        let clock = ManualClock::new(1_000_000);
        let audit = MemoryAudit::default();
        let m = ConsentManager::new(Policy::default(), Arc::new(clock.clone()), Box::new(audit.clone()));
        (m, clock, audit)
    }

    fn approved(m: &mut ConsentManager, control_offered: bool, control: bool) -> Grant {
        let inv = m.create_invite(control_offered).unwrap();
        let req = m.request(&inv, "Pixel 8").unwrap();
        m.decide(&req.id, Decision::Allow { control }).unwrap().unwrap()
    }

    #[test]
    fn nothing_streams_without_an_owner_yes() {
        let (mut m, _c, _a) = manager();
        let inv = m.create_invite(true).unwrap();
        let req = m.request(&inv, "Pixel 8").unwrap();
        assert_eq!(m.status().phase, Phase::Pending);
        assert!(!m.can_control());
        assert_eq!(m.decide(&req.id, Decision::Deny).unwrap(), None);
        assert_eq!(m.status().phase, Phase::Idle);
        assert!(matches!(m.take_events().last(), Some(Event::Denied { .. })));
    }

    #[test]
    fn view_only_is_default_and_control_needs_a_second_yes() {
        let (mut m, _c, _a) = manager();
        let g = approved(&mut m, true, false);
        assert!(!g.session.control);
        m.attach(&g.resume_token).unwrap();
        assert!(!m.can_control());
        m.set_control(true).unwrap();
        assert!(m.can_control());
        m.set_control(false).unwrap();
        assert!(!m.can_control());
    }

    #[test]
    fn view_only_invite_can_never_gain_control() {
        let (mut m, _c, _a) = manager();
        let inv = m.create_invite(false).unwrap();
        let req = m.request(&inv, "Pixel 8").unwrap();
        assert_eq!(
            m.decide(&req.id, Decision::Allow { control: true }),
            Err(ConsentError::ControlNotPermitted)
        );
        let g = m.decide(&req.id, Decision::Allow { control: false }).unwrap().unwrap();
        m.attach(&g.resume_token).unwrap();
        assert_eq!(m.set_control(true), Err(ConsentError::ControlNotPermitted));
    }

    #[test]
    fn consent_times_out() {
        let (mut m, c, _a) = manager();
        let inv = m.create_invite(false).unwrap();
        let req = m.request(&inv, "Pixel 8").unwrap();
        c.advance(60_000);
        assert_eq!(m.decide(&req.id, Decision::Allow { control: false }), Err(ConsentError::NoSuchRequest));
        assert_eq!(m.status().phase, Phase::Idle);
    }

    #[test]
    fn one_viewer_at_a_time_and_busy_does_not_burn_the_invite() {
        let (mut m, _c, _a) = manager();
        let first = m.create_invite(false).unwrap();
        let req = m.request(&first, "A").unwrap();
        // While pending a second device is turned away...
        assert_eq!(m.request("whatever", "B"), Err(ConsentError::Busy));
        m.decide(&req.id, Decision::Deny).unwrap();
        // ...and invites can only be minted while idle; a spare minted earlier survives.
        let spare = m.create_invite(false).unwrap();
        let req2 = m.request(&spare, "B").unwrap();
        assert_eq!(m.request(&spare, "C"), Err(ConsentError::Busy));
        m.decide(&req2.id, Decision::Deny).unwrap();
    }

    #[test]
    fn reconnect_inside_grace_needs_no_new_consent_and_after_grace_does() {
        let (mut m, c, _a) = manager();
        let g = approved(&mut m, false, false);
        m.attach(&g.resume_token).unwrap();
        m.detach();
        assert_eq!(m.status().phase, Phase::Grace);
        c.advance(29_000);
        assert!(m.attach(&g.resume_token).is_ok());
        m.detach();
        c.advance(30_000);
        assert_eq!(m.attach(&g.resume_token), Err(ConsentError::NoSession));
        assert_eq!(m.status().phase, Phase::Idle);
    }

    #[test]
    fn unattached_approval_expires() {
        let (mut m, c, _a) = manager();
        let g = approved(&mut m, false, false);
        c.advance(31_000);
        assert_eq!(m.attach(&g.resume_token), Err(ConsentError::NoSession));
    }

    #[test]
    fn resume_token_dies_with_the_session_and_cannot_cross_sessions() {
        let (mut m, _c, _a) = manager();
        let g1 = approved(&mut m, false, false);
        m.attach(&g1.resume_token).unwrap();
        m.end("owner stopped");
        assert_eq!(m.attach(&g1.resume_token), Err(ConsentError::NoSession));
        let g2 = approved(&mut m, false, false);
        assert_eq!(m.attach(&g1.resume_token), Err(ConsentError::NoSession));
        assert!(m.attach(&g2.resume_token).is_ok());
    }

    #[test]
    fn idle_and_length_limits_end_the_session() {
        let (mut m, c, a) = manager();
        let g = approved(&mut m, false, false);
        m.attach(&g.resume_token).unwrap();
        c.advance(29 * 60 * 1000);
        m.note_activity();
        c.advance(29 * 60 * 1000);
        assert_eq!(m.status().phase, Phase::Active);
        c.advance(2 * 60 * 1000);
        assert_eq!(m.status().phase, Phase::Idle);
        assert!(a.names().contains(&"session_ended".to_string()));
    }

    #[test]
    fn audit_records_the_lifecycle_without_secrets() {
        let (mut m, _c, a) = manager();
        let inv = m.create_invite(true).unwrap();
        let req = m.request(&inv, "Pixel 8").unwrap();
        let g = m.decide(&req.id, Decision::Allow { control: true }).unwrap().unwrap();
        m.attach(&g.resume_token).unwrap();
        m.end("owner stopped");
        assert_eq!(
            a.names(),
            ["invite_created", "consent_requested", "consent_granted", "session_attached", "session_ended"]
        );
        let dump = serde_json::to_string(&a.events()).unwrap();
        assert!(!dump.contains(&inv) && !dump.contains(&g.resume_token));
    }

    #[test]
    fn bad_invites_are_audited_and_rejected() {
        let (mut m, _c, a) = manager();
        assert!(matches!(m.request("nope", "X"), Err(ConsentError::Auth(AuthError::InvalidInvite))));
        assert!(a.names().contains(&"invite_rejected".to_string()));
    }
}
