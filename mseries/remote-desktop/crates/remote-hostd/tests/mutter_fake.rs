//! Marshalling check for the Mutter backend against a fake RemoteDesktop /
//! ScreenCast / DisplayConfig service on a private session bus. It proves the
//! method names, argument signatures and call order match the interface XML
//! in mutter-main; it does not prove behaviour on a real Gala.

#![cfg(feature = "mutter")]

use std::collections::HashMap;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

use remote_core::input::InputSink;
use remote_core::protocol::{Button, InputEvent, Modifier};
use remote_hostd::backend::mutter::{LockWatch, MutterBackend, MutterInput};
use zbus::object_server::SignalEmitter;
use zbus::zvariant::{OwnedObjectPath, OwnedValue, Value};

type Log = Arc<Mutex<Vec<String>>>;

struct Rd(Log);
struct RdSession(Log);
struct Sc(Log);
struct ScSession(Log);
struct Stream;
struct DisplayConfig;

const SESSION: &str = "/org/gnome/Mutter/RemoteDesktop/Session/1";
const SC_SESSION: &str = "/org/gnome/Mutter/ScreenCast/Session/1";
const STREAM: &str = "/org/gnome/Mutter/ScreenCast/Stream/1";

#[zbus::interface(name = "org.gnome.Mutter.RemoteDesktop")]
impl Rd {
    async fn create_session(&self) -> zbus::fdo::Result<OwnedObjectPath> {
        self.0.lock().unwrap().push("rd.CreateSession".into());
        Ok(OwnedObjectPath::try_from(SESSION).unwrap())
    }
    #[zbus(property)]
    async fn version(&self) -> i32 {
        1
    }
}

#[zbus::interface(name = "org.gnome.Mutter.RemoteDesktop.Session")]
impl RdSession {
    #[zbus(property)]
    async fn session_id(&self) -> String {
        "rd-session-1".into()
    }
    async fn start(&self, #[zbus(connection)] conn: &zbus::Connection) -> zbus::fdo::Result<()> {
        self.0.lock().unwrap().push("rd.Start".into());
        let emitter = SignalEmitter::new(conn, STREAM).unwrap();
        Stream::pipe_wire_stream_added(&emitter, 42).await.unwrap();
        Ok(())
    }
    async fn stop(&self) {
        self.0.lock().unwrap().push("rd.Stop".into());
    }
    async fn notify_keyboard_keysym(&self, keysym: u32, state: bool) {
        self.0
            .lock()
            .unwrap()
            .push(format!("key {keysym:#x} {state}"));
    }
    async fn notify_pointer_button(&self, button: i32, state: bool) {
        self.0
            .lock()
            .unwrap()
            .push(format!("button {button:#x} {state}"));
    }
    async fn notify_pointer_axis(&self, dx: f64, dy: f64, flags: u32) {
        self.0
            .lock()
            .unwrap()
            .push(format!("axis {dx} {dy} {flags}"));
    }
    async fn notify_pointer_motion_relative(&self, dx: f64, dy: f64) {
        self.0.lock().unwrap().push(format!("rel {dx} {dy}"));
    }
    async fn notify_pointer_motion_absolute(&self, stream: String, x: f64, y: f64) {
        self.0.lock().unwrap().push(format!("abs {stream} {x} {y}"));
    }
}

#[zbus::interface(name = "org.gnome.Mutter.ScreenCast")]
impl Sc {
    async fn create_session(
        &self,
        props: HashMap<String, OwnedValue>,
    ) -> zbus::fdo::Result<OwnedObjectPath> {
        let id: String = props["remote-desktop-session-id"]
            .downcast_ref::<String>()
            .unwrap();
        self.0
            .lock()
            .unwrap()
            .push(format!("sc.CreateSession rd={id}"));
        Ok(OwnedObjectPath::try_from(SC_SESSION).unwrap())
    }
}

#[zbus::interface(name = "org.gnome.Mutter.ScreenCast.Session")]
impl ScSession {
    async fn record_monitor(
        &self,
        connector: String,
        props: HashMap<String, OwnedValue>,
    ) -> zbus::fdo::Result<OwnedObjectPath> {
        let cursor: u32 = props["cursor-mode"].downcast_ref::<u32>().unwrap();
        self.0
            .lock()
            .unwrap()
            .push(format!("sc.RecordMonitor {connector} cursor={cursor}"));
        Ok(OwnedObjectPath::try_from(STREAM).unwrap())
    }
}

#[zbus::interface(name = "org.gnome.Mutter.ScreenCast.Stream")]
impl Stream {
    #[zbus(signal)]
    async fn pipe_wire_stream_added(emitter: &SignalEmitter<'_>, node_id: u32) -> zbus::Result<()>;
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
type Logical = (
    i32,
    i32,
    f64,
    u32,
    bool,
    Vec<(String, String, String, String)>,
    HashMap<String, OwnedValue>,
);

#[zbus::interface(name = "org.gnome.Mutter.DisplayConfig")]
impl DisplayConfig {
    async fn get_current_state(
        &self,
    ) -> (u32, Vec<Monitor>, Vec<Logical>, HashMap<String, OwnedValue>) {
        let mut cur = HashMap::new();
        cur.insert(
            "is-current".to_string(),
            OwnedValue::try_from(Value::from(true)).unwrap(),
        );
        let mode: Mode = (
            "3024x1964@120".into(),
            3024,
            1964,
            120.0,
            120.0,
            vec![2.0],
            cur,
        );
        let mon: Monitor = (
            ("eDP-1".into(), "APP".into(), "m1".into(), "0".into()),
            vec![mode],
            HashMap::new(),
        );
        let logical: Logical = (
            0,
            0,
            2.0,
            0,
            true,
            vec![("eDP-1".into(), "APP".into(), "m1".into(), "0".into())],
            HashMap::new(),
        );
        (1, vec![mon], vec![logical], HashMap::new())
    }
    #[zbus(property)]
    async fn dummy(&self) -> i32 {
        0
    }
}

struct Bus(Child);
impl Drop for Bus {
    fn drop(&mut self) {
        let _ = self.0.kill();
    }
}

fn private_bus() -> Option<(Bus, String)> {
    let mut child = Command::new("dbus-daemon")
        .args(["--session", "--nofork", "--print-address=1"])
        .stdout(Stdio::piped())
        .spawn()
        .ok()?;
    use std::io::{BufRead, BufReader};
    let mut line = String::new();
    BufReader::new(child.stdout.take()?)
        .read_line(&mut line)
        .ok()?;
    Some((Bus(child), line.trim().to_string()))
}

#[test]
fn backend_talks_the_documented_protocol() {
    let Some((_bus, addr)) = private_bus() else {
        eprintln!("dbus-daemon not available; skipping");
        return;
    };
    // SAFETY-equivalent: single test in this binary, set before any bus use.
    std::env::set_var("DBUS_SESSION_BUS_ADDRESS", &addr);

    let log: Log = Arc::new(Mutex::new(Vec::new()));
    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap();
    let l = log.clone();
    let _service = rt.block_on(async move {
        zbus::connection::Builder::session()
            .unwrap()
            .name("org.gnome.Mutter.RemoteDesktop")
            .unwrap()
            .name("org.gnome.Mutter.ScreenCast")
            .unwrap()
            .name("org.gnome.Mutter.DisplayConfig")
            .unwrap()
            .serve_at("/org/gnome/Mutter/RemoteDesktop", Rd(l.clone()))
            .unwrap()
            .serve_at(SESSION, RdSession(l.clone()))
            .unwrap()
            .serve_at("/org/gnome/Mutter/ScreenCast", Sc(l.clone()))
            .unwrap()
            .serve_at(SC_SESSION, ScSession(l.clone()))
            .unwrap()
            .serve_at(STREAM, Stream)
            .unwrap()
            .serve_at("/org/gnome/Mutter/DisplayConfig", DisplayConfig)
            .unwrap()
            .build()
            .await
            .unwrap()
    });

    MutterBackend::probe().expect("probe finds the fake RemoteDesktop service");
    let (session, node, size) = MutterBackend::new().connect(1920).expect("session setup");
    assert_eq!(node, 42);
    // 3024x1964 at scale 2 => 1512x982 logical; below the 1920 cap, even.
    assert_eq!(size, (1512, 982));

    let mut input = MutterInput::new(session, LockWatch::fixed(false));
    input
        .apply(&InputEvent::Move { dx: 3.5, dy: -2.0 })
        .unwrap();
    input
        .apply(&InputEvent::MoveAbs { x: 0.5, y: 0.25 })
        .unwrap();
    input
        .apply(&InputEvent::Click {
            button: Button::Right,
        })
        .unwrap();
    input
        .apply(&InputEvent::Scroll { dx: 0.0, dy: 12.0 })
        .unwrap();
    input
        .apply(&InputEvent::Key {
            key: "c".into(),
            modifiers: vec![Modifier::Ctrl],
        })
        .unwrap();
    input
        .apply(&InputEvent::Text { text: "hi".into() })
        .unwrap();
    input
        .apply(&InputEvent::Button {
            button: Button::Left,
            down: true,
        })
        .unwrap();
    input.release_all();

    let got = log.lock().unwrap().clone();
    let want = [
        "rd.CreateSession",
        "sc.CreateSession rd=rd-session-1",
        "sc.RecordMonitor eDP-1 cursor=1",
        "rd.Start",
        "rel 3.5 -2",
        "abs /org/gnome/Mutter/ScreenCast/Stream/1 756 245.5",
        "button 0x111 true",
        "button 0x111 false",
        "axis 0 12 4",
        "key 0xffe3 true",
        "key 0x63 true",
        "key 0x63 false",
        "key 0xffe3 false",
        "key 0x68 true",
        "key 0x68 false",
        "key 0x69 true",
        "key 0x69 false",
        "button 0x110 true",
        "button 0x110 false", // release_all
    ];
    assert_eq!(got, want, "fake service saw a different call sequence");

    // A locked desktop gets nothing, and the held-key/button state is cleaned up on drop.
    let (session2, _, _) = MutterBackend::new().connect(1920).unwrap();
    let mut locked = MutterInput::new(session2, LockWatch::fixed(true));
    let before = log.lock().unwrap().len();
    assert!(locked
        .apply(&InputEvent::Text {
            text: "secret".into()
        })
        .is_err());
    let after: Vec<String> = log.lock().unwrap()[before..].to_vec();
    assert!(
        after.iter().all(|l| !l.starts_with("key")),
        "typed into a locked desktop: {after:?}"
    );
    drop(locked);
    drop(input);
    std::thread::sleep(std::time::Duration::from_millis(200));
    assert!(log.lock().unwrap().iter().any(|l| l == "rd.Stop"));
}
