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
        xwm::{Reorder, ResizeEdge, XwmId},
    },
};

use crate::grabs::{
    MoveSurfaceGrab, ResizeSurfaceGrab, resize_grab::ResizeEdge as PantheonResizeEdge,
};
use crate::{PantheonCompositor, state::ManagedWindow};

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

    fn map_window_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        if let Err(error) = surface.set_mapped(true) {
            tracing::warn!(?error, "could not map X11 window");
            return;
        }
        let geometry = surface.last_configure();
        let location = self
            .space
            .outputs()
            .find_map(|output| {
                let rect = self.space.output_geometry(output)?;
                Some(Point::from((
                    rect.loc.x + (rect.size.w - geometry.size.w).max(0) / 2,
                    rect.loc.y + (rect.size.h - geometry.size.h).max(0) / 2,
                )))
            })
            .unwrap_or(Point::from((0, 0)));
        let window = Window::new_x11_window(surface.clone());
        self.space.map_element(window.clone(), location, true);
        self.workspace_manager.add_window(window.clone(), location);
        let configured = Rectangle::new(location, geometry.size);
        if let Err(error) = surface.configure(Some(configured)) {
            tracing::warn!(?error, "could not configure mapped X11 window");
        }
        window.set_activated(true);
        if !self.session_locked {
            self.focus_window_keyboard(&window, smithay::utils::SERIAL_COUNTER.next_serial());
        }
    }

    fn mapped_override_redirect_window(&mut self, _xwm: XwmId, surface: X11Surface) {
        let location = surface.last_configure().loc;
        self.space
            .map_element(Window::new_x11_window(surface), location, true);
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
            self.space.unmap_elem(&window);
            if !self
                .x11_minimized_windows
                .contains_key(&surface.window_id())
            {
                self.workspace_manager.remove_window(window.id());
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
        if let Some(wl_surface) = surface.wl_surface() {
            self.clear_tiling_for_surface(&wl_surface);
        }
        self.x11_managed_windows.remove(&surface.window_id());
        self.x11_minimized_windows.remove(&surface.window_id());
        let id = self
            .workspace_manager
            .windows()
            .into_iter()
            .find(|(window, _, _)| window.x11_surface() == Some(&surface))
            .map(|(window, _, _)| window.id());
        if let Some(id) = id {
            self.workspace_manager.remove_window(id);
        }
    }

    fn maximize_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        self.configure_x11_window_mode(&surface, true, false);
    }

    fn unmaximize_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        self.configure_x11_window_mode(&surface, false, false);
    }

    fn fullscreen_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        self.configure_x11_window_mode(&surface, false, true);
    }

    fn unfullscreen_request(&mut self, _xwm: XwmId, surface: X11Surface) {
        self.configure_x11_window_mode(&surface, false, false);
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
}

impl PantheonCompositor {
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

    pub(crate) fn configure_x11_window_mode(
        &mut self,
        surface: &X11Surface,
        maximized: bool,
        fullscreen: bool,
    ) {
        let Some(window) = self.find_x11_window(surface) else {
            return;
        };
        if let Some(wl_surface) = surface.wl_surface() {
            self.clear_tiling_for_surface(&wl_surface);
        }
        let id = surface.window_id();
        let restore = *self
            .x11_managed_windows
            .entry(id)
            .or_insert_with(|| ManagedWindow {
                restore_location: self.space.element_location(&window).unwrap_or_default(),
                restore_size: window.geometry().size,
                maximized: false,
                fullscreen: false,
            });
        if let Some(managed) = self.x11_managed_windows.get_mut(&id) {
            managed.maximized = maximized;
            managed.fullscreen = fullscreen;
        }
        let output = self
            .space
            .outputs_for_element(&window)
            .first()
            .cloned()
            .or_else(|| self.primary_output());
        let Some(output_geometry) = output.and_then(|output| self.space.output_geometry(&output))
        else {
            return;
        };
        let target = if fullscreen {
            output_geometry
        } else if maximized {
            self.work_area_for_output(output_geometry)
        } else {
            smithay::utils::Rectangle::new(restore.restore_location, restore.restore_size)
        };
        if let Err(error) = surface.set_maximized(maximized) {
            tracing::warn!(?error, "could not update X11 maximized state");
        }
        if let Err(error) = surface.set_fullscreen(fullscreen) {
            tracing::warn!(?error, "could not update X11 fullscreen state");
        }
        if let Err(error) = surface.configure(Some(target)) {
            tracing::warn!(?error, "could not configure X11 window state");
        }
        self.place_window(&window, target.loc);
        if !maximized && !fullscreen {
            self.x11_managed_windows.remove(&id);
        }
        self.refresh_panel_visibility();
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
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
        let Some(initial_window_location) = self.space.element_location(&window) else {
            return;
        };
        if let Some(wl_surface) = surface.wl_surface() {
            self.clear_tiling_for_surface(&wl_surface);
        }
        self.move_grab_active = true;
        self.corner_snap_cancelled = false;
        self.corner_snap_preview = None;
        let grab = MoveSurfaceGrab {
            start_data,
            window,
            initial_window_location,
        };
        pointer.set_grab(
            self,
            grab,
            smithay::utils::SERIAL_COUNTER.next_serial(),
            Focus::Clear,
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
        let Some(location) = self.space.element_location(&window) else {
            return;
        };
        if let Some(wl_surface) = surface.wl_surface() {
            self.clear_tiling_for_surface(&wl_surface);
        }
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
        let rect = Rectangle::new(location, window.geometry().size);
        let grab = ResizeSurfaceGrab::start(start_data, window, edges, rect);
        pointer.set_grab(
            self,
            grab,
            smithay::utils::SERIAL_COUNTER.next_serial(),
            Focus::Clear,
        );
    }

    pub(crate) fn set_x11_keyboard_focus(
        &mut self,
        focus: Option<X11Surface>,
        serial: smithay::utils::Serial,
    ) {
        if self.x11_keyboard_focus == focus {
            return;
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
        for candidate in self.space.elements() {
            candidate.set_activated(candidate == window);
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
