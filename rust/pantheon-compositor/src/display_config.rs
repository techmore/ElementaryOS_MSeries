use std::{
    collections::HashMap,
    fs, io,
    path::PathBuf,
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
    pub transform: u32,
    pub x: i32,
    pub y: i32,
    pub primary: bool,
    pub enabled: bool,
}

#[derive(Clone, Debug)]
pub struct OutputModeSnapshot {
    pub width: i32,
    pub height: i32,
    pub refresh_millihz: i32,
    pub preferred: bool,
}

pub fn transform_to_dbus(transform: smithay::utils::Transform) -> u32 {
    match transform {
        smithay::utils::Transform::Normal => 0,
        smithay::utils::Transform::_90 => 1,
        smithay::utils::Transform::_180 => 2,
        smithay::utils::Transform::_270 => 3,
        smithay::utils::Transform::Flipped => 4,
        smithay::utils::Transform::Flipped90 => 5,
        smithay::utils::Transform::Flipped180 => 6,
        smithay::utils::Transform::Flipped270 => 7,
    }
}

#[derive(Clone, Debug)]
pub struct SavedMonitorConfiguration {
    pub connector: String,
    pub mode: String,
    pub x: i32,
    pub y: i32,
    pub scale: f64,
    pub transform: u32,
    pub primary: bool,
    pub enabled: bool,
}

fn monitor_configuration_path() -> Option<PathBuf> {
    std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".config")))
        .map(|base| base.join("pantheon-rust-compositor/monitors.conf"))
}

pub fn load_saved_monitor_configurations() -> HashMap<String, SavedMonitorConfiguration> {
    let Some(path) = monitor_configuration_path() else {
        return HashMap::new();
    };
    let Ok(contents) = fs::read_to_string(path) else {
        return HashMap::new();
    };
    let configurations = contents
        .lines()
        .filter_map(|line| {
            let mut fields = line.split('\t');
            let [
                Some(connector),
                Some(mode),
                Some(x),
                Some(y),
                Some(scale),
                Some(transform),
                Some(primary),
            ] = [
                fields.next(),
                fields.next(),
                fields.next(),
                fields.next(),
                fields.next(),
                fields.next(),
                fields.next(),
            ]
            else {
                return None;
            };
            let enabled = match fields.next() {
                None | Some("1") => true,
                Some("0") => false,
                Some(_) => return None,
            };
            if fields.next().is_some() {
                return None;
            }
            let scale = scale.parse::<f64>().ok()?;
            let transform = transform.parse::<u32>().ok()?;
            if !scale.is_finite() || !(0.5..=4.0).contains(&scale) || transform > 7 {
                return None;
            }
            Some(SavedMonitorConfiguration {
                connector: connector.to_string(),
                mode: mode.to_string(),
                x: x.parse().ok()?,
                y: y.parse().ok()?,
                scale,
                transform,
                primary: primary == "1",
                enabled,
            })
        })
        .map(|configuration| (configuration.connector.clone(), configuration))
        .collect::<HashMap<_, _>>();
    if configurations
        .values()
        .filter(|configuration| configuration.primary && configuration.enabled)
        .count()
        == 1
    {
        configurations
    } else {
        HashMap::new()
    }
}

pub fn save_monitor_configurations(configurations: &[SavedMonitorConfiguration]) -> io::Result<()> {
    let path = monitor_configuration_path().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::NotFound,
            "no user configuration directory is available",
        )
    })?;
    let parent = path
        .parent()
        .expect("monitor configuration path has a parent");
    fs::create_dir_all(parent)?;
    let temporary_path = path.with_extension("conf.tmp");
    let mut contents = String::new();
    for configuration in configurations {
        if configuration.connector.contains(['\t', '\n'])
            || configuration.mode.contains(['\t', '\n'])
            || !configuration.scale.is_finite()
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "invalid monitor configuration value",
            ));
        }
        contents.push_str(&format!(
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n",
            configuration.connector,
            configuration.mode,
            configuration.x,
            configuration.y,
            configuration.scale,
            configuration.transform,
            u8::from(configuration.primary),
            u8::from(configuration.enabled),
        ));
    }
    fs::write(&temporary_path, contents)?;
    fs::rename(temporary_path, path)
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

pub struct ApplyRequest {
    pub serial: u32,
    pub method: u32,
    pub logical_monitors: Vec<ApplyLogicalMonitor>,
    pub current_outputs: Vec<OutputSnapshot>,
    pub response: mpsc::SyncSender<Result<(), String>>,
}

enum DisplayConfigUpdate {
    Upsert(OutputSnapshot),
    UpsertMany(Vec<OutputSnapshot>),
    Remove(String),
}

impl DisplayConfigHandle {
    pub fn start() -> (Self, mpsc::Receiver<ApplyRequest>) {
        let (updates, receiver) = mpsc::channel();
        let (apply_requests, apply_receiver) = mpsc::channel();
        let apply_requests_for_service = apply_requests.clone();
        thread::Builder::new()
            .name("pantheon-display-config-dbus".into())
            .spawn(move || serve_display_config(receiver, apply_requests_for_service))
            .expect("failed to start display config D-Bus thread");
        (Self { updates }, apply_receiver)
    }

    pub fn update(&self, snapshot: OutputSnapshot) {
        let _ = self.updates.send(DisplayConfigUpdate::Upsert(snapshot));
    }

    pub fn update_many(&self, snapshots: Vec<OutputSnapshot>) {
        if !snapshots.is_empty() {
            let _ = self
                .updates
                .send(DisplayConfigUpdate::UpsertMany(snapshots));
        }
    }

    pub fn remove(&self, connector: impl Into<String>) {
        let _ = self
            .updates
            .send(DisplayConfigUpdate::Remove(connector.into()));
    }
}

type Properties = HashMap<String, OwnedValue>;
type MonitorInfo = (String, String, String, String);
type Mode = (String, i32, i32, f64, f64, Vec<f64>, Properties);
type Monitor = (MonitorInfo, Vec<Mode>, Properties);
type LogicalMonitor = (i32, i32, f64, u32, bool, Vec<MonitorInfo>, Properties);
pub type ApplyMonitor = (String, String, Properties);
pub type ApplyLogicalMonitor = (i32, i32, f64, u32, bool, Vec<ApplyMonitor>, Properties);

struct DisplayConfigServer(
    Arc<Mutex<(u32, HashMap<String, OutputSnapshot>)>>,
    mpsc::Sender<ApplyRequest>,
);

#[interface(name = "org.gnome.Mutter.DisplayConfig")]
impl DisplayConfigServer {
    fn get_current_state(&self) -> (u32, Vec<Monitor>, Vec<LogicalMonitor>, Properties) {
        let (serial, outputs) = self.0.lock().expect("display config lock poisoned").clone();
        let mut outputs = outputs.into_values().collect::<Vec<_>>();
        outputs.sort_by(|a, b| (a.x, a.y, &a.connector).cmp(&(b.x, b.y, &b.connector)));
        if !outputs
            .iter()
            .any(|output| output.primary && output.enabled)
            && let Some(first) = outputs.iter_mut().find(|output| output.enabled)
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
                    let mut scales = vec![0.5, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0];
                    if !scales.contains(&output.scale) {
                        scales.push(output.scale);
                        scales.sort_by(f64::total_cmp);
                    }
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
                        scales,
                        mode_properties,
                    )
                })
                .collect();
            monitors.push((monitor_info.clone(), modes, Properties::new()));
            if output.enabled {
                logical_monitors.push((
                    output.x,
                    output.y,
                    output.scale,
                    output.transform,
                    output.primary,
                    vec![monitor_info],
                    Properties::new(),
                ));
            }
        }
        let mut properties = Properties::new();
        properties.insert("layout-mode".into(), OwnedValue::from(1_u32));
        (serial, monitors, logical_monitors, properties)
    }

    fn apply_monitors_config(
        &self,
        serial: u32,
        method: u32,
        logical_monitors: Vec<ApplyLogicalMonitor>,
        _properties: Properties,
    ) -> zbus::fdo::Result<()> {
        let (current_serial, current_outputs) = self
            .0
            .lock()
            .map_err(|_| {
                zbus::fdo::Error::Failed("display configuration state is unavailable".into())
            })?
            .clone();
        if serial != current_serial {
            return Err(zbus::fdo::Error::Failed(format!(
                "stale display configuration serial {serial}; current serial is {current_serial}"
            )));
        }
        if !matches!(method, 0..=2) {
            return Err(zbus::fdo::Error::InvalidArgs(format!(
                "unknown ApplyMonitorsConfig method {method}"
            )));
        }

        let (response, result) = mpsc::sync_channel(1);
        self.1
            .send(ApplyRequest {
                serial,
                method,
                logical_monitors,
                current_outputs: current_outputs.into_values().collect(),
                response,
            })
            .map_err(|_| zbus::fdo::Error::Failed("compositor event loop is unavailable".into()))?;
        match result.recv_timeout(Duration::from_secs(10)) {
            Ok(Ok(())) => Ok(()),
            Ok(Err(error)) => Err(zbus::fdo::Error::Failed(error)),
            Err(mpsc::RecvTimeoutError::Timeout) => Err(zbus::fdo::Error::Timeout(
                "compositor did not apply the display configuration in time".into(),
            )),
            Err(mpsc::RecvTimeoutError::Disconnected) => Err(zbus::fdo::Error::Failed(
                "compositor stopped before applying the display configuration".into(),
            )),
        }
    }

    #[zbus(property)]
    fn apply_monitors_config_allowed(&self) -> bool {
        true
    }

    #[zbus(signal)]
    async fn monitors_changed(emitter: &SignalEmitter<'_>) -> zbus::Result<()>;
}

fn serve_display_config(
    receiver: mpsc::Receiver<DisplayConfigUpdate>,
    apply_requests: mpsc::Sender<ApplyRequest>,
) {
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
    if let Err(error) = connection.object_server().at(
        OBJECT_PATH,
        DisplayConfigServer(snapshot.clone(), apply_requests),
    ) {
        tracing::warn!(%error, "cannot register the display config compatibility interface");
        return;
    }

    if let Err(error) = connection.request_name(BUS_NAME) {
        tracing::warn!(%error, "cannot own the Mutter display config compatibility name");
        return;
    }

    tracing::info!("serving Mutter display configuration queries and apply requests");
    loop {
        match receiver.recv() {
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
                    DisplayConfigUpdate::UpsertMany(outputs) => {
                        for output in &outputs {
                            if output.primary {
                                for current in state.1.values_mut() {
                                    current.primary = false;
                                }
                            }
                            state.1.insert(output.connector.clone(), output.clone());
                        }
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
            Err(_) => return,
        }
    }
}
