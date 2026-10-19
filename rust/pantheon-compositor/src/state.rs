use std::collections::{HashMap, HashSet};
use std::{ffi::OsString, sync::Arc};

use smithay::{
    backend::renderer::element::memory::MemoryRenderBuffer,
    desktop::{PopupManager, Space, Window, WindowSurfaceType},
    input::{Seat, SeatState, pointer::CursorImageStatus},
    reexports::{
        calloop::{EventLoop, Interest, LoopSignal, Mode, PostAction, generic::Generic},
        wayland_server::{
            Display, DisplayHandle,
            backend::{ClientData, ClientId, DisconnectReason},
            protocol::wl_surface::WlSurface,
        },
    },
    utils::{Logical, Point, Size},
    wayland::{
        compositor::{CompositorClientState, CompositorState},
        output::OutputManagerState,
        selection::data_device::DataDeviceState,
        shell::xdg::XdgShellState,
        shm::ShmState,
        socket::ListeningSocketSource,
    },
};

use crate::cursor::default_cursor_buffer;
use crate::display_config::DisplayConfigHandle;
#[cfg(feature = "native-drm")]
use crate::native::NativeBackend;
use crate::pantheon_shell::{PanelState, PantheonShellState};
use crate::shell_compat::ShellCompatHandle;
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
    pub seat_state: SeatState<PantheonCompositor>,
    pub data_device_state: DataDeviceState,
    pub pantheon_shell_state: PantheonShellState,
    pub display_config: DisplayConfigHandle,
    pub shell_compat: ShellCompatHandle,
    pub panels: HashMap<smithay::reexports::wayland_server::backend::ObjectId, PanelState>,
    pub last_work_area: Option<smithay::utils::Rectangle<i32, smithay::utils::Logical>>,
    pub managed_windows:
        HashMap<smithay::reexports::wayland_server::backend::ObjectId, ManagedWindow>,
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

        // Data device is responsible for clipboard and drag-and-drop
        let data_device_state = DataDeviceState::new::<Self>(&dh);
        let pantheon_shell_state = PantheonShellState::new::<Self>(&dh);
        let display_config = DisplayConfigHandle::start();
        let shell_compat = ShellCompatHandle::start();

        // A seat is a group of keyboards, pointer and touch devices.
        // A seat typically has a pointer and maintains a keyboard focus and a pointer focus.
        let mut seat_state = SeatState::new();
        let mut seat: Seat<Self> = seat_state.new_wl_seat(&dh, seat_name);

        // Notify clients that we have a keyboard, for the sake of the example we assume that keyboard is always present.
        // You may want to track keyboard hot-plug in real compositor.
        seat.add_keyboard(Default::default(), 200, 25).unwrap();

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
            seat_state,
            data_device_state,
            pantheon_shell_state,
            display_config,
            shell_compat,
            panels: HashMap::new(),
            last_work_area: None,
            managed_windows: HashMap::new(),
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
        self.space
            .element_under(pos)
            .and_then(|(window, location)| {
                window
                    .surface_under(pos - location.to_f64(), WindowSurfaceType::ALL)
                    .map(|(s, p)| (s, (p + location).to_f64()))
            })
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
