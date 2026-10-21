//! Transport configuration shared by both peers.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IceServer {
    pub urls: Vec<String>,
    pub username: String,
    pub credential: String,
}

#[derive(Debug, Clone)]
pub struct RtcConfig {
    /// Local UDP addresses to bind. `0.0.0.0:0` binds every non-loopback
    /// interface (LAN, Tailscale, dock Ethernet); tests use `127.0.0.1:0`.
    pub udp_bind: Vec<String>,
    pub ice_servers: Vec<IceServer>,
    /// How long to wait for local candidate gathering before answering.
    pub gather_timeout_ms: u64,
    pub fps: u32,
    pub bitrate_bps: u32,
    /// Force an IDR at least this often so a viewer that lost a packet heals.
    pub keyframe_interval_s: u32,
}

impl Default for RtcConfig {
    fn default() -> Self {
        Self {
            udp_bind: vec!["0.0.0.0:0".into()],
            ice_servers: Vec::new(),
            gather_timeout_ms: 3000,
            fps: 30,
            bitrate_bps: 4_000_000,
            keyframe_interval_s: 3,
        }
    }
}

impl RtcConfig {
    pub fn loopback() -> Self {
        Self {
            udp_bind: vec!["127.0.0.1:0".into()],
            gather_timeout_ms: 2000,
            ..Self::default()
        }
    }
}
