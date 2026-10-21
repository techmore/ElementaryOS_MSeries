//! Snapping, maximize and restore, driven by one [`WindowRecord`] per window.
//! The geometry rules live in [`crate::placement`]; this file applies them to
//! Wayland and X11 windows.

use std::time::Duration;

use gio::{Settings, SettingsBackend, SettingsSchemaSource, prelude::SettingsExtManual};
use smithay::{
    desktop::Window,
    input::{
        keyboard::{Keysym, ModifiersState},
        pointer::{Focus, GrabStartData as PointerGrabStartData, PointerHandle},
    },
    output::Output,
    reexports::{
        calloop::timer::{TimeoutAction, Timer},
        wayland_protocols::xdg::shell::server::xdg_toplevel,
        wayland_server::protocol::wl_surface::WlSurface,
    },
    utils::{Logical, Point, Rectangle, Serial, Size},
    wayland::{
        compositor,
        shell::xdg::{SurfaceCachedState, ToplevelSurface},
    },
    xwayland::X11Surface,
};

use crate::grabs::MoveSurfaceGrab;
use crate::placement::{
    self, Direction, KeyOutcome, PendingMove, Placement, Tile, TilePosition, WindowKey,
};
use crate::shell_compat::{ParsedAccelerator, matches_accelerator, parse_accelerator};
use crate::state::PantheonCompositor;

type Rect = Rectangle<i32, Logical>;

/// How long a client may take to ack a placement before the window is moved anyway.
const ACK_TIMEOUT: Duration = Duration::from_millis(400);

#[derive(Clone, Copy)]
enum TilingAction {
    Quarter(TilePosition),
    Arrow(Direction),
    MoveOutput(i32),
}

#[derive(Clone, Copy)]
struct TilingBinding {
    accelerator: ParsedAccelerator,
    action: TilingAction,
}

#[derive(Clone)]
pub struct CornerSnapPreview {
    pub output: Output,
    pub position: TilePosition,
    pub rect: Rect,
}

pub struct TilingBindings {
    bindings: Vec<TilingBinding>,
}

/// A client or keyboard request to change a window's mode.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModeRequest {
    Maximize,
    Unmaximize,
    Fullscreen,
    Unfullscreen,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum TargetKind {
    Floating,
    Tiled(TilePosition),
    Maximized,
    Fullscreen,
}

/// Where a placement puts a window right now.
struct Target {
    rect: Rect,
    kind: TargetKind,
    /// Zone and work area, for tiles: re-fitted to the size the client commits.
    zone: Option<(Rect, Rect)>,
}

impl TilingBindings {
    pub fn load() -> Self {
        let mut bindings = Vec::new();
        for (key, action, fallback) in [
            (
                "top-left",
                TilingAction::Quarter(TilePosition::TopLeft),
                vec!["<Super>KP_Home", "<Super>KP_7", "<Super><Alt>u"],
            ),
            (
                "top-right",
                TilingAction::Quarter(TilePosition::TopRight),
                vec!["<Super>KP_Prior", "<Super>KP_9", "<Super><Alt>i"],
            ),
            (
                "bottom-left",
                TilingAction::Quarter(TilePosition::BottomLeft),
                vec!["<Super>KP_End", "<Super>KP_1", "<Super><Alt>j"],
            ),
            (
                "bottom-right",
                TilingAction::Quarter(TilePosition::BottomRight),
                vec!["<Super>KP_Next", "<Super>KP_3", "<Super><Alt>k"],
            ),
            (
                "maximize",
                TilingAction::Arrow(Direction::Up),
                vec!["<Super>Up"],
            ),
            (
                "restore",
                TilingAction::Arrow(Direction::Down),
                vec!["<Super>Down"],
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
                TilingAction::Arrow(Direction::Left),
                vec!["<Super>Left"],
            ),
            (
                "org.gnome.mutter.keybindings",
                "toggle-tiled-right",
                TilingAction::Arrow(Direction::Right),
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

/// Send `kind`'s xdg states and `size`; returns the serial when a configure went out.
fn configure_toplevel(
    toplevel: &ToplevelSurface,
    kind: TargetKind,
    size: Option<Size<i32, Logical>>,
) -> Option<Serial> {
    use xdg_toplevel::State;
    toplevel.with_pending_state(|state| {
        for managed in [
            State::Maximized,
            State::Fullscreen,
            State::TiledLeft,
            State::TiledRight,
            State::TiledTop,
            State::TiledBottom,
        ] {
            state.states.unset(managed);
        }
        match kind {
            TargetKind::Floating => {}
            TargetKind::Maximized => {
                state.states.set(State::Maximized);
            }
            TargetKind::Fullscreen => {
                state.states.set(State::Fullscreen);
            }
            TargetKind::Tiled(position) => {
                let edges = position.tiled_edges();
                for (on, edge) in [
                    (edges.left, State::TiledLeft),
                    (edges.right, State::TiledRight),
                    (edges.top, State::TiledTop),
                    (edges.bottom, State::TiledBottom),
                ] {
                    if on {
                        state.states.set(edge);
                    }
                }
            }
        }
        state.size = size;
    });
    toplevel.send_pending_configure()
}

/// Set an X11 window's EWMH state and geometry for `kind`.
fn configure_x11(surface: &X11Surface, kind: TargetKind, rect: Rect) -> bool {
    if let Err(error) = surface
        .set_maximized(kind == TargetKind::Maximized)
        .and_then(|_| surface.set_fullscreen(kind == TargetKind::Fullscreen))
    {
        tracing::warn!(?error, "could not update X11 window state");
    }
    if let Err(error) = surface.configure(Some(rect)) {
        tracing::warn!(?error, "could not configure X11 window placement");
        return false;
    }
    true
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
            TilingAction::Quarter(position) => {
                self.keyboard_snap(|current| placement::quarter_outcome(current, position));
            }
            TilingAction::Arrow(direction) => self.snap_focused_window(direction),
            TilingAction::MoveOutput(direction) => self.move_focused_window_to_output(direction),
        }
        true
    }

    /// Super+Arrow on the focused window.
    pub(crate) fn snap_focused_window(&mut self, direction: Direction) {
        self.keyboard_snap(|current| placement::directional_outcome(current, direction));
    }

    fn keyboard_snap(&mut self, outcome: impl FnOnce(&Placement) -> KeyOutcome) {
        self.dismiss_snap_assist();
        let Some(window) = self.focused_window() else {
            return;
        };
        if !self.is_placeable(&window) {
            return;
        }
        match outcome(&self.placement_of(&window)) {
            KeyOutcome::Tile(position) => {
                if let Some(output) = self.primary_output_for(&window) {
                    self.tile_window(&window, &output, position, None, true);
                }
            }
            KeyOutcome::Maximize => self.set_window_mode(&window, ModeRequest::Maximize),
            KeyOutcome::Unmaximize => self.set_window_mode(&window, ModeRequest::Unmaximize),
            KeyOutcome::Float => self.float_window(&window),
            KeyOutcome::Nothing => {}
        }
    }

    /// Application windows; never panels or X11 override-redirect surfaces.
    fn is_placeable(&self, window: &Window) -> bool {
        if let Some(toplevel) = window.toplevel() {
            !self.is_panel_surface(toplevel.wl_surface())
        } else {
            window
                .x11_surface()
                .is_some_and(|surface| !surface.is_override_redirect())
        }
    }

    pub(crate) fn placement_of(&self, window: &Window) -> Placement {
        self.placements
            .get(&window.id())
            .map(|record| record.placement.clone())
            .unwrap_or_default()
    }

    /// The window is floating with no placement waiting for an ack, so
    /// work-area clamping may move it.
    pub(crate) fn is_free_floating(&self, window: &Window) -> bool {
        self.placements
            .get(&window.id())
            .is_none_or(|record| record.placement.is_floating() && record.pending.is_none())
    }

    pub(crate) fn forget_window_placement(&mut self, key: WindowKey) {
        self.placements.remove(&key);
        if self.grabbed_window == Some(key) {
            self.grabbed_window = None;
        }
        self.snap_assist_forget(key);
        // A closed member leaves its sibling tiled on a plain half.
        self.prune_snap_groups();
    }

    pub(crate) fn pointer_output(&self) -> Option<Output> {
        let pointer = self.seat.get_pointer()?.current_location();
        self.space
            .outputs()
            .find(|output| {
                self.space
                    .output_geometry(output)
                    .is_some_and(|geometry| geometry.to_f64().contains(pointer))
            })
            .cloned()
    }

    /// The output a window is on: the one its geometry overlaps most (S3),
    /// then the pointer's, then the primary output. Unlike
    /// `outputs_for_element().first()` this ignores CSD shadows and does not
    /// depend on HashMap order.
    pub(crate) fn primary_output_for(&self, window: &Window) -> Option<Output> {
        self.space
            .element_geometry(window)
            .and_then(|geometry| {
                placement::largest_overlap(
                    geometry,
                    self.space.outputs().filter_map(|output| {
                        Some((output.clone(), self.space.output_geometry(output)?))
                    }),
                )
            })
            // Reading the pointer inside a pointer grab would deadlock on
            // its lock; a dragged window always has geometry anyway.
            .or_else(|| {
                (!self.move_grab_active && !self.split_grab_active)
                    .then(|| self.pointer_output())
                    .flatten()
            })
            .or_else(|| self.primary_output())
    }

    fn output_named(&self, name: &str) -> Option<Output> {
        self.space
            .outputs()
            .find(|output| output.name() == name)
            .cloned()
    }

    fn work_area_of(&self, output: &Output) -> Option<Rect> {
        self.space
            .output_geometry(output)
            .map(|geometry| self.work_area_for_output(geometry))
    }

    pub(crate) fn size_hints(window: &Window) -> (Size<i32, Logical>, Size<i32, Logical>) {
        if let Some(surface) = window.toplevel() {
            compositor::with_states(surface.wl_surface(), |states| {
                let mut cached = states.cached_state.get::<SurfaceCachedState>();
                let current = cached.current();
                (current.min_size, current.max_size)
            })
        } else if let Some(surface) = window.x11_surface() {
            (
                surface.min_size().unwrap_or_default(),
                surface.max_size().unwrap_or_default(),
            )
        } else {
            Default::default()
        }
    }

    /// The rect a window's placement asks for. `output` overrides the
    /// window's own output (moving to another monitor).
    fn placement_target(&self, window: &Window, output: Option<&Output>) -> Option<Target> {
        let record = self.placements.get(&window.id());
        let placement = record.map_or(&Placement::Floating, |record| &record.placement);
        let output_for_window = || output.cloned().or_else(|| self.primary_output_for(window));
        match placement {
            Placement::Tiled(tile) => {
                // A missing output (unplugged) falls back to the window's
                // current one; the name is kept so a re-plug snaps it home.
                let output = output
                    .cloned()
                    .or_else(|| self.output_named(&tile.output))
                    .or_else(|| self.primary_output_for(window))?;
                let area = self.work_area_of(&output)?;
                // A snap group member gets its share of the group's split.
                let zone = self
                    .group_zone(window.id(), &output.name(), area)
                    .unwrap_or_else(|| placement::tile_rect(area, tile.position));
                let (min, max) = Self::size_hints(window);
                let size = placement::hinted_size(zone.size, min, max, area.size);
                Some(Target {
                    rect: placement::fit_to_zone(zone, area, tile.position, size),
                    kind: TargetKind::Tiled(tile.position),
                    zone: Some((zone, area)),
                })
            }
            Placement::Maximized { .. } => Some(Target {
                rect: self.work_area_of(&output_for_window()?)?,
                kind: TargetKind::Maximized,
                zone: None,
            }),
            Placement::Fullscreen { .. } => Some(Target {
                rect: self.space.output_geometry(&output_for_window()?)?,
                kind: TargetKind::Fullscreen,
                zone: None,
            }),
            Placement::Floating => {
                let area = self.work_area_of(&output_for_window()?)?;
                let rect = record
                    .and_then(|record| record.floating)
                    .map(|floating| placement::restore_into(floating, area))
                    .unwrap_or_else(|| placement::default_floating(area));
                Some(Target {
                    rect,
                    kind: TargetKind::Floating,
                    zone: None,
                })
            }
        }
    }

    /// Where a window should sit for the size it has committed: tiles are
    /// anchored to their zone's outer edge (S5), everything else at the target.
    fn settled_location(window: &Window, target: &Target) -> Point<i32, Logical> {
        match (target.kind, target.zone) {
            (TargetKind::Tiled(position), Some((zone, area))) => {
                placement::fit_to_zone(zone, area, position, window.geometry().size).loc
            }
            _ => target.rect.loc,
        }
    }

    /// A tile's settled location, recomputed for its own output and work area.
    fn settled_tile_location(&self, window: &Window) -> Option<Point<i32, Logical>> {
        self.placement_of(window).tile()?;
        let target = self.placement_target(window, None)?;
        Some(Self::settled_location(window, &target))
    }

    /// Configure a window for its placement. X11 windows move at once;
    /// Wayland windows move when the client acks the new size (S4), so a
    /// stale commit is never laid out (or pushed by the dock) at the new spot.
    pub(crate) fn apply_placement(&mut self, window: &Window) {
        self.apply_placement_on(window, None);
    }

    fn apply_placement_on(&mut self, window: &Window, output: Option<&Output>) {
        let Some(target) = self.placement_target(window, output) else {
            return;
        };
        let key = window.id();
        tracing::debug!(
            window = key,
            placement = %self.placement_of(window).label(),
            rect = ?target.rect,
            "applying window placement"
        );
        if let Some(toplevel) = window.toplevel() {
            let serial = configure_toplevel(toplevel, target.kind, Some(target.rect.size));
            let record = self.placements.entry(key).or_default();
            match (serial, record.pending.as_mut()) {
                (Some(serial), _) => {
                    record.pending = Some(PendingMove {
                        serial,
                        rect: target.rect,
                    });
                    self.arm_ack_timeout(key, serial);
                }
                // An earlier configure with this size is still unacked.
                (None, Some(pending)) => pending.rect = target.rect,
                (None, None) => {
                    // The client already has this size: only the spot changes.
                    if self.grabbed_window != Some(key) {
                        let location = Self::settled_location(window, &target);
                        self.place_window(window, location);
                    }
                }
            }
        } else if let Some(surface) = window.x11_surface() {
            if surface.is_override_redirect() {
                return;
            }
            if !configure_x11(surface, target.kind, target.rect) {
                return;
            }
            self.place_window(window, target.rect.loc);
        }
        self.request_native_redraw();
    }

    fn arm_ack_timeout(&mut self, key: WindowKey, serial: Serial) {
        let result = self.loop_handle.insert_source(
            Timer::from_duration(ACK_TIMEOUT),
            move |_, _, state| {
                state.settle_pending_placement(key, Some(serial));
                TimeoutAction::Drop
            },
        );
        if let Err(error) = result {
            tracing::warn!(?error, "could not arm the placement ack timeout");
        }
    }

    /// Move a window to its pending placement; `only` limits it to one configure.
    fn settle_pending_placement(&mut self, key: WindowKey, only: Option<Serial>) {
        let Some(record) = self.placements.get_mut(&key) else {
            return;
        };
        let Some(pending) = record.pending else {
            return;
        };
        if only.is_some_and(|serial| serial != pending.serial) {
            return;
        }
        record.pending = None;
        if self.grabbed_window == Some(key) {
            return;
        }
        let Some(window) = self
            .space
            .elements()
            .find(|window| window.id() == key)
            .cloned()
        else {
            return;
        };
        if only.is_some() {
            tracing::debug!(window = key, "client did not ack the placement in time");
        }
        // Maximized, fullscreen and floating targets were computed for the
        // right output when sent (it may be another monitor); tiles re-fit
        // the size the client actually committed.
        let location = self
            .settled_tile_location(&window)
            .unwrap_or(pending.rect.loc);
        self.place_window(&window, location);
        self.request_native_redraw();
    }

    /// Called on every toplevel commit.
    pub(crate) fn update_placement_after_commit(&mut self, surface: &WlSurface) {
        let Some(window) = self.find_window_for_surface(surface) else {
            return;
        };
        let key = window.id();
        if self.grabbed_window == Some(key) {
            return;
        }
        let Some(record) = self.placements.get(&key) else {
            return;
        };
        if let Some(pending) = record.pending {
            let acked = window.toplevel().and_then(|toplevel| {
                toplevel.with_cached_state(|state| {
                    state.last_acked.as_ref().map(|configure| configure.serial)
                })
            });
            if acked.is_some_and(|acked| acked.is_no_older_than(&pending.serial)) {
                self.settle_pending_placement(key, None);
            }
            return;
        }
        if let Some(location) = self.settled_tile_location(&window)
            && self.space.element_location(&window) != Some(location)
        {
            // The client committed another size (minimum size, its own
            // resize): it stays snapped, anchored to the zone's outer edge.
            self.place_window(&window, location);
        }
    }

    /// Snap `window` to `position` on `output`. `restore` overrides the rect
    /// saved for un-snapping (for a drag: where the window was when it began).
    pub(crate) fn tile_window(
        &mut self,
        window: &Window,
        output: &Output,
        position: TilePosition,
        restore: Option<Rect>,
        offer_assist: bool,
    ) {
        if !self.is_placeable(window) {
            return;
        }
        let current = restore
            .or_else(|| self.space.element_geometry(window))
            .unwrap_or_default();
        self.placements.entry(window.id()).or_default().tile(
            Tile {
                position,
                output: output.name(),
            },
            current,
        );
        self.apply_placement(window);
        // Join the window on the other half, or offer Snap Assist.
        self.after_user_tile(window, offer_assist);
        self.refresh_panel_visibility();
    }

    /// Un-snap to the saved floating rect (Super+Down, toggles).
    pub(crate) fn float_window(&mut self, window: &Window) {
        self.placements.entry(window.id()).or_default().float();
        self.apply_placement(window);
        self.prune_snap_groups();
        self.refresh_panel_visibility();
    }

    pub(crate) fn set_window_mode(&mut self, window: &Window, request: ModeRequest) {
        if !self.is_placeable(window) {
            return;
        }
        let current = self.space.element_geometry(window).unwrap_or_default();
        let record = self.placements.entry(window.id()).or_default();
        let changed = match request {
            ModeRequest::Maximize => record.maximize(current),
            ModeRequest::Unmaximize => record.unmaximize(),
            ModeRequest::Fullscreen => record.fullscreen(current),
            ModeRequest::Unfullscreen => record.unfullscreen(),
        };
        if !changed && record.placement.is_floating() {
            // Clients send unset_maximized/unset_fullscreen at startup; a
            // floating window stays exactly where it is. Answer the request.
            if let Some(toplevel) = window.toplevel() {
                toplevel.send_configure();
            }
            return;
        }
        // Reconfigure even when nothing changed: the client asked and expects
        // the current state back.
        self.dismiss_snap_assist();
        self.apply_placement(window);
        self.prune_snap_groups();
        self.refresh_panel_visibility();
    }

    pub fn request_toplevel_mode(&mut self, surface: &ToplevelSurface, request: ModeRequest) {
        if let Some(window) = self.find_window_for_surface(surface.wl_surface()) {
            self.set_window_mode(&window, request);
        }
    }

    /// An interactive resize makes a managed window floating where it is.
    pub(crate) fn float_in_place(&mut self, window: &Window) {
        let Some(record) = self.placements.get_mut(&window.id()) else {
            return;
        };
        if record.placement.is_floating() && record.pending.is_none() {
            return;
        }
        record.placement = Placement::Floating;
        record.pending = None;
        if let Some(toplevel) = window.toplevel() {
            toplevel.with_pending_state(|state| {
                use xdg_toplevel::State;
                for managed in [
                    State::Maximized,
                    State::Fullscreen,
                    State::TiledLeft,
                    State::TiledRight,
                    State::TiledTop,
                    State::TiledBottom,
                ] {
                    state.states.unset(managed);
                }
            });
        } else if let Some(surface) = window.x11_surface()
            && let Err(error) = surface
                .set_maximized(false)
                .and_then(|_| surface.set_fullscreen(false))
        {
            tracing::warn!(?error, "could not clear X11 window state for resize");
        }
        self.prune_snap_groups();
        self.refresh_panel_visibility();
    }

    /// Start dragging `window`. Snapped and maximized windows stay put until
    /// the pointer leaves the start point, then restore their floating size
    /// under the pointer (S1).
    pub(crate) fn start_move_grab(
        &mut self,
        pointer: &PointerHandle<Self>,
        start_data: PointerGrabStartData<Self>,
        window: Window,
        serial: Serial,
    ) {
        let Some(initial_window_location) = self.space.element_location(&window) else {
            return;
        };
        let placement = self.placement_of(&window);
        if placement.is_fullscreen() {
            return;
        }
        self.dismiss_snap_assist();
        let key = window.id();
        if let Some(record) = self.placements.get_mut(&key) {
            // The grab owns the location from now on.
            record.pending = None;
        }
        self.grabbed_window = Some(key);
        self.move_grab_active = true;
        self.corner_snap_cancelled = false;
        self.corner_snap_preview = None;
        let detach = !placement.is_floating();
        // Un-snapping later returns here, not to wherever the drag drops it.
        let restore = if detach {
            self.placements.get(&key).and_then(|record| record.floating)
        } else {
            self.space.element_geometry(&window)
        };
        let grab =
            MoveSurfaceGrab::new(start_data, window, initial_window_location, detach, restore);
        pointer.set_grab(self, grab, serial, Focus::Clear);
    }

    /// Un-snap a dragged window: floating size, same title-bar point under
    /// the pointer. Returns the new location.
    pub(crate) fn detach_for_drag(
        &mut self,
        window: &Window,
        pointer: Point<f64, Logical>,
    ) -> Option<Point<i32, Logical>> {
        let current = self.space.element_geometry(window)?;
        let area = self.work_area_of(&self.primary_output_for(window)?)?;
        let record = self.placements.get_mut(&window.id())?;
        if record.placement.is_floating() || record.placement.is_fullscreen() {
            return None;
        }
        let saved = record
            .floating
            .unwrap_or_else(|| placement::default_floating(area))
            .size;
        let size = Size::from((saved.w.min(area.size.w), saved.h.min(area.size.h)));
        let location = placement::drag_out_location(current, size, pointer);
        record.placement = Placement::Floating;
        record.pending = None;
        if let Some(toplevel) = window.toplevel() {
            configure_toplevel(toplevel, TargetKind::Floating, Some(size));
        } else if let Some(surface) = window.x11_surface() {
            configure_x11(
                surface,
                TargetKind::Floating,
                Rectangle::new(location, size),
            );
        }
        self.place_window(window, location);
        // Its sibling goes back to a plain half.
        self.prune_snap_groups();
        // Runs inside the pointer grab: panel visibility reads the pointer.
        self.loop_handle
            .insert_idle(|state| state.refresh_panel_visibility());
        Some(location)
    }

    /// The pointer button was released. Snap to the preview, recomputed for
    /// the current work area (S6), or put an undetached tile back. Called
    /// from an idle callback, outside the pointer grab.
    pub(crate) fn end_move(
        &mut self,
        window: &Window,
        snap: Option<CornerSnapPreview>,
        detached: bool,
        restore: Option<Rect>,
    ) {
        if let Some(snap) = snap {
            self.tile_window(window, &snap.output, snap.position, restore, true);
        } else if !detached && !self.placement_of(window).is_floating() {
            self.apply_placement(window);
        }
    }

    pub(crate) fn update_corner_snap_preview(
        &mut self,
        window: &Window,
        pointer: Point<f64, Logical>,
    ) {
        if self.corner_snap_cancelled {
            return;
        }
        if !self.is_placeable(window) || self.placement_of(window).is_fullscreen() {
            self.corner_snap_preview = None;
            return;
        }
        if window
            .x11_surface()
            .is_some_and(|surface| surface.is_fullscreen())
        {
            self.corner_snap_preview = None;
            return;
        }
        let (min_size, max_size) = Self::size_hints(window);
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
            let position = placement::snap_position(geometry, pointer)?;
            let area = self.work_area_for_output(geometry);
            let zone = placement::tile_rect(area, position);
            // Preview what the window will actually get (S5).
            let size = placement::hinted_size(zone.size, min_size, max_size, area.size);
            Some(CornerSnapPreview {
                output: output.clone(),
                position,
                rect: placement::fit_to_zone(zone, area, position, size),
            })
        });
        self.request_native_redraw();
    }

    pub(crate) fn cancel_move_snap(&mut self) {
        self.corner_snap_cancelled = true;
        self.corner_snap_preview = None;
        self.request_native_redraw();
    }

    pub(crate) fn finish_move_snap(&mut self) {
        self.move_grab_active = false;
        self.grabbed_window = None;
        self.corner_snap_cancelled = false;
        self.corner_snap_preview = None;
        self.request_native_redraw();
    }

    fn move_focused_window_to_output(&mut self, direction: i32) {
        let Some(window) = self.focused_window() else {
            return;
        };
        if !self.is_placeable(&window) {
            return;
        }
        let Some(current_output) = self.primary_output_for(&window) else {
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
        let Some(current_work_area) = self.work_area_of(&current_output) else {
            return;
        };
        let offset = target_work_area.loc - current_work_area.loc;
        let key = window.id();
        if let Some(record) = self.placements.get_mut(&key) {
            // The restore rect and any remembered tile travel with the window.
            if let Some(floating) = record.floating.as_mut() {
                floating.loc += offset;
            }
            record.placement.retarget(&target_output.name());
        }
        match self.placement_of(&window) {
            Placement::Floating => {
                let Some(current_geometry) = self.space.element_geometry(&window) else {
                    return;
                };
                let moved = Rectangle::new(current_geometry.loc + offset, current_geometry.size);
                let location = placement::restore_into(moved, target_work_area).loc;
                if let Some(surface) = window.x11_surface()
                    && let Err(error) =
                        surface.configure(Some(Rectangle::new(location, current_geometry.size)))
                {
                    tracing::warn!(?error, "could not move X11 window to output");
                    return;
                }
                self.place_window(&window, location);
                self.request_native_redraw();
            }
            // S14: maximized and fullscreen windows take the new output's size.
            _ => self.apply_placement_on(&window, Some(&target_output)),
        }
        self.prune_snap_groups();
    }

    /// Re-apply every managed placement, for example after the work area changed.
    pub(crate) fn reconfigure_placed_windows(&mut self) {
        let managed = self
            .space
            .elements()
            .filter(|window| {
                self.placements
                    .get(&window.id())
                    .is_some_and(|record| !record.placement.is_floating())
            })
            .cloned()
            .collect::<Vec<_>>();
        for window in managed {
            self.apply_placement(&window);
        }
    }

    /// Test and probe summary of a window's placement.
    #[cfg(feature = "gesture-probe")]
    pub(crate) fn placement_summary(&self, window: &Window) -> String {
        let record = self.placements.get(&window.id());
        let geometry = self.space.element_geometry(window).unwrap_or_default();
        let toplevel_states = window
            .toplevel()
            .map(|toplevel| {
                use xdg_toplevel::State;
                toplevel.with_committed_state(|state| {
                    let Some(state) = state else {
                        return String::new();
                    };
                    [
                        State::Maximized,
                        State::Fullscreen,
                        State::TiledLeft,
                        State::TiledRight,
                        State::TiledTop,
                        State::TiledBottom,
                    ]
                    .into_iter()
                    .filter(|candidate| state.states.contains(*candidate))
                    .map(|candidate| format!("{candidate:?}"))
                    .collect::<Vec<_>>()
                    .join("+")
                })
            })
            .unwrap_or_default();
        format!(
            "placement={} x={} y={} w={} h={} pending={} group={} states={}",
            record.map_or("floating".into(), |record| record.placement.label()),
            geometry.loc.x,
            geometry.loc.y,
            geometry.size.w,
            geometry.size.h,
            record.is_some_and(|record| record.pending.is_some()),
            self.group_summary(window),
            if toplevel_states.is_empty() {
                "-"
            } else {
                &toplevel_states
            },
        )
    }
}
