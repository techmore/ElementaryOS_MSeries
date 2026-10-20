use std::collections::HashMap;

use smithay::{
    desktop::Window,
    reexports::wayland_server::{
        Client, DataInit, Dispatch, DisplayHandle, GlobalDispatch, New, Resource,
        backend::GlobalId, protocol::wl_surface::WlSurface,
    },
    utils::{Logical, Point, Rectangle, SERIAL_COUNTER, Size},
    wayland::shell::xdg::ToplevelSurface,
};

use smithay::reexports::wayland_protocols::xdg::shell::server::xdg_toplevel;

use crate::{
    PantheonCompositor, protocols::pantheon_desktop_shell_v1::server as protocol,
    state::ManagedWindow,
};

pub struct PantheonShellState {
    _global: GlobalId,
}

impl PantheonShellState {
    pub fn new<D>(display: &DisplayHandle) -> Self
    where
        D: GlobalDispatch<
                protocol::io_elementary_pantheon_shell_v1::IoElementaryPantheonShellV1,
                (),
            > + 'static,
    {
        let global = display.create_global::<D, protocol::io_elementary_pantheon_shell_v1::IoElementaryPantheonShellV1, _>(2, ());
        Self { _global: global }
    }
}

#[derive(Clone)]
pub struct ShellSurfaceData {
    pub surface: WlSurface,
}

#[derive(Clone, Debug, Default)]
pub struct PanelState {
    /// Connector name selected for this panel. Missing or disconnected names
    /// fall back to the first active output and are updated on placement.
    pub output_name: Option<String>,
    /// Pantheon protocol values: top=0, bottom=1, left=2, right=3.
    pub anchor: Option<u32>,
    /// Non-positive dimensions use the committed surface size.
    pub width: i32,
    pub height: i32,
    pub offset: i32,
    /// Pantheon protocol values: never=0, maximized-focused=1,
    /// overlapping-focused=2, overlapping-any=3, always=4.
    pub hide_mode: u32,
    /// Whether the compositor has moved this panel out of view for its hide mode.
    pub hidden: bool,
    pub visible_in_multitasking_view: bool,
    /// Whether this panel has committed its first non-null buffer this session.
    pub first_buffer_committed: bool,
}

#[derive(Clone)]
pub struct PanelSurfaceData {
    pub surface: WlSurface,
}

impl GlobalDispatch<protocol::io_elementary_pantheon_shell_v1::IoElementaryPantheonShellV1, ()>
    for PantheonCompositor
{
    fn bind(
        _state: &mut Self,
        _handle: &DisplayHandle,
        _client: &Client,
        resource: New<protocol::io_elementary_pantheon_shell_v1::IoElementaryPantheonShellV1>,
        _global_data: &(),
        data_init: &mut DataInit<'_, Self>,
    ) {
        data_init.init(resource, ());
    }
}

impl Dispatch<protocol::io_elementary_pantheon_shell_v1::IoElementaryPantheonShellV1, ()>
    for PantheonCompositor
{
    fn request(
        state: &mut Self,
        _client: &Client,
        _resource: &protocol::io_elementary_pantheon_shell_v1::IoElementaryPantheonShellV1,
        request: protocol::io_elementary_pantheon_shell_v1::Request,
        _data: &(),
        _dhandle: &DisplayHandle,
        data_init: &mut DataInit<'_, Self>,
    ) {
        match request {
            protocol::io_elementary_pantheon_shell_v1::Request::GetPanel { output, surface } => {
                state.add_panel(surface.clone());
                data_init.init(output, PanelSurfaceData { surface });
            }
            protocol::io_elementary_pantheon_shell_v1::Request::GetWidget { output, surface } => {
                data_init.init(output, ShellSurfaceData { surface });
            }
            protocol::io_elementary_pantheon_shell_v1::Request::GetExtendedBehavior {
                output,
                surface,
            } => {
                data_init.init(output, ShellSurfaceData { surface });
            }
            protocol::io_elementary_pantheon_shell_v1::Request::GetGreeter { output, surface } => {
                data_init.init(output, ShellSurfaceData { surface });
            }
        }
    }
}

impl
    Dispatch<
        protocol::io_elementary_pantheon_panel_v1::IoElementaryPantheonPanelV1,
        PanelSurfaceData,
    > for PantheonCompositor
{
    fn request(
        state: &mut Self,
        _client: &Client,
        _resource: &protocol::io_elementary_pantheon_panel_v1::IoElementaryPantheonPanelV1,
        request: protocol::io_elementary_pantheon_panel_v1::Request,
        data: &PanelSurfaceData,
        _dhandle: &DisplayHandle,
        _data_init: &mut DataInit<'_, Self>,
    ) {
        let surface = &data.surface;
        match request {
            protocol::io_elementary_pantheon_panel_v1::Request::Destroy => {}
            protocol::io_elementary_pantheon_panel_v1::Request::SetAnchor { anchor } => {
                state.update_panel(surface, |panel| panel.anchor = Some(anchor.into()));
            }
            protocol::io_elementary_pantheon_panel_v1::Request::Focus => {
                // The bottom dock has no keyboard UI. Its requests must not
                // interrupt typing; top-panel menus retain their focus path.
                if !state.session_locked
                    && state.panels.get(&surface.id()).is_some_and(|panel| panel.anchor == Some(0))
                    && state.find_window_for_surface(surface).is_some()
                    && let Some(keyboard) = state.seat.get_keyboard()
                {
                    state.set_x11_keyboard_focus(None, SERIAL_COUNTER.next_serial());
                    keyboard.set_focus(
                        state,
                        Some(surface.clone()),
                        SERIAL_COUNTER.next_serial(),
                    );
                }
            }
            protocol::io_elementary_pantheon_panel_v1::Request::SetSize { width, height } => {
                state.update_panel(surface, |panel| {
                    panel.width = width;
                    panel.height = height;
                });
            }
            protocol::io_elementary_pantheon_panel_v1::Request::SetHideMode { hide_mode } => {
                state.update_panel(surface, |panel| panel.hide_mode = hide_mode.into());
            }
            protocol::io_elementary_pantheon_panel_v1::Request::RequestVisibleInMultitaskingView => {
                state.update_panel(surface, |panel| panel.visible_in_multitasking_view = true);
            }
            protocol::io_elementary_pantheon_panel_v1::Request::AddBlur { .. }
            | protocol::io_elementary_pantheon_panel_v1::Request::RemoveBlur => {
                // The nested prototype has no blur renderer yet.
            }
            protocol::io_elementary_pantheon_panel_v1::Request::SetOffset { offset } => {
                state.update_panel(surface, |panel| panel.offset = offset);
            }
        }
    }

    fn destroyed(
        state: &mut Self,
        _client: smithay::reexports::wayland_server::backend::ClientId,
        _resource: &protocol::io_elementary_pantheon_panel_v1::IoElementaryPantheonPanelV1,
        data: &PanelSurfaceData,
    ) {
        state.remove_panel(&data.surface);
    }
}

impl
    Dispatch<
        protocol::io_elementary_pantheon_widget_v1::IoElementaryPantheonWidgetV1,
        ShellSurfaceData,
    > for PantheonCompositor
{
    fn request(
        _state: &mut Self,
        _client: &Client,
        _resource: &protocol::io_elementary_pantheon_widget_v1::IoElementaryPantheonWidgetV1,
        _request: protocol::io_elementary_pantheon_widget_v1::Request,
        _data: &ShellSurfaceData,
        _dhandle: &DisplayHandle,
        _data_init: &mut DataInit<'_, Self>,
    ) {
    }
}

impl Dispatch<protocol::io_elementary_pantheon_extended_behavior_v1::IoElementaryPantheonExtendedBehaviorV1, ShellSurfaceData>
    for PantheonCompositor
{
    fn request(
        _state: &mut Self,
        _client: &Client,
        _resource: &protocol::io_elementary_pantheon_extended_behavior_v1::IoElementaryPantheonExtendedBehaviorV1,
        _request: protocol::io_elementary_pantheon_extended_behavior_v1::Request,
        _data: &ShellSurfaceData,
        _dhandle: &DisplayHandle,
        _data_init: &mut DataInit<'_, Self>,
    ) {
    }
}

impl
    Dispatch<
        protocol::io_elementary_pantheon_greeter_v1::IoElementaryPantheonGreeterV1,
        ShellSurfaceData,
    > for PantheonCompositor
{
    fn request(
        _state: &mut Self,
        _client: &Client,
        _resource: &protocol::io_elementary_pantheon_greeter_v1::IoElementaryPantheonGreeterV1,
        _request: protocol::io_elementary_pantheon_greeter_v1::Request,
        _data: &ShellSurfaceData,
        _dhandle: &DisplayHandle,
        _data_init: &mut DataInit<'_, Self>,
    ) {
    }
}

impl PantheonCompositor {
    pub fn add_panel(&mut self, surface: WlSurface) {
        self.panels.insert(surface.id(), PanelState::default());
        tracing::info!(surface = ?surface.id(), "Pantheon panel surface requested");
        let window_id = self
            .workspace_manager
            .windows()
            .into_iter()
            .find(|(window, _, _)| {
                window
                    .toplevel()
                    .is_some_and(|toplevel| toplevel.wl_surface() == &surface)
            })
            .map(|(window, _, _)| window.id());
        if let Some(window_id) = window_id {
            self.workspace_manager.remove_window(window_id);
        }
        self.position_panel(&surface);
    }

    pub fn note_panel_buffer_commit(&mut self, surface: &WlSurface, has_buffer: bool) {
        if !has_buffer {
            return;
        }
        let Some(panel) = self.panels.get_mut(&surface.id()) else {
            return;
        };
        if panel.first_buffer_committed {
            return;
        }
        panel.first_buffer_committed = true;
        tracing::info!(surface = ?surface.id(), "first Pantheon panel buffer committed");
    }

    pub fn remove_panel(&mut self, surface: &WlSurface) {
        self.panels.remove(&surface.id());
        if self.refresh_work_areas() {
            self.reconfigure_managed_windows();
        }
        self.request_native_redraw();
    }

    pub fn update_panel(&mut self, surface: &WlSurface, update: impl FnOnce(&mut PanelState)) {
        let panel = self.panels.entry(surface.id()).or_default();
        update(panel);
        self.position_panel(surface);
        self.refresh_panel_visibility();
        if self.refresh_work_areas() {
            self.reconfigure_managed_windows();
        }
        self.request_native_redraw();
    }

    pub fn is_panel_surface(&self, surface: &WlSurface) -> bool {
        self.panels.contains_key(&surface.id())
    }

    pub fn work_area_for_output(
        &self,
        output_geometry: Rectangle<i32, Logical>,
    ) -> Rectangle<i32, Logical> {
        let (mut top, mut bottom, mut left, mut right) = (0, 0, 0, 0);
        for (surface_id, panel) in &self.panels {
            if panel.anchor.is_none() || panel.hidden {
                continue;
            }
            let Some(window) = self.space.elements().find(|window| {
                window
                    .toplevel()
                    .is_some_and(|toplevel| toplevel.wl_surface().id() == *surface_id)
            }) else {
                continue;
            };
            let rect = self.space.element_geometry(window).unwrap_or_else(|| {
                let geometry = window.geometry();
                Rectangle::new(
                    self.space.element_location(window).unwrap_or_default(),
                    geometry.size,
                )
            });
            let Some(intersection) = rect.intersection(output_geometry) else {
                continue;
            };
            match panel.anchor.unwrap() {
                0 => top = top.max(intersection.size.h),
                1 => bottom = bottom.max(intersection.size.h),
                2 => left = left.max(intersection.size.w),
                3 => right = right.max(intersection.size.w),
                _ => {}
            }
        }

        let left = left.min(output_geometry.size.w);
        let right = right.min(output_geometry.size.w - left);
        let top = top.min(output_geometry.size.h);
        let bottom = bottom.min(output_geometry.size.h - top);
        Rectangle::new(
            Point::from((output_geometry.loc.x + left, output_geometry.loc.y + top)),
            Size::from((
                output_geometry.size.w - left - right,
                output_geometry.size.h - top - bottom,
            )),
        )
    }

    fn refresh_work_areas(&mut self) -> bool {
        let work_areas = self
            .space
            .outputs()
            .filter_map(|output| {
                let geometry = self.space.output_geometry(output)?;
                Some((output.name(), self.work_area_for_output(geometry)))
            })
            .collect::<HashMap<_, _>>();
        if self.last_work_areas == work_areas {
            return false;
        }
        self.last_work_areas = work_areas;
        true
    }

    pub(crate) fn find_window_for_surface(&self, surface: &WlSurface) -> Option<Window> {
        self.space
            .elements()
            .find(|window| {
                window
                    .toplevel()
                    .is_some_and(|toplevel| toplevel.wl_surface() == surface)
            })
            .cloned()
    }

    fn position_panel(&mut self, surface: &WlSurface) {
        let Some(mut panel) = self.panels.get(&surface.id()).cloned() else {
            return;
        };
        let Some(anchor) = panel.anchor else {
            return;
        };
        let Some(window) = self.find_window_for_surface(surface) else {
            return;
        };
        let Some(output) = panel
            .output_name
            .as_deref()
            .and_then(|name| self.space.outputs().find(|output| output.name() == name))
            .cloned()
            .or_else(|| self.space.outputs_for_element(&window).first().cloned())
            .or_else(|| self.primary_output())
        else {
            return;
        };
        let Some(output_geometry) = self.space.output_geometry(&output) else {
            return;
        };
        if panel.output_name.as_deref() != Some(output.name().as_str()) {
            panel.output_name = Some(output.name());
            self.panels.insert(surface.id(), panel.clone());
        }

        let surface_size = window.geometry().size;
        let width = if panel.width > 0 {
            panel.width
        } else {
            surface_size.w
        };
        let height = if panel.height > 0 {
            panel.height
        } else {
            surface_size.h
        };
        let offset = panel.offset;
        let mut location = match anchor {
            0 => (
                output_geometry.loc.x + (output_geometry.size.w - width) / 2 + offset,
                output_geometry.loc.y,
            ),
            1 => (
                output_geometry.loc.x + (output_geometry.size.w - width) / 2 + offset,
                output_geometry.loc.y + output_geometry.size.h - height,
            ),
            2 => (
                output_geometry.loc.x,
                output_geometry.loc.y + (output_geometry.size.h - height) / 2 + offset,
            ),
            3 => (
                output_geometry.loc.x + output_geometry.size.w - width,
                output_geometry.loc.y + (output_geometry.size.h - height) / 2 + offset,
            ),
            _ => return,
        };
        if panel.hidden {
            match anchor {
                0 => location.1 -= height,
                1 => location.1 += height,
                2 => location.0 -= width,
                3 => location.0 += width,
                _ => return,
            }
        }
        self.space.map_element(window.clone(), location, false);
        self.space.raise_element(&window, false);
    }

    /// Apply the hide mode requested by the Pantheon panel protocol. The
    /// current Dock uses `overlapping-window`; edge motion reveals it again.
    pub fn refresh_panel_visibility(&mut self) {
        const EDGE_REVEAL_DISTANCE: f64 = 2.0;

        let pointer = self
            .seat
            .get_pointer()
            .map(|pointer| pointer.current_location());
        let panels = self
            .panels
            .iter()
            .map(|(id, panel)| (id.clone(), panel.clone()))
            .collect::<Vec<_>>();
        let mut changed = false;

        for (surface_id, mut panel) in panels {
            if panel.anchor.is_none() {
                continue;
            }
            let Some(window) = self.space.elements().find(|window| {
                window
                    .toplevel()
                    .is_some_and(|top| top.wl_surface().id() == surface_id)
            }) else {
                continue;
            };
            let Some(output) = panel
                .output_name
                .as_deref()
                .and_then(|name| self.space.outputs().find(|output| output.name() == name))
                .cloned()
                .or_else(|| self.space.outputs_for_element(window).first().cloned())
                .or_else(|| self.primary_output())
            else {
                continue;
            };
            let Some(output_rect) = self.space.output_geometry(&output) else {
                continue;
            };
            let surface_size = window.geometry().size;
            let width = if panel.width > 0 {
                panel.width
            } else {
                surface_size.w
            };
            let height = if panel.height > 0 {
                panel.height
            } else {
                surface_size.h
            };
            let base_location = match panel.anchor.unwrap() {
                0 => (
                    output_rect.loc.x + (output_rect.size.w - width) / 2 + panel.offset,
                    output_rect.loc.y,
                ),
                1 => (
                    output_rect.loc.x + (output_rect.size.w - width) / 2 + panel.offset,
                    output_rect.loc.y + output_rect.size.h - height,
                ),
                2 => (
                    output_rect.loc.x,
                    output_rect.loc.y + (output_rect.size.h - height) / 2 + panel.offset,
                ),
                3 => (
                    output_rect.loc.x + output_rect.size.w - width,
                    output_rect.loc.y + (output_rect.size.h - height) / 2 + panel.offset,
                ),
                _ => continue,
            };
            let panel_rect =
                Rectangle::new(Point::from(base_location), Size::from((width, height)));
            let pointer_over_panel = !panel.hidden
                && pointer.is_some_and(|position| panel_rect.to_f64().contains(position));
            let pointer_at_edge = pointer.is_some_and(|position| {
                output_rect.to_f64().contains(position)
                    && match panel.anchor.unwrap() {
                        0 => position.y <= (output_rect.loc.y as f64 + EDGE_REVEAL_DISTANCE),
                        1 => {
                            position.y
                                >= (output_rect.loc.y + output_rect.size.h) as f64
                                    - EDGE_REVEAL_DISTANCE
                        }
                        2 => position.x <= (output_rect.loc.x as f64 + EDGE_REVEAL_DISTANCE),
                        3 => {
                            position.x
                                >= (output_rect.loc.x + output_rect.size.w) as f64
                                    - EDGE_REVEAL_DISTANCE
                        }
                        _ => false,
                    }
            });
            let pointer_reveals_panel = pointer_over_panel || pointer_at_edge;

            let focused_window = self
                .seat
                .get_keyboard()
                .and_then(|keyboard| keyboard.current_focus())
                .map(|mut focused| {
                    while let Some(parent) = smithay::wayland::compositor::get_parent(&focused) {
                        focused = parent;
                    }
                    focused
                })
                .and_then(|focused| self.find_window_for_surface(&focused));
            let focused_window = focused_window.filter(|focused| {
                focused
                    .toplevel()
                    .is_none_or(|top| !self.is_panel_surface(top.wl_surface()))
            });
            let focused_maximized = focused_window.as_ref().is_some_and(|focused| {
                focused
                    .toplevel()
                    .and_then(|top| self.managed_windows.get(&top.wl_surface().id()))
                    .is_some_and(|managed| managed.maximized || managed.fullscreen)
            });
            let focused_overlaps = focused_window.as_ref().is_some_and(|focused| {
                self.window_overlaps_panel(focused, panel_rect, panel.anchor.unwrap())
            });
            let any_window_overlaps = self.space.elements().any(|other| {
                let Some(top) = other.toplevel() else {
                    return false;
                };
                if self.is_panel_surface(top.wl_surface()) {
                    return false;
                }
                self.window_overlaps_panel(other, panel_rect, panel.anchor.unwrap())
            });
            let should_hide = match panel.hide_mode {
                0 => false,
                1 => focused_maximized,
                2 => focused_overlaps,
                3 => any_window_overlaps,
                4 => true,
                _ => false,
            };
            let hidden = should_hide && !pointer_reveals_panel;
            if panel.hidden != hidden {
                panel.hidden = hidden;
                self.panels.insert(surface_id.clone(), panel);
                if let Some(surface) = self
                    .panels
                    .get(&surface_id)
                    .and_then(|_| {
                        self.space.elements().find(|window| {
                            window
                                .toplevel()
                                .is_some_and(|top| top.wl_surface().id() == surface_id)
                        })
                    })
                    .and_then(|window| window.toplevel().map(|top| top.wl_surface().clone()))
                {
                    self.position_panel(&surface);
                }
                changed = true;
            }
        }

        if changed {
            if self.refresh_work_areas() {
                self.reconfigure_managed_windows();
            }
            self.request_native_redraw();
        }
    }

    fn window_overlaps_panel(
        &self,
        window: &Window,
        panel_rect: Rectangle<i32, Logical>,
        anchor: u32,
    ) -> bool {
        let collision_rect = match anchor {
            0 => Rectangle::new(
                panel_rect.loc,
                Size::from((panel_rect.size.w, panel_rect.size.h + 1)),
            ),
            1 => Rectangle::new(
                Point::from((panel_rect.loc.x, panel_rect.loc.y - 1)),
                Size::from((panel_rect.size.w, panel_rect.size.h + 1)),
            ),
            2 => Rectangle::new(
                panel_rect.loc,
                Size::from((panel_rect.size.w + 1, panel_rect.size.h)),
            ),
            3 => Rectangle::new(
                Point::from((panel_rect.loc.x - 1, panel_rect.loc.y)),
                Size::from((panel_rect.size.w + 1, panel_rect.size.h)),
            ),
            _ => panel_rect,
        };
        let geometry = self.space.element_geometry(window).unwrap_or_else(|| {
            let size = window.geometry().size;
            Rectangle::new(
                self.space.element_location(window).unwrap_or_default(),
                size,
            )
        });
        collision_rect.intersection(geometry).is_some()
    }

    pub fn configure_window_mode(
        &mut self,
        surface: ToplevelSurface,
        maximized: bool,
        fullscreen: bool,
    ) {
        let wl_surface = surface.wl_surface();
        let Some(window) = self.find_window_for_surface(wl_surface) else {
            return;
        };

        let surface_id = wl_surface.id();
        self.clear_tiling_for_surface(wl_surface);
        let restore = *self
            .managed_windows
            .entry(surface_id.clone())
            .or_insert_with(|| ManagedWindow {
                restore_location: self.space.element_location(&window).unwrap_or_default(),
                restore_size: window.geometry().size,
                maximized: false,
                fullscreen: false,
            });

        if let Some(managed) = self.managed_windows.get_mut(&surface_id) {
            managed.maximized = maximized;
            managed.fullscreen = fullscreen;
        }

        self.apply_window_mode(&surface, &window, restore, maximized, fullscreen);
        self.refresh_panel_visibility();

        if !maximized && !fullscreen {
            self.managed_windows.remove(&surface_id);
        }
    }

    fn apply_window_mode(
        &mut self,
        surface: &ToplevelSurface,
        window: &Window,
        restore: ManagedWindow,
        maximized: bool,
        fullscreen: bool,
    ) {
        let Some(output) = self
            .space
            .outputs_for_element(window)
            .first()
            .cloned()
            .or_else(|| self.primary_output())
        else {
            return;
        };
        let Some(output_geometry) = self.space.output_geometry(&output) else {
            return;
        };

        let target = if fullscreen {
            output_geometry
        } else if maximized {
            self.work_area_for_output(output_geometry)
        } else {
            Rectangle::new(restore.restore_location, restore.restore_size)
        };

        surface.with_pending_state(|state| {
            if maximized {
                state.states.set(xdg_toplevel::State::Maximized);
            } else {
                state.states.unset(xdg_toplevel::State::Maximized);
            }
            if fullscreen {
                state.states.set(xdg_toplevel::State::Fullscreen);
            } else {
                state.states.unset(xdg_toplevel::State::Fullscreen);
            }
            state.size = Some(target.size);
        });
        surface.send_pending_configure();
        self.space.map_element(window.clone(), target.loc, false);
    }

    pub(crate) fn reconfigure_managed_windows(&mut self) {
        let mut managed = Vec::new();
        for window in self.space.elements() {
            let Some(surface) = window.toplevel().cloned() else {
                continue;
            };
            let Some(state) = self.managed_windows.get(&surface.wl_surface().id()) else {
                continue;
            };
            managed.push((surface, (*window).clone(), *state));
        }

        for (surface, window, state) in managed {
            self.apply_window_mode(&surface, &window, state, state.maximized, state.fullscreen);
        }
        self.reconfigure_tiled_windows();
        self.constrain_floating_windows();
    }

    /// Reserve visible panel space for ordinary apps without raising or focusing them.
    fn constrain_floating_windows(&mut self) {
        let windows: Vec<_> = self.space.elements().cloned().collect();
        for window in windows {
            if let Some(surface) = Self::tile_surface(&window)
                && (self.is_panel_surface(&surface)
                    || self.tiled_windows.contains_key(&surface.id())
                    || self.managed_windows.contains_key(&surface.id()))
            {
                continue;
            }
            if let Some(surface) = window.x11_surface()
                && (surface.is_override_redirect() || surface.is_fullscreen())
            {
                continue;
            }
            let Some(output) = self.space.outputs_for_element(&window).first().cloned() else {
                continue;
            };
            let Some(output_geometry) = self.space.output_geometry(&output) else {
                continue;
            };
            let Some(location) = self.space.element_location(&window) else {
                continue;
            };
            let current = Rectangle::new(location, window.geometry().size);
            let area = self.work_area_for_output(output_geometry);
            let target = fit_window_to_work_area(current, area);
            if target == current {
                continue;
            }
            if let Some(surface) = window.toplevel() {
                surface.with_pending_state(|state| state.size = Some(target.size));
                surface.send_pending_configure();
            } else if let Some(surface) = window.x11_surface()
                && let Err(error) = surface.configure(Some(target))
            {
                tracing::warn!(?error, "could not fit X11 window above dock");
                continue;
            }
            self.space.map_element(window, target.loc, false);
        }
    }
}

pub fn handle_surface_commit(state: &mut PantheonCompositor, surface: &WlSurface) {
    if state.is_panel_surface(surface) {
        state.update_panel(surface, |_| {});
    } else {
        state.update_tiling_after_commit(surface);
        state.refresh_panel_visibility();
    }
}

/// Move first; shrink only when the window cannot fit inside the usable area.
fn fit_window_to_work_area(
    rect: Rectangle<i32, Logical>,
    area: Rectangle<i32, Logical>,
) -> Rectangle<i32, Logical> {
    let size = Size::from((
        rect.size.w.min(area.size.w).max(1),
        rect.size.h.min(area.size.h).max(1),
    ));
    let x = rect.loc.x.clamp(
        area.loc.x,
        (area.loc.x + area.size.w - size.w).max(area.loc.x),
    );
    let y = rect.loc.y.clamp(
        area.loc.y,
        (area.loc.y + area.size.h - size.h).max(area.loc.y),
    );
    Rectangle::new((x, y).into(), size)
}

#[cfg(test)]
mod work_area_tests {
    use super::*;

    #[test]
    fn moves_overlapping_window_without_resizing() {
        let area = Rectangle::new((0, 32).into(), (1920, 960).into());
        let rect = Rectangle::new((100, 800).into(), (640, 400).into());
        assert_eq!(
            fit_window_to_work_area(rect, area),
            Rectangle::new((100, 592).into(), (640, 400).into())
        );
    }

    #[test]
    fn shrinks_oversized_window_on_offset_monitor() {
        let area = Rectangle::new((-1920, 32).into(), (1920, 960).into());
        let rect = Rectangle::new((-2000, 0).into(), (2200, 1080).into());
        assert_eq!(fit_window_to_work_area(rect, area), area);
    }

    #[test]
    fn leaves_clear_window_in_place() {
        let area = Rectangle::new((0, 32).into(), (1920, 960).into());
        let rect = Rectangle::new((100, 100).into(), (640, 400).into());
        assert_eq!(fit_window_to_work_area(rect, area), rect);
    }
}
