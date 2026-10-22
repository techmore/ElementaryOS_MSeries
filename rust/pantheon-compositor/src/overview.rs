//! Grid overview ("expose") mode: the explicit supported replacement for
//! Gala's multitasking view until a scaled overview renderer exists.
//!
//! The installed Gala customization triggers `org.pantheon.gala.PerformAction(1)`
//! for the configured overlay gesture/hot corner. Instead of erroring, this
//! compositor now arranges the active workspace's windows into a per-output
//! grid inside each output's work area. Clicking a window focuses it and
//! closes the overview; Escape closes it and restores the prior arrangement.
//!
//! Windows are reconfigured rather than rendered scaled, so the mode reuses
//! the existing xdg/X11 configure paths. Clients that decline the grid size
//! (fixed-size windows) simply keep their committed size inside the cell.

use std::collections::HashSet;

use smithay::{
    desktop::Window,
    reexports::wayland_protocols::xdg::shell::server::xdg_toplevel,
    utils::{Logical, Point, Rectangle, SERIAL_COUNTER, Size},
};

use crate::placement::WindowRecord;
use crate::state::PantheonCompositor;

/// Gap between overview cells, in logical pixels.
const OVERVIEW_GAP: i32 = 12;
/// Margin between the work area edge and the outermost cells.
const OVERVIEW_MARGIN: i32 = 24;

pub(crate) struct OverviewWindow {
    window: Window,
    id: usize,
    location: Point<i32, Logical>,
    size: Size<i32, Logical>,
    /// Placement taken out of the store while the grid owns the window.
    record: Option<WindowRecord>,
}

pub(crate) struct OverviewState {
    windows: Vec<OverviewWindow>,
}

/// Lay out `count` equally sized, centered rows in `area`, one slot per item.
pub(crate) fn grid_rects(
    area: Rectangle<i32, Logical>,
    count: usize,
) -> Vec<Rectangle<i32, Logical>> {
    if count == 0 {
        return Vec::new();
    }
    let inner: Rectangle<i32, Logical> = Rectangle::new(
        (area.loc.x + OVERVIEW_MARGIN, area.loc.y + OVERVIEW_MARGIN).into(),
        Size::from((
            (area.size.w - 2 * OVERVIEW_MARGIN).max(1),
            (area.size.h - 2 * OVERVIEW_MARGIN).max(1),
        )),
    );
    let columns = (count as f64).sqrt().ceil().max(1.0) as i32;
    let rows = ((count as i32) + columns - 1) / columns;
    let cell_width = ((inner.size.w - OVERVIEW_GAP * (columns - 1)) / columns).max(1);
    let cell_height = ((inner.size.h - OVERVIEW_GAP * (rows - 1)) / rows).max(1);
    (0..count)
        .map(|index| {
            let column = index as i32 % columns;
            let row = index as i32 / columns;
            let items_in_row = (count as i32 - row * columns).clamp(1, columns);
            let row_width = items_in_row * cell_width + OVERVIEW_GAP * (items_in_row - 1);
            let row_offset = ((inner.size.w - row_width) / 2).max(0);
            Rectangle::new(
                (
                    inner.loc.x + row_offset + column * (cell_width + OVERVIEW_GAP),
                    inner.loc.y + row * (cell_height + OVERVIEW_GAP),
                )
                    .into(),
                Size::from((cell_width, cell_height)),
            )
        })
        .collect()
}

/// Preserve the client's aspect ratio and never enlarge a thumbnail.
pub(crate) fn fit_overview_rect(
    cell: Rectangle<i32, Logical>,
    size: Size<i32, Logical>,
) -> Rectangle<i32, Logical> {
    let scale = (cell.size.w as f64 / size.w.max(1) as f64)
        .min(cell.size.h as f64 / size.h.max(1) as f64)
        .min(1.0);
    let width = (size.w as f64 * scale).round().max(1.0) as i32;
    let height = (size.h as f64 * scale).round().max(1.0) as i32;
    Rectangle::new(
        (
            cell.loc.x + (cell.size.w - width) / 2,
            cell.loc.y + (cell.size.h - height) / 2,
        )
            .into(),
        (width, height).into(),
    )
}

impl PantheonCompositor {
    /// Snapshot render rectangles without configuring clients during a swipe.
    pub(crate) fn overview_preview_windows(&self) -> Vec<crate::gesture_animation::PreviewWindow> {
        use crate::gesture_animation::PreviewWindow;
        if let Some(overview) = &self.overview {
            return overview
                .windows
                .iter()
                .filter_map(|entry| {
                    let location = self.space.element_location(&entry.window)?;
                    Some(PreviewWindow {
                        window: entry.window.clone(),
                        from: Rectangle::new(location, entry.window.geometry().size),
                        to: Rectangle::new(entry.location, entry.size),
                    })
                })
                .collect();
        }
        let mut groups: Vec<(smithay::output::Output, Vec<Window>)> = Vec::new();
        for window in self.space.elements() {
            if self.workspace_manager.workspace_for(window.id())
                != Some(self.workspace_manager.active())
                || window
                    .toplevel()
                    .is_some_and(|top| self.is_panel_surface(top.wl_surface()))
            {
                continue;
            }
            let Some(output) = self.primary_output_for(window) else {
                continue;
            };
            if let Some((_, windows)) = groups.iter_mut().find(|(known, _)| known == &output) {
                windows.push(window.clone());
            } else {
                groups.push((output, vec![window.clone()]));
            }
        }
        groups
            .into_iter()
            .flat_map(|(output, windows)| {
                let rects = self
                    .space
                    .output_geometry(&output)
                    .map(|area| grid_rects(self.work_area_for_output(area), windows.len()))
                    .unwrap_or_default();
                windows
                    .into_iter()
                    .zip(rects)
                    .filter_map(|(window, to)| {
                        let from = Rectangle::new(
                            self.space.element_location(&window)?,
                            window.geometry().size,
                        );
                        let to = fit_overview_rect(to, from.size);
                        Some(PreviewWindow { window, from, to })
                    })
                    .collect::<Vec<_>>()
            })
            .collect()
    }

    pub(crate) fn overview_active(&self) -> bool {
        self.overview.is_some()
    }

    /// Toggle the grid overview. Used by the Gala `PerformAction(1)` bridge and
    /// by a three-finger upward swipe.
    pub(crate) fn toggle_overview(&mut self) -> Result<(), String> {
        self.discard_gesture_animation();
        if self.overview_active() {
            self.exit_overview(None)
        } else {
            self.enter_overview()
        }
    }

    fn enter_overview(&mut self) -> Result<(), String> {
        if self.session_locked {
            return Err("cannot open the overview while the session is locked".into());
        }
        // Menus would float over the grid and keep the keyboard.
        self.end_popup_grab_unless(None);
        self.dismiss_snap_assist();
        let active = self.workspace_manager.active();
        let minimized = self
            .minimized_windows
            .values()
            .map(|(window, _)| window.id())
            .chain(
                self.x11_minimized_windows
                    .values()
                    .map(|(window, _)| window.id()),
            )
            .collect::<HashSet<_>>();

        // Group visible application windows by the output they occupy.
        let mut groups: Vec<(smithay::output::Output, Vec<Window>)> = Vec::new();
        for window in self.space.elements() {
            if self.workspace_manager.workspace_for(window.id()) != Some(active)
                || minimized.contains(&window.id())
                || window
                    .toplevel()
                    .is_some_and(|toplevel| self.is_panel_surface(toplevel.wl_surface()))
            {
                continue;
            }
            let Some(output) = self.primary_output_for(window) else {
                continue;
            };
            if let Some(group) = groups
                .iter_mut()
                .find(|(group, _)| group.name() == output.name())
            {
                group.1.push((*window).clone());
            } else {
                groups.push((output, vec![(*window).clone()]));
            }
        }
        if groups.is_empty() {
            return Err("there are no windows to show in the overview".into());
        }

        let mut saved = Vec::new();
        for (output, windows) in groups {
            let Some(output_geometry) = self.space.output_geometry(&output) else {
                continue;
            };
            let work_area = self.work_area_for_output(output_geometry);
            for (window, rect) in windows.iter().zip(grid_rects(work_area, windows.len())) {
                self.place_overview_window(
                    window,
                    fit_overview_rect(rect, window.geometry().size),
                    &mut saved,
                );
            }
        }
        if saved.is_empty() {
            return Err("there are no windows to show in the overview".into());
        }

        self.overview = Some(OverviewState { windows: saved });
        self.refresh_panel_visibility();
        self.gala_compat.request_windows_changed();
        self.request_native_redraw();
        tracing::info!(
            windows = self.overview_windows().unwrap_or(0),
            "opened the grid overview"
        );
        Ok(())
    }

    fn place_overview_window(
        &mut self,
        window: &Window,
        rect: Rectangle<i32, Logical>,
        saved: &mut Vec<OverviewWindow>,
    ) {
        let id = window.id();
        let location = self.space.element_location(window).unwrap_or_default();
        let size = window.geometry().size;
        let record = self.placements.remove(&id);

        if let Some(toplevel) = window.toplevel() {
            toplevel.with_pending_state(|state| {
                for managed in [
                    xdg_toplevel::State::Maximized,
                    xdg_toplevel::State::Fullscreen,
                    xdg_toplevel::State::TiledLeft,
                    xdg_toplevel::State::TiledRight,
                    xdg_toplevel::State::TiledTop,
                    xdg_toplevel::State::TiledBottom,
                ] {
                    state.states.unset(managed);
                }
                state.size = Some(rect.size);
            });
            toplevel.send_pending_configure();
        } else if let Some(surface) = window.x11_surface() {
            if let Err(error) = surface.set_maximized(false) {
                tracing::warn!(
                    ?error,
                    "could not clear X11 maximized state for the overview"
                );
            }
            if let Err(error) = surface.set_fullscreen(false) {
                tracing::warn!(
                    ?error,
                    "could not clear X11 fullscreen state for the overview"
                );
            }
            if let Err(error) = surface.configure(Some(rect)) {
                tracing::warn!(?error, "could not configure X11 window for the overview");
            }
        } else {
            return;
        }
        self.space.map_element(window.clone(), rect.loc, false);
        saved.push(OverviewWindow {
            window: window.clone(),
            id,
            location,
            size,
            record,
        });
    }

    /// Close the overview and restore every saved arrangement. `focus` may name
    /// the window that was selected with the pointer; otherwise the last saved
    /// window is focused.
    pub(crate) fn exit_overview(&mut self, focus: Option<usize>) -> Result<(), String> {
        self.discard_gesture_animation();
        let Some(state) = self.overview.take() else {
            return Err("the overview is not open".into());
        };
        let selected = focus
            .and_then(|id| {
                state
                    .windows
                    .iter()
                    .find(|entry| entry.id == id)
                    .map(|entry| entry.window.clone())
            })
            .or_else(|| state.windows.last().map(|entry| entry.window.clone()));

        for entry in &state.windows {
            let window = &entry.window;
            if !self.space.elements().any(|candidate| candidate == window) {
                continue;
            }
            if let Some(record) = entry.record.clone() {
                let managed = !record.placement.is_floating();
                let mut record = record;
                record.pending = None;
                self.placements.insert(entry.id, record);
                if managed {
                    // Re-fit the current work area: tiles, maximize and fullscreen.
                    self.apply_placement(window);
                    continue;
                }
            }
            if let Some(surface) = window.toplevel() {
                surface.with_pending_state(|state| {
                    state.size = Some(entry.size);
                });
                surface.send_pending_configure();
                self.space
                    .map_element(window.clone(), entry.location, false);
            } else if let Some(surface) = window.x11_surface() {
                if let Err(error) =
                    surface.configure(Some(Rectangle::new(entry.location, entry.size)))
                {
                    tracing::warn!(?error, "could not restore X11 window after the overview");
                } else {
                    self.space
                        .map_element(window.clone(), entry.location, false);
                }
            }
        }

        if let Some(window) = selected {
            self.raise_window(&window, true);
            self.focus_window_keyboard(&window, SERIAL_COUNTER.next_serial());
        }
        self.refresh_panel_visibility();
        self.gala_compat.request_windows_changed();
        self.request_native_redraw();
        tracing::info!("closed the grid overview");
        Ok(())
    }

    fn overview_windows(&self) -> Option<usize> {
        self.overview.as_ref().map(|state| state.windows.len())
    }

    /// Handle the overview's Escape shortcut from the keyboard filter. Returns
    /// true when the key was consumed.
    pub(crate) fn handle_overview_key(&mut self) -> bool {
        if !self.overview_active() {
            return false;
        }
        let _ = self.exit_overview(None);
        true
    }

    /// Handle a pointer press while the overview is open: select the window
    /// under the pointer (if any) and close the overview. Returns true when the
    /// press was consumed.
    pub(crate) fn handle_overview_click(&mut self, location: Point<f64, Logical>) -> bool {
        if !self.overview_active() {
            return false;
        }
        let target = self
            .space
            .element_under(location)
            .map(|(window, _)| (*window).clone())
            .filter(|window| {
                window
                    .toplevel()
                    .is_none_or(|toplevel| !self.is_panel_surface(toplevel.wl_surface()))
            })
            .map(|window| window.id());
        let _ = self.exit_overview(target);
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn area() -> Rectangle<i32, Logical> {
        Rectangle::new((0, 0).into(), (1000, 600).into())
    }

    #[test]
    fn thumbnails_keep_aspect_and_do_not_grow() {
        let cell = Rectangle::new((100, 200).into(), (600, 400).into());
        let fitted = fit_overview_rect(cell, (1200, 600).into());
        assert_eq!(fitted, Rectangle::new((100, 250).into(), (600, 300).into()));
        let small = fit_overview_rect(cell, (200, 100).into());
        assert_eq!(small, Rectangle::new((300, 350).into(), (200, 100).into()));
    }

    #[test]
    fn empty_overview_has_no_slots() {
        assert!(grid_rects(area(), 0).is_empty());
    }

    #[test]
    fn single_window_fills_the_work_area_margins() {
        let rects = grid_rects(area(), 1);
        assert_eq!(rects.len(), 1);
        assert_eq!(rects[0].loc, (OVERVIEW_MARGIN, OVERVIEW_MARGIN).into());
        assert_eq!(
            rects[0].size,
            (1000 - 2 * OVERVIEW_MARGIN, 600 - 2 * OVERVIEW_MARGIN).into()
        );
    }

    #[test]
    fn four_windows_form_a_two_by_two_grid() {
        let rects = grid_rects(area(), 4);
        assert_eq!(rects.len(), 4);
        assert_eq!(rects[0].loc.y, rects[1].loc.y);
        assert_eq!(rects[0].loc.x, rects[2].loc.x);
        assert!(rects[1].loc.x > rects[0].loc.x);
        assert!(rects[2].loc.y > rects[0].loc.y);
        // The third row-less row stays centered for odd counts.
        let rects = grid_rects(area(), 3);
        assert_eq!(rects[0].loc.y, rects[1].loc.y);
        assert!(rects[2].loc.y > rects[0].loc.y);
        let last = rects[2];
        let centered = (1000 - last.size.w) / 2;
        assert_eq!(last.loc.x, centered);
    }
}
