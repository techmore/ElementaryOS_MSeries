use gio::{Settings, SettingsBackend, SettingsSchemaSource, prelude::SettingsExtManual};
use smithay::{
    desktop::Window,
    input::keyboard::{Keysym, ModifiersState},
    reexports::wayland_server::Resource,
    utils::{Logical, Point, Rectangle, Size},
    wayland::{
        compositor,
        shell::xdg::{SurfaceCachedState, ToplevelSurface},
    },
};

use crate::shell_compat::{ParsedAccelerator, matches_accelerator, parse_accelerator};
use crate::state::{PantheonCompositor, TilePosition, TiledWindow};

#[derive(Clone, Copy)]
enum TilingAction {
    Tile(TilePosition),
    MoveOutput(i32),
}

#[derive(Clone, Copy)]
struct TilingBinding {
    accelerator: ParsedAccelerator,
    action: TilingAction,
}

#[derive(Clone)]
pub struct CornerSnapPreview {
    pub output: smithay::output::Output,
    pub position: TilePosition,
    pub rect: Rectangle<i32, Logical>,
}

pub struct TilingBindings {
    bindings: Vec<TilingBinding>,
}

impl TilingBindings {
    pub fn load() -> Self {
        let mut bindings = Vec::new();
        for (key, action, fallback) in [
            (
                "top-left",
                TilingAction::Tile(TilePosition::TopLeft),
                vec!["<Super>KP_Home", "<Super>KP_7", "<Super><Alt>u"],
            ),
            (
                "top-right",
                TilingAction::Tile(TilePosition::TopRight),
                vec!["<Super>KP_Prior", "<Super>KP_9", "<Super><Alt>i"],
            ),
            (
                "bottom-left",
                TilingAction::Tile(TilePosition::BottomLeft),
                vec!["<Super>KP_End", "<Super>KP_1", "<Super><Alt>j"],
            ),
            (
                "bottom-right",
                TilingAction::Tile(TilePosition::BottomRight),
                vec!["<Super>KP_Next", "<Super>KP_3", "<Super><Alt>k"],
            ),
        ] {
            for accelerator in settings_shortcuts("org.techmore.mseries.snapping", key, &fallback) {
                push_binding(&mut bindings, &accelerator, action);
            }
        }

        for (schema_id, key, action, fallback) in [
            (
                "org.gnome.mutter.keybindings",
                "toggle-tiled-left",
                TilingAction::Tile(TilePosition::Left),
                vec!["<Super>Left"],
            ),
            (
                "org.gnome.mutter.keybindings",
                "toggle-tiled-right",
                TilingAction::Tile(TilePosition::Right),
                vec!["<Super>Right"],
            ),
            (
                "org.gnome.desktop.wm.keybindings",
                "move-to-monitor-left",
                TilingAction::MoveOutput(-1),
                vec!["<Super><Shift>Left"],
            ),
            (
                "org.gnome.desktop.wm.keybindings",
                "move-to-monitor-right",
                TilingAction::MoveOutput(1),
                vec!["<Super><Shift>Right"],
            ),
        ] {
            for accelerator in settings_shortcuts(schema_id, key, &fallback) {
                push_binding(&mut bindings, &accelerator, action);
            }
        }

        Self { bindings }
    }
}

fn settings_shortcuts(schema_id: &str, key: &str, fallback: &[&str]) -> Vec<String> {
    let Some(source) = SettingsSchemaSource::default() else {
        return fallback.iter().map(|value| (*value).to_owned()).collect();
    };
    let Some(schema) = source.lookup(schema_id, true) else {
        return fallback.iter().map(|value| (*value).to_owned()).collect();
    };
    if !schema.has_key(key) {
        return fallback.iter().map(|value| (*value).to_owned()).collect();
    }
    let settings = Settings::new_full(&schema, None::<&SettingsBackend>, None);
    settings
        .strv(key)
        .iter()
        .map(|value| value.to_string())
        .collect()
}

fn push_binding(bindings: &mut Vec<TilingBinding>, accelerator: &str, action: TilingAction) {
    if let Some(accelerator) = parse_accelerator(accelerator, 0) {
        bindings.push(TilingBinding {
            accelerator,
            action,
        });
    }
}

impl PantheonCompositor {
    pub fn handle_tiling_shortcut(&mut self, keysym: Keysym, modifiers: &ModifiersState) -> bool {
        if self.session_locked {
            return false;
        }
        let Some(binding) = self
            .tiling_bindings
            .bindings
            .iter()
            .find(|binding| matches_accelerator(binding.accelerator, keysym, modifiers))
            .copied()
        else {
            return false;
        };
        match binding.action {
            TilingAction::Tile(position) => self.tile_focused_window(position),
            TilingAction::MoveOutput(direction) => self.move_focused_window_to_output(direction),
        }
        true
    }

    fn tile_focused_window(&mut self, position: TilePosition) {
        let Some(window) = self.focused_window() else {
            return;
        };
        if window
            .toplevel()
            .is_some_and(|surface| self.is_panel_surface(surface.wl_surface()))
        {
            return;
        }
        let Some(output) = self.space.outputs_for_element(&window).first().cloned() else {
            return;
        };
        let Some(output_geometry) = self.space.output_geometry(&output) else {
            return;
        };
        let rect = tile_rect(self.work_area_for_output(output_geometry), position);
        self.apply_window_tile(&window, output, position, rect);
    }

    pub(crate) fn update_corner_snap_preview(
        &mut self,
        window: &Window,
        pointer: Point<f64, Logical>,
    ) {
        if self.corner_snap_cancelled {
            return;
        }
        let (min_size, max_size) = if let Some(surface) = window.toplevel() {
            if self.is_panel_surface(surface.wl_surface())
                || self
                    .managed_windows
                    .get(&surface.wl_surface().id())
                    .is_some_and(|managed| managed.fullscreen)
            {
                self.corner_snap_preview = None;
                return;
            }
            compositor::with_states(surface.wl_surface(), |states| {
                let mut cached = states.cached_state.get::<SurfaceCachedState>();
                let current = cached.current();
                (current.min_size, current.max_size)
            })
        } else if let Some(surface) = window.x11_surface() {
            if surface.is_override_redirect() || surface.is_fullscreen() {
                self.corner_snap_preview = None;
                return;
            }
            (
                surface.min_size().unwrap_or_default(),
                surface.max_size().unwrap_or_default(),
            )
        } else {
            self.corner_snap_preview = None;
            return;
        };
        let fixed_width = min_size.w > 0 && max_size.w == min_size.w;
        let fixed_height = min_size.h > 0 && max_size.h == min_size.h;
        if fixed_width && fixed_height {
            self.corner_snap_preview = None;
            return;
        }

        self.corner_snap_preview = self.space.outputs().find_map(|output| {
            let geometry = self.space.output_geometry(output)?;
            if !geometry.to_f64().contains(pointer) {
                return None;
            }
            let position = snap_position(geometry, pointer)?;
            let rect = tile_rect(self.work_area_for_output(geometry), position);
            Some(CornerSnapPreview {
                output: output.clone(),
                position,
                rect,
            })
        });
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    pub(crate) fn cancel_move_snap(&mut self) {
        self.corner_snap_cancelled = true;
        self.corner_snap_preview = None;
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    pub(crate) fn finish_move_snap(&mut self) {
        self.move_grab_active = false;
        self.corner_snap_cancelled = false;
        self.corner_snap_preview = None;
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    pub(crate) fn commit_move_snap(&mut self, window: &Window, preview: CornerSnapPreview) {
        self.apply_window_tile(window, preview.output, preview.position, preview.rect);
    }

    pub(crate) fn tile_surface(
        window: &Window,
    ) -> Option<smithay::reexports::wayland_server::protocol::wl_surface::WlSurface> {
        window
            .toplevel()
            .map(|surface| surface.wl_surface().clone())
            .or_else(|| {
                window
                    .x11_surface()
                    .and_then(|surface| surface.wl_surface())
            })
    }

    pub(crate) fn apply_window_tile(
        &mut self,
        window: &Window,
        output: smithay::output::Output,
        position: TilePosition,
        rect: Rectangle<i32, Logical>,
    ) {
        if let Some(surface) = window.toplevel() {
            self.managed_windows.remove(&surface.wl_surface().id());
            self.apply_tile(surface, window, output, position, rect);
        } else if let Some(surface) = window.x11_surface() {
            if surface.is_override_redirect() {
                return;
            }
            let Some(wl_surface) = surface.wl_surface() else {
                return;
            };
            let result = surface
                .set_maximized(false)
                .and_then(|_| surface.set_fullscreen(false));
            if let Err(error) = result {
                tracing::warn!(?error, "could not tile X11 window");
                return;
            }
            if let Err(error) = surface.configure(Some(rect)) {
                tracing::warn!(?error, "could not configure X11 tile");
                return;
            }
            self.x11_managed_windows.remove(&surface.window_id());
            self.place_window(&window, rect.loc);
            self.tiled_windows.insert(
                wl_surface.id(),
                TiledWindow {
                    position,
                    output,
                    rect,
                    committed_size: window.geometry().size,
                },
            );
            #[cfg(feature = "native-drm")]
            self.request_native_redraw();
        }
    }

    fn move_focused_window_to_output(&mut self, direction: i32) {
        let Some(window) = self.focused_window() else {
            return;
        };
        let Some(current_output) = self.space.outputs_for_element(&window).first().cloned() else {
            return;
        };
        let mut outputs = self
            .space
            .outputs()
            .filter_map(|output| {
                self.space
                    .output_geometry(output)
                    .map(|geometry| (output.clone(), geometry))
            })
            .collect::<Vec<_>>();
        outputs.sort_by_key(|(_, geometry)| (geometry.loc.x, geometry.loc.y));
        let Some(current_index) = outputs
            .iter()
            .position(|(output, _)| output.name() == current_output.name())
        else {
            return;
        };
        let target_index = current_index as i32 + direction;
        if !(0..outputs.len() as i32).contains(&target_index) {
            return;
        }
        let (target_output, target_geometry) = outputs.swap_remove(target_index as usize);
        let target_work_area = self.work_area_for_output(target_geometry);
        if let Some(position) = Self::tile_surface(&window)
            .and_then(|surface| self.tiled_windows.get(&surface.id()))
            .map(|placement| placement.position)
        {
            let rect = tile_rect(target_work_area, position);
            self.apply_window_tile(&window, target_output, position, rect);
        } else if let Some(current_geometry) = self.space.element_geometry(&window) {
            let current_output_geometry = self.space.output_geometry(&current_output).unwrap();
            let current_work_area = self.work_area_for_output(current_output_geometry);
            let offset = current_geometry.loc - current_work_area.loc;
            let max_x = (target_work_area.loc.x + target_work_area.size.w
                - current_geometry.size.w)
                .max(target_work_area.loc.x);
            let max_y = (target_work_area.loc.y + target_work_area.size.h
                - current_geometry.size.h)
                .max(target_work_area.loc.y);
            let location: smithay::utils::Point<i32, Logical> = (
                (target_work_area.loc.x + offset.x).clamp(target_work_area.loc.x, max_x),
                (target_work_area.loc.y + offset.y).clamp(target_work_area.loc.y, max_y),
            )
                .into();
            if let Some(surface) = window.x11_surface()
                && let Err(error) =
                    surface.configure(Some(Rectangle::new(location, current_geometry.size)))
            {
                tracing::warn!(?error, "could not move X11 window to output");
                return;
            }
            self.place_window(&window, location);
            #[cfg(feature = "native-drm")]
            self.request_native_redraw();
        }
    }

    pub(crate) fn apply_tile(
        &mut self,
        surface: &ToplevelSurface,
        window: &Window,
        output: smithay::output::Output,
        position: TilePosition,
        rect: Rectangle<i32, Logical>,
    ) {
        surface.with_pending_state(|state| {
            state.states.unset(smithay::reexports::wayland_protocols::xdg::shell::server::xdg_toplevel::State::Maximized);
            state.states.unset(smithay::reexports::wayland_protocols::xdg::shell::server::xdg_toplevel::State::Fullscreen);
            state.size = Some(rect.size);
        });
        surface.send_pending_configure();
        self.place_window(&window, rect.loc);
        self.tiled_windows.insert(
            surface.wl_surface().id(),
            TiledWindow {
                position,
                output,
                rect,
                committed_size: window.geometry().size,
            },
        );
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    pub(crate) fn reconfigure_tiled_windows(&mut self) {
        let mut tiled = Vec::new();
        for window in self.space.elements() {
            let Some(surface) = Self::tile_surface(window) else {
                continue;
            };
            let Some(placement) = self.tiled_windows.get(&surface.id()) else {
                continue;
            };
            tiled.push((surface, (*window).clone(), placement.clone()));
        }

        for (surface, window, placement) in tiled {
            let Some(output_geometry) = self.space.output_geometry(&placement.output) else {
                self.tiled_windows.remove(&surface.id());
                continue;
            };
            let rect = tile_rect(
                self.work_area_for_output(output_geometry),
                placement.position,
            );
            self.apply_window_tile(&window, placement.output, placement.position, rect);
        }
    }

    pub(crate) fn clear_tiling_for_surface(
        &mut self,
        surface: &smithay::reexports::wayland_server::protocol::wl_surface::WlSurface,
    ) {
        self.tiled_windows.remove(&surface.id());
    }

    pub(crate) fn update_tiling_after_commit(
        &mut self,
        surface: &smithay::reexports::wayland_server::protocol::wl_surface::WlSurface,
    ) {
        let Some(window) = self.find_window_for_surface(surface) else {
            return;
        };
        let Some(placement) = self.tiled_windows.get(&surface.id()).cloned() else {
            return;
        };
        let committed_size = window.geometry().size;
        if committed_size == placement.rect.size {
            if let Some(placement) = self.tiled_windows.get_mut(&surface.id()) {
                placement.committed_size = committed_size;
            }
        } else if committed_size != placement.committed_size {
            // A client that commits a different size declined the tile (for
            // example because its minimum-size hints do not fit the work area).
            self.tiled_windows.remove(&surface.id());
        }
    }
}

pub(crate) fn tile_rect(
    area: Rectangle<i32, Logical>,
    position: TilePosition,
) -> Rectangle<i32, Logical> {
    let half_width = area.size.w / 2;
    let half_height = area.size.h / 2;
    let (right, bottom, width, height) = match position {
        TilePosition::Left => (false, false, half_width, area.size.h),
        TilePosition::Right => (true, false, area.size.w - half_width, area.size.h),
        TilePosition::TopLeft => (false, false, half_width, half_height),
        TilePosition::TopRight => (true, false, area.size.w - half_width, half_height),
        TilePosition::BottomLeft => (false, true, half_width, area.size.h - half_height),
        TilePosition::BottomRight => (
            true,
            true,
            area.size.w - half_width,
            area.size.h - half_height,
        ),
    };
    let min_width = 1.min(width);
    let min_height = 1.min(height);
    Rectangle::new(
        (
            area.loc.x + if right { half_width } else { 0 },
            area.loc.y + if bottom { half_height } else { 0 },
        )
            .into(),
        Size::from((width.max(min_width), height.max(min_height))),
    )
}

// Output edges select halves; the corner zones take precedence for quarters.
fn snap_position(
    area: Rectangle<i32, Logical>,
    pointer: Point<f64, Logical>,
) -> Option<TilePosition> {
    if !area.to_f64().contains(pointer) {
        return None;
    }
    let left = pointer.x < (area.loc.x + 40) as f64;
    let right = pointer.x >= (area.loc.x + area.size.w - 40) as f64;
    let top = pointer.y < (area.loc.y + 40) as f64;
    let bottom = pointer.y >= (area.loc.y + area.size.h - 40) as f64;
    match (left, right, top, bottom) {
        (true, _, true, _) => Some(TilePosition::TopLeft),
        (_, true, true, _) => Some(TilePosition::TopRight),
        (true, _, _, true) => Some(TilePosition::BottomLeft),
        (_, true, _, true) => Some(TilePosition::BottomRight),
        (true, _, _, _) => Some(TilePosition::Left),
        (_, true, _, _) => Some(TilePosition::Right),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn edge_zones_respect_offset_output_and_corner_precedence() {
        let area = Rectangle::new((-1920, 30).into(), (1920, 1080).into());
        for (point, expected) in [
            ((-1920.0, 500.0), Some(TilePosition::Left)),
            ((-1.0, 500.0), Some(TilePosition::Right)),
            ((-1920.0, 30.0), Some(TilePosition::TopLeft)),
            ((-1.0, 30.0), Some(TilePosition::TopRight)),
            ((-1920.0, 1109.0), Some(TilePosition::BottomLeft)),
            ((-1.0, 1109.0), Some(TilePosition::BottomRight)),
            ((-960.0, 500.0), None),
            ((0.0, 500.0), None),
            ((-1921.0, 500.0), None),
        ] {
            assert_eq!(snap_position(area, point.into()), expected);
        }
    }
}
