//! `~/.config/mseries/remote-desktop.toml`. Every field has a safe default.

use std::path::{Path, PathBuf};

use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    /// Address the phone-facing HTTP/WebSocket listener binds to while sharing is enabled.
    pub listen: String,
    /// `mutter` (Pantheon/Gala on Wayland) or `test` (synthetic desktop, no input).
    pub backend: String,
    pub fps: u32,
    pub bitrate_kbps: u32,
    pub max_width: u32,
    pub keyframe_interval_s: u32,
    pub stun: Vec<String>,
    pub turn: Option<TurnConfig>,
    /// Hostnames/IPs to offer in invite links instead of auto-detected interfaces.
    pub advertise: Vec<String>,
    /// Start the listener at login. Off by default: sharing is an explicit act.
    pub enable_at_start: bool,
    pub audit_log: Option<PathBuf>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TurnConfig {
    pub urls: Vec<String>,
    pub username: String,
    pub credential: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            listen: "0.0.0.0:8484".into(),
            backend: "mutter".into(),
            fps: 30,
            bitrate_kbps: 4000,
            max_width: 1920,
            keyframe_interval_s: 3,
            stun: Vec::new(),
            turn: None,
            advertise: Vec::new(),
            enable_at_start: false,
            audit_log: None,
        }
    }
}

impl Config {
    pub fn default_path() -> PathBuf {
        let base = std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".config")))
            .unwrap_or_else(|| PathBuf::from("."));
        base.join("mseries").join("remote-desktop.toml")
    }

    pub fn default_audit_path() -> PathBuf {
        let base = std::env::var_os("XDG_STATE_HOME")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".local/state")))
            .unwrap_or_else(|| PathBuf::from("."));
        base.join("mseries").join("remote-desktop-audit.jsonl")
    }

    pub fn load(path: &Path) -> Result<Self, String> {
        match std::fs::read_to_string(path) {
            Ok(text) => Self::parse(&text),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Self::default()),
            Err(e) => Err(format!("{}: {e}", path.display())),
        }
    }

    pub fn parse(text: &str) -> Result<Self, String> {
        let cfg: Config = toml::from_str(text).map_err(|e| e.to_string())?;
        cfg.validate()?;
        Ok(cfg)
    }

    pub fn validate(&self) -> Result<(), String> {
        if !(1..=60).contains(&self.fps) {
            return Err("fps must be 1..=60".into());
        }
        if !(200..=50_000).contains(&self.bitrate_kbps) {
            return Err("bitrate_kbps must be 200..=50000".into());
        }
        if !(320..=3840).contains(&self.max_width) {
            return Err("max_width must be 320..=3840".into());
        }
        if !matches!(self.backend.as_str(), "mutter" | "test") {
            return Err("backend must be \"mutter\" or \"test\"".into());
        }
        self.listen
            .parse::<std::net::SocketAddr>()
            .map_err(|e| format!("listen: {e}"))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_safe() {
        let c = Config::default();
        assert!(!c.enable_at_start);
        assert!(c.validate().is_ok());
    }

    #[test]
    fn rejects_unknown_keys_and_bad_values() {
        assert!(Config::parse("bogus = 1").is_err());
        assert!(Config::parse("fps = 0").is_err());
        assert!(Config::parse("backend = \"vnc\"").is_err());
        assert!(Config::parse("listen = \"not-an-addr\"").is_err());
        assert!(Config::parse("fps = 24\nbitrate_kbps = 2500").is_ok());
    }
}
