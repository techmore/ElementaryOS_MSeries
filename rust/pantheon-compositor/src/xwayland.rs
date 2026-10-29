use std::process::Stdio;

use smithay::{
    desktop::Window,
    input::keyboard::KeyboardTarget,
    input::pointer::Focus,
    reexports::calloop::EventLoop,
    utils::{Logical, Point, Rectangle},
    wayland::{
        selection::{
            SelectionTarget,
            data_device::{
                clear_data_device_selection, current_data_device_selection_userdata,
                request_data_device_client_selection, set_data_device_selection,
            },
            primary_selection::{
                clear_primary_selection, current_primary_selection_userdata,
                request_primary_client_selection, set_primary_selection,
            },
        },
        xwayland_shell::XWaylandShellHandler,
    },
    xwayland::{
        X11Surface, X11Wm, XWayland, XWaylandEvent, XwmHandler,
        xwm::{Reorder, ResizeEdge, WmInputModel, WmWindowProperty, XwmId},
    },
};

use smithay::{
    backend::renderer::{
        ImportMem,
        element::{Kind, memory::MemoryRenderBufferRenderElement},
    },
    desktop::space::SpaceElement,
    input::pointer::{CursorIcon, GrabStartData as PointerGrabStartData, PointerHandle},
    output::Output,
    utils::Serial,
};

use crate::decorations::{self, ButtonKind, FrameHit, FrameSpec, PaintKey, TITLE_HEIGHT};
use crate::grabs::{ResizeSurfaceGrab, resize_grab::ResizeEdge as PantheonResizeEdge};
use crate::{PantheonCompositor, attention::Reason, tiling::ModeRequest};

/// BTN_LEFT from linux/input-event-codes.h.
const BTN_LEFT: u32 = 0x110;
/// Two title-bar clicks closer than this maximize or restore the window.
const DOUBLE_CLICK: std::time::Duration = std::time::Duration::from_millis(400);

/// Whether the window manager may give this X11 window keyboard focus and
/// draw it as active. Override-redirect windows (menus, tooltips, the
/// notification cards from `desktop-notifications/popup.py`) and windows with
/// ICCCM input model "No Input" (`WM_HINTS.input = False` without
/// `WM_TAKE_FOCUS`) must only ever be raised: activating one deactivated the
/// focused app, and focusing one left keystrokes with nobody.
pub(crate) fn x11_accepts_focus(surface: &X11Surface) -> bool {
    !surface.is_override_redirect() && surface.input_model() != WmInputModel::None
}

pub(crate) fn window_accepts_focus(window: &Window) -> bool {
    window.x11_surface().is_none_or(x11_accepts_focus)
}

pub fn start(
    event_loop: &mut EventLoop<'static, PantheonCompositor>,
    state: &mut PantheonCompositor,
    export_session_environment: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    let (source, client) = XWayland::spawn(
        &state.display_handle,
        None,
        std::iter::empty::<(String, String)>(),
        std::iter::empty::<String>(),
        true,
        Stdio::null(),
        Stdio::null(),
        |_| (),
    )?;
    let display_handle = state.display_handle.clone();
    let loop_handle = event_loop.handle();
    event_loop
        .handle()
        .insert_source(source, move |event, _, state| {
            match event {
                XWaylandEvent::Ready {
                    x11_socket,
                    display_number,
                } => {
                    match X11Wm::start_wm(
                        loop_handle.clone(),
                        &display_handle,
                        x11_socket,
                        client.clone(),
                    ) {
                        Ok(wm) => {
                            state.xwm = Some(wm);
                            state.xdisplay = Some(display_number);
                            let display = format!(":{display_number}");
                            // SAFETY: compositor startup owns the session environment before
                            // launching any requested clients.
                            unsafe { std::env::set_var("DISPLAY", &display) };
                            if export_session_environment {
                                let activation_display = format!("DISPLAY={display}");
                                match std::process::Command::new(
                                    "dbus-update-activation-environment",
                                )
                                .args(["--systemd", &activation_display])
                                .status()
                                {
                                    Ok(status) if status.success() => {}
                                    Ok(status) => tracing::warn!(
                                        ?status,
                                        "could not update desktop DISPLAY environment for XWayland"
                                    ),
                                    Err(error) => tracing::warn!(
                                        ?error,
                                        "could not update desktop DISPLAY environment for XWayland"
                                    ),
                                }
                            }
                            if state.notify_systemd_when_ready {
                                state.notify_systemd_when_ready = false;
                                if let Err(error) = crate::notify_systemd_ready() {
                                    tracing::error!(
                                        ?error,
                                        "could not notify systemd that Pantheon is ready"
                                    );
                                }
                                crate::watchdog::start(state);
                            }
                            if let Some((program, args)) = state.pending_command.take()
                                && let Err(error) =
                                    std::process::Command::new(program).args(args).spawn()
                            {
                                tracing::error!(?error, "could not launch requested client");
                            }
                            tracing::info!(display_number, "XWayland is ready");
                        }
                        Err(error) => {
                            tracing::error!(?error, "could not attach the XWayland window manager")
                        }
                    }
                }
                XWaylandEvent::Error => tracing::error!("XWayland failed to start"),
            }
        })?;
    Ok(())
}

impl XWaylandShellHandler for PantheonCompositor {
    fn xwayland_shell_state(
        &mut self,
    ) -> &mut smithay::wayland::xwayland_shell::XWaylandShellState {
        &mut self.xwayland_shell_state
    }
}

impl XwmHandler for PantheonCompositor {
    fn xwm_state(&mut self, xwm: XwmId) -> &mut X11Wm {
        let wm = self
            .xwm
            .as_mut()
            .expect("XWayland window manager is not ready");
        debug_assert_eq!(wm.id(), xwm);
        wm
    }

    fn new_window(&mut self, _xwm: XwmId, _window: X11Surface) {}

    fn new_override_redirect_window(&mut self, _xwm: XwmId, _window: X11Surface) {}

    fn property_notify(&mut self, _xwm: XwmId, surface: X11Surface, property: WmWindowProperty) {
        // Title, class, pid and hints feed the Gala window snapshot.
        self.note_title_changed();
        match property {
            // The server-side frame shows the title and follows the hints.
            WmWindowProperty::Title
            | WmWindowProperty::NormalHints
            | WmWindowProperty::WindowType => {
                self.request_native_redraw();
                self.request_winit_redraw();
            }
            // A window that starts or stops asking for a frame: keep it in the work area.
            WmWindowProperty::MotifHints => {
                self.reconfigure_managed_windows();
                self.request_native_redraw();
                self.request_winit_redraw();
            }
            _ => {}
        }
        // WM_HINTS urgency is an attention request (see attention.rs).
        if property != WmWindowProperty::Hints {
            return;
        }
        let Some(window) = self.x11_workspace_window(&surface) else {
            return;
        };
        if surface.hints().is_some_and(|hints| hints.urgent) {
            self.request_attention(&window, Reason::X11Urgency);
        } else if !surface.demands_attention() {
            self.clear_attention(&window);
        }
    }

    fn map_window_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        if let Err(error) = surface.set_mapped(true) {
            tracing::warn!(?error, "could not map X11 window");
            return;
        }
        let geometry = surface.last_configure();
        // A framed window is centred with its title bar in the work area.
        let framed = decorations::wants_frame(&surface);
        let location = self
            .space
            .outputs()
            .find_map(|output| {
                let rect = self.space.output_geometry(output)?;
                if framed {
                    let area = self.work_area_for_output(rect);
                    let height = geometry.size.h + TITLE_HEIGHT;
                    return Some(Point::from((
                        area.loc.x + (area.size.w - geometry.size.w).max(0) / 2,
                        area.loc.y + TITLE_HEIGHT + (area.size.h - height).max(0) / 2,
                    )));
                }
                Some(Point::from((
                    rect.loc.x + (rect.size.w - geometry.size.w).max(0) / 2,
                    rect.loc.y + (rect.size.h - geometry.size.h).max(0) / 2,
                )))
            })
            .unwrap_or(Point::from((0, 0)));
        let window = Window::new_x11_window(surface.clone());
        let takes_focus = x11_accepts_focus(&surface);
        self.space
            .map_element(window.clone(), location, takes_focus);
        self.workspace_manager.add_window(window.clone(), location);
        let configured = Rectangle::new(location, geometry.size);
        if let Err(error) = surface.configure(Some(configured)) {
            tracing::warn!(?error, "could not configure mapped X11 window");
        }
        if takes_focus {
            window.set_activated(true);
            if !self.session_locked {
                self.focus_window_keyboard(&window, smithay::utils::SERIAL_COUNTER.next_serial());
            }
        }
    }

    fn mapped_override_redirect_window(&mut self, _xwm: XwmId, surface: X11Surface) {
        // Never activate: that deactivated the focused app on every
        // notification card, tooltip and X11 menu, and set
        // _NET_WM_STATE_FOCUSED on windows that are destroyed moments later
        // (the ChangeProperty BadWindow bursts in the xwm log).
        let location = surface.last_configure().loc;
        self.space
            .map_element(Window::new_x11_window(surface), location, false);
    }

    fn unmapped_window(&mut self, _xwm: XwmId, surface: X11Surface) {
        let window = {
            self.space
                .elements()
                .find(|window| {
                    window
                        .x11_surface()
                        .is_some_and(|candidate| candidate == &surface)
                })
                .cloned()
        }
        .or_else(|| {
            self.workspace_manager
                .windows()
                .into_iter()
                .find(|(window, _, _)| window.x11_surface() == Some(&surface))
                .map(|(window, _, _)| window)
        });
        if let Some(window) = window {
            self.frame_buffers.forget(window.id());
            self.space.unmap_elem(&window);
            if !self
                .x11_minimized_windows
                .contains_key(&surface.window_id())
            {
                self.workspace_manager.remove_window(window.id());
                // A remap creates a new Window, so this record is unreachable.
                self.forget_window_placement(window.id());
            }
        }
        if !surface.is_override_redirect()
            && let Err(error) = surface.set_mapped(false)
        {
            tracing::warn!(?error, "could not unmap X11 window");
        }
        if self.x11_keyboard_focus.as_ref() == Some(&surface) {
            self.set_x11_keyboard_focus(None, smithay::utils::SERIAL_COUNTER.next_serial());
            self.focus_next_window();
        }
    }

    fn destroyed_window(&mut self, _xwm: XwmId, surface: X11Surface) {
        if let Some((window, _)) = self.x11_minimized_windows.remove(&surface.window_id()) {
            self.forget_window_placement(window.id());
        }
        if let Some(window) = self.find_x11_window(&surface) {
            self.forget_window_placement(window.id());
        }
        if let Some(window) = self.x11_workspace_window(&surface) {
            self.attention.clear(window.id());
        }
        let id = self
            .workspace_manager
            .windows()
            .into_iter()
            .find(|(window, _, _)| window.x11_surface() == Some(&surface))
            .map(|(window, _, _)| window.id());
        if let Some(id) = id {
            self.forget_window_placement(id);
            self.workspace_manager.remove_window(id);
        }
    }

    fn maximize_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        self.request_x11_mode(&surface, ModeRequest::Maximize);
    }

    fn unmaximize_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        self.request_x11_mode(&surface, ModeRequest::Unmaximize);
    }

    fn fullscreen_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        self.request_x11_mode(&surface, ModeRequest::Fullscreen);
    }

    fn unfullscreen_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        self.request_x11_mode(&surface, ModeRequest::Unfullscreen);
    }

    fn minimize_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        let Some(window) = self.find_x11_window(&surface) else {
            return;
        };
        let Some(location) = self.space.element_location(&window) else {
            return;
        };
        self.x11_minimized_windows
            .insert(surface.window_id(), (window.clone(), location));
        self.workspace_manager.set_location(window.id(), location);
        window.set_activated(false);
        self.space.unmap_elem(&window);
        if let Err(error) = surface.set_mapped(false) {
            tracing::warn!(?error, "could not minimize X11 window");
        }
        if self.x11_keyboard_focus.as_ref() == Some(&surface) {
            self.set_x11_keyboard_focus(None, smithay::utils::SERIAL_COUNTER.next_serial());
            self.focus_next_window();
        }
    }

    fn unminimize_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        let Some((window, location)) = self.x11_minimized_windows.remove(&surface.window_id())
        else {
            return;
        };
        if let Err(error) = surface.set_mapped(true) {
            tracing::warn!(?error, "could not restore minimized X11 window");
            self.x11_minimized_windows
                .insert(surface.window_id(), (window, location));
            return;
        }
        self.space.map_element(window.clone(), location, true);
        window.set_activated(true);
        self.focus_window_keyboard(&window, smithay::utils::SERIAL_COUNTER.next_serial());
    }

    fn configure_request(
        &mut self,
        _xwm: XwmId,
        surface: X11Surface,
        x: Option<i32>,
        y: Option<i32>,
        width: Option<u32>,
        height: Option<u32>,
        _reorder: Option<Reorder>,
    ) {
        // S7: a snapped, maximized or fullscreen X11 window that resizes
        // itself (Wine, Java, Steam) is told its managed rect again.
        if let Some(window) = self.find_x11_window(&surface)
            && !self.placement_of(&window).is_floating()
        {
            self.apply_placement(&window);
            return;
        }
        let mut geometry = surface.last_configure();
        if let Some(x) = x {
            geometry.loc.x = x;
        }
        if let Some(y) = y {
            geometry.loc.y = y;
        }
        if let Some(width) = width {
            geometry.size.w = width as i32;
        }
        if let Some(height) = height {
            geometry.size.h = height as i32;
        }
        if let Err(error) = surface.configure(Some(geometry)) {
            tracing::warn!(?error, "could not honor X11 configure request");
        }
    }

    fn configure_notify(
        &mut self,
        _xwm: XwmId,
        surface: X11Surface,
        geometry: Rectangle<i32, Logical>,
        _above: Option<smithay::xwayland::xwm::X11Window>,
    ) {
        let window = {
            self.space
                .elements()
                .find(|window| {
                    window
                        .x11_surface()
                        .is_some_and(|candidate| candidate == &surface)
                })
                .cloned()
        };
        if let Some(window) = window {
            self.place_window(&window, geometry.loc);
        }
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    fn resize_request(&mut self, _xwm: XwmId, window: X11Surface, _button: u32, edge: ResizeEdge) {
        self.begin_x11_resize(&window, edge);
    }

    fn move_request(&mut self, _xwm: XwmId, window: X11Surface, _button: u32) {
        self.begin_x11_move(&window);
    }

    fn allow_selection_access(&mut self, xwm: XwmId, _selection: SelectionTarget) -> bool {
        self.x11_keyboard_focus
            .as_ref()
            .is_some_and(|surface| surface.xwm_id() == Some(xwm))
    }

    fn send_selection(
        &mut self,
        _xwm: XwmId,
        selection: SelectionTarget,
        mime_type: String,
        fd: std::os::fd::OwnedFd,
    ) {
        match selection {
            SelectionTarget::Clipboard => {
                if let Err(error) = request_data_device_client_selection(&self.seat, mime_type, fd)
                {
                    tracing::warn!(?error, "could not transfer Wayland clipboard to XWayland");
                }
            }
            SelectionTarget::Primary => {
                if let Err(error) = request_primary_client_selection(&self.seat, mime_type, fd) {
                    tracing::warn!(
                        ?error,
                        "could not transfer Wayland PRIMARY selection to XWayland"
                    );
                }
            }
        }
    }

    fn new_selection(&mut self, _xwm: XwmId, selection: SelectionTarget, mime_types: Vec<String>) {
        if selection == SelectionTarget::Clipboard {
            set_data_device_selection(&self.display_handle, &self.seat, mime_types, ());
        } else {
            set_primary_selection(&self.display_handle, &self.seat, mime_types, ());
        }
    }

    fn cleared_selection(&mut self, _xwm: XwmId, selection: SelectionTarget) {
        if selection == SelectionTarget::Clipboard
            && current_data_device_selection_userdata(&self.seat).is_some()
        {
            clear_data_device_selection(&self.display_handle, &self.seat);
        } else if selection == SelectionTarget::Primary
            && current_primary_selection_userdata(&self.seat).is_some()
        {
            clear_primary_selection(&self.display_handle, &self.seat);
        }
    }

    fn active_window_request(
        &mut self,
        _xwm: XwmId,
        surface: X11Surface,
        _timestamp: u32,
        _currently_active_window: Option<X11Surface>,
    ) {
        if self.session_locked {
            return;
        }
        let Some(window) = self.find_x11_window(&surface) else {
            return;
        };
        self.raise_window(&window, true);
        self.focus_window_keyboard(&window, smithay::utils::SERIAL_COUNTER.next_serial());
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    fn demands_attention_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        if let Some(window) = self.x11_workspace_window(&surface) {
            self.request_attention(&window, Reason::X11Request);
        }
    }

    fn undemands_attention_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        if let Some(window) = self.x11_workspace_window(&surface) {
            self.clear_attention(&window);
        }
    }
}

impl PantheonCompositor {
    /// The managed window for `surface`, mapped, minimized or on another workspace.
    fn x11_workspace_window(&self, surface: &X11Surface) -> Option<Window> {
        self.find_x11_window(surface).or_else(|| {
            self.workspace_manager
                .windows()
                .into_iter()
                .find(|(window, _, _)| window.x11_surface() == Some(surface))
                .map(|(window, _, _)| window)
        })
    }

    fn find_x11_window(&self, surface: &X11Surface) -> Option<Window> {
        self.space
            .elements()
            .find(|window| {
                window
                    .x11_surface()
                    .is_some_and(|candidate| candidate == surface)
            })
            .cloned()
    }

    fn request_x11_mode(&mut self, surface: &X11Surface, request: ModeRequest) {
        if let Some(window) = self.find_x11_window(surface) {
            self.set_window_mode(&window, request);
        }
    }

    fn begin_x11_move(&mut self, surface: &X11Surface) {
        let Some(pointer) = self.seat.get_pointer() else {
            return;
        };
        let Some(start_data) = pointer.grab_start_data() else {
            return;
        };
        let Some(window) = self.find_x11_window(surface) else {
            return;
        };
        self.start_move_grab(
            &pointer,
            start_data,
            window,
            smithay::utils::SERIAL_COUNTER.next_serial(),
        );
    }

    fn begin_x11_resize(&mut self, surface: &X11Surface, edge: ResizeEdge) {
        let Some(pointer) = self.seat.get_pointer() else {
            return;
        };
        let Some(start_data) = pointer.grab_start_data() else {
            return;
        };
        let Some(window) = self.find_x11_window(surface) else {
            return;
        };
        let edges = match edge {
            ResizeEdge::Top => PantheonResizeEdge::TOP,
            ResizeEdge::Bottom => PantheonResizeEdge::BOTTOM,
            ResizeEdge::Left => PantheonResizeEdge::LEFT,
            ResizeEdge::TopLeft => PantheonResizeEdge::TOP_LEFT,
            ResizeEdge::BottomLeft => PantheonResizeEdge::BOTTOM_LEFT,
            ResizeEdge::Right => PantheonResizeEdge::RIGHT,
            ResizeEdge::TopRight => PantheonResizeEdge::TOP_RIGHT,
            ResizeEdge::BottomRight => PantheonResizeEdge::BOTTOM_RIGHT,
        };
        self.start_x11_resize_grab(
            &pointer,
            start_data,
            window,
            edges,
            smithay::utils::SERIAL_COUNTER.next_serial(),
        );
    }

    /// Resize an X11 window from `edges`, for `_NET_WM_MOVERESIZE` and the frame.
    fn start_x11_resize_grab(
        &mut self,
        pointer: &PointerHandle<Self>,
        start_data: PointerGrabStartData<Self>,
        window: Window,
        edges: PantheonResizeEdge,
        serial: Serial,
    ) {
        if self.placement_of(&window).is_fullscreen() {
            return;
        }
        // The shared edge of a snap group resizes both members.
        if self.try_start_split_resize(pointer, start_data.clone(), &window, edges, serial) {
            return;
        }
        self.float_in_place(&window);
        let Some(location) = self.space.element_location(&window) else {
            return;
        };
        let rect = Rectangle::new(location, window.geometry().size);
        let grab = ResizeSurfaceGrab::start(start_data, window, edges, rect);
        pointer.set_grab(self, grab, serial, Focus::Clear);
    }

    pub(crate) fn set_x11_keyboard_focus(
        &mut self,
        focus: Option<X11Surface>,
        serial: smithay::utils::Serial,
    ) {
        if self.x11_keyboard_focus == focus {
            return;
        }
        if let Some(surface) = focus.as_ref() {
            // An xdg popup grab would otherwise keep the keys (see end_popup_grab_unless).
            self.end_popup_grab_unless(None);
            if let Some(window) = self.x11_workspace_window(surface) {
                self.clear_attention(&window);
            }
        }
        let seat = self.seat.clone();
        if let Some(previous) = self.x11_keyboard_focus.take() {
            <X11Surface as KeyboardTarget<PantheonCompositor>>::leave(
                &previous, &seat, self, serial,
            );
        }
        self.x11_keyboard_focus = focus.clone();
        if let Some(focus) = focus {
            if let Some(keyboard) = self.seat.get_keyboard() {
                keyboard.set_focus(self, None, serial);
            }
            <X11Surface as KeyboardTarget<PantheonCompositor>>::enter(
                &focus,
                &seat,
                self,
                Vec::new(),
                serial,
            );
        }
    }

    pub(crate) fn focus_window_keyboard(
        &mut self,
        window: &Window,
        serial: smithay::utils::Serial,
    ) {
        if !window_accepts_focus(window)
            || crate::overlays::is_no_focus_overlay(self.window_app_id(window).as_deref())
        {
            return;
        }
        let keep = window
            .toplevel()
            .map(|toplevel| toplevel.wl_surface().clone());
        self.end_popup_grab_unless(keep.as_ref());
        self.clear_attention(window);
        // Send the activated state now: D-Bus focus, workspace switches and
        // panel/polkit focus have no later configure, so the app kept drawing
        // itself inactive while it had the keyboard.
        for candidate in self.space.elements() {
            candidate.set_activated(candidate == window);
            if let Some(toplevel) = candidate.toplevel() {
                toplevel.send_pending_configure();
            }
        }
        if let Some(surface) = window.x11_surface() {
            self.set_x11_keyboard_focus(Some(surface.clone()), serial);
        } else if let Some(toplevel) = window.toplevel() {
            self.set_x11_keyboard_focus(None, serial);
            if let Some(keyboard) = self.seat.get_keyboard() {
                keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
            }
        }
    }
}

/// Server-side frames for X11 windows (see `decorations.rs`).
impl PantheonCompositor {
    pub(crate) fn refresh_frame_style(&mut self) {
        let style = decorations::FrameStyle::load();
        if style != self.frame_style {
            self.frame_style = style;
            self.frame_buffers.clear();
            self.request_native_redraw();
            self.request_winit_redraw();
        }
    }

    /// The frame of `window` whose own geometry is `content` (space coordinates).
    pub(crate) fn frame_spec(
        &self,
        window: &Window,
        content: Rectangle<i32, Logical>,
    ) -> Option<FrameSpec> {
        let surface = window.x11_surface()?;
        if !decorations::wants_frame(surface) || surface.is_fullscreen() {
            return None;
        }
        let placement = self.placement_of(window);
        if placement.is_fullscreen() {
            return None;
        }
        let functions = surface.motif_hints().functions;
        let allows = |function| decorations::motif_allows(functions, function);
        use smithay::xwayland::xwm::MwmFunctionsHint as F;
        let (min, max) = Self::size_hints(window);
        let fixed = max.w > 0 && max.h > 0 && min == max;
        let resizable = !fixed && allows(F::RESIZE);
        Some(FrameSpec {
            content,
            resizable: resizable && !placement.is_maximized(),
            can_close: allows(F::CLOSE),
            can_minimize: allows(F::MINIMIZE) && surface.is_transient_for().is_none(),
            can_maximize: resizable && allows(F::MAXIMIZE),
            maximized: placement.is_maximized(),
        })
    }

    /// The frame of a mapped window, if it has one.
    pub(crate) fn window_frame(&self, window: &Window) -> Option<FrameSpec> {
        let location = self.space.element_location(window)?;
        self.frame_spec(window, Rectangle::new(location, window.geometry().size))
    }

    /// Height of the window's server-side title bar, 0 without one.
    pub(crate) fn frame_top(&self, window: &Window) -> i32 {
        self.window_frame(window).map_or(0, |_| TITLE_HEIGHT)
    }

    /// The frame part under `pos`, unless a popup or a window above covers it.
    pub(crate) fn frame_under(&self, pos: Point<f64, Logical>) -> Option<(Window, FrameHit)> {
        if self.session_locked || self.overview.is_some() || self.gesture_animation.is_some() {
            return None;
        }
        if crate::popup_stack::popup_under(&self.space, pos).is_some() {
            return None;
        }
        for window in self.space.elements().rev() {
            let Some(location) = self.space.element_location(window) else {
                continue;
            };
            if let Some(spec) = self.window_frame(window)
                && let Some(hit) = spec.hit(&self.frame_style.layout, pos)
            {
                return Some((window.clone(), hit));
            }
            let local = pos - (location - window.geometry().loc).to_f64();
            if window.bbox().to_f64().contains(local) && window.is_in_input_region(&local) {
                return None;
            }
        }
        None
    }

    /// The title bar of `window` as a render element for `output`.
    pub(crate) fn frame_render_elements<R>(
        &self,
        renderer: &mut R,
        window: &Window,
        content: Rectangle<i32, Logical>,
        output: &Output,
    ) -> Option<decorations::FrameElements<R>>
    where
        R: ImportMem,
        R::TextureId: Send + Clone + 'static,
    {
        let spec = self.frame_spec(window, content)?;
        let surface = window.x11_surface()?;
        let outer = spec.outer();
        let title = spec.title_bar();
        let Some(geometry) = self.space.output_geometry(output) else {
            return Some((outer, Vec::new()));
        };
        if !title.overlaps(geometry) {
            return Some((outer, Vec::new()));
        }
        let scale = output.current_scale().fractional_scale();
        let key = PaintKey {
            width: content.size.w,
            scale: scale.ceil().max(1.0) as i32,
            title: surface.title(),
            active: surface.is_activated(),
            hovered: self
                .frame_hover
                .filter(|(id, _)| *id == window.id())
                .map(|(_, kind)| kind),
            buttons: spec.buttons(&self.frame_style.layout),
            maximized: spec.maximized,
            style: self.frame_style.clone(),
        };
        let Some(buffer) = self.frame_buffers.get(window.id(), key) else {
            return Some((outer, Vec::new()));
        };
        let location = (title.loc - geometry.loc).to_f64().to_physical(scale);
        let element = MemoryRenderBufferRenderElement::from_buffer(
            renderer,
            location,
            &buffer,
            None,
            None,
            Some(title.size),
            Kind::Unspecified,
        )
        .ok();
        Some((outer, element.into_iter().collect()))
    }

    /// Pointer motion with no grab: frame cursor and title-bar button hover.
    pub(crate) fn update_frame_pointer(&mut self, pos: Point<f64, Logical>) {
        let hit = self.frame_under(pos);
        let cursor = hit.as_ref().map(|(_, hit)| match hit {
            FrameHit::Edge(edges) => decorations::edge_cursor(*edges),
            FrameHit::Title | FrameHit::Button(_) => CursorIcon::Default,
        });
        let hover = hit.and_then(|(window, hit)| match hit {
            FrameHit::Button(kind) => Some((window.id(), kind)),
            _ => None,
        });
        if cursor != self.frame_cursor || hover != self.frame_hover {
            self.frame_cursor = cursor;
            self.frame_hover = hover;
            self.request_native_redraw();
            self.request_winit_redraw();
        }
    }

    /// A button press on a window frame: raise and focus, then drag, resize or
    /// arm a title-bar button. Returns false when `pos` is not on a frame.
    pub(crate) fn handle_frame_press(
        &mut self,
        pointer: &PointerHandle<Self>,
        pos: Point<f64, Logical>,
        button: u32,
        serial: Serial,
    ) -> bool {
        let Some((window, hit)) = self.frame_under(pos) else {
            return false;
        };
        self.raise_window(&window, true);
        self.focus_window_keyboard(&window, serial);
        if button != BTN_LEFT {
            return true;
        }
        let start_data = PointerGrabStartData {
            focus: None,
            button,
            location: pos,
        };
        match hit {
            FrameHit::Button(kind) => {
                self.frame_press = Some((window.id(), kind));
            }
            FrameHit::Title => {
                let now = std::time::Instant::now();
                let double = self
                    .last_title_click
                    .is_some_and(|(id, at)| id == window.id() && now - at < DOUBLE_CLICK);
                if double {
                    self.last_title_click = None;
                    self.toggle_frame_maximize(&window);
                } else {
                    self.last_title_click = Some((window.id(), now));
                    self.start_move_grab(pointer, start_data, window, serial);
                }
            }
            FrameHit::Edge(edges) => {
                self.start_x11_resize_grab(pointer, start_data, window, edges, serial);
            }
        }
        true
    }

    /// Button release: a title-bar button acts when released over itself.
    pub(crate) fn handle_frame_release(&mut self, pos: Point<f64, Logical>) {
        let Some((id, kind)) = self.frame_press.take() else {
            return;
        };
        let Some((window, FrameHit::Button(over))) = self.frame_under(pos) else {
            return;
        };
        if window.id() != id || over != kind {
            return;
        }
        let Some(surface) = window.x11_surface().cloned() else {
            return;
        };
        match kind {
            ButtonKind::Close => {
                // WM_DELETE_WINDOW when the client supports it, else XKillClient-like destroy.
                if let Err(error) = surface.close() {
                    tracing::warn!(?error, "could not close X11 window");
                }
            }
            ButtonKind::Minimize => {
                if let Some(xwm) = surface.xwm_id() {
                    XwmHandler::minimize_request(self, xwm, surface);
                }
                self.frame_hover = None;
            }
            ButtonKind::Maximize => self.toggle_frame_maximize(&window),
        }
        self.request_native_redraw();
        self.request_winit_redraw();
    }

    fn toggle_frame_maximize(&mut self, window: &Window) {
        let Some(spec) = self.window_frame(window) else {
            return;
        };
        if spec.maximized {
            self.set_window_mode(window, ModeRequest::Unmaximize);
        } else if spec.can_maximize {
            self.set_window_mode(window, ModeRequest::Maximize);
        }
    }
}
