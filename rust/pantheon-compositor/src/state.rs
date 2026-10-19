use std::collections::{HashMap, HashSet};
use std::{ffi::OsString, sync::Arc, time::Duration};

use smithay::{
    backend::renderer::element::memory::MemoryRenderBuffer,
    desktop::{PopupManager, Space, Window, WindowSurfaceType},
    input::{Seat, SeatState, pointer::CursorImageStatus},
    reexports::{
        calloop::{
            EventLoop, Interest, LoopSignal, Mode, PostAction, channel,
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
        fractional_scale::{
            FractionalScaleHandler, FractionalScaleManagerState, with_fractional_scale,
        },
        output::OutputManagerState,
        selection::data_device::DataDeviceState,
        session_lock::{LockSurface, SessionLockManagerState, SessionLocker},
        shell::xdg::XdgShellState,
        shm::ShmState,
        socket::ListeningSocketSource,
        viewporter::ViewporterState,
        xdg_activation::{
            XdgActivationHandler, XdgActivationState, XdgActivationToken, XdgActivationTokenData,
        },
    },
};

use crate::cursor::default_cursor_buffer;
use crate::display_config::{
    ApplyRequest, DisplayConfigHandle, OutputModeSnapshot, OutputSnapshot,
    SavedMonitorConfiguration, save_monitor_configurations, transform_to_dbus,
};
#[cfg(feature = "native-drm")]
use crate::native::NativeBackend;
use crate::pantheon_shell::{PanelState, PantheonShellState};
use crate::shell_compat::ShellCompatHandle;
use crate::tiling::{CornerSnapPreview, TilingBindings};
#[cfg(feature = "native-drm")]
use smithay::reexports::calloop::channel::Sender;

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
    pub output_manager_state: OutputManagerState,
    pub fractional_scale_manager_state: FractionalScaleManagerState,
    pub viewporter_state: ViewporterState,
    pub xdg_activation_state: XdgActivationState,
    pub session_lock_state: SessionLockManagerState,
    pub session_locked: bool,
    pub lock_surfaces: HashMap<String, LockSurface>,
    pub lock_owner: Option<smithay::reexports::wayland_server::backend::ObjectId>,
    pub lock_confirmation: Option<SessionLocker>,
    pub lock_confirmation_outputs: HashSet<String>,
    pub keyboard_focus_before_lock: Option<WlSurface>,
    pub seat_state: SeatState<PantheonCompositor>,
    pub(crate) keyboard_config: crate::input::StartupKeyboardConfig,
    pub data_device_state: DataDeviceState,
    pub pantheon_shell_state: PantheonShellState,
    pub display_config: DisplayConfigHandle,
    pub shell_compat: ShellCompatHandle,
    pub primary_output_name: Option<String>,
    pub panels: HashMap<smithay::reexports::wayland_server::backend::ObjectId, PanelState>,
    pub last_work_areas: HashMap<String, smithay::utils::Rectangle<i32, smithay::utils::Logical>>,
    pub managed_windows:
        HashMap<smithay::reexports::wayland_server::backend::ObjectId, ManagedWindow>,
    pub tiled_windows: HashMap<smithay::reexports::wayland_server::backend::ObjectId, TiledWindow>,
    pub tiling_bindings: TilingBindings,
    pub corner_snap_preview: Option<CornerSnapPreview>,
    pub corner_snap_cancelled: bool,
    pub move_grab_active: bool,
    pub minimized_windows: HashMap<
        smithay::reexports::wayland_server::backend::ObjectId,
        (Window, Point<i32, Logical>),
    >,
    pub initially_positioned: HashSet<smithay::reexports::wayland_server::backend::ObjectId>,
    pub popups: PopupManager,
    pub cursor_status: CursorImageStatus,
    pub default_cursor: MemoryRenderBuffer,

    pub seat: Seat<Self>,
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
        event_loop: &mut EventLoop<Self>,
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
        let popups = PopupManager::default();

        let output_manager_state = OutputManagerState::new_with_xdg_output::<Self>(&dh);
        let fractional_scale_manager_state = FractionalScaleManagerState::new::<Self>(&dh);
        let viewporter_state = ViewporterState::new::<Self>(&dh);
        let xdg_activation_state = XdgActivationState::new::<Self>(&dh);
        let session_lock_state = SessionLockManagerState::new::<Self, _>(&dh, |_| true);

        // Data device is responsible for clipboard and drag-and-drop
        let data_device_state = DataDeviceState::new::<Self>(&dh);
        let pantheon_shell_state = PantheonShellState::new::<Self>(&dh);
        let (display_config, apply_requests) = DisplayConfigHandle::start();
        event_loop.handle().insert_source(
            Timer::from_duration(Duration::from_millis(25)),
            move |_, _, state| {
                while let Ok(request) = apply_requests.try_recv() {
                    let result = state.apply_display_configuration(&request);
                    let _ = request.response.send(result);
                }
                TimeoutAction::ToDuration(Duration::from_millis(25))
            },
        )?;
        event_loop.handle().insert_source(
            Timer::from_duration(Duration::from_secs(10)),
            |_, _, state| {
                state
                    .xdg_activation_state
                    .retain_tokens(|_, token| token.timestamp.elapsed() < Duration::from_secs(60));
                TimeoutAction::ToDuration(Duration::from_secs(10))
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
        event_loop.handle().insert_source(
            Timer::from_duration(Duration::from_secs(1)),
            |_, _, state| {
                let config = crate::input::startup_keyboard_config();
                if let Some(keyboard) = state.seat.get_keyboard() {
                    let keymap_changed = config.model != state.keyboard_config.model
                        || config.layout != state.keyboard_config.layout
                        || config.variant != state.keyboard_config.variant
                        || config.options != state.keyboard_config.options;
                    if keymap_changed
                        && let Err(error) =
                            keyboard.set_xkb_config(state, crate::input::xkb_config(&config))
                    {
                        tracing::warn!(?error, "could not apply changed XKB settings");
                    }
                    if config.repeat_delay != state.keyboard_config.repeat_delay
                        || config.repeat_rate != state.keyboard_config.repeat_rate
                    {
                        keyboard.change_repeat_info(config.repeat_rate, config.repeat_delay);
                    }
                }
                state.keyboard_config = config;
                TimeoutAction::ToDuration(Duration::from_secs(1))
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

        // Setup a wayland socket that will be used to accept clients
        let socket_name = Self::init_wayland_listener(display, event_loop)?;
        let (osd_redraw_sender, osd_redraw_receiver) = channel::channel();
        event_loop
            .handle()
            .insert_source(osd_redraw_receiver, |event, _, _state| {
                if matches!(event, channel::Event::Msg(())) {
                    #[cfg(feature = "native-drm")]
                    _state.request_native_redraw();
                }
            })?;
        let shell_compat = ShellCompatHandle::start(socket_name.clone(), osd_redraw_sender);

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
            output_manager_state,
            fractional_scale_manager_state,
            viewporter_state,
            xdg_activation_state,
            session_lock_state,
            session_locked: false,
            lock_surfaces: HashMap::new(),
            lock_owner: None,
            lock_confirmation: None,
            lock_confirmation_outputs: HashSet::new(),
            keyboard_focus_before_lock: None,
            seat_state,
            keyboard_config,
            data_device_state,
            pantheon_shell_state,
            display_config,
            shell_compat,
            primary_output_name: None,
            panels: HashMap::new(),
            last_work_areas: HashMap::new(),
            managed_windows: HashMap::new(),
            tiled_windows: HashMap::new(),
            tiling_bindings: TilingBindings::load(),
            corner_snap_preview: None,
            corner_snap_cancelled: false,
            move_grab_active: false,
            minimized_windows: HashMap::new(),
            initially_positioned: HashSet::new(),
            popups,
            cursor_status: CursorImageStatus::default_named(),
            default_cursor: default_cursor_buffer(),
            seat,
            #[cfg(feature = "native-drm")]
            native_backend: None,
            #[cfg(feature = "native-drm")]
            native_redraw_sender: None,
        })
    }

    #[cfg(feature = "native-drm")]
    pub fn request_native_redraw(&self) {
        if let Some(sender) = &self.native_redraw_sender {
            let _ = sender.send(());
        }
    }

    pub fn primary_output(&self) -> Option<smithay::output::Output> {
        self.primary_output_name
            .as_deref()
            .and_then(|name| self.space.outputs().find(|output| output.name() == name))
            .cloned()
            .or_else(|| self.space.outputs().next().cloned())
    }

    fn apply_display_configuration(&mut self, request: &ApplyRequest) -> Result<(), String> {
        if request.logical_monitors.is_empty() {
            return Err("at least one logical monitor is required".into());
        }
        if self.session_locked {
            return Err("monitor configuration cannot change while the session is locked".into());
        }

        let outputs = self.space.outputs().cloned().collect::<Vec<_>>();
        if request.logical_monitors.len() != outputs.len() {
            return Err("disabling outputs and monitor mirroring are not supported yet".into());
        }

        let mut configurations = HashMap::new();
        let mut saved_configurations = Vec::new();
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
            let Some(output) = outputs.iter().find(|output| output.name() == *connector) else {
                return Err(format!("monitor {connector} is no longer connected"));
            };
            let Some(mode) = output.modes().into_iter().find(|mode| {
                format!(
                    "{}x{}@{:.3}",
                    mode.size.w,
                    mode.size.h,
                    f64::from(mode.refresh) / 1000.0
                ) == *mode_id
            }) else {
                return Err(format!("mode {mode_id} is unavailable on {connector}"));
            };
            if configurations
                .insert(
                    connector.clone(),
                    (*x, *y, *scale, transform, *primary, mode),
                )
                .is_some()
            {
                return Err(format!("monitor {connector} appears more than once"));
            }
            if *primary {
                primary_count += 1;
            }
            saved_configurations.push(SavedMonitorConfiguration {
                connector: connector.clone(),
                mode: mode_id.clone(),
                x: *x,
                y: *y,
                scale: *scale,
                transform: transform_value,
                primary: *primary,
            });
        }
        if configurations.len() != outputs.len() {
            return Err("every connected output must appear exactly once".into());
        }
        if primary_count != 1 {
            return Err("exactly one primary monitor is required".into());
        }

        if request.method == 0 {
            return Ok(());
        }

        let primary_output_name = outputs
            .iter()
            .find(|output| configurations[&output.name()].4)
            .map(|output| output.name());

        let requested_modes = configurations
            .iter()
            .map(|(name, (_, _, _, _, _, mode))| (name.clone(), *mode))
            .collect::<HashMap<_, _>>();
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
                result?;
            }
            #[cfg(not(feature = "native-drm"))]
            return Err("this build cannot change native display modes".into());
        }

        let mut snapshots = Vec::with_capacity(outputs.len());
        for output in outputs {
            let (x, y, scale, transform, primary, mode) = configurations[&output.name()];
            output.change_current_state(
                Some(mode),
                Some(transform),
                Some(smithay::output::Scale::Fractional(scale)),
                Some((x, y).into()),
            );
            self.space.map_output(&output, (x, y));
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
                scale,
                transform: transform_to_dbus(transform),
                x,
                y,
                primary,
            });
        }
        self.primary_output_name = primary_output_name;
        self.display_config.update_many(snapshots);

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
            // Inside the callback, you should insert the client into the display.
            //
            // You may also associate some data with the client when inserting the client.
            state
                .display_handle
                .insert_client(client_stream, Arc::new(ClientState::default()))
                .unwrap();
        })?;

        // You also need to add the display itself to the event loop, so that client events will be processed by wayland-server.
        loop_handle
            .insert_source(
                Generic::new(display, Interest::READ, Mode::Level),
                |_, display, state| {
                    // Safety: we don't drop the display
                    unsafe {
                        display.get_mut().dispatch_clients(state).unwrap();
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
                let Some(lock_surface) = self.lock_surfaces.get(&output_name) else {
                    return None;
                };
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
        if self.lock_confirmation_outputs.is_empty() {
            if let Some(confirmation) = self.lock_confirmation.take() {
                confirmation.lock();
                self.shell_compat.set_locked(true);
            }
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

impl XdgActivationHandler for PantheonCompositor {
    fn activation_state(&mut self) -> &mut XdgActivationState {
        &mut self.xdg_activation_state
    }

    fn token_created(&mut self, _token: XdgActivationToken, data: XdgActivationTokenData) -> bool {
        self.xdg_activation_state
            .retain_tokens(|_, token| token.timestamp.elapsed() < Duration::from_secs(60));
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
        let root_id = root.id();
        let window = self.find_window_for_surface(&root).or_else(|| {
            let (window, location) = self.minimized_windows.remove(&root_id)?;
            self.space.map_element(window.clone(), location, false);
            Some(window)
        });
        let Some(window) = window else {
            return;
        };
        self.space.raise_element(&window, true);
        if let Some(surface) = window
            .toplevel()
            .map(|toplevel| toplevel.wl_surface().clone())
        {
            let serial = smithay::utils::SERIAL_COUNTER.next_serial();
            if let Some(keyboard) = self.seat.get_keyboard() {
                keyboard.set_focus(self, Some(surface), serial);
            }
            self.space.elements().for_each(|window| {
                if let Some(toplevel) = window.toplevel() {
                    toplevel.send_pending_configure();
                }
            });
        }
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }
}

/// Data associated with a wayland client that connects to PantheonCompositor.
/// One instance of this type per client.
#[derive(Default)]
pub struct ClientState {
    pub compositor_state: CompositorClientState,
}

impl ClientData for ClientState {
    fn initialized(&self, _client_id: ClientId) {}
    fn disconnected(&self, _client_id: ClientId, _reason: DisconnectReason) {}
}
