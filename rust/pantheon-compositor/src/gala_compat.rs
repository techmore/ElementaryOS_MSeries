use std::{
    collections::{HashMap, HashSet},
    sync::{Arc, Mutex, mpsc},
    thread,
    time::Duration,
};

use zbus::{blocking::Connection, interface, object_server::SignalEmitter, zvariant::OwnedValue};

const BUS_NAME: &str = "org.pantheon.gala";
const ROOT_PATH: &str = "/org/pantheon/gala";
const DESKTOP_PATH: &str = "/org/pantheon/gala/DesktopInterface";

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct GalaWindow {
    pub uid: u64,
    pub app_id: String,
    pub has_focus: bool,
    pub workspace_index: i32,
    pub time_appeared_on_workspace: i64,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct DesktopSnapshot {
    pub windows: Vec<GalaWindow>,
    pub active_workspace: i32,
    pub workspace_count: i32,
}

#[derive(Clone, Debug)]
pub(crate) enum GalaAction {
    PerformAction(i32),
    ShowWindowsFor(String),
    FocusWindow(u64),
    MoveWindowToWorkspace(u64, i32),
    ActivateWorkspace(i32),
    ReorderWorkspace(i32, i32),
}

pub(crate) struct GalaActionRequest {
    pub action: GalaAction,
    pub response: mpsc::SyncSender<Result<(), String>>,
}

enum GalaSignal {
    RunningApplicationsChanged,
    WindowsChanged,
    ActiveWorkspaceChanged,
}

#[derive(Clone)]
pub(crate) struct GalaCompatHandle {
    snapshot: Arc<Mutex<DesktopSnapshot>>,
    signals: mpsc::Sender<GalaSignal>,
}

impl GalaCompatHandle {
    pub fn start() -> (Self, mpsc::Receiver<GalaActionRequest>) {
        let snapshot = Arc::new(Mutex::new(DesktopSnapshot {
            workspace_count: 2,
            ..DesktopSnapshot::default()
        }));
        let (signals, signal_receiver) = mpsc::channel();
        let (actions, action_receiver) = mpsc::channel();
        let service_snapshot = snapshot.clone();
        thread::Builder::new()
            .name("pantheon-gala-compat-dbus".into())
            .spawn(move || serve_gala_compat(service_snapshot, actions, signal_receiver))
            .expect("failed to start Pantheon Gala compatibility D-Bus thread");
        (Self { snapshot, signals }, action_receiver)
    }

    pub fn update(&self, next: DesktopSnapshot) {
        let (windows_changed, apps_changed, active_changed, count_changed) = {
            let mut snapshot = self
                .snapshot
                .lock()
                .expect("Pantheon D-Bus snapshot lock poisoned");
            let previous_apps = snapshot
                .windows
                .iter()
                .map(|window| window.app_id.as_str())
                .collect::<HashSet<_>>();
            let next_apps = next
                .windows
                .iter()
                .map(|window| window.app_id.as_str())
                .collect::<HashSet<_>>();
            let windows_changed = snapshot.windows != next.windows;
            let apps_changed = previous_apps != next_apps;
            let active_changed = snapshot.active_workspace != next.active_workspace;
            let count_changed = snapshot.workspace_count != next.workspace_count;
            if windows_changed || active_changed || snapshot.workspace_count != next.workspace_count
            {
                *snapshot = next;
            }
            (windows_changed, apps_changed, active_changed, count_changed)
        };

        if apps_changed {
            let _ = self.signals.send(GalaSignal::RunningApplicationsChanged);
        }
        if windows_changed || count_changed {
            let _ = self.signals.send(GalaSignal::WindowsChanged);
        }
        if active_changed {
            let _ = self.signals.send(GalaSignal::ActiveWorkspaceChanged);
        }
    }

    pub fn request_windows_changed(&self) {
        let _ = self.signals.send(GalaSignal::WindowsChanged);
    }
}

struct GalaRootServer(mpsc::Sender<GalaActionRequest>);

#[interface(name = "org.pantheon.gala")]
impl GalaRootServer {
    fn perform_action(&self, action: i32) -> zbus::fdo::Result<()> {
        dispatch_action(&self.0, GalaAction::PerformAction(action))
    }
}

struct DesktopIntegrationServer(Arc<Mutex<DesktopSnapshot>>, mpsc::Sender<GalaActionRequest>);

type WindowProperties = (u64, HashMap<String, OwnedValue>);
type RunningApplication = (String, HashMap<String, OwnedValue>);

#[interface(name = "org.pantheon.gala.DesktopIntegration")]
impl DesktopIntegrationServer {
    #[zbus(property)]
    fn version(&self) -> u32 {
        1
    }

    fn get_running_applications(&self) -> zbus::fdo::Result<Vec<RunningApplication>> {
        let snapshot = self
            .0
            .lock()
            .map_err(|_| zbus::fdo::Error::Failed("window snapshot is unavailable".into()))?;
        let mut seen = HashSet::new();
        Ok(snapshot
            .windows
            .iter()
            .filter(|window| !window.app_id.is_empty() && seen.insert(window.app_id.clone()))
            .map(|window| (window.app_id.clone(), HashMap::new()))
            .collect())
    }

    fn get_windows(&self) -> zbus::fdo::Result<Vec<WindowProperties>> {
        let snapshot = self
            .0
            .lock()
            .map_err(|_| zbus::fdo::Error::Failed("window snapshot is unavailable".into()))?;
        snapshot
            .windows
            .iter()
            .map(|window| {
                let mut properties = HashMap::new();
                properties.insert("app-id".into(), string_value(&window.app_id)?);
                properties.insert("has-focus".into(), OwnedValue::from(window.has_focus));
                properties.insert(
                    "workspace-index".into(),
                    OwnedValue::from(window.workspace_index),
                );
                properties.insert(
                    "time-appeared-on-workspace".into(),
                    OwnedValue::from(window.time_appeared_on_workspace),
                );
                Ok((window.uid, properties))
            })
            .collect()
    }

    fn focus_window(&self, uid: u64) -> zbus::fdo::Result<()> {
        dispatch_action(&self.1, GalaAction::FocusWindow(uid))
    }

    fn move_window_to_workspace(&self, uid: u64, index: i32) -> zbus::fdo::Result<()> {
        dispatch_action(&self.1, GalaAction::MoveWindowToWorkspace(uid, index))
    }

    fn activate_workspace(&self, index: i32) -> zbus::fdo::Result<()> {
        dispatch_action(&self.1, GalaAction::ActivateWorkspace(index))
    }

    fn get_n_workspaces(&self) -> zbus::fdo::Result<i32> {
        Ok(self
            .0
            .lock()
            .map_err(|_| zbus::fdo::Error::Failed("workspace state is unavailable".into()))?
            .workspace_count)
    }

    fn get_active_workspace(&self) -> zbus::fdo::Result<i32> {
        Ok(self
            .0
            .lock()
            .map_err(|_| zbus::fdo::Error::Failed("workspace state is unavailable".into()))?
            .active_workspace)
    }

    fn show_windows_for(&self, app_id: String) -> zbus::fdo::Result<()> {
        dispatch_action(&self.1, GalaAction::ShowWindowsFor(app_id))
    }

    fn reorder_workspace(&self, index: i32, new_index: i32) -> zbus::fdo::Result<()> {
        dispatch_action(&self.1, GalaAction::ReorderWorkspace(index, new_index))
    }

    #[zbus(signal)]
    async fn running_applications_changed(emitter: &SignalEmitter<'_>) -> zbus::Result<()>;

    #[zbus(signal)]
    async fn windows_changed(emitter: &SignalEmitter<'_>) -> zbus::Result<()>;

    #[zbus(signal)]
    async fn active_workspace_changed(emitter: &SignalEmitter<'_>) -> zbus::Result<()>;

    #[zbus(signal)]
    async fn workspace_removed(emitter: &SignalEmitter<'_>, index: i32) -> zbus::Result<()>;
}

fn string_value(value: &str) -> zbus::fdo::Result<OwnedValue> {
    OwnedValue::try_from(zbus::zvariant::Value::from(zbus::zvariant::Str::from(
        value,
    )))
    .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))
}

fn dispatch_action(
    sender: &mpsc::Sender<GalaActionRequest>,
    action: GalaAction,
) -> zbus::fdo::Result<()> {
    let (response, result) = mpsc::sync_channel(1);
    sender
        .send(GalaActionRequest { action, response })
        .map_err(|_| zbus::fdo::Error::Failed("compositor event loop is unavailable".into()))?;
    match result.recv_timeout(Duration::from_secs(5)) {
        Ok(Ok(())) => Ok(()),
        Ok(Err(error)) => Err(zbus::fdo::Error::Failed(error)),
        Err(mpsc::RecvTimeoutError::Timeout) => Err(zbus::fdo::Error::Timeout(
            "compositor did not complete the requested action in time".into(),
        )),
        Err(mpsc::RecvTimeoutError::Disconnected) => Err(zbus::fdo::Error::Failed(
            "compositor stopped before completing the requested action".into(),
        )),
    }
}

fn serve_gala_compat(
    snapshot: Arc<Mutex<DesktopSnapshot>>,
    actions: mpsc::Sender<GalaActionRequest>,
    signal_receiver: mpsc::Receiver<GalaSignal>,
) {
    let connection = match Connection::session() {
        Ok(connection) => connection,
        Err(error) => {
            tracing::warn!(%error, "cannot connect to the session bus; Pantheon Dock integration is disabled");
            return;
        }
    };

    if let Err(error) = connection
        .object_server()
        .at(ROOT_PATH, GalaRootServer(actions.clone()))
    {
        tracing::warn!(%error, "cannot register the Pantheon Gala action interface");
        return;
    }
    if let Err(error) = connection
        .object_server()
        .at(DESKTOP_PATH, DesktopIntegrationServer(snapshot, actions))
    {
        tracing::warn!(%error, "cannot register the Pantheon desktop integration interface");
        return;
    }
    if let Err(error) = connection.request_name(BUS_NAME) {
        tracing::warn!(%error, "cannot own the Pantheon Gala compatibility name");
        return;
    }

    tracing::info!("serving Pantheon Dock window and workspace integration");
    loop {
        let signal = match signal_receiver.recv_timeout(Duration::from_millis(100)) {
            Ok(signal) => signal,
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            Err(mpsc::RecvTimeoutError::Disconnected) => return,
        };
        let result = match signal {
            GalaSignal::RunningApplicationsChanged => connection.emit_signal(
                None::<&str>,
                DESKTOP_PATH,
                "org.pantheon.gala.DesktopIntegration",
                "RunningApplicationsChanged",
                &(),
            ),
            GalaSignal::WindowsChanged => connection.emit_signal(
                None::<&str>,
                DESKTOP_PATH,
                "org.pantheon.gala.DesktopIntegration",
                "WindowsChanged",
                &(),
            ),
            GalaSignal::ActiveWorkspaceChanged => connection.emit_signal(
                None::<&str>,
                DESKTOP_PATH,
                "org.pantheon.gala.DesktopIntegration",
                "ActiveWorkspaceChanged",
                &(),
            ),
        };
        if let Err(error) = result {
            tracing::warn!(%error, "could not emit a Pantheon desktop integration signal");
        }
    }
}
