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
    pub modes: Vec<OutputModeSnapshot>,
    pub scale: f64,
    pub x: i32,
    pub y: i32,
    pub primary: bool,
}

#[derive(Clone, Debug)]
pub struct OutputModeSnapshot {
    pub width: i32,
    pub height: i32,
    pub refresh_millihz: i32,
    pub preferred: bool,
}

impl OutputModeSnapshot {
    pub fn id(&self) -> String {
        format!(
            "{}x{}@{:.3}",
            self.width,
            self.height,
            f64::from(self.refresh_millihz) / 1000.0
        )
    }
}

#[derive(Clone)]
pub struct DisplayConfigHandle {
    updates: mpsc::Sender<DisplayConfigUpdate>,
}

enum DisplayConfigUpdate {
    Upsert(OutputSnapshot),
    Remove(String),
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
        let _ = self.updates.send(DisplayConfigUpdate::Upsert(snapshot));
    }

    pub fn remove(&self, connector: impl Into<String>) {
        let _ = self
            .updates
            .send(DisplayConfigUpdate::Remove(connector.into()));
    }
}

struct DisplayConfigServer(Arc<Mutex<(u32, HashMap<String, OutputSnapshot>)>>);

type Properties = HashMap<String, OwnedValue>;
type MonitorInfo = (String, String, String, String);
type Mode = (String, i32, i32, f64, f64, Vec<f64>, Properties);
type Monitor = (MonitorInfo, Vec<Mode>, Properties);
type LogicalMonitor = (i32, i32, f64, u32, bool, Vec<MonitorInfo>, Properties);

#[interface(name = "org.gnome.Mutter.DisplayConfig")]
impl DisplayConfigServer {
    fn get_current_state(&self) -> (u32, Vec<Monitor>, Vec<LogicalMonitor>, Properties) {
        let (serial, outputs) = self.0.lock().expect("display config lock poisoned").clone();
        let mut outputs = outputs.into_values().collect::<Vec<_>>();
        outputs.sort_by(|a, b| (a.x, a.y, &a.connector).cmp(&(b.x, b.y, &b.connector)));
        if !outputs.iter().any(|output| output.primary)
            && let Some(first) = outputs.first_mut()
        {
            first.primary = true;
        }

        let mut monitors = Vec::with_capacity(outputs.len());
        let mut logical_monitors = Vec::with_capacity(outputs.len());
        for output in outputs {
            let monitor_info = (
                output.connector.clone(),
                output.vendor,
                output.product,
                output.serial,
            );
            let modes = if output.modes.is_empty() {
                vec![OutputModeSnapshot {
                    width: output.width,
                    height: output.height,
                    refresh_millihz: output.refresh_millihz,
                    preferred: true,
                }]
            } else {
                output.modes
            };
            let modes = modes
                .into_iter()
                .map(|mode| {
                    let mut mode_properties = Properties::new();
                    let current = mode.width == output.width
                        && mode.height == output.height
                        && mode.refresh_millihz == output.refresh_millihz;
                    if current {
                        mode_properties.insert("is-current".into(), OwnedValue::from(true));
                    }
                    if mode.preferred {
                        mode_properties.insert("is-preferred".into(), OwnedValue::from(true));
                    }
                    (
                        mode.id(),
                        mode.width,
                        mode.height,
                        f64::from(mode.refresh_millihz) / 1000.0,
                        output.scale,
                        vec![output.scale],
                        mode_properties,
                    )
                })
                .collect();
            monitors.push((monitor_info.clone(), modes, Properties::new()));
            logical_monitors.push((
                output.x,
                output.y,
                output.scale,
                0,
                output.primary,
                vec![monitor_info],
                Properties::new(),
            ));
        }
        let mut properties = Properties::new();
        properties.insert("layout-mode".into(), OwnedValue::from(1_u32));
        (serial, monitors, logical_monitors, properties)
    }

    #[zbus(signal)]
    async fn monitors_changed(emitter: &SignalEmitter<'_>) -> zbus::Result<()>;
}

fn serve_display_config(receiver: mpsc::Receiver<DisplayConfigUpdate>) {
    let connection = match Connection::session() {
        Ok(connection) => connection,
        Err(error) => {
            tracing::warn!(%error, "cannot connect to the session bus; display config service is disabled");
            return;
        }
    };

    // Backends publish their real outputs during startup. Avoid advertising a
    // fabricated Winit monitor when native DRM is selected.
    let initial = HashMap::new();
    let snapshot = Arc::new(Mutex::new((1, initial)));
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
            Ok(update) => {
                let mut state = snapshot.lock().expect("display config lock poisoned");
                match update {
                    DisplayConfigUpdate::Upsert(output) => {
                        if output.primary {
                            for current in state.1.values_mut() {
                                current.primary = false;
                            }
                        }
                        state.1.insert(output.connector.clone(), output);
                    }
                    DisplayConfigUpdate::Remove(connector) => {
                        state.1.remove(&connector);
                    }
                }
                state.0 = state.0.wrapping_add(1).max(1);
                drop(state);
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
