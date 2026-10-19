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

#[derive(Clone, Copy, Debug, Default)]
pub struct PanelState {
    /// Pantheon protocol values: top=0, bottom=1, left=2, right=3.
    pub anchor: Option<u32>,
    /// Non-positive dimensions use the committed surface size.
    pub width: i32,
    pub height: i32,
    pub offset: i32,
    /// Pantheon protocol values: never=0, maximized-focused=1,
    /// overlapping-focused=2, overlapping-any=3, always=4.
    pub hide_mode: u32,
    pub visible_in_multitasking_view: bool,
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
                if state.find_window_for_surface(surface).is_some() {
                    if let Some(keyboard) = state.seat.get_keyboard() {
                        keyboard.set_focus(
                            state,
                            Some(surface.clone()),
                            SERIAL_COUNTER.next_serial(),
                        );
                    }
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
        self.position_panel(&surface);
    }

    pub fn remove_panel(&mut self, surface: &WlSurface) {
        self.panels.remove(&surface.id());
    }

    pub fn update_panel(&mut self, surface: &WlSurface, update: impl FnOnce(&mut PanelState)) {
        let panel = self.panels.entry(surface.id()).or_default();
        update(panel);
        self.position_panel(surface);
        if self.refresh_work_area() {
            self.reconfigure_managed_windows();
        }
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
            if panel.anchor.is_none() || panel.hide_mode != 0 {
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

    fn refresh_work_area(&mut self) -> bool {
        let Some(output) = self.space.outputs().next().cloned() else {
            return false;
        };
        let Some(output_geometry) = self.space.output_geometry(&output) else {
            return false;
        };
        let work_area = self.work_area_for_output(output_geometry);
        if self.last_work_area == Some(work_area) {
            return false;
        }
        self.last_work_area = Some(work_area);
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
        let Some(panel) = self.panels.get(&surface.id()).copied() else {
            return;
        };
        let Some(anchor) = panel.anchor else {
            return;
        };
        let Some(window) = self.find_window_for_surface(surface) else {
            return;
        };
        let Some(output) = self.space.outputs().next().cloned() else {
            return;
        };
        let Some(output_geometry) = self.space.output_geometry(&output) else {
            return;
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
        let offset = panel.offset;
        let location = match anchor {
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
        self.space.map_element(window.clone(), location, false);
        self.space.raise_element(&window, false);
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
        let Some(output) = self.space.outputs().next().cloned() else {
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
    }
}

pub fn handle_surface_commit(state: &mut PantheonCompositor, surface: &WlSurface) {
    if state.is_panel_surface(surface) {
        state.update_panel(surface, |_| {});
    } else {
        state.update_tiling_after_commit(surface);
    }
}
