//! Pantheon (Gala = Mutter) backend: ScreenCast + RemoteDesktop over D-Bus.
//!
//! One RemoteDesktop session is created per viewer and the ScreenCast session
//! is linked to it, so the same grant yields frames (PipeWire node, read with
//! `gst-launch-1.0 pipewiresrc`) and input injection. Signatures follow
//! mutter's `data/dbus-interfaces/org.gnome.Mutter.{RemoteDesktop,ScreenCast}.xml`.
//!
//! **Not verified on hardware.** The owner's current session is the
//! experimental Rust compositor, which does not export these interfaces; the
//! marshalling is covered by `tests/mutter_fake.rs` against a fake service on
//! a private bus, not against a real Gala.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use remote_core::capture::{CaptureError, GstPipeSource};
use remote_core::input::{InputError, InputSink};
use remote_core::keysym;
use remote_core::protocol::InputEvent;
use zbus::blocking::{Connection, Proxy};
use zbus::zvariant::{OwnedObjectPath, OwnedValue, Value};

use super::{fit, Backend, BackendError, Streams};

const RD_NAME: &str = "org.gnome.Mutter.RemoteDesktop";
const RD_PATH: &str = "/org/gnome/Mutter/RemoteDesktop";
const SC_NAME: &str = "org.gnome.Mutter.ScreenCast";
const SC_PATH: &str = "/org/gnome/Mutter/ScreenCast";
const DC_NAME: &str = "org.gnome.Mutter.DisplayConfig";
const DC_PATH: &str = "/org/gnome/Mutter/DisplayConfig";

/// `NotifyPointerAxis` flags (mutter-main meta-remote-desktop-session.c).
const AXIS_SOURCE_FINGER: u32 = 1 << 2;
/// ScreenCast `cursor-mode`: 1 = embedded in the frames.
const CURSOR_EMBEDDED: u32 = 1;

fn berr(e: impl std::fmt::Display) -> BackendError {
    BackendError::Other(e.to_string())
}

type Mode = (
    String,
    i32,
    i32,
    f64,
    f64,
    Vec<f64>,
    HashMap<String, OwnedValue>,
);
type Monitor = (
    (String, String, String, String),
    Vec<Mode>,
    HashMap<String, OwnedValue>,
);
type LogicalMonitor = (
    i32,
    i32,
    f64,
    u32,
    bool,
    Vec<(String, String, String, String)>,
    HashMap<String, OwnedValue>,
);

/// The primary monitor's connector and its current logical size in pixels.
#[derive(Debug, Clone, PartialEq)]
pub struct Target {
    pub connector: String,
    pub width: u32,
    pub height: u32,
}

pub fn pick_target(monitors: &[Monitor], logical: &[LogicalMonitor]) -> Option<Target> {
    let primary = logical.iter().find(|l| l.4).or_else(|| logical.first())?;
    let connector = primary.5.first()?.0.clone();
    let scale = if primary.2 > 0.0 { primary.2 } else { 1.0 };
    let monitor = monitors.iter().find(|m| m.0 .0 == connector)?;
    let mode = monitor
        .1
        .iter()
        .find(|m| {
            matches!(
                m.6.get("is-current").and_then(|v| bool::try_from(v).ok()),
                Some(true)
            )
        })
        .or_else(|| monitor.1.first())?;
    Some(Target {
        connector,
        width: (mode.1 as f64 / scale).round() as u32,
        height: (mode.2 as f64 / scale).round() as u32,
    })
}

/// Pixel size of the logical monitor the stream shows: absolute pointer
/// coordinates are expressed in it.
pub struct Session {
    conn: Connection,
    rd_path: OwnedObjectPath,
    stream_path: String,
    logical: (f64, f64),
}

impl Drop for Session {
    fn drop(&mut self) {
        if let Ok(p) = Proxy::new(
            &self.conn,
            RD_NAME,
            self.rd_path.as_str(),
            "org.gnome.Mutter.RemoteDesktop.Session",
        ) {
            let _ = p.call_method("Stop", &());
        }
    }
}

#[derive(Default)]
pub struct MutterBackend;

/// Session, PipeWire node id, encode size.
pub type Connected = (Arc<Session>, u32, (u32, u32));

impl MutterBackend {
    pub fn new() -> Self {
        Self
    }

    /// Is an active, unlocked Wayland session available? Cheap probe for `--check`.
    pub fn probe() -> Result<(), String> {
        let conn = Connection::session().map_err(|e| e.to_string())?;
        let rd = Proxy::new(&conn, RD_NAME, RD_PATH, RD_NAME).map_err(|e| e.to_string())?;
        let version: i32 = rd
            .get_property("Version")
            .map_err(|e| format!("{RD_NAME} is not available: {e}"))?;
        let _ = version;
        Ok(())
    }

    /// Create the RemoteDesktop + ScreenCast sessions and return them with the
    /// PipeWire node and the encode size. Split out so the D-Bus marshalling
    /// can be exercised against a fake service without GStreamer.
    #[doc(hidden)]
    pub fn connect(&self, max_width: u32) -> Result<Connected, BackendError> {
        let conn = Connection::session().map_err(berr)?;

        let dc = Proxy::new(&conn, DC_NAME, DC_PATH, DC_NAME).map_err(berr)?;
        let state = dc.call_method("GetCurrentState", &()).map_err(berr)?;
        let (_serial, monitors, logical, _props): (
            u32,
            Vec<Monitor>,
            Vec<LogicalMonitor>,
            HashMap<String, OwnedValue>,
        ) = state.body().deserialize().map_err(berr)?;
        let target = pick_target(&monitors, &logical)
            .ok_or_else(|| BackendError::Other("no monitor to share".into()))?;

        let rd = Proxy::new(&conn, RD_NAME, RD_PATH, RD_NAME).map_err(berr)?;
        let rd_path: OwnedObjectPath = rd.call("CreateSession", &()).map_err(berr)?;
        let rd_session = Proxy::new(
            &conn,
            RD_NAME,
            rd_path.clone(),
            "org.gnome.Mutter.RemoteDesktop.Session",
        )
        .map_err(berr)?;
        let session_id: String = rd_session.get_property("SessionId").map_err(berr)?;

        let sc = Proxy::new(&conn, SC_NAME, SC_PATH, SC_NAME).map_err(berr)?;
        let mut props: HashMap<&str, Value<'_>> = HashMap::new();
        props.insert("remote-desktop-session-id", Value::from(session_id));
        let sc_path: OwnedObjectPath = sc.call("CreateSession", &(props,)).map_err(berr)?;
        let sc_session = Proxy::new(
            &conn,
            SC_NAME,
            sc_path.clone(),
            "org.gnome.Mutter.ScreenCast.Session",
        )
        .map_err(berr)?;
        let mut rprops: HashMap<&str, Value<'_>> = HashMap::new();
        rprops.insert("cursor-mode", Value::from(CURSOR_EMBEDDED));
        let stream_path: OwnedObjectPath = sc_session
            .call("RecordMonitor", &(target.connector.as_str(), rprops))
            .map_err(berr)?;
        let stream = Proxy::new(
            &conn,
            SC_NAME,
            stream_path.clone(),
            "org.gnome.Mutter.ScreenCast.Stream",
        )
        .map_err(berr)?;
        // Subscribe before Start: the node id arrives as a signal.
        let mut added = stream.receive_signal("PipeWireStreamAdded").map_err(berr)?;

        rd_session.call_method("Start", &()).map_err(berr)?;

        let node = wait_for_node(&mut added, Duration::from_secs(5))?;
        let size = fit(target.width, target.height, max_width);
        let session = Arc::new(Session {
            conn,
            rd_path,
            stream_path: stream_path.to_string(),
            logical: (target.width as f64, target.height as f64),
        });
        Ok((session, node, size))
    }
}

fn wait_for_node(
    added: &mut zbus::blocking::proxy::SignalIterator<'_>,
    timeout: Duration,
) -> Result<u32, BackendError> {
    // The iterator blocks; bound it with a watchdog thread-free deadline check
    // by polling `next` on a helper thread.
    let deadline = Instant::now() + timeout;
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::scope(|scope| {
        scope.spawn(|| {
            if let Some(msg) = added.next() {
                let _ = tx.send(msg.body().deserialize::<u32>().map_err(berr));
            }
        });
        match rx.recv_timeout(deadline.saturating_duration_since(Instant::now())) {
            Ok(r) => r,
            Err(_) => Err(BackendError::Other(
                "the compositor did not start the screen stream".into(),
            )),
        }
    })
}

impl Backend for MutterBackend {
    fn name(&self) -> &'static str {
        "mutter"
    }

    fn open(&self, max_width: u32, fps: u32) -> Result<Streams, BackendError> {
        let (session, node, (w, h)) = self.connect(max_width)?;
        let source = GstPipeSource::spawn(node, w, h, fps)
            .map_err(|e: CaptureError| BackendError::Capture(e))?;
        Ok(Streams {
            source: Box::new(source),
            input: Box::new(MutterInput::new(session, LockWatch::logind())),
        })
    }
}

/// Reads logind's `LockedHint` / `Active` for this session, cached briefly.
pub struct LockWatch {
    session_proxy: Option<Proxy<'static>>,
    cached: Mutex<(Instant, bool)>,
    fixed: Option<bool>,
}

impl LockWatch {
    /// Test hook: a constant answer instead of asking logind.
    #[doc(hidden)]
    pub fn fixed(locked: bool) -> Self {
        Self {
            session_proxy: None,
            cached: Mutex::new((Instant::now(), locked)),
            fixed: Some(locked),
        }
    }

    pub fn logind() -> Self {
        let proxy = Connection::system().ok().and_then(|sys| {
            let mgr = Proxy::new(
                &sys,
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager",
            )
            .ok()?;
            let path: OwnedObjectPath = mgr.call("GetSession", &("auto",)).ok()?;
            Proxy::new(
                &sys,
                "org.freedesktop.login1",
                path.to_owned(),
                "org.freedesktop.login1.Session",
            )
            .ok()
        });
        Self {
            session_proxy: proxy,
            cached: Mutex::new((Instant::now() - Duration::from_secs(10), false)),
            fixed: None,
        }
    }

    /// Locked or inactive. Unknown (no logind) counts as locked: fail closed.
    fn locked(&self) -> bool {
        if let Some(v) = self.fixed {
            return v;
        }
        let mut c = self.cached.lock().unwrap();
        if c.0.elapsed() < Duration::from_millis(500) {
            return c.1;
        }
        let locked = match &self.session_proxy {
            Some(p) => {
                let hint: bool = p.get_property("LockedHint").unwrap_or(true);
                let active: bool = p.get_property("Active").unwrap_or(false);
                hint || !active
            }
            None => true,
        };
        *c = (Instant::now(), locked);
        locked
    }
}

pub struct MutterInput {
    session: Arc<Session>,
    login: LockWatch,
    keys_down: Vec<u32>,
    buttons_down: Vec<i32>,
}

impl MutterInput {
    pub fn new(session: Arc<Session>, login: LockWatch) -> Self {
        Self {
            session,
            login,
            keys_down: Vec::new(),
            buttons_down: Vec::new(),
        }
    }

    fn rd(&self) -> Result<Proxy<'static>, InputError> {
        Proxy::new(
            &self.session.conn,
            RD_NAME,
            self.session.rd_path.to_owned(),
            "org.gnome.Mutter.RemoteDesktop.Session",
        )
        .map_err(|e| InputError::Backend(e.to_string()))
    }

    fn key(&mut self, rd: &Proxy<'_>, sym: u32, down: bool) -> Result<(), InputError> {
        rd.call_method("NotifyKeyboardKeysym", &(sym, down))
            .map_err(|e| InputError::Backend(e.to_string()))?;
        if down {
            self.keys_down.push(sym);
        } else {
            self.keys_down.retain(|k| *k != sym);
        }
        Ok(())
    }

    fn button(&mut self, rd: &Proxy<'_>, code: i32, down: bool) -> Result<(), InputError> {
        rd.call_method("NotifyPointerButton", &(code, down))
            .map_err(|e| InputError::Backend(e.to_string()))?;
        if down {
            self.buttons_down.push(code);
        } else {
            self.buttons_down.retain(|b| *b != code);
        }
        Ok(())
    }
}

impl InputSink for MutterInput {
    fn apply(&mut self, event: &InputEvent) -> Result<(), InputError> {
        // Never type into a lock screen. Pure motion is harmless but still gated:
        // a locked desktop is not something a remote viewer should be poking.
        if self.login.locked() {
            return Err(InputError::Locked);
        }
        let rd = self.rd()?;
        let e = |err: zbus::Error| InputError::Backend(err.to_string());
        match event {
            InputEvent::Move { dx, dy } => {
                rd.call_method("NotifyPointerMotionRelative", &(*dx, *dy))
                    .map_err(e)?;
            }
            InputEvent::MoveAbs { x, y } => {
                let (w, h) = self.session.logical;
                rd.call_method(
                    "NotifyPointerMotionAbsolute",
                    &(self.session.stream_path.as_str(), x * w, y * h),
                )
                .map_err(e)?;
            }
            InputEvent::Button { button, down } => {
                self.button(&rd, button.evdev() as i32, *down)?
            }
            InputEvent::Click { button } => {
                let code = button.evdev() as i32;
                let down = self.button(&rd, code, true);
                let up = self.button(&rd, code, false);
                down.and(up)?;
            }
            InputEvent::Scroll { dx, dy } => {
                rd.call_method("NotifyPointerAxis", &(*dx, *dy, AXIS_SOURCE_FINGER))
                    .map_err(e)?;
            }
            InputEvent::Key { key, modifiers } => {
                let sym = keysym::keysym(key)
                    .ok_or_else(|| InputError::Backend("unmapped key".into()))?;
                let mut held = Vec::new();
                let result = (|| {
                    for m in modifiers {
                        let s = keysym::modifier_keysym(*m);
                        self.key(&rd, s, true)?;
                        held.push(s);
                    }
                    self.key(&rd, sym, true)?;
                    self.key(&rd, sym, false)
                })();
                // Always release what we pressed, in reverse, even after an error.
                for s in held.into_iter().rev() {
                    let _ = self.key(&rd, s, false);
                }
                result?;
            }
            InputEvent::Text { text } => {
                for sym in keysym::text_keysyms(text) {
                    if self.login.locked() {
                        return Err(InputError::Locked);
                    }
                    self.key(&rd, sym, true)?;
                    self.key(&rd, sym, false)?;
                }
            }
            InputEvent::Ping { .. } | InputEvent::Keyframe => {}
        }
        Ok(())
    }

    fn release_all(&mut self) {
        if let Ok(rd) = self.rd() {
            for s in std::mem::take(&mut self.keys_down) {
                let _ = rd.call_method("NotifyKeyboardKeysym", &(s, false));
            }
            for b in std::mem::take(&mut self.buttons_down) {
                let _ = rd.call_method("NotifyPointerButton", &(b, false));
            }
        }
    }
}

impl Drop for MutterInput {
    fn drop(&mut self) {
        self.release_all();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mode(w: i32, h: i32, current: bool) -> Mode {
        let mut props = HashMap::new();
        props.insert(
            "is-current".to_string(),
            OwnedValue::try_from(Value::from(current)).unwrap(),
        );
        ("m".into(), w, h, 60.0, 60.0, vec![1.0], props)
    }

    #[test]
    fn picks_primary_monitor_current_mode_at_logical_size() {
        let monitors = vec![
            (
                ("DP-1".into(), "".into(), "".into(), "".into()),
                vec![mode(1920, 1080, true)],
                HashMap::new(),
            ),
            (
                ("eDP-1".into(), "".into(), "".into(), "".into()),
                vec![mode(3024, 1964, false), mode(3024, 1964, true)],
                HashMap::new(),
            ),
        ];
        let logical = vec![
            (
                0,
                0,
                1.0,
                0,
                false,
                vec![("DP-1".into(), "".into(), "".into(), "".into())],
                HashMap::new(),
            ),
            (
                1920,
                0,
                2.0,
                0,
                true,
                vec![("eDP-1".into(), "".into(), "".into(), "".into())],
                HashMap::new(),
            ),
        ];
        let t = pick_target(&monitors, &logical).unwrap();
        assert_eq!(
            t,
            Target {
                connector: "eDP-1".into(),
                width: 1512,
                height: 982
            }
        );
    }

    #[test]
    fn no_monitors_means_no_target() {
        assert_eq!(pick_target(&[], &[]), None);
    }
}
