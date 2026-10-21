//! Transport-independent core of the M-Series WebRTC remote desktop.
//!
//! Everything here is synchronous and testable without a desktop session, a
//! network or a GPU: the wire protocol, the invite/token authentication, the
//! consent state machine and its audit trail, input validation, and the capture
//! and H.264 encode pipeline (with a deterministic test-pattern source).
//!
//! Scope: POS management, desktop and support use. View-only is the default,
//! frames are never recorded, and every session needs an explicit owner yes.

pub mod audit;
pub mod auth;
pub mod backoff;
pub mod capture;
pub mod clock;
pub mod consent;
pub mod encode;
pub mod input;
pub mod keysym;
pub mod protocol;
