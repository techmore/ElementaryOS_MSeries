//! WebRTC peers for the M-Series remote desktop.
//!
//! * [`host::HostPeer`] answers a viewer's offer, streams H.264 from a
//!   [`remote_core::capture::FrameSource`] and hands validated input events to
//!   a callback.
//! * [`viewer::ViewerPeer`] is the headless counterpart used by the loopback
//!   tests and by `tm-remote-viewer`: it offers, receives and decodes video and
//!   sends input. The phone's browser plays the same role in production.

pub mod config;
pub mod host;
pub mod viewer;

pub use config::{IceServer, RtcConfig};

#[derive(Debug, thiserror::Error)]
pub enum RtcError {
    #[error("webrtc: {0}")]
    WebRtc(String),
    #[error("signalling: {0}")]
    Signal(String),
    #[error("timed out: {0}")]
    Timeout(&'static str),
}

impl From<webrtc::error::Error> for RtcError {
    fn from(e: webrtc::error::Error) -> Self {
        RtcError::WebRtc(e.to_string())
    }
}

/// Connection state as seen by the signalling layer.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LinkState {
    Connecting,
    Connected,
    /// Transient loss; ICE may recover on its own or via a restart offer.
    Disconnected,
    Failed,
    Closed,
}
pub use webrtc::peer_connection::RTCIceCandidateInit;
