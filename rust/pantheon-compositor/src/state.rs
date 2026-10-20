use std::collections::{HashMap, HashSet};
use std::{ffi::OsString, sync::Arc, time::Duration};

use smithay::{
    desktop::{PopupGrab, PopupManager, Space, Window, WindowSurfaceType},
    input::{Seat, SeatState, pointer::CursorImageStatus},
    reexports::{
        calloop::{
            EventLoop, Interest, LoopHandle, LoopSignal, Mode, PostAction, channel,
            generic::Generic,
            timer::{TimeoutAction, Timer},
        },
        wayland_server::{
            Display, DisplayHandle, Resource,
            backend::{ClientData, ClientId, DisconnectReason},
            protocol::wl_surface::WlSurface,
        },
    },
    utils::{Logical, Point, Size},
    wayland::{
        compositor::{CompositorClientState, CompositorState},
        dmabuf::DmabufState,
        fractional_scale::{
            FractionalScaleHandler, FractionalScaleManagerState, with_fractional_scale,
        },
        input_method::InputMethodManagerState,
        output::OutputManagerState,
        selection::{data_device::DataDeviceState, primary_selection::PrimarySelectionState},
        session_lock::{LockSurface, SessionLockManagerState, SessionLocker},
        shell::xdg::XdgShellState,
        shm::ShmState,
        socket::ListeningSocketSource,
        text_input::TextInputManagerState,
        viewporter::ViewporterState,
        xdg_activation::{
            XdgActivationHandler, XdgActivationState, XdgActivationToken, XdgActivationTokenData,
        },
        xwayland_shell::XWaylandShellState,
    },
};

use crate::display_config::{
    ApplyRequest, DisplayConfigHandle, OutputModeSnapshot, OutputSnapshot,
    SavedMonitorConfiguration, save_monitor_configurations, transform_to_dbus,
};
use crate::gala_compat::{DesktopSnapshot, GalaAction, GalaCompatHandle, GalaWindow};
#[cfg(feature = "native-drm")]
use crate::native::NativeBackend;
use crate::pantheon_shell::{PanelState, PantheonShellState};
use crate::shell_compat::ShellCompatHandle;
use crate::tiling::{CornerSnapPreview, TilingBindings};
use crate::workspace::WorkspaceManager;
#[cfg(feature = "native-drm")]
use smithay::reexports::calloop::channel::Sender;

fn is_ibus_input_method_stream(stream: &std::os::unix::net::UnixStream) -> bool {
    use std::os::unix::fs::MetadataExt;

    let Ok(credentials) = smithay::reexports::rustix::net::sockopt::socket_peercred(stream) else {
        return false;
    };
    let Ok(current_user) = std::fs::metadata("/proc/self") else {
        return false;
    };
    if credentials.uid.as_raw() != current_user.uid() {
        return false;
    }

    std::fs::read_link(format!("/proc/{}/exe", credentials.pid.as_raw_pid()))
        .ok()
        .and_then(|path| path.file_name().map(|name| name.to_owned()))
        .is_some_and(|name| name == "ibus-daemon")
}

/// Imports a client dmabuf with the active renderer.
pub type DmabufImporter = Box<dyn FnMut(&smithay::backend::allocator::dmabuf::Dmabuf) -> bool>;

pub struct PantheonCompositor {
    pub start_time: std::time::Instant,
    pub socket_name: OsString,
    pub display_handle: DisplayHandle,

    pub space: Space<Window>,
    pub loop_signal: LoopSignal,

    // Smithay State
    pub compositor_state: CompositorState,
    pub xdg_shell_state: XdgShellState,
    pub shm_state: ShmState,
    pub dmabuf_state: DmabufState,
    /// Imports a client dmabuf with the active renderer; `None` until a backend
    /// that owns a renderer installs one (then the global is also created).
    pub dmabuf_importer: Option<DmabufImporter>,
    pub output_manager_state: OutputManagerState,
    pub fractional_scale_manager_state: FractionalScaleManagerState,
    pub viewporter_state: ViewporterState,
    pub xdg_activation_state: XdgActivationState,
    pub(crate) loop_handle: LoopHandle<'static, PantheonCompositor>,
    activation_sweep_armed: bool,
    pub session_lock_state: SessionLockManagerState,
    pub session_locked: bool,
    pub lock_surfaces: HashMap<String, LockSurface>,
    pub lock_owner: Option<smithay::reexports::wayland_server::backend::ObjectId>,
    pub lock_confirmation: Option<SessionLocker>,
    pub lock_confirmation_outputs: HashSet<String>,
    pub keyboard_focus_before_lock: Option<WlSurface>,
    pub x11_keyboard_focus_before_lock: Option<smithay::xwayland::X11Surface>,
    pub x11_keyboard_focus: Option<smithay::xwayland::X11Surface>,
    pub xwayland_shell_state: XWaylandShellState,
    pub xwm: Option<smithay::xwayland::X11Wm>,
    pub xdisplay: Option<u32>,
    pub pending_command: Option<(String, Vec<String>)>,
    pub notify_systemd_when_ready: bool,
    pub fatal_error: Option<String>,
    pub seat_state: SeatState<PantheonCompositor>,
    pub(crate) keyboard_config: crate::input::StartupKeyboardConfig,
    pub data_device_state: DataDeviceState,
    pub primary_selection_state: PrimarySelectionState,
    pub text_input_manager_state: TextInputManagerState,
    pub input_method_manager_state: InputMethodManagerState,
    pub pantheon_shell_state: PantheonShellState,
    pub display_config: DisplayConfigHandle,
    pub(crate) gala_compat: GalaCompatHandle,
    pub(crate) workspace_manager: WorkspaceManager,
    pub shell_compat: ShellCompatHandle,
    pub primary_output_name: Option<String>,
    pub panels: HashMap<smithay::reexports::wayland_server::backend::ObjectId, PanelState>,
    /// Runtime-only top-panel suppression (Windows Work Mode). Lives only in
    /// compositor memory, so every new session starts with the top bar shown.
    pub top_panel_mode: crate::pantheon_shell::TopPanelMode,
    pub last_work_areas: HashMap<String, smithay::utils::Rectangle<i32, smithay::utils::Logical>>,
    pub managed_windows:
        HashMap<smithay::reexports::wayland_server::backend::ObjectId, ManagedWindow>,
    pub x11_managed_windows: HashMap<u32, ManagedWindow>,
    pub x11_minimized_windows: HashMap<u32, (Window, Point<i32, Logical>)>,
    pub tiled_windows: HashMap<smithay::reexports::wayland_server::backend::ObjectId, TiledWindow>,
    pub tiling_bindings: TilingBindings,
    pub corner_snap_preview: Option<CornerSnapPreview>,
    pub corner_snap_cancelled: bool,
    pub move_grab_active: bool,
    /// In-flight touchpad gesture and whether the compositor or a client owns it.
    pub(crate) gesture_animation: Option<crate::gesture_animation::GestureAnimation>,
    pub(crate) active_gesture: Option<crate::gestures::ActiveGesture>,
    /// Gesture bindings from elementary's and the M-series gesture settings.
    pub(crate) gesture_bindings: crate::gestures::GestureBindings,
    /// Touchpad and mouse settings applied to every libinput device.
    pub(crate) peripheral_settings: crate::touchpad::PeripheralSettings,
    /// libinput devices, kept so settings changes can be re-applied.
    #[cfg(feature = "native-drm")]
    pub(crate) input_devices: Vec<smithay::reexports::input::Device>,
    /// Registers `zwp_pointer_gestures_v1` so clients receive forwarded gestures.
    pub pointer_gestures_state: smithay::wayland::pointer_gestures::PointerGesturesState,
    /// Active grid overview ("expose") session, if any.
    pub(crate) overview: Option<crate::overview::OverviewState>,
    pub minimized_windows: HashMap<
        smithay::reexports::wayland_server::backend::ObjectId,
        (Window, Point<i32, Logical>),
    >,
    pub initially_positioned: HashSet<smithay::reexports::wayland_server::backend::ObjectId>,
    pub popups: PopupManager,
    /// The seat's current popup grab and its root surface. Smithay keeps one grab
    /// stack per seat, so a grab from another root must end this one first.
    pub active_popup_grab: Option<(WlSurface, PopupGrab<PantheonCompositor>)>,
    pub cursor_status: CursorImageStatus,
    pub(crate) cursor_theme: crate::cursor_theme::CursorTheme,
    pub(crate) wallpaper: Option<crate::wallpaper::Wallpaper>,
    pub(crate) wallpaper_selection: Option<crate::wallpaper::WallpaperSelection>,

    pub seat: Seat<Self>,
    pub winit_redraw_sender: Option<channel::Sender<()>>,
    #[cfg(feature = "native-drm")]
    pub native_backend: Option<NativeBackend>,
    #[cfg(feature = "native-drm")]
    pub native_redraw_sender: Option<Sender<()>>,
}

#[derive(Clone, Copy)]
pub struct ManagedWindow {
    pub restore_location: Point<i32, Logical>,
    pub restore_size: Size<i32, Logical>,
    pub maximized: bool,
    pub fullscreen: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TilePosition {
    Left,
    Right,
    TopLeft,
    TopRight,
    BottomLeft,
    BottomRight,
}

#[derive(Clone)]
pub struct TiledWindow {
    pub position: TilePosition,
    pub output: smithay::output::Output,
    pub rect: smithay::utils::Rectangle<i32, Logical>,
    pub committed_size: Size<i32, Logical>,
}

impl PantheonCompositor {
    pub fn new(
        event_loop: &mut EventLoop<'static, Self>,
        display: Display<Self>,
        seat_name: &str,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let start_time = std::time::Instant::now();

        let dh = display.handle();

        // Here we initialize implementations of some wayland protocols
        // Some of them require us to implement traits on the PantheonCompositor state,
        // you can find those implementations in the `crate::handlers` module

        // Initialize protocols needed for displaying windows
        let compositor_state = CompositorState::new::<Self>(&dh);
        let xdg_shell_state = XdgShellState::new::<Self>(&dh);
        let shm_state = ShmState::new::<Self>(&dh, vec![]);
        let dmabuf_state = DmabufState::new();
        let popups = PopupManager::default();

        let output_manager_state = OutputManagerState::new_with_xdg_output::<Self>(&dh);
        let fractional_scale_manager_state = FractionalScaleManagerState::new::<Self>(&dh);
        let viewporter_state = ViewporterState::new::<Self>(&dh);
        let xdg_activation_state = XdgActivationState::new::<Self>(&dh);
        let session_lock_state = SessionLockManagerState::new::<Self, _>(&dh, |_| true);
        let xwayland_shell_state = XWaylandShellState::new::<Self>(&dh);

        // Data device is responsible for clipboard and drag-and-drop
        let data_device_state = DataDeviceState::new::<Self>(&dh);
        let primary_selection_state = PrimarySelectionState::new::<Self>(&dh);
        let text_input_manager_state = TextInputManagerState::new::<Self>(&dh);
        let input_method_manager_state = InputMethodManagerState::new::<Self, _>(&dh, |client| {
            client
                .get_data::<ClientState>()
                .is_some_and(|data| data.is_ibus_input_method_client)
        });
        let pantheon_shell_state = PantheonShellState::new::<Self>(&dh);
        let pointer_gestures_state =
            smithay::wayland::pointer_gestures::PointerGesturesState::new::<Self>(&dh);
        let (display_config, apply_requests) = DisplayConfigHandle::start();
        event_loop.handle().insert_source(
            crate::wakeups::forward("display-apply", apply_requests),
            |event, _, state| {
                if let channel::Event::Msg(request) = event {
                    let result = state.apply_display_configuration(&request);
                    let _ = request.response.send(result);
                }
            },
        )?;

        // A seat is a group of keyboards, pointer and touch devices.
        // A seat typically has a pointer and maintains a keyboard focus and a pointer focus.
        let mut seat_state = SeatState::new();
        let mut seat: Seat<Self> = seat_state.new_wl_seat(&dh, seat_name);

        // Initialize the physical keyboard with the user's XKB layout,
        // Command/Ctrl options, and repeat preferences when the desktop
        // settings schemas are available.
        let keyboard_config = crate::input::startup_keyboard_config();
        if let Err(error) = seat.add_keyboard(
            crate::input::xkb_config(&keyboard_config),
            keyboard_config.repeat_delay,
            keyboard_config.repeat_rate,
        ) {
            tracing::warn!(
                ?error,
                "configured XKB keymap failed; using environment defaults"
            );
            seat.add_keyboard(
                Default::default(),
                keyboard_config.repeat_delay,
                keyboard_config.repeat_rate,
            )?;
        }
        // GSettings change notifications replace the former 1 s keyboard and
        // 2 s wallpaper polls. Each handler re-reads and diffs exactly as the
        // polls did, so a spurious notification is harmless.
        event_loop.handle().insert_source(
            crate::wakeups::watch_settings(&[
                "org.gnome.desktop.input-sources",
                "org.gnome.desktop.peripherals.keyboard",
            ]),
            |event, _, state| {
                if matches!(event, channel::Event::Msg(())) {
                    state.refresh_keyboard_config();
                }
            },
        )?;
        event_loop.handle().insert_source(
            crate::wakeups::watch_settings(crate::gestures::SETTINGS_SCHEMAS),
            |event, _, state| {
                if matches!(event, channel::Event::Msg(())) {
                    state.gesture_bindings = crate::gestures::GestureBindings::load();
                }
            },
        )?;
        event_loop.handle().insert_source(
            crate::wakeups::watch_settings(crate::touchpad::SETTINGS_SCHEMAS),
            |event, _, state| {
                if matches!(event, channel::Event::Msg(())) {
                    state.refresh_peripheral_settings();
                }
            },
        )?;
        event_loop.handle().insert_source(
            crate::wakeups::watch_settings(&["org.gnome.desktop.interface"]),
            |event, _, state| {
                if matches!(event, channel::Event::Msg(())) {
                    state.refresh_cursor_theme();
                }
            },
        )?;
        event_loop.handle().insert_source(
            crate::wakeups::watch_settings(&["org.gnome.desktop.background"]),
            |event, _, state| {
                if matches!(event, channel::Event::Msg(())) {
                    state.refresh_wallpaper();
                }
            },
        )?;

        // Notify clients that we have a pointer (mouse)
        // Here we assume that there is always pointer plugged in
        seat.add_pointer();

        // A space represents a two-dimensional plane. Windows and Outputs can be mapped onto it.
        //
        // Windows get a position and stacking order through mapping.
        // Outputs become views of a part of the Space and can be rendered via Space::render_output.
        let space = Space::default();

        let wallpaper_selection = match crate::wallpaper::configured_selection() {
            Ok(selection) => selection,
            Err(error) => {
                tracing::warn!(%error, "could not read desktop wallpaper settings");
                None
            }
        };
        let wallpaper = wallpaper_selection
            .as_ref()
            .and_then(crate::wallpaper::load_wallpaper);

        // Setup a wayland socket that will be used to accept clients
        let socket_name = Self::init_wayland_listener(display, event_loop)?;
        let (osd_redraw_sender, osd_redraw_receiver) = channel::channel();
        event_loop
            .handle()
            .insert_source(osd_redraw_receiver, |event, _, _state| {
                if matches!(event, channel::Event::Msg(())) {
                    _state.request_native_redraw();
                }
            })?;
        let shell_compat = ShellCompatHandle::start(socket_name.clone(), osd_redraw_sender);
        let (gala_compat, gala_actions) = GalaCompatHandle::start();
        event_loop.handle().insert_source(
            crate::wakeups::forward("gala-actions", gala_actions),
            |event, _, state| {
                if let channel::Event::Msg(request) = event {
                    let result = state.handle_gala_action(request.action);
                    state.publish_gala_snapshot();
                    let _ = request.response.send(result);
                }
            },
        )?;
        let loop_handle = event_loop.handle();

        // Get the loop signal, used to stop the event loop
        let loop_signal = event_loop.get_signal();

        Ok(Self {
            start_time,
            display_handle: dh,

            space,
            loop_signal,
            socket_name,

            compositor_state,
            xdg_shell_state,
            shm_state,
            dmabuf_state,
            dmabuf_importer: None,
            output_manager_state,
            fractional_scale_manager_state,
            viewporter_state,
            xdg_activation_state,
            loop_handle,
            activation_sweep_armed: false,
            session_lock_state,
            session_locked: false,
            lock_surfaces: HashMap::new(),
            lock_owner: None,
            lock_confirmation: None,
            lock_confirmation_outputs: HashSet::new(),
            keyboard_focus_before_lock: None,
            x11_keyboard_focus_before_lock: None,
            x11_keyboard_focus: None,
            xwayland_shell_state,
            xwm: None,
            xdisplay: None,
            pending_command: None,
            notify_systemd_when_ready: false,
            fatal_error: None,
            seat_state,
            keyboard_config,
            data_device_state,
            primary_selection_state,
            text_input_manager_state,
            input_method_manager_state,
            pantheon_shell_state,
            display_config,
            gala_compat,
            workspace_manager: WorkspaceManager::new(),
            shell_compat,
            primary_output_name: None,
            panels: HashMap::new(),
            top_panel_mode: crate::pantheon_shell::TopPanelMode::Normal,
            last_work_areas: HashMap::new(),
            managed_windows: HashMap::new(),
            x11_managed_windows: HashMap::new(),
            x11_minimized_windows: HashMap::new(),
            tiled_windows: HashMap::new(),
            tiling_bindings: TilingBindings::load(),
            corner_snap_preview: None,
            corner_snap_cancelled: false,
            move_grab_active: false,
            gesture_animation: None,
            active_gesture: None,
            gesture_bindings: crate::gestures::GestureBindings::load(),
            peripheral_settings: crate::touchpad::PeripheralSettings::load(),
            #[cfg(feature = "native-drm")]
            input_devices: Vec::new(),
            pointer_gestures_state,
            overview: None,
            minimized_windows: HashMap::new(),
            initially_positioned: HashSet::new(),
            popups,
            active_popup_grab: None,
            cursor_status: CursorImageStatus::default_named(),
            cursor_theme: crate::cursor_theme::CursorTheme::load(
                crate::cursor_theme::configured_selection(),
            ),
            wallpaper,
            wallpaper_selection,
            seat,
            winit_redraw_sender: None,
            #[cfg(feature = "native-drm")]
            native_backend: None,
            #[cfg(feature = "native-drm")]
            native_redraw_sender: None,
        })
    }

    pub fn request_native_redraw(&self) {
        self.request_winit_redraw();
        #[cfg(feature = "native-drm")]
        if let Some(sender) = &self.native_redraw_sender {
            let _ = sender.send(());
        }
    }

    pub fn request_winit_redraw(&self) {
        if let Some(sender) = &self.winit_redraw_sender {
            let _ = sender.send(());
        }
    }

    /// Re-read the touchpad and mouse settings and apply them to every device.
    fn refresh_peripheral_settings(&mut self) {
        self.peripheral_settings = crate::touchpad::PeripheralSettings::load();
        #[cfg(feature = "native-drm")]
        for device in &mut self.input_devices {
            crate::touchpad::apply(&self.peripheral_settings, device);
        }
    }

    /// Re-read the keyboard settings and apply any difference.
    fn refresh_keyboard_config(&mut self) {
        let config = crate::input::startup_keyboard_config();
        if let Some(keyboard) = self.seat.get_keyboard() {
            let keymap_changed = config.model != self.keyboard_config.model
                || config.layout != self.keyboard_config.layout
                || config.variant != self.keyboard_config.variant
                || config.options != self.keyboard_config.options;
            if keymap_changed
                && let Err(error) = keyboard.set_xkb_config(self, crate::input::xkb_config(&config))
            {
                tracing::warn!(?error, "could not apply changed XKB settings");
            }
            if config.repeat_delay != self.keyboard_config.repeat_delay
                || config.repeat_rate != self.keyboard_config.repeat_rate
            {
                keyboard.change_repeat_info(config.repeat_rate, config.repeat_delay);
            }
        }
        self.keyboard_config = config;
    }

    /// Reload the compositor cursor when the interface cursor theme or size changed.
    fn refresh_cursor_theme(&mut self) {
        let selection = crate::cursor_theme::configured_selection();
        if &selection != self.cursor_theme.selection() {
            self.cursor_theme = crate::cursor_theme::CursorTheme::load(selection);
            self.request_native_redraw();
        }
    }

    /// Reload the wallpaper when the configured URI or crop mode changed.
    fn refresh_wallpaper(&mut self) {
        match crate::wallpaper::configured_selection() {
            Ok(selection) => {
                if selection != self.wallpaper_selection {
                    tracing::info!(?selection, "desktop wallpaper settings changed");
                    self.wallpaper = selection
                        .as_ref()
                        .and_then(crate::wallpaper::load_wallpaper);
                    self.wallpaper_selection = selection;
                    self.request_native_redraw();
                }
            }
            Err(error) => {
                tracing::debug!(%error, "could not check desktop wallpaper settings")
            }
        }
    }

    /// Publish the window/workspace snapshot to the Gala-compat D-Bus service.
    /// Called after every event-loop dispatch (it only copies on change).
    pub(crate) fn publish_gala_snapshot(&self) {
        let focus = self
            .seat
            .get_keyboard()
            .and_then(|keyboard| keyboard.current_focus());
        let windows = self
            .workspace_manager
            .windows()
            .into_iter()
            .filter(|(window, _, _)| {
                window
                    .toplevel()
                    .is_none_or(|toplevel| !self.is_panel_surface(toplevel.wl_surface()))
            })
            .map(|(window, workspace_index, _)| {
                let (app_id, title) = if let Some(toplevel) = window.toplevel() {
                    smithay::wayland::compositor::with_states(toplevel.wl_surface(), |states| {
                        states
                            .data_map
                            .get::<smithay::wayland::shell::xdg::XdgToplevelSurfaceData>()
                            .and_then(|attributes| attributes.lock().ok())
                            .map(|attributes| {
                                (
                                    attributes.app_id.clone().unwrap_or_default(),
                                    attributes.title.clone().unwrap_or_default(),
                                )
                            })
                            .unwrap_or_default()
                    })
                } else if let Some(surface) = window.x11_surface() {
                    let class = surface.class();
                    (
                        if class.is_empty() {
                            surface.title()
                        } else {
                            class
                        },
                        surface.title(),
                    )
                } else {
                    (String::new(), String::new())
                };
                let has_focus = window
                    .toplevel()
                    .is_some_and(|toplevel| focus.as_ref() == Some(toplevel.wl_surface()))
                    || window
                        .x11_surface()
                        .is_some_and(|surface| self.x11_keyboard_focus.as_ref() == Some(surface));
                GalaWindow {
                    uid: window.id() as u64,
                    app_id,
                    title,
                    has_focus,
                    workspace_index: workspace_index as i32,
                    time_appeared_on_workspace: window.id() as i64,
                }
            })
            .collect();
        self.gala_compat.update(DesktopSnapshot {
            windows,
            active_workspace: self.workspace_manager.active() as i32,
            workspace_count: self.workspace_manager.workspace_count() as i32 + 1,
        });
    }

    fn handle_gala_action(&mut self, action: GalaAction) -> Result<(), String> {
        match action {
            GalaAction::FocusWindow(uid) => self.focus_window_by_uid(uid),
            GalaAction::ShowWindowsFor(app_id) => {
                let uid = self
                    .workspace_manager
                    .windows()
                    .into_iter()
                    .find(|(window, _, _)| {
                        self.window_app_id(window).as_deref() == Some(app_id.as_str())
                    })
                    .map(|(window, _, _)| window.id() as u64);
                if let Some(uid) = uid {
                    self.focus_window_by_uid(uid)
                } else {
                    Err(format!("no mapped windows found for app {app_id}"))
                }
            }
            GalaAction::MoveWindowToWorkspace(uid, index) => {
                self.move_window_to_workspace(uid, index)
            }
            GalaAction::ActivateWorkspace(index) => self.activate_workspace(index),
            GalaAction::ReorderWorkspace(index, new_index) => {
                if self.session_locked {
                    return Err("cannot reorder workspaces while the session is locked".into());
                }
                let (Ok(index), Ok(new_index)) =
                    (usize::try_from(index), usize::try_from(new_index))
                else {
                    return Err("workspace indices must be non-negative".into());
                };
                if self.workspace_manager.reorder_workspace(index, new_index) {
                    self.gala_compat.request_windows_changed();
                    Ok(())
                } else {
                    Err("workspace index is outside the current workspace list".into())
                }
            }
            GalaAction::PerformAction(1) => self.toggle_overview(),
            GalaAction::PerformAction(2) => self.maximize_focused_window(),
            GalaAction::PerformAction(3) => self.minimize_focused_window(),
            GalaAction::PerformAction(4) => self.launch_panel_main_menu(),
            GalaAction::SetTopPanelMode(mode) => {
                let mode = crate::pantheon_shell::TopPanelMode::from_u32(mode)
                    .ok_or_else(|| format!("unknown top panel mode {mode}"))?;
                self.set_top_panel_mode(mode);
                Ok(())
            }
            GalaAction::PerformAction(action) => Err(format!(
                "Gala action {action} is not implemented by this compositor"
            )),
        }
    }

    fn launch_panel_main_menu(&self) -> Result<(), String> {
        use gio::prelude::SettingsExt;

        if self.session_locked {
            return Err("cannot open the application launcher while the session is locked".into());
        }
        let settings = gio::Settings::new("io.elementary.desktop.wm.behavior");
        let command = settings.string("panel-main-menu-action");
        let argv = gio::glib::shell_parse_argv(command.as_str())
            .map_err(|error| format!("could not parse panel main-menu action: {error}"))?;
        if argv.is_empty() {
            return Err("panel main-menu action is empty".into());
        }
        let argv = argv
            .iter()
            .map(std::ffi::OsString::as_os_str)
            .collect::<Vec<_>>();
        gio::Subprocess::newv(&argv, gio::SubprocessFlags::NONE)
            .map_err(|error| format!("could not launch panel main-menu action: {error}"))?;
        Ok(())
    }

    pub(crate) fn focused_window(&self) -> Option<Window> {
        if let Some(surface) = self
            .seat
            .get_keyboard()
            .and_then(|keyboard| keyboard.current_focus())
        {
            let mut root = surface;
            while let Some(parent) = smithay::wayland::compositor::get_parent(&root) {
                root = parent;
            }
            if let Some(window) = self.find_window_for_surface(&root) {
                return Some(window);
            }
        }
        let surface = self.x11_keyboard_focus.as_ref()?;
        self.space
            .elements()
            .find(|window| window.x11_surface() == Some(surface))
            .cloned()
    }

    fn maximize_focused_window(&mut self) -> Result<(), String> {
        if self.session_locked {
            return Err("cannot maximize a window while the session is locked".into());
        }
        let window = self
            .focused_window()
            .ok_or_else(|| "there is no focused application window to maximize".to_string())?;
        if let Some(toplevel) = window.toplevel().cloned() {
            if self.is_panel_surface(toplevel.wl_surface()) {
                return Err("cannot maximize a panel surface".into());
            }
            let maximized = self
                .managed_windows
                .get(&toplevel.wl_surface().id())
                .is_some_and(|state| state.maximized);
            self.configure_window_mode(toplevel, !maximized, false);
        } else if let Some(surface) = window.x11_surface().cloned() {
            let maximized = self
                .x11_managed_windows
                .get(&surface.window_id())
                .is_some_and(|state| state.maximized);
            self.configure_x11_window_mode(&surface, !maximized, false);
        } else {
            return Err("the focused surface is not a managed application window".into());
        }
        self.refresh_panel_visibility();
        self.request_native_redraw();
        Ok(())
    }

    fn minimize_focused_window(&mut self) -> Result<(), String> {
        if self.session_locked {
            return Err("cannot minimize a window while the session is locked".into());
        }
        let window = self
            .focused_window()
            .ok_or_else(|| "there is no focused application window to minimize".to_string())?;
        let Some(location) = self.space.element_location(&window) else {
            return Err("the focused window is not currently mapped".into());
        };

        if let Some(toplevel) = window.toplevel() {
            let surface = toplevel.wl_surface();
            if self.is_panel_surface(surface) {
                return Err("cannot minimize a panel surface".into());
            }
            let was_focused = self
                .seat
                .get_keyboard()
                .and_then(|keyboard| keyboard.current_focus())
                .is_some_and(|mut focused| {
                    while let Some(parent) = smithay::wayland::compositor::get_parent(&focused) {
                        focused = parent;
                    }
                    focused == *surface
                });
            self.workspace_manager.set_location(window.id(), location);
            window.set_activated(false);
            self.space.unmap_elem(&window);
            self.minimized_windows
                .insert(surface.id(), (window, location));
            if was_focused {
                self.focus_next_window();
            }
        } else if let Some(surface) = window.x11_surface().cloned() {
            surface
                .set_mapped(false)
                .map_err(|error| format!("could not minimize X11 window: {error}"))?;
            let id = surface.window_id();
            self.workspace_manager.set_location(window.id(), location);
            window.set_activated(false);
            self.space.unmap_elem(&window);
            self.x11_minimized_windows.insert(id, (window, location));
            if self.x11_keyboard_focus.as_ref() == Some(&surface) {
                self.set_x11_keyboard_focus(None, smithay::utils::SERIAL_COUNTER.next_serial());
                self.focus_next_window();
            }
        } else {
            return Err("the focused surface is not a managed application window".into());
        }
        self.refresh_panel_visibility();
        self.gala_compat.request_windows_changed();
        self.request_native_redraw();
        Ok(())
    }

    fn window_app_id(&self, window: &Window) -> Option<String> {
        if let Some(toplevel) = window.toplevel() {
            smithay::wayland::compositor::with_states(toplevel.wl_surface(), |states| {
                states
                    .data_map
                    .get::<smithay::wayland::shell::xdg::XdgToplevelSurfaceData>()
                    .and_then(|attributes| attributes.lock().ok())
                    .and_then(|attributes| attributes.app_id.clone())
            })
        } else {
            window.x11_surface().map(|surface| {
                let class = surface.class();
                if class.is_empty() {
                    surface.title()
                } else {
                    class
                }
            })
        }
    }

    fn focus_window_by_uid(&mut self, uid: u64) -> Result<(), String> {
        if self.session_locked {
            return Err("cannot focus a window while the session is locked".into());
        }
        let Ok(id) = usize::try_from(uid) else {
            return Err("window ID is outside the supported range".into());
        };
        let Some(workspace) = self.workspace_manager.workspace_for(id) else {
            return Err(format!("window {uid} does not exist"));
        };
        if workspace != self.workspace_manager.active() {
            self.switch_workspace(workspace)?;
        }
        let Some(window) = self.workspace_manager.window(id).cloned() else {
            return Err(format!("window {uid} does not exist"));
        };
        if !self.space.elements().any(|candidate| candidate == &window) {
            self.restore_minimized_workspace_window(&window);
            if !self.space.elements().any(|candidate| candidate == &window) {
                return Err(format!("window {uid} could not be restored"));
            }
        }
        self.space.raise_element(&window, true);
        let serial = smithay::utils::SERIAL_COUNTER.next_serial();
        self.focus_window_keyboard(&window, serial);
        self.refresh_panel_visibility();
        self.request_native_redraw();
        Ok(())
    }

    /// Apply the outcome of a finished touchpad gesture. Workspace changes stop
    /// at the first and last workspace instead of creating or wrapping.
    pub(crate) fn apply_swipe_outcome(
        &mut self,
        outcome: crate::gestures::GestureOutcome,
    ) -> Result<(), String> {
        use crate::gestures::GestureOutcome;
        match outcome {
            GestureOutcome::None => Ok(()),
            GestureOutcome::SwitchWorkspace(delta) => self.switch_workspace_relative(delta),
            GestureOutcome::MoveWindowToWorkspace(delta) => {
                self.move_focused_window_relative(delta)
            }
            GestureOutcome::CycleWindows(forward) => self.cycle_windows(forward),
            GestureOutcome::ToggleOverview => self.toggle_overview(),
            GestureOutcome::CloseOverview => {
                if self.overview_active() {
                    self.toggle_overview()
                } else {
                    Ok(())
                }
            }
            GestureOutcome::ToggleMaximized => self.maximize_focused_window(),
            GestureOutcome::OpenLauncher => self.launch_panel_main_menu(),
        }
    }

    /// Take the focused window to the adjacent workspace and follow it there.
    fn move_focused_window_relative(&mut self, delta: i32) -> Result<(), String> {
        let window = self
            .focused_window()
            .ok_or_else(|| "there is no focused application window to move".to_string())?;
        let target = self.workspace_manager.active() as i32 + delta;
        if target < 0 || target as usize >= self.workspace_manager.workspace_count() {
            return Err("no adjacent workspace in that direction".into());
        }
        self.move_window_to_workspace(window.id() as u64, target)?;
        self.activate_workspace(target)?;
        self.focus_window_by_uid(window.id() as u64)
    }

    /// Rotate focus through this workspace's application windows. Forward
    /// raises the bottom-most window, so repeated swipes visit every window;
    /// backward returns to the window under the focused one, like Alt+Tab.
    fn cycle_windows(&mut self, forward: bool) -> Result<(), String> {
        if self.session_locked {
            return Err("cannot switch windows while the session is locked".into());
        }
        let windows = self
            .space
            .elements()
            .filter(|window| {
                self.workspace_manager.workspace_for(window.id())
                    == Some(self.workspace_manager.active())
                    && window
                        .x11_surface()
                        .is_none_or(|surface| !surface.is_override_redirect())
                    && window
                        .toplevel()
                        .is_none_or(|top| !self.is_panel_surface(top.wl_surface()))
            })
            .cloned()
            .collect::<Vec<_>>();
        if windows.len() < 2 {
            return Err("there is no other window to switch to".into());
        }
        let target = if forward {
            &windows[0]
        } else {
            &windows[windows.len() - 2]
        };
        self.focus_window_by_uid(target.id() as u64)
    }

    fn switch_workspace_relative(&mut self, delta: i32) -> Result<(), String> {
        let target = self.workspace_manager.active() as i32 + delta;
        if target < 0 || target as usize >= self.workspace_manager.workspace_count() {
            return Err("no adjacent workspace in that direction".into());
        }
        self.activate_workspace(target)
    }

    pub(crate) fn activate_workspace(&mut self, index: i32) -> Result<(), String> {
        if self.session_locked {
            return Err("cannot switch workspaces while the session is locked".into());
        }
        let Ok(index) = usize::try_from(index) else {
            return Err("workspace index must be non-negative".into());
        };
        let workspace = if index == self.workspace_manager.dynamic_workspace_index() {
            self.workspace_manager.add_workspace()
        } else {
            index
        };
        self.switch_workspace(workspace)
    }

    fn switch_workspace(&mut self, workspace: usize) -> Result<(), String> {
        self.discard_gesture_animation();
        let current = self.workspace_manager.active();
        if workspace >= self.workspace_manager.workspace_count() {
            return Err("workspace index is outside the current workspace list".into());
        }
        if current == workspace {
            return Ok(());
        }

        let visible = self
            .space
            .elements()
            .filter(|window| self.workspace_manager.workspace_for(window.id()) == Some(current))
            .cloned()
            .collect::<Vec<_>>();
        let ordered_ids = visible.iter().map(Window::id).collect::<Vec<_>>();
        for window in &visible {
            if let Some(location) = self.space.element_location(window) {
                self.workspace_manager.set_location(window.id(), location);
            }
        }
        self.workspace_manager
            .set_order_from_visible(&ordered_ids, current);

        let focused = self
            .seat
            .get_keyboard()
            .and_then(|keyboard| keyboard.current_focus());
        if focused.as_ref().is_some_and(|surface| {
            visible.iter().any(|window| {
                window
                    .toplevel()
                    .is_some_and(|toplevel| toplevel.wl_surface() == surface)
            })
        }) && let Some(keyboard) = self.seat.get_keyboard()
        {
            keyboard.set_focus(self, None, smithay::utils::SERIAL_COUNTER.next_serial());
        }
        if self.x11_keyboard_focus.as_ref().is_some_and(|focused| {
            visible
                .iter()
                .any(|window| window.x11_surface() == Some(focused))
        }) {
            self.set_x11_keyboard_focus(None, smithay::utils::SERIAL_COUNTER.next_serial());
        }

        for window in &visible {
            window.set_activated(false);
            self.space.unmap_elem(window);
        }
        self.workspace_manager.set_active(workspace);

        let minimized_wayland = self
            .minimized_windows
            .values()
            .map(|(window, _)| window.id())
            .collect::<std::collections::HashSet<_>>();
        let minimized_x11 = self
            .x11_minimized_windows
            .values()
            .map(|(window, _)| window.id())
            .collect::<std::collections::HashSet<_>>();
        let target_windows = self
            .workspace_manager
            .windows_in(workspace)
            .into_iter()
            .filter(|(window, _)| {
                !minimized_wayland.contains(&window.id()) && !minimized_x11.contains(&window.id())
            })
            .collect::<Vec<_>>();
        for (window, location) in &target_windows {
            self.space.map_element(window.clone(), *location, false);
        }
        if let Some((window, _)) = target_windows.last() {
            self.space.raise_element(window, true);
            let serial = smithay::utils::SERIAL_COUNTER.next_serial();
            if let Some(toplevel) = window.toplevel() {
                if let Some(keyboard) = self.seat.get_keyboard() {
                    keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
                }
            } else if let Some(surface) = window.x11_surface().cloned() {
                self.set_x11_keyboard_focus(Some(surface), serial);
            }
        }
        self.refresh_panel_visibility();
        self.reconfigure_managed_windows();
        self.update_fractional_scale_preferences();
        self.gala_compat.request_windows_changed();
        self.request_native_redraw();
        Ok(())
    }

    pub(crate) fn move_window_to_workspace(&mut self, uid: u64, index: i32) -> Result<(), String> {
        if self.session_locked {
            return Err("cannot move windows while the session is locked".into());
        }
        let Ok(id) = usize::try_from(uid) else {
            return Err("window ID is outside the supported range".into());
        };
        let Ok(index) = usize::try_from(index) else {
            return Err("workspace index must be non-negative".into());
        };
        if self.workspace_manager.workspace_for(id).is_none() {
            return Err(format!("window {uid} does not exist"));
        }
        let target = if index == self.workspace_manager.dynamic_workspace_index() {
            self.workspace_manager.add_workspace()
        } else {
            index
        };
        if target >= self.workspace_manager.workspace_count() {
            return Err("workspace index is outside the current workspace list".into());
        }
        let source = self.workspace_manager.workspace_for(id).unwrap();
        if source == target {
            return Ok(());
        }
        let Some(window) = self.workspace_manager.window(id).cloned() else {
            return Err(format!("window {uid} does not exist"));
        };
        if source == self.workspace_manager.active() {
            if let Some(location) = self.space.element_location(&window) {
                self.workspace_manager.set_location(id, location);
            }
            let was_x11_focused = window
                .x11_surface()
                .is_some_and(|surface| self.x11_keyboard_focus.as_ref() == Some(surface));
            window.set_activated(false);
            self.space.unmap_elem(&window);
            if was_x11_focused {
                self.set_x11_keyboard_focus(None, smithay::utils::SERIAL_COUNTER.next_serial());
                self.focus_next_window();
            }
            if window.toplevel().is_some_and(|toplevel| {
                self.seat
                    .get_keyboard()
                    .and_then(|keyboard| keyboard.current_focus())
                    .is_some_and(|focused| focused == *toplevel.wl_surface())
            }) {
                self.focus_next_window();
            }
        }
        self.workspace_manager.assign_window(id, target);
        if target == self.workspace_manager.active() && !self.is_workspace_window_minimized(&window)
        {
            if let Some(location) = self.workspace_manager.location(id) {
                self.space.map_element(window.clone(), location, true);
            }
            self.focus_window_by_uid(uid)?;
        }
        self.refresh_panel_visibility();
        self.request_native_redraw();
        self.gala_compat.request_windows_changed();
        Ok(())
    }

    fn is_workspace_window_minimized(&self, window: &Window) -> bool {
        self.minimized_windows
            .values()
            .any(|(minimized, _)| minimized == window)
            || self
                .x11_minimized_windows
                .values()
                .any(|(minimized, _)| minimized == window)
    }

    fn restore_minimized_workspace_window(&mut self, window: &Window) {
        if let Some((_, location)) = window
            .toplevel()
            .and_then(|toplevel| self.minimized_windows.remove(&toplevel.wl_surface().id()))
        {
            let location = self
                .workspace_manager
                .location(window.id())
                .unwrap_or(location);
            self.space.map_element(window.clone(), location, true);
            return;
        }
        if let Some(surface) = window.x11_surface()
            && let Some((_, location)) = self.x11_minimized_windows.remove(&surface.window_id())
        {
            let location = self
                .workspace_manager
                .location(window.id())
                .unwrap_or(location);
            if surface.set_mapped(true).is_ok() {
                self.space.map_element(window.clone(), location, true);
                window.set_activated(true);
            }
        }
    }

    #[cfg(feature = "native-drm")]
    pub fn stop_with_error(&mut self, error: impl Into<String>) {
        self.fatal_error = Some(error.into());
        self.loop_signal.stop();
    }

    pub fn primary_output(&self) -> Option<smithay::output::Output> {
        self.primary_output_name
            .as_deref()
            .and_then(|name| self.space.outputs().find(|output| output.name() == name))
            .cloned()
            .or_else(|| self.space.outputs().next().cloned())
    }

    #[cfg(feature = "native-drm")]
    fn restore_native_outputs_from_snapshots(
        &mut self,
        snapshots: &[OutputSnapshot],
    ) -> Result<(), String> {
        let enabled = snapshots
            .iter()
            .filter(|snapshot| snapshot.enabled)
            .map(|snapshot| snapshot.connector.clone())
            .collect::<std::collections::HashSet<_>>();
        let requested_mode_ids = snapshots
            .iter()
            .filter(|snapshot| snapshot.enabled)
            .map(|snapshot| {
                (
                    snapshot.connector.clone(),
                    format!(
                        "{}x{}@{:.3}",
                        snapshot.width,
                        snapshot.height,
                        f64::from(snapshot.refresh_millihz) / 1000.0
                    ),
                )
            })
            .collect::<HashMap<_, _>>();
        let Some(mut backend) = self.native_backend.take() else {
            return Err("native DRM backend is unavailable during monitor rollback".into());
        };
        let result = (|| {
            let mut restored = false;
            let mut last_error = String::new();
            for _ in 0..=snapshots.len() {
                match backend.kms.set_enabled_outputs(
                    &mut backend.renderer,
                    self,
                    &enabled,
                    &requested_mode_ids,
                ) {
                    Ok(()) => {
                        restored = true;
                        break;
                    }
                    Err(error) => last_error = error,
                }
            }
            if !restored {
                return Err(format!(
                    "could not restore the previous output set: {last_error}"
                ));
            }
            let outputs = self.space.outputs().cloned().collect::<Vec<_>>();
            let mut requested_modes = HashMap::new();
            for output in &outputs {
                let snapshot = snapshots
                    .iter()
                    .find(|snapshot| snapshot.connector == output.name() && snapshot.enabled)
                    .ok_or_else(|| format!("missing rollback state for {}", output.name()))?;
                let mode = output
                    .modes()
                    .into_iter()
                    .find(|mode| {
                        mode.size.w == snapshot.width
                            && mode.size.h == snapshot.height
                            && mode.refresh == snapshot.refresh_millihz
                    })
                    .ok_or_else(|| {
                        format!("rollback mode is no longer available on {}", output.name())
                    })?;
                requested_modes.insert(output.name(), mode);
            }
            backend
                .kms
                .apply_modes(&mut backend.renderer, self, &requested_modes)?;

            let primary = snapshots
                .iter()
                .find(|snapshot| snapshot.enabled && snapshot.primary)
                .map(|snapshot| snapshot.connector.clone());
            for output in outputs {
                let snapshot = snapshots
                    .iter()
                    .find(|snapshot| snapshot.connector == output.name() && snapshot.enabled)
                    .expect("rollback state was validated for every active output");
                let transform = match snapshot.transform {
                    0 => smithay::utils::Transform::Normal,
                    1 => smithay::utils::Transform::_90,
                    2 => smithay::utils::Transform::_180,
                    3 => smithay::utils::Transform::_270,
                    4 => smithay::utils::Transform::Flipped,
                    5 => smithay::utils::Transform::Flipped90,
                    6 => smithay::utils::Transform::Flipped180,
                    _ => smithay::utils::Transform::Flipped270,
                };
                let mode = requested_modes[&output.name()];
                output.change_current_state(
                    Some(mode),
                    Some(transform),
                    Some(smithay::output::Scale::Fractional(snapshot.scale)),
                    Some((snapshot.x, snapshot.y).into()),
                );
                self.space.map_output(&output, (snapshot.x, snapshot.y));
            }
            self.primary_output_name = primary;
            self.display_config.update_many(snapshots.to_vec());
            self.last_work_areas.clear();
            let panels = self
                .space
                .elements()
                .filter_map(|window| {
                    let surface = window.toplevel()?.wl_surface();
                    self.is_panel_surface(surface).then(|| surface.clone())
                })
                .collect::<Vec<_>>();
            for panel in panels {
                self.update_panel(&panel, |_| {});
            }
            self.reconfigure_managed_windows();
            self.space.refresh();
            self.update_fractional_scale_preferences();
            self.request_native_redraw();
            let _ = self.display_handle.flush_clients();
            Ok(())
        })();
        self.native_backend = Some(backend);
        result
    }

    #[cfg(feature = "native-drm")]
    fn reconcile_display_config_after_failed_apply(&mut self, previous: &[OutputSnapshot]) {
        let outputs = self.space.outputs().cloned().collect::<Vec<_>>();
        let active_names = outputs
            .iter()
            .map(|output| output.name())
            .collect::<std::collections::HashSet<_>>();
        let primary = self
            .primary_output_name
            .as_ref()
            .filter(|name| active_names.contains(*name))
            .cloned()
            .or_else(|| {
                outputs
                    .iter()
                    .find(|output| output.name().starts_with("eDP-"))
                    .map(|output| output.name())
            })
            .or_else(|| outputs.first().map(|output| output.name()));
        self.primary_output_name = primary.clone();

        let mut snapshots = outputs
            .iter()
            .filter_map(|output| {
                let mode = output.current_mode()?;
                let physical = output.physical_properties();
                let location = output.current_location();
                Some(OutputSnapshot {
                    connector: output.name(),
                    vendor: physical.make,
                    product: physical.model,
                    serial: physical.serial_number,
                    width: mode.size.w,
                    height: mode.size.h,
                    refresh_millihz: mode.refresh,
                    modes: output
                        .modes()
                        .into_iter()
                        .map(|mode| OutputModeSnapshot {
                            width: mode.size.w,
                            height: mode.size.h,
                            refresh_millihz: mode.refresh,
                            preferred: output.preferred_mode() == Some(mode),
                        })
                        .collect(),
                    scale: output.current_scale().fractional_scale(),
                    transform: transform_to_dbus(output.current_transform()),
                    x: location.x,
                    y: location.y,
                    primary: primary.as_deref() == Some(output.name().as_str()),
                    enabled: true,
                })
            })
            .collect::<Vec<_>>();
        snapshots.extend(previous.iter().filter_map(|snapshot| {
            if active_names.contains(&snapshot.connector) {
                return None;
            }
            let mut snapshot = snapshot.clone();
            snapshot.enabled = false;
            snapshot.primary = false;
            Some(snapshot)
        }));
        self.display_config.update_many(snapshots);
    }

    fn apply_display_configuration(&mut self, request: &ApplyRequest) -> Result<(), String> {
        if request.logical_monitors.is_empty() {
            return Err("at least one logical monitor is required".into());
        }
        if self.session_locked {
            return Err("monitor configuration cannot change while the session is locked".into());
        }

        #[cfg(not(feature = "native-drm"))]
        let outputs = self.space.outputs().cloned().collect::<Vec<_>>();
        let known_outputs = request
            .current_outputs
            .iter()
            .map(|output| (output.connector.clone(), output.clone()))
            .collect::<HashMap<_, _>>();
        let mut configurations = HashMap::new();
        let mut primary_count = 0;
        for (x, y, scale, transform, primary, monitors, properties) in &request.logical_monitors {
            if !scale.is_finite() || !(0.5..=4.0).contains(scale) {
                return Err("monitor scale must be between 0.5 and 4.0".into());
            }
            if !properties.is_empty() {
                return Err("logical monitor properties are not supported".into());
            }
            let transform_value = *transform;
            let transform = match transform_value {
                0 => smithay::utils::Transform::Normal,
                1 => smithay::utils::Transform::_90,
                2 => smithay::utils::Transform::_180,
                3 => smithay::utils::Transform::_270,
                4 => smithay::utils::Transform::Flipped,
                5 => smithay::utils::Transform::Flipped90,
                6 => smithay::utils::Transform::Flipped180,
                7 => smithay::utils::Transform::Flipped270,
                _ => return Err(format!("unknown monitor transform {transform_value}")),
            };
            if monitors.len() != 1 {
                return Err("mirrored monitor groups are not supported yet".into());
            }
            let (connector, mode_id, monitor_properties) = &monitors[0];
            if !monitor_properties.is_empty() {
                return Err("monitor configuration properties are not supported".into());
            }
            let Some(snapshot) = known_outputs.get(connector) else {
                return Err(format!("monitor {connector} is no longer connected"));
            };
            if !snapshot.modes.iter().any(|mode| {
                format!(
                    "{}x{}@{:.3}",
                    mode.width,
                    mode.height,
                    f64::from(mode.refresh_millihz) / 1000.0
                ) == *mode_id
            }) {
                return Err(format!("mode {mode_id} is unavailable on {connector}"));
            }
            if configurations
                .insert(
                    connector.clone(),
                    (
                        *x,
                        *y,
                        *scale,
                        transform,
                        *primary,
                        mode_id.clone(),
                        transform_value,
                    ),
                )
                .is_some()
            {
                return Err(format!("monitor {connector} appears more than once"));
            }
            if *primary {
                primary_count += 1;
            }
        }
        if configurations.is_empty() || primary_count != 1 {
            return Err("exactly one primary monitor is required".into());
        }
        if configurations
            .values()
            .filter(|configuration| configuration.4)
            .count()
            != 1
        {
            return Err("at least one enabled output and exactly one primary are required".into());
        }

        let mut saved_configurations = known_outputs
            .values()
            .map(|snapshot| {
                if let Some((x, y, scale, _transform, primary, mode, transform_value)) =
                    configurations.get(&snapshot.connector)
                {
                    SavedMonitorConfiguration {
                        connector: snapshot.connector.clone(),
                        mode: mode.clone(),
                        x: *x,
                        y: *y,
                        scale: *scale,
                        transform: *transform_value,
                        primary: *primary,
                        enabled: true,
                    }
                } else {
                    SavedMonitorConfiguration {
                        connector: snapshot.connector.clone(),
                        mode: format!(
                            "{}x{}@{:.3}",
                            snapshot.width,
                            snapshot.height,
                            f64::from(snapshot.refresh_millihz) / 1000.0
                        ),
                        x: snapshot.x,
                        y: snapshot.y,
                        scale: snapshot.scale,
                        transform: snapshot.transform,
                        primary: false,
                        enabled: false,
                    }
                }
            })
            .collect::<Vec<_>>();
        saved_configurations.sort_by(|a, b| a.connector.cmp(&b.connector));

        if request.method == 0 {
            return Ok(());
        }

        let primary_output_name = configurations
            .iter()
            .find_map(|(name, configuration)| configuration.4.then(|| name.clone()));

        let enabled_connectors = configurations
            .keys()
            .cloned()
            .collect::<std::collections::HashSet<_>>();
        #[cfg(feature = "native-drm")]
        let requested_mode_ids = configurations
            .iter()
            .map(|(name, configuration)| (name.clone(), configuration.5.clone()))
            .collect::<HashMap<_, _>>();
        #[cfg(feature = "native-drm")]
        {
            let Some(mut backend) = self.native_backend.take() else {
                return Err("native DRM backend is unavailable".into());
            };
            let result = backend.kms.set_enabled_outputs(
                &mut backend.renderer,
                self,
                &enabled_connectors,
                &requested_mode_ids,
            );
            self.native_backend = Some(backend);
            if let Err(error) = result {
                if let Err(rollback_error) =
                    self.restore_native_outputs_from_snapshots(&request.current_outputs)
                {
                    self.reconcile_display_config_after_failed_apply(&request.current_outputs);
                    return Err(format!(
                        "{error}; monitor rollback failed: {rollback_error}"
                    ));
                }
                return Err(error);
            }
        }
        #[cfg(not(feature = "native-drm"))]
        if outputs
            .iter()
            .map(|output| output.name())
            .collect::<std::collections::HashSet<_>>()
            != enabled_connectors
        {
            return Err("the nested backend cannot enable or disable monitors".into());
        }

        let outputs = self.space.outputs().cloned().collect::<Vec<_>>();

        let mut requested_modes = HashMap::new();
        for output in &outputs {
            let (_, _, _, _, _, mode_id, _) = &configurations[&output.name()];
            let mode = output
                .modes()
                .into_iter()
                .find(|mode| {
                    format!(
                        "{}x{}@{:.3}",
                        mode.size.w,
                        mode.size.h,
                        f64::from(mode.refresh) / 1000.0
                    ) == *mode_id
                })
                .ok_or_else(|| format!("mode {mode_id} is unavailable on {}", output.name()))?;
            requested_modes.insert(output.name(), mode);
        }
        if outputs
            .iter()
            .any(|output| output.current_mode() != requested_modes.get(&output.name()).copied())
        {
            #[cfg(feature = "native-drm")]
            {
                let Some(mut backend) = self.native_backend.take() else {
                    return Err("the nested backend cannot change display modes".into());
                };
                let result = backend
                    .kms
                    .apply_modes(&mut backend.renderer, self, &requested_modes);
                self.native_backend = Some(backend);
                if let Err(error) = result {
                    if let Err(rollback_error) =
                        self.restore_native_outputs_from_snapshots(&request.current_outputs)
                    {
                        self.reconcile_display_config_after_failed_apply(&request.current_outputs);
                        return Err(format!(
                            "{error}; monitor rollback failed: {rollback_error}"
                        ));
                    }
                    return Err(error);
                }
            }
            #[cfg(not(feature = "native-drm"))]
            return Err("this build cannot change native display modes".into());
        }

        let mut snapshots = Vec::with_capacity(outputs.len());
        for output in outputs {
            let (x, y, scale, transform, primary, _mode_id, _) = &configurations[&output.name()];
            let mode = requested_modes[&output.name()];
            output.change_current_state(
                Some(mode),
                Some(*transform),
                Some(smithay::output::Scale::Fractional(*scale)),
                Some((*x, *y).into()),
            );
            self.space.map_output(&output, (*x, *y));
            let physical = output.physical_properties();
            snapshots.push(OutputSnapshot {
                connector: output.name(),
                vendor: physical.make,
                product: physical.model,
                serial: physical.serial_number,
                width: mode.size.w,
                height: mode.size.h,
                refresh_millihz: mode.refresh,
                modes: output
                    .modes()
                    .into_iter()
                    .map(|mode| OutputModeSnapshot {
                        width: mode.size.w,
                        height: mode.size.h,
                        refresh_millihz: mode.refresh,
                        preferred: output.preferred_mode() == Some(mode),
                    })
                    .collect(),
                scale: *scale,
                transform: transform_to_dbus(*transform),
                x: *x,
                y: *y,
                primary: *primary,
                enabled: true,
            });
        }
        for output in &request.current_outputs {
            if !enabled_connectors.contains(&output.connector) {
                let mut disabled = output.clone();
                disabled.enabled = false;
                disabled.primary = false;
                snapshots.push(disabled);
            }
        }
        self.primary_output_name = primary_output_name;
        self.display_config.update_many(snapshots);

        let output_geometries = self
            .space
            .outputs()
            .filter_map(|output| self.space.output_geometry(output))
            .collect::<Vec<_>>();
        if let Some(fallback) = self
            .primary_output()
            .and_then(|output| self.space.output_geometry(&output))
        {
            let windows = self.space.elements().cloned().collect::<Vec<_>>();
            for window in windows {
                let Some(location) = self.space.element_location(&window) else {
                    continue;
                };
                let size = window.geometry().size;
                let center_x = location.x + size.w / 2;
                let center_y = location.y + size.h / 2;
                let visible = output_geometries.iter().any(|geometry| {
                    center_x >= geometry.loc.x
                        && center_x < geometry.loc.x + geometry.size.w
                        && center_y >= geometry.loc.y
                        && center_y < geometry.loc.y + geometry.size.h
                });
                if !visible {
                    let target = Point::from((fallback.loc.x + 32, fallback.loc.y + 32));
                    self.space.map_element(window.clone(), target, false);
                    self.workspace_manager.set_location(window.id(), target);
                }
            }

            let hidden_windows = self
                .workspace_manager
                .windows()
                .into_iter()
                .filter(|(_, workspace, _)| *workspace != self.workspace_manager.active())
                .collect::<Vec<_>>();
            for (window, _, location) in hidden_windows {
                let size = window.geometry().size;
                let center_x = location.x + size.w / 2;
                let center_y = location.y + size.h / 2;
                let visible = output_geometries.iter().any(|geometry| {
                    center_x >= geometry.loc.x
                        && center_x < geometry.loc.x + geometry.size.w
                        && center_y >= geometry.loc.y
                        && center_y < geometry.loc.y + geometry.size.h
                });
                if !visible {
                    self.workspace_manager.set_location(
                        window.id(),
                        Point::from((fallback.loc.x + 32, fallback.loc.y + 32)),
                    );
                }
            }
        }

        self.last_work_areas.clear();
        let panels = self
            .space
            .elements()
            .filter_map(|window| {
                let surface = window.toplevel()?.wl_surface();
                self.is_panel_surface(surface).then(|| surface.clone())
            })
            .collect::<Vec<_>>();
        for panel in panels {
            self.update_panel(&panel, |_| {});
        }
        self.reconfigure_managed_windows();
        self.space.refresh();
        self.update_fractional_scale_preferences();
        let _ = self.display_handle.flush_clients();
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
        if request.method == 2 {
            save_monitor_configurations(&saved_configurations)
                .map_err(|error| format!("could not save monitor configuration: {error}"))?;
        }
        Ok(())
    }

    pub fn update_fractional_scale_preferences(&self) {
        for window in self.space.elements() {
            let Some(output) = self.space.outputs_for_element(window).first().cloned() else {
                continue;
            };
            let scale = output.current_scale().fractional_scale();
            window.with_surfaces(|_, states| {
                with_fractional_scale(states, |fractional_scale| {
                    fractional_scale.set_preferred_scale(scale);
                });
            });
        }
    }

    fn init_wayland_listener(
        display: Display<PantheonCompositor>,
        event_loop: &mut EventLoop<Self>,
    ) -> Result<OsString, Box<dyn std::error::Error>> {
        // A session service may request a stable name; nested development keeps automatic allocation.
        let listening_socket = if let Some(name) = std::env::var_os("PANTHEON_WAYLAND_DISPLAY") {
            let name = name
                .to_str()
                .ok_or("PANTHEON_WAYLAND_DISPLAY must be valid UTF-8")?;
            ListeningSocketSource::with_name(name)?
        } else {
            ListeningSocketSource::new_auto()?
        };

        // Get the name of the listening socket.
        // Clients will connect to this socket.
        let socket_name = listening_socket.socket_name().to_os_string();

        let loop_handle = event_loop.handle();

        loop_handle.insert_source(listening_socket, move |client_stream, _, state| {
            tracing::debug!("accepted Wayland client connection");
            // Inside the callback, you should insert the client into the display.
            //
            // You may also associate some data with the client when inserting the client.
            let is_ibus_input_method_client = is_ibus_input_method_stream(&client_stream);
            state
                .display_handle
                .insert_client(
                    client_stream,
                    Arc::new(ClientState {
                        is_ibus_input_method_client,
                        ..ClientState::default()
                    }),
                )
                .unwrap();
        })?;

        // You also need to add the display itself to the event loop, so that client events will be processed by wayland-server.
        loop_handle
            .insert_source(
                Generic::new(display, Interest::READ, Mode::Level),
                |_, display, state| {
                    // Safety: we don't drop the display
                    unsafe {
                        let display = display.get_mut();
                        display.dispatch_clients(state).unwrap();
                        display.flush_clients().unwrap();
                    }
                    Ok(PostAction::Continue)
                },
            )
            .unwrap();

        Ok(socket_name)
    }

    pub fn surface_under(
        &self,
        pos: Point<f64, Logical>,
    ) -> Option<(WlSurface, Point<f64, Logical>)> {
        if self.session_locked {
            for output in self.space.outputs() {
                let Some(geometry) = self.space.output_geometry(output) else {
                    continue;
                };
                if !geometry.to_f64().contains(pos) {
                    continue;
                }
                let output_name = output.name();
                let lock_surface = self.lock_surfaces.get(&output_name)?;
                let local = pos - geometry.loc.to_f64();
                return smithay::desktop::utils::under_from_surface_tree(
                    lock_surface.wl_surface(),
                    local,
                    (0, 0),
                    WindowSurfaceType::ALL,
                )
                .map(|(surface, location)| (surface, location.to_f64()));
            }
            return None;
        }
        self.space
            .element_under(pos)
            .and_then(|(window, location)| {
                window
                    .surface_under(pos - location.to_f64(), WindowSurfaceType::ALL)
                    .map(|(s, p)| (s, (p + location).to_f64()))
            })
    }

    pub fn track_output_for_lock(&mut self, output: &smithay::output::Output) {
        if self.session_locked && self.lock_confirmation.is_some() {
            self.lock_confirmation_outputs
                .insert(output.name().to_string());
        }
    }

    pub fn confirm_lock_output_frame(&mut self, output_name: &str) {
        if !self.session_locked || self.lock_confirmation.is_none() {
            return;
        }
        self.lock_confirmation_outputs.remove(output_name);
        self.finish_lock_confirmation_if_ready();
    }

    pub fn forget_output_during_lock(&mut self, output_name: &str) {
        self.lock_confirmation_outputs.remove(output_name);
        self.finish_lock_confirmation_if_ready();
    }

    fn finish_lock_confirmation_if_ready(&mut self) {
        if !self.session_locked || self.lock_confirmation.is_none() {
            return;
        }
        if self.lock_confirmation_outputs.is_empty()
            && let Some(confirmation) = self.lock_confirmation.take()
        {
            confirmation.lock();
            self.shell_compat.set_locked(true);
        }
    }
}

impl FractionalScaleHandler for PantheonCompositor {
    fn new_fractional_scale(&mut self, surface: WlSurface) {
        let mut root = surface.clone();
        while let Some(parent) = smithay::wayland::compositor::get_parent(&root) {
            root = parent;
        }
        let output = self
            .find_window_for_surface(&root)
            .and_then(|window| self.space.outputs_for_element(&window).first().cloned())
            .or_else(|| self.primary_output());
        if let Some(output) = output {
            smithay::wayland::compositor::with_states(&surface, |states| {
                with_fractional_scale(states, |fractional_scale| {
                    fractional_scale.set_preferred_scale(output.current_scale().fractional_scale());
                });
            });
        }
    }
}

const ACTIVATION_TOKEN_TTL: Duration = Duration::from_secs(60);

impl PantheonCompositor {
    /// Expire stale activation tokens without a periodic timer: a one-shot
    /// timer is armed when a token exists and drops itself once none remain.
    fn arm_activation_sweep(&mut self) {
        if self.activation_sweep_armed {
            return;
        }
        self.activation_sweep_armed = true;
        let armed = self.loop_handle.insert_source(
            Timer::from_duration(ACTIVATION_TOKEN_TTL),
            |_, _, state| {
                let mut oldest = Duration::ZERO;
                state.xdg_activation_state.retain_tokens(|_, token| {
                    let age = token.timestamp.elapsed();
                    let keep = age < ACTIVATION_TOKEN_TTL;
                    if keep {
                        oldest = oldest.max(age);
                    }
                    keep
                });
                if oldest.is_zero() {
                    state.activation_sweep_armed = false;
                    TimeoutAction::Drop
                } else {
                    TimeoutAction::ToDuration(ACTIVATION_TOKEN_TTL - oldest)
                }
            },
        );
        if armed.is_err() {
            self.activation_sweep_armed = false;
        }
    }
}

impl XdgActivationHandler for PantheonCompositor {
    fn activation_state(&mut self) -> &mut XdgActivationState {
        &mut self.xdg_activation_state
    }

    fn token_created(&mut self, _token: XdgActivationToken, data: XdgActivationTokenData) -> bool {
        self.xdg_activation_state
            .retain_tokens(|_, token| token.timestamp.elapsed() < ACTIVATION_TOKEN_TTL);
        self.arm_activation_sweep();
        let Some((serial, seat)) = data.serial else {
            return false;
        };
        let Some(keyboard) = self.seat.get_keyboard() else {
            return false;
        };
        Seat::from_resource(&seat) == Some(self.seat.clone())
            && keyboard
                .last_enter()
                .is_some_and(|last_enter| serial.is_no_older_than(&last_enter))
    }

    fn request_activation(
        &mut self,
        token: XdgActivationToken,
        token_data: XdgActivationTokenData,
        surface: WlSurface,
    ) {
        self.xdg_activation_state.remove_token(&token);
        if self.session_locked || token_data.timestamp.elapsed() > Duration::from_secs(10) {
            return;
        }

        let mut root = surface;
        while let Some(parent) = smithay::wayland::compositor::get_parent(&root) {
            root = parent;
        }
        if self.is_panel_surface(&root) {
            return;
        }
        let managed = self
            .workspace_manager
            .windows()
            .into_iter()
            .find(|(window, _, _)| {
                window
                    .toplevel()
                    .is_some_and(|toplevel| toplevel.wl_surface() == &root)
            });
        if let Some((_, workspace, _)) = &managed
            && *workspace != self.workspace_manager.active()
        {
            let _ = self.switch_workspace(*workspace);
        }
        let window = self
            .find_window_for_surface(&root)
            .or_else(|| managed.map(|(window, _, _)| window));
        let Some(window) = window else {
            return;
        };
        if !self.space.elements().any(|candidate| candidate == &window) {
            self.restore_minimized_workspace_window(&window);
            if !self.space.elements().any(|candidate| candidate == &window) {
                return;
            }
        }
        self.space.raise_element(&window, true);
        let serial = smithay::utils::SERIAL_COUNTER.next_serial();
        self.focus_window_keyboard(&window, serial);
        self.space.elements().for_each(|window| {
            if let Some(toplevel) = window.toplevel() {
                toplevel.send_pending_configure();
            }
        });
        self.refresh_panel_visibility();
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }
}

/// Data associated with a wayland client that connects to PantheonCompositor.
/// One instance of this type per client.
#[derive(Default)]
pub struct ClientState {
    pub compositor_state: CompositorClientState,
    pub is_ibus_input_method_client: bool,
}

impl ClientData for ClientState {
    fn initialized(&self, _client_id: ClientId) {}
    fn disconnected(&self, _client_id: ClientId, _reason: DisconnectReason) {}
}
