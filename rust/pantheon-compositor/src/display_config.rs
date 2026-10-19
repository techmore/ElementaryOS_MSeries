use std::{
    collections::HashMap,
    sync::{Arc, Mutex, mpsc},
    thread,
    time::Duration,
};

use zbus::{blocking::Connection, interface, object_server::SignalEmitter, zvariant::OwnedValue};

const BUS_NAME: &str = "org.gnome.Mutter.DisplayConfig";
const OBJECT_PATH: &str = "/org/gnome/Mutter/DisplayConfig";
const INTERFACE: &str = "org.gnome.Mutter.DisplayConfig";

#[derive(Clone, Debug)]
pub struct OutputSnapshot {
    pub connector: String,
    pub vendor: String,
    pub product: String,
    pub serial: String,
    pub width: i32,
    pub height: i32,
    pub refresh_millihz: i32,
    pub scale: f64,
}

impl Default for OutputSnapshot {
    fn default() -> Self {
        Self {
            connector: "winit".into(),
            vendor: "Smithay".into(),
            product: "Winit".into(),
            serial: "Nested".into(),
            width: 1280,
            height: 800,
            refresh_millihz: 60_000,
            scale: 1.0,
        }
    }
}

#[derive(Clone)]
pub struct DisplayConfigHandle {
    updates: mpsc::Sender<OutputSnapshot>,
}

impl DisplayConfigHandle {
    pub fn start() -> Self {
        let (updates, receiver) = mpsc::channel();
        thread::Builder::new()
            .name("pantheon-display-config-dbus".into())
            .spawn(move || serve_display_config(receiver))
            .expect("failed to start display config D-Bus thread");
        Self { updates }
    }

    pub fn update(&self, snapshot: OutputSnapshot) {
        let _ = self.updates.send(snapshot);
    }
}

struct DisplayConfigServer(Arc<Mutex<OutputSnapshot>>);

type Properties = HashMap<String, OwnedValue>;
type MonitorInfo = (String, String, String, String);
type Mode = (String, i32, i32, f64, f64, Vec<f64>, Properties);
type Monitor = (MonitorInfo, Vec<Mode>, Properties);
type LogicalMonitor = (i32, i32, f64, u32, bool, Vec<MonitorInfo>, Properties);

#[interface(name = "org.gnome.Mutter.DisplayConfig")]
impl DisplayConfigServer {
    fn get_current_state(&self) -> (u32, Vec<Monitor>, Vec<LogicalMonitor>, Properties) {
        let output = self.0.lock().expect("display config lock poisoned").clone();
        let monitor_info = (
            output.connector.clone(),
            output.vendor,
            output.product,
            output.serial,
        );
        let mode_id = format!(
            "{}x{}@{:.3}",
            output.width,
            output.height,
            f64::from(output.refresh_millihz) / 1000.0
        );
        let mut mode_properties = Properties::new();
        mode_properties.insert("is-current".into(), OwnedValue::from(true));
        mode_properties.insert("is-preferred".into(), OwnedValue::from(true));
        let mode = (
            mode_id,
            output.width,
            output.height,
            f64::from(output.refresh_millihz) / 1000.0,
            output.scale,
            vec![output.scale],
            mode_properties,
        );
        let monitor = (monitor_info.clone(), vec![mode], Properties::new());
        let logical_monitor = (
            0,
            0,
            output.scale,
            0,
            true,
            vec![monitor_info],
            Properties::new(),
        );
        let mut properties = Properties::new();
        properties.insert("layout-mode".into(), OwnedValue::from(1_u32));
        (1, vec![monitor], vec![logical_monitor], properties)
    }

    #[zbus(signal)]
    async fn monitors_changed(emitter: &SignalEmitter<'_>) -> zbus::Result<()>;
}

fn serve_display_config(receiver: mpsc::Receiver<OutputSnapshot>) {
    let connection = match Connection::session() {
        Ok(connection) => connection,
        Err(error) => {
            tracing::warn!(%error, "cannot connect to the session bus; display config service is disabled");
            return;
        }
    };

    let snapshot = Arc::new(Mutex::new(OutputSnapshot::default()));
    if let Err(error) = connection
        .object_server()
        .at(OBJECT_PATH, DisplayConfigServer(snapshot.clone()))
    {
        tracing::warn!(%error, "cannot register the display config compatibility interface");
        return;
    }

    if let Err(error) = connection.request_name(BUS_NAME) {
        tracing::warn!(%error, "cannot own the Mutter display config compatibility name");
        return;
    }

    tracing::info!("serving the read-only Mutter display config query used by Wingpanel");
    loop {
        match receiver.recv_timeout(Duration::from_millis(100)) {
            Ok(output) => {
                *snapshot.lock().expect("display config lock poisoned") = output;
                if let Err(error) = connection.emit_signal(
                    None::<&str>,
                    OBJECT_PATH,
                    INTERFACE,
                    "MonitorsChanged",
                    &(),
                ) {
                    tracing::warn!(%error, "could not emit MonitorsChanged");
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => return,
        }
    }
}
