//! Wire protocol. Signalling travels over a WebSocket as JSON text frames;
//! input and host status travel over the `input` WebRTC data channel.
//!
//! Every field a peer controls is bounded in [`ClientMsg::validate`] and
//! [`InputEvent::validate`] before anything acts on it.

use serde::{Deserialize, Serialize};

use crate::keysym;

pub const PROTOCOL_VERSION: u32 = 1;
/// Largest signalling frame accepted from a viewer (an SDP is a few KiB).
pub const MAX_SIGNAL_BYTES: usize = 64 * 1024;
/// Largest data-channel message accepted from a viewer.
pub const MAX_INPUT_BYTES: usize = 4 * 1024;
pub const INPUT_CHANNEL_LABEL: &str = "input";

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum ProtocolError {
    #[error("message too large")]
    TooLarge,
    #[error("malformed message: {0}")]
    Malformed(String),
    #[error("unsupported protocol version {0}")]
    Version(u32),
    #[error("invalid field: {0}")]
    Invalid(&'static str),
}

/// Viewer -> host over the signalling socket.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ClientMsg {
    /// First message. Exactly one of `invite` (first pairing) or `resume`
    /// (reconnect inside the grace period) must be present.
    Hello {
        version: u32,
        device: String,
        #[serde(default)]
        invite: Option<String>,
        #[serde(default)]
        resume: Option<String>,
    },
    Offer {
        sdp: String,
    },
    Candidate {
        candidate: String,
        #[serde(default)]
        sdp_mid: Option<String>,
        #[serde(default)]
        sdp_mline_index: Option<u16>,
    },
    Bye,
}

/// STUN/TURN entry the viewer should use (sent only after the owner approves).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IceServerInfo {
    pub urls: Vec<String>,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub username: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub credential: String,
}

/// Host -> viewer over the signalling socket.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ServerMsg {
    /// Invite accepted; the owner has been asked and has not answered yet.
    Pending {
        request_id: String,
        expires_in_s: u64,
    },
    /// Owner said yes. `resume_token` re-attaches during the grace period.
    Granted {
        session_id: String,
        resume_token: String,
        control: bool,
        grace_s: u64,
        #[serde(default)]
        ice_servers: Vec<IceServerInfo>,
    },
    Denied {
        reason: String,
    },
    Answer {
        sdp: String,
    },
    Candidate {
        candidate: String,
        sdp_mid: Option<String>,
        sdp_mline_index: Option<u16>,
    },
    /// Session ended by the owner, policy or timeout. Terminal.
    Ended {
        reason: String,
    },
    Error {
        code: String,
        message: String,
    },
}

impl ClientMsg {
    pub fn parse(text: &str) -> Result<Self, ProtocolError> {
        if text.len() > MAX_SIGNAL_BYTES {
            return Err(ProtocolError::TooLarge);
        }
        let msg: ClientMsg =
            serde_json::from_str(text).map_err(|e| ProtocolError::Malformed(e.to_string()))?;
        msg.validate()?;
        Ok(msg)
    }

    pub fn validate(&self) -> Result<(), ProtocolError> {
        match self {
            ClientMsg::Hello {
                version,
                device,
                invite,
                resume,
            } => {
                if *version != PROTOCOL_VERSION {
                    return Err(ProtocolError::Version(*version));
                }
                if device.is_empty()
                    || device.chars().count() > 64
                    || device.chars().any(|c| c.is_control())
                {
                    return Err(ProtocolError::Invalid("device"));
                }
                match (invite, resume) {
                    (Some(t), None) | (None, Some(t)) if !t.is_empty() && t.len() <= 512 => Ok(()),
                    _ => Err(ProtocolError::Invalid("invite/resume")),
                }
            }
            ClientMsg::Offer { sdp } => {
                if sdp.is_empty() || sdp.len() > MAX_SIGNAL_BYTES - 1024 {
                    Err(ProtocolError::Invalid("sdp"))
                } else {
                    Ok(())
                }
            }
            ClientMsg::Candidate { candidate, .. } => {
                if candidate.len() > 2048 {
                    Err(ProtocolError::Invalid("candidate"))
                } else {
                    Ok(())
                }
            }
            ClientMsg::Bye => Ok(()),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Button {
    Left,
    Right,
    Middle,
}

impl Button {
    /// Linux evdev button code.
    pub fn evdev(self) -> u32 {
        match self {
            Button::Left => 0x110,
            Button::Right => 0x111,
            Button::Middle => 0x112,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Modifier {
    Ctrl,
    Alt,
    Shift,
    Meta,
}

/// Input from the viewer over the `input` data channel.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum InputEvent {
    /// Relative pointer motion in logical pixels (touchpad swipe).
    Move {
        dx: f64,
        dy: f64,
    },
    /// Absolute pointer position, normalised 0.0..=1.0 across the stream.
    MoveAbs {
        x: f64,
        y: f64,
    },
    /// Press or release a button (drag).
    Button {
        button: Button,
        down: bool,
    },
    /// Press and release atomically.
    Click {
        button: Button,
    },
    Scroll {
        dx: f64,
        dy: f64,
    },
    /// Tap one key (names like `Enter`, `ArrowLeft` or a single character).
    Key {
        key: String,
        #[serde(default)]
        modifiers: Vec<Modifier>,
    },
    /// Type literal text.
    Text {
        text: String,
    },
    /// Latency probe; answered with [`HostEvent::Pong`] even in view-only mode.
    Ping {
        t: u64,
    },
    /// The viewer's video stalled (lost packets); ask for an immediate IDR.
    /// Handled by the media layer and allowed in view-only mode.
    Keyframe,
}

/// Host -> viewer over the `input` data channel.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum HostEvent {
    Pong {
        t: u64,
    },
    /// Current permission; sent on open and whenever it changes.
    Mode {
        control: bool,
    },
    /// Input was dropped (view-only, rate limit, locked desktop, invalid).
    Rejected {
        reason: String,
    },
    Ended {
        reason: String,
    },
}

const MAX_MOTION: f64 = 2000.0;

impl InputEvent {
    pub fn parse(bytes: &[u8]) -> Result<Self, ProtocolError> {
        if bytes.len() > MAX_INPUT_BYTES {
            return Err(ProtocolError::TooLarge);
        }
        let ev: InputEvent =
            serde_json::from_slice(bytes).map_err(|e| ProtocolError::Malformed(e.to_string()))?;
        ev.validate()?;
        Ok(ev)
    }

    pub fn validate(&self) -> Result<(), ProtocolError> {
        fn finite_bounded(v: f64) -> bool {
            v.is_finite() && v.abs() <= MAX_MOTION
        }
        match self {
            InputEvent::Move { dx, dy } | InputEvent::Scroll { dx, dy } => {
                if finite_bounded(*dx) && finite_bounded(*dy) {
                    Ok(())
                } else {
                    Err(ProtocolError::Invalid("motion"))
                }
            }
            InputEvent::MoveAbs { x, y } => {
                if (0.0..=1.0).contains(x) && (0.0..=1.0).contains(y) {
                    Ok(())
                } else {
                    Err(ProtocolError::Invalid("position"))
                }
            }
            InputEvent::Button { .. }
            | InputEvent::Click { .. }
            | InputEvent::Ping { .. }
            | InputEvent::Keyframe => Ok(()),
            InputEvent::Key { key, modifiers } => {
                let mut seen = std::collections::HashSet::new();
                if key.is_empty()
                    || key.chars().count() > 32
                    || modifiers.len() > 4
                    || !modifiers.iter().all(|m| seen.insert(*m))
                    || keysym::keysym(key).is_none()
                {
                    Err(ProtocolError::Invalid("key"))
                } else {
                    Ok(())
                }
            }
            InputEvent::Text { text } => {
                if text.is_empty()
                    || text.chars().count() > 512
                    || !text.chars().all(keysym::typeable)
                {
                    Err(ProtocolError::Invalid("text"))
                } else {
                    Ok(())
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hello_requires_exactly_one_credential() {
        let ok = r#"{"type":"hello","version":1,"device":"Pixel","invite":"abc"}"#;
        assert!(ClientMsg::parse(ok).is_ok());
        let both = r#"{"type":"hello","version":1,"device":"Pixel","invite":"a","resume":"b"}"#;
        assert!(ClientMsg::parse(both).is_err());
        let none = r#"{"type":"hello","version":1,"device":"Pixel"}"#;
        assert!(ClientMsg::parse(none).is_err());
    }

    #[test]
    fn rejects_wrong_version_and_oversize() {
        let v2 = r#"{"type":"hello","version":2,"device":"x","invite":"a"}"#;
        assert_eq!(ClientMsg::parse(v2), Err(ProtocolError::Version(2)));
        let big = format!(
            r#"{{"type":"offer","sdp":"{}"}}"#,
            "a".repeat(MAX_SIGNAL_BYTES)
        );
        assert_eq!(ClientMsg::parse(&big), Err(ProtocolError::TooLarge));
    }

    #[test]
    fn rejects_unknown_fields_types() {
        assert!(ClientMsg::parse(r#"{"type":"shell","cmd":"ls"}"#).is_err());
        assert!(InputEvent::parse(br#"{"kind":"exec","cmd":"ls"}"#).is_err());
    }

    #[test]
    fn input_bounds() {
        assert!(InputEvent::parse(br#"{"kind":"move","dx":10,"dy":-3}"#).is_ok());
        assert!(InputEvent::parse(br#"{"kind":"move","dx":1e9,"dy":0}"#).is_err());
        assert!(InputEvent::parse(br#"{"kind":"move_abs","x":1.5,"y":0}"#).is_err());
        assert!(InputEvent::parse(br#"{"kind":"key","key":"Enter","modifiers":["ctrl"]}"#).is_ok());
        assert!(
            InputEvent::parse(br#"{"kind":"key","key":"Enter","modifiers":["ctrl","ctrl"]}"#)
                .is_err()
        );
        assert!(InputEvent::parse(br#"{"kind":"key","key":"NoSuchKey"}"#).is_err());
        assert!(InputEvent::parse(br#"{"kind":"text","text":""}"#).is_err());
    }

    #[test]
    fn nan_is_not_representable_in_json_but_infinity_text_is_rejected() {
        assert!(InputEvent::Move {
            dx: f64::NAN,
            dy: 0.0
        }
        .validate()
        .is_err());
        assert!(InputEvent::Move {
            dx: f64::INFINITY,
            dy: 0.0
        }
        .validate()
        .is_err());
    }
}
