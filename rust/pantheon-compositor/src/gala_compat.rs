use std::{
    collections::{HashMap, HashSet},
    sync::{
        Arc, Mutex,
        atomic::{AtomicU32, Ordering},
        mpsc,
    },
    thread,
    time::Duration,
};

use zbus::{blocking::Connection, interface, object_server::SignalEmitter, zvariant::OwnedValue};

const BUS_NAME: &str = "org.pantheon.gala";
const ROOT_PATH: &str = "/org/pantheon/gala";
const DESKTOP_PATH: &str = "/org/pantheon/gala/DesktopInterface";
/// M-Series panel control, served on the same bus name as the Gala shim.
const PANELS_PATH: &str = "/org/techmore/mseries/Panels";

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct GalaWindow {
    pub uid: u64,
    pub app_id: String,
    pub title: String,
    pub has_focus: bool,
    /// Asked to be raised and was not; cleared when the window gets focus.
    pub demands_attention: bool,
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
    /// 0 = normal, 1 = hidden (shown only while one of its menus is open),
    /// 2 = autohide (also revealed at the top screen edge).
    SetTopPanelMode(u32),
}

pub(crate) struct GalaActionRequest {
    pub action: GalaAction,
    pub response: mpsc::SyncSender<Result<(), String>>,
}

enum GalaSignal {
    RunningApplications,
    Windows,
    ActiveWorkspace,
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
            let _ = self.signals.send(GalaSignal::RunningApplications);
        }
        if windows_changed || count_changed {
            let _ = self.signals.send(GalaSignal::Windows);
        }
        if active_changed {
            let _ = self.signals.send(GalaSignal::ActiveWorkspace);
        }
    }

    pub fn request_windows_changed(&self) {
        let _ = self.signals.send(GalaSignal::Windows);
    }
}

/// The `a{sv}` Gala's `GetWindows` returns for one window. Keys beyond Gala's
/// own (`demands-attention`) are ignored by stock clients.
fn window_properties(window: &GalaWindow) -> zbus::fdo::Result<HashMap<String, OwnedValue>> {
    let mut properties = HashMap::new();
    properties.insert("app-id".into(), string_value(&window.app_id)?);
    properties.insert("title".into(), string_value(&window.title)?);
    properties.insert("has-focus".into(), OwnedValue::from(window.has_focus));
    properties.insert(
        "demands-attention".into(),
        OwnedValue::from(window.demands_attention),
    );
    properties.insert(
        "workspace-index".into(),
        OwnedValue::from(window.workspace_index),
    );
    properties.insert(
        "time-appeared-on-workspace".into(),
        OwnedValue::from(window.time_appeared_on_workspace),
    );
    Ok(properties)
}

struct GalaRootServer(mpsc::Sender<GalaActionRequest>);

#[interface(name = "org.pantheon.gala")]
impl GalaRootServer {
    fn perform_action(&self, action: i32) -> zbus::fdo::Result<()> {
        dispatch_action(&self.0, GalaAction::PerformAction(action))
    }
}

/// Runtime-only top-bar control for Windows Work Mode. The mode lives in
/// compositor memory, so a new session (or a compositor restart) always
/// starts with the top bar shown, even if the caller never restores it.
struct PanelControlServer(mpsc::Sender<GalaActionRequest>, Arc<AtomicU32>);

#[interface(name = "org.techmore.mseries.Panels")]
impl PanelControlServer {
    fn set_top_panel_mode(&self, mode: u32) -> zbus::fdo::Result<()> {
        dispatch_action(&self.0, GalaAction::SetTopPanelMode(mode))?;
        self.1.store(mode, Ordering::SeqCst);
        Ok(())
    }

    #[zbus(property)]
    fn top_panel_mode(&self) -> u32 {
        self.1.load(Ordering::SeqCst)
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

    // Explicit capability for the recovery tool: older sessions can leave
    // XWayland routing active after focusing a native Wayland window.
    #[zbus(property)]
    fn focus_routing_version(&self) -> u32 {
        1
    }

    /// Native shelf placement without activation, keyed by its application ID.
    #[zbus(property)]
    fn screenshot_shelf_placement_version(&self) -> u32 {
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
            .map(|window| Ok((window.uid, window_properties(window)?)))
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
    if let Err(error) = connection.object_server().at(
        PANELS_PATH,
        PanelControlServer(actions.clone(), Arc::new(AtomicU32::new(0))),
    ) {
        tracing::warn!(%error, "cannot register the M-Series panel control interface");
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
        let signal = match signal_receiver.recv() {
            Ok(signal) => signal,
            Err(_) => return,
        };
        let result = match signal {
            GalaSignal::RunningApplications => connection.emit_signal(
                None::<&str>,
                DESKTOP_PATH,
                "org.pantheon.gala.DesktopIntegration",
                "RunningApplicationsChanged",
                &(),
            ),
            GalaSignal::Windows => connection.emit_signal(
                None::<&str>,
                DESKTOP_PATH,
                "org.pantheon.gala.DesktopIntegration",
                "WindowsChanged",
                &(),
            ),
            GalaSignal::ActiveWorkspace => connection.emit_signal(
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

#[cfg(test)]
mod tests {
    use super::*;

    fn handle() -> (GalaCompatHandle, mpsc::Receiver<GalaSignal>) {
        let (signals, receiver) = mpsc::channel();
        let snapshot = Arc::new(Mutex::new(DesktopSnapshot::default()));
        (GalaCompatHandle { snapshot, signals }, receiver)
    }

    fn window(demands_attention: bool) -> GalaWindow {
        GalaWindow {
            uid: 4,
            app_id: "org.example.App".into(),
            title: "Example".into(),
            demands_attention,
            ..GalaWindow::default()
        }
    }

    #[test]
    fn get_windows_exports_demands_attention() {
        let properties = window_properties(&window(true)).unwrap();
        assert!(bool::try_from(properties["demands-attention"].try_clone().unwrap()).unwrap());
        let properties = window_properties(&window(false)).unwrap();
        assert!(!bool::try_from(properties["demands-attention"].try_clone().unwrap()).unwrap());
    }

    #[test]
    fn an_attention_change_alone_emits_windows_changed() {
        let (handle, signals) = handle();
        let snapshot = |demands| DesktopSnapshot {
            windows: vec![window(demands)],
            active_workspace: 0,
            workspace_count: 2,
        };
        handle.update(snapshot(false));
        while signals.try_recv().is_ok() {}

        handle.update(snapshot(true));
        let emitted = signals.try_iter().collect::<Vec<_>>();
        assert!(
            emitted
                .iter()
                .any(|signal| matches!(signal, GalaSignal::Windows))
        );
        assert!(
            !emitted
                .iter()
                .any(|signal| matches!(signal, GalaSignal::RunningApplications)),
            "the app list did not change"
        );
    }
}
