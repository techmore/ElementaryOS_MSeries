use smithay::{
    desktop::{
        PopupKeyboardGrab, PopupKind, PopupPointerGrab, PopupUngrabStrategy, Window,
        find_popup_root_surface, get_popup_toplevel_coords,
    },
    input::{
        Seat,
        pointer::{Focus, GrabStartData as PointerGrabStartData},
    },
    reexports::{
        wayland_protocols::xdg::shell::server::xdg_toplevel,
        wayland_server::{
            Resource,
            protocol::{wl_seat, wl_surface::WlSurface},
        },
    },
    utils::{Rectangle, Serial},
    wayland::{
        compositor::with_states,
        shell::xdg::{
            PopupSurface, PositionerState, ToplevelSurface, XdgShellHandler, XdgShellState,
            XdgToplevelSurfaceData,
        },
    },
};

use crate::{
    PantheonCompositor,
    grabs::{MoveSurfaceGrab, ResizeSurfaceGrab},
};

impl XdgShellHandler for PantheonCompositor {
    fn xdg_shell_state(&mut self) -> &mut XdgShellState {
        &mut self.xdg_shell_state
    }

    fn new_toplevel(&mut self, surface: ToplevelSurface) {
        let window = Window::new_wayland_window(surface);
        self.space.map_element(window, (0, 0), false);
    }

    fn new_popup(&mut self, surface: PopupSurface, _positioner: PositionerState) {
        self.unconstrain_popup(&surface);
        let _ = self.popups.track_popup(PopupKind::Xdg(surface));
    }

    fn reposition_request(
        &mut self,
        surface: PopupSurface,
        positioner: PositionerState,
        token: u32,
    ) {
        surface.with_pending_state(|state| {
            let geometry = positioner.get_geometry();
            state.geometry = geometry;
            state.positioner = positioner;
        });
        self.unconstrain_popup(&surface);
        surface.send_repositioned(token);
    }

    fn move_request(&mut self, surface: ToplevelSurface, seat: wl_seat::WlSeat, serial: Serial) {
        let seat = Seat::from_resource(&seat).unwrap();

        let wl_surface = surface.wl_surface();

        if let Some(start_data) = check_grab(&seat, wl_surface, serial) {
            self.clear_tiling_for_surface(wl_surface);
            self.move_grab_active = true;
            self.corner_snap_cancelled = false;
            self.corner_snap_preview = None;
            let pointer = seat.get_pointer().unwrap();

            let window = self
                .space
                .elements()
                .find(|w| w.toplevel().unwrap().wl_surface() == wl_surface)
                .unwrap()
                .clone();
            let initial_window_location = self.space.element_location(&window).unwrap();

            let grab = MoveSurfaceGrab {
                start_data,
                window,
                initial_window_location,
            };

            pointer.set_grab(self, grab, serial, Focus::Clear);
        }
    }

    fn resize_request(
        &mut self,
        surface: ToplevelSurface,
        seat: wl_seat::WlSeat,
        serial: Serial,
        edges: xdg_toplevel::ResizeEdge,
    ) {
        let seat = Seat::from_resource(&seat).unwrap();

        let wl_surface = surface.wl_surface();

        if let Some(start_data) = check_grab(&seat, wl_surface, serial) {
            self.clear_tiling_for_surface(wl_surface);
            let pointer = seat.get_pointer().unwrap();

            let window = self
                .space
                .elements()
                .find(|w| w.toplevel().unwrap().wl_surface() == wl_surface)
                .unwrap()
                .clone();
            let initial_window_location = self.space.element_location(&window).unwrap();
            let initial_window_size = window.geometry().size;

            surface.with_pending_state(|state| {
                state.states.set(xdg_toplevel::State::Resizing);
            });

            surface.send_pending_configure();

            let grab = ResizeSurfaceGrab::start(
                start_data,
                window,
                edges.into(),
                Rectangle::new(initial_window_location, initial_window_size),
            );

            pointer.set_grab(self, grab, serial, Focus::Clear);
        }
    }

    fn maximize_request(&mut self, surface: ToplevelSurface) {
        self.configure_window_mode(surface, true, false);
    }

    fn unmaximize_request(&mut self, surface: ToplevelSurface) {
        self.configure_window_mode(surface, false, false);
    }

    fn fullscreen_request(
        &mut self,
        surface: ToplevelSurface,
        _output: Option<smithay::reexports::wayland_server::protocol::wl_output::WlOutput>,
    ) {
        self.configure_window_mode(surface, false, true);
    }

    fn unfullscreen_request(&mut self, surface: ToplevelSurface) {
        self.configure_window_mode(surface, false, false);
    }

    fn minimize_request(&mut self, surface: ToplevelSurface) {
        if self.session_locked {
            return;
        }
        let wl_surface = surface.wl_surface();
        if self.is_panel_surface(wl_surface) {
            return;
        }
        let Some(window) = self
            .space
            .elements()
            .find(|window| {
                window
                    .toplevel()
                    .is_some_and(|top| top.wl_surface() == wl_surface)
            })
            .cloned()
        else {
            return;
        };
        let Some(location) = self.space.element_location(&window) else {
            return;
        };
        let id = wl_surface.id();
        let was_focused = self
            .seat
            .get_keyboard()
            .and_then(|keyboard| keyboard.current_focus())
            .is_some_and(|focused| surface_has_root(&focused, wl_surface));
        self.space.unmap_elem(&window);
        self.minimized_windows.insert(id, (window, location));
        if was_focused {
            self.focus_next_window();
        }
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    fn toplevel_destroyed(&mut self, surface: ToplevelSurface) {
        let wl_surface = surface.wl_surface();
        let id = wl_surface.id();
        let was_focused = self
            .seat
            .get_keyboard()
            .and_then(|keyboard| keyboard.current_focus())
            .is_some_and(|focused| surface_has_root(&focused, wl_surface));
        self.initially_positioned.remove(&id);
        self.managed_windows.remove(&id);
        self.tiled_windows.remove(&id);
        self.minimized_windows.remove(&id);

        let window = self
            .space
            .elements()
            .find(|window| {
                window
                    .toplevel()
                    .is_some_and(|top| top.wl_surface() == wl_surface)
            })
            .cloned();
        if let Some(window) = window {
            self.space.unmap_elem(&window);
        }

        if was_focused {
            self.focus_next_window();
        }
    }

    fn grab(&mut self, surface: PopupSurface, seat_resource: wl_seat::WlSeat, serial: Serial) {
        let seat = Seat::from_resource(&seat_resource).unwrap();
        let kind = PopupKind::Xdg(surface);
        let Ok(root_surface) = find_popup_root_surface(&kind) else {
            return;
        };
        let Some(root) = self.space.elements().find_map(|window| {
            window
                .toplevel()
                .filter(|toplevel| toplevel.wl_surface() == &root_surface)
                .map(|toplevel| toplevel.wl_surface().clone())
        }) else {
            return;
        };

        let Ok(mut grab) = self.popups.grab_popup(root, kind, &seat, serial) else {
            return;
        };

        if let Some(keyboard) = seat.get_keyboard() {
            if keyboard.is_grabbed()
                && !(keyboard.has_grab(serial)
                    || keyboard.has_grab(grab.previous_serial().unwrap_or(serial)))
            {
                grab.ungrab(PopupUngrabStrategy::All);
                return;
            }
            keyboard.set_focus(self, grab.current_grab(), serial);
            keyboard.set_grab(self, PopupKeyboardGrab::new(&grab), serial);
        }

        if let Some(pointer) = seat.get_pointer() {
            if pointer.is_grabbed()
                && !(pointer.has_grab(serial)
                    || pointer.has_grab(grab.previous_serial().unwrap_or_else(|| grab.serial())))
            {
                grab.ungrab(PopupUngrabStrategy::All);
                return;
            }
            pointer.set_grab(self, PopupPointerGrab::new(&grab), serial, Focus::Keep);
        }
    }
}

impl PantheonCompositor {
    pub(crate) fn focus_next_window(&mut self) {
        if self.session_locked {
            return;
        }
        let next_window = self
            .space
            .elements()
            .rev()
            .find(|window| {
                window
                    .toplevel()
                    .is_some_and(|top| !self.is_panel_surface(top.wl_surface()))
            })
            .cloned();
        if let Some(window) = next_window {
            self.space.raise_element(&window, true);
            if let Some(surface) = window.toplevel().map(|top| top.wl_surface().clone()) {
                let serial = smithay::utils::SERIAL_COUNTER.next_serial();
                self.seat
                    .get_keyboard()
                    .unwrap()
                    .set_focus(self, Some(surface), serial);
                self.space.elements().for_each(|window| {
                    if let Some(toplevel) = window.toplevel() {
                        toplevel.send_pending_configure();
                    }
                });
            }
        } else {
            let serial = smithay::utils::SERIAL_COUNTER.next_serial();
            self.seat
                .get_keyboard()
                .unwrap()
                .set_focus(self, Option::<WlSurface>::None, serial);
        }
    }
}

fn check_grab(
    seat: &Seat<PantheonCompositor>,
    surface: &WlSurface,
    serial: Serial,
) -> Option<PointerGrabStartData<PantheonCompositor>> {
    let pointer = seat.get_pointer()?;

    // Check that this surface has a click grab.
    if !pointer.has_grab(serial) {
        return None;
    }

    let start_data = pointer.grab_start_data()?;

    let (focus, _) = start_data.focus.as_ref()?;
    // If the focus was for a different surface, ignore the request.
    if !focus.id().same_client_as(&surface.id()) {
        return None;
    }

    Some(start_data)
}

fn surface_has_root(surface: &WlSurface, expected_root: &WlSurface) -> bool {
    let mut root = surface.clone();
    while let Some(parent) = smithay::wayland::compositor::get_parent(&root) {
        root = parent;
    }
    root == *expected_root
}

/// Should be called on `WlSurface::commit` after `Window::on_commit`.
pub fn handle_commit(state: &mut PantheonCompositor, surface: &WlSurface) {
    // Handle toplevel commits.
    let window = state
        .space
        .elements()
        .find(|w| w.toplevel().unwrap().wl_surface() == surface)
        .cloned();
    if let Some(window) = window {
        let initial_configure_sent = with_states(surface, |states| {
            states
                .data_map
                .get::<XdgToplevelSurfaceData>()
                .unwrap()
                .lock()
                .unwrap()
                .initial_configure_sent
        });

        if !initial_configure_sent {
            window.toplevel().unwrap().send_configure();
        }

        // The first committed buffer makes the requested window size known.
        // Center new app windows on the first available output and offset later
        // launches so they remain visible and easy to find.
        let surface_id = surface.id();
        let size = window.geometry().size;
        if size.w > 0 && size.h > 0 && !state.initially_positioned.contains(&surface_id) {
            let cascade = (state.space.elements().count().saturating_sub(1) % 10) as i32 * 24;
            let placement = state
                .space
                .outputs()
                .next()
                .and_then(|output| state.space.output_geometry(output))
                .map(|output_geometry| {
                    let max_x = output_geometry.loc.x + (output_geometry.size.w - size.w).max(0);
                    let max_y = output_geometry.loc.y + (output_geometry.size.h - size.h).max(0);
                    let x =
                        (output_geometry.loc.x + (output_geometry.size.w - size.w) / 2 + cascade)
                            .clamp(output_geometry.loc.x, max_x);
                    let y =
                        (output_geometry.loc.y + (output_geometry.size.h - size.h) / 2 + cascade)
                            .clamp(output_geometry.loc.y, max_y);
                    (x, y)
                });

            if let Some(location) = placement {
                state.space.map_element(window.clone(), location, true);
                state.initially_positioned.insert(surface_id);

                let serial = smithay::utils::SERIAL_COUNTER.next_serial();
                state
                    .seat
                    .get_keyboard()
                    .unwrap()
                    .set_focus(state, Some(surface.clone()), serial);
                state.space.elements().for_each(|window| {
                    if let Some(toplevel) = window.toplevel() {
                        toplevel.send_pending_configure();
                    }
                });
            }
        }
    }

    // Handle popup commits.
    state.popups.commit(surface);
    if let Some(popup) = state.popups.find_popup(surface) {
        match popup {
            PopupKind::Xdg(ref xdg) => {
                if !xdg.is_initial_configure_sent() {
                    // NOTE: This should never fail as the initial configure is always
                    // allowed.
                    xdg.send_configure().expect("initial configure failed");
                }
            }
            PopupKind::InputMethod(ref _input_method) => {}
        }
    }
}

impl PantheonCompositor {
    fn unconstrain_popup(&self, popup: &PopupSurface) {
        let Ok(root) = find_popup_root_surface(&PopupKind::Xdg(popup.clone())) else {
            return;
        };
        let Some(window) = self
            .space
            .elements()
            .find(|w| w.toplevel().unwrap().wl_surface() == &root)
        else {
            return;
        };

        let output = self.space.outputs().next().unwrap();
        let output_geo = self.space.output_geometry(output).unwrap();
        let window_geo = self.space.element_geometry(window).unwrap();

        // The target geometry for the positioner should be relative to its parent's geometry, so
        // we will compute that here.
        let mut target = output_geo;
        target.loc -= get_popup_toplevel_coords(&PopupKind::Xdg(popup.clone()));
        target.loc -= window_geo.loc;

        popup.with_pending_state(|state| {
            state.geometry = state.positioner.get_unconstrained_geometry(target);
        });
    }
}
