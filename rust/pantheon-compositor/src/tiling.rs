use gio::{Settings, SettingsBackend, SettingsSchemaSource, prelude::SettingsExtManual};
use smithay::{
    desktop::Window,
    input::keyboard::{Keysym, ModifiersState},
    reexports::wayland_server::Resource,
    utils::{Logical, Rectangle, Size},
    wayland::shell::xdg::ToplevelSurface,
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
        let Some(focused) = self
            .seat
            .get_keyboard()
            .and_then(|keyboard| keyboard.current_focus())
        else {
            return;
        };
        let Some(window) = self.find_window_for_surface(&focused) else {
            return;
        };
        let Some(surface) = window.toplevel().cloned() else {
            return;
        };
        if self.is_panel_surface(surface.wl_surface()) {
            return;
        }
        let Some(output) = self.space.outputs_for_element(&window).first().cloned() else {
            return;
        };
        let Some(output_geometry) = self.space.output_geometry(&output) else {
            return;
        };
        let rect = tile_rect(self.work_area_for_output(output_geometry), position);
        self.managed_windows.remove(&surface.wl_surface().id());
        self.apply_tile(&surface, &window, output, position, rect);
    }

    fn move_focused_window_to_output(&mut self, direction: i32) {
        let Some(focused) = self
            .seat
            .get_keyboard()
            .and_then(|keyboard| keyboard.current_focus())
        else {
            return;
        };
        let Some(window) = self.find_window_for_surface(&focused) else {
            return;
        };
        let Some(surface) = window.toplevel().cloned() else {
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
        if let Some(position) = self
            .tiled_windows
            .get(&surface.wl_surface().id())
            .map(|placement| placement.position)
        {
            let rect = tile_rect(target_work_area, position);
            self.apply_tile(&surface, &window, target_output, position, rect);
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
            self.space.map_element(window, location, false);
            #[cfg(feature = "native-drm")]
            self.request_native_redraw();
        }
    }

    fn apply_tile(
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
        self.space.map_element(window.clone(), rect.loc, false);
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
            let Some(surface) = window.toplevel().cloned() else {
                continue;
            };
            let Some(placement) = self.tiled_windows.get(&surface.wl_surface().id()) else {
                continue;
            };
            tiled.push((surface, (*window).clone(), placement.clone()));
        }

        for (surface, window, placement) in tiled {
            let Some(output_geometry) = self.space.output_geometry(&placement.output) else {
                self.tiled_windows.remove(&surface.wl_surface().id());
                continue;
            };
            let rect = tile_rect(
                self.work_area_for_output(output_geometry),
                placement.position,
            );
            self.apply_tile(
                &surface,
                &window,
                placement.output,
                placement.position,
                rect,
            );
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

fn tile_rect(area: Rectangle<i32, Logical>, position: TilePosition) -> Rectangle<i32, Logical> {
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
