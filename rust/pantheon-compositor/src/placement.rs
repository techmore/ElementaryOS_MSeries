//! Window placement model: one record per window (S2) and the pure geometry
//! behind snapping, maximize and restore. Nothing here touches Wayland or X11,
//! so every rule is unit-tested.

use smithay::utils::{Logical, Point, Rectangle, Serial, Size};

/// smithay `Window::id()`, which is also the uid Gala clients see.
pub type WindowKey = usize;

type Rect = Rectangle<i32, Logical>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TilePosition {
    Left,
    Right,
    TopLeft,
    TopRight,
    BottomLeft,
    BottomRight,
}

impl TilePosition {
    /// The zone touches the work area's right edge.
    fn is_right(self) -> bool {
        matches!(self, Self::Right | Self::TopRight | Self::BottomRight)
    }

    /// The zone touches the work area's bottom edge but not its top.
    fn is_bottom(self) -> bool {
        matches!(self, Self::BottomLeft | Self::BottomRight)
    }

    /// The zone touches the work area's top edge but not its bottom.
    fn is_top(self) -> bool {
        matches!(self, Self::TopLeft | Self::TopRight)
    }

    /// Work-area edges the zone lies on (S8). The inner, shared edge stays
    /// untiled so the client keeps its resize border there, as Mutter does.
    pub fn tiled_edges(self) -> Edges {
        Edges {
            left: !self.is_right(),
            right: self.is_right(),
            top: !self.is_bottom(),
            bottom: !self.is_top(),
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Edges {
    pub left: bool,
    pub right: bool,
    pub top: bool,
    pub bottom: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Tile {
    pub position: TilePosition,
    /// Output (connector) name the tile belongs to.
    pub output: String,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub enum Placement {
    #[default]
    Floating,
    Tiled(Tile),
    /// `prior` is the placement to return to: `Floating` or `Tiled`.
    Maximized {
        prior: Box<Placement>,
    },
    /// `prior` may itself be `Maximized`.
    Fullscreen {
        prior: Box<Placement>,
    },
}

impl Placement {
    pub fn tile(&self) -> Option<&Tile> {
        match self {
            Self::Tiled(tile) => Some(tile),
            _ => None,
        }
    }

    /// The tile this window returns to: its own, or the one remembered under
    /// maximize or fullscreen.
    pub fn resting_tile(&self) -> Option<&Tile> {
        match self {
            Self::Floating => None,
            Self::Tiled(tile) => Some(tile),
            Self::Maximized { prior } | Self::Fullscreen { prior } => prior.resting_tile(),
        }
    }

    pub fn is_floating(&self) -> bool {
        matches!(self, Self::Floating)
    }

    pub fn is_maximized(&self) -> bool {
        matches!(self, Self::Maximized { .. })
    }

    pub fn is_fullscreen(&self) -> bool {
        matches!(self, Self::Fullscreen { .. })
    }

    /// Point every tile in this placement (including a remembered one under
    /// maximize or fullscreen) at `output`.
    pub fn retarget(&mut self, output: &str) {
        match self {
            Self::Floating => {}
            Self::Tiled(tile) => tile.output = output.to_owned(),
            Self::Maximized { prior } | Self::Fullscreen { prior } => prior.retarget(output),
        }
    }

    /// Short name for logs and probes.
    pub fn label(&self) -> String {
        match self {
            Self::Floating => "floating".into(),
            Self::Tiled(tile) => format!("tiled-{:?}", tile.position).to_lowercase(),
            Self::Maximized { prior } => format!("maximized({})", prior.label()),
            Self::Fullscreen { prior } => format!("fullscreen({})", prior.label()),
        }
    }
}

/// A Wayland placement waiting for the client to ack `serial` (S4).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PendingMove {
    pub serial: Serial,
    pub rect: Rect,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct WindowRecord {
    pub placement: Placement,
    /// Last free-floating geometry, restored on un-snap and un-maximize (S1).
    pub floating: Option<Rect>,
    pub pending: Option<PendingMove>,
}

impl WindowRecord {
    fn remember_floating(&mut self, current: Rect) {
        if self.placement.is_floating() && current.size.w > 0 && current.size.h > 0 {
            self.floating = Some(current);
        }
    }

    /// Snap to `tile`. `current` is the window's geometry now; it becomes the
    /// restore rect only when the window was floating.
    pub fn tile(&mut self, tile: Tile, current: Rect) {
        self.remember_floating(current);
        self.placement = match std::mem::take(&mut self.placement) {
            // A fullscreen window keeps covering the output; it re-tiles on exit.
            Placement::Fullscreen { .. } => Placement::Fullscreen {
                prior: Box::new(Placement::Tiled(tile)),
            },
            _ => Placement::Tiled(tile),
        };
    }

    pub fn maximize(&mut self, current: Rect) -> bool {
        self.remember_floating(current);
        let placement = std::mem::take(&mut self.placement);
        let (changed, placement) = match placement {
            Placement::Maximized { .. } => (false, placement),
            Placement::Fullscreen { prior } => match *prior {
                Placement::Maximized { .. } => (false, Placement::Fullscreen { prior }),
                base => (
                    true,
                    Placement::Fullscreen {
                        prior: Box::new(Placement::Maximized {
                            prior: Box::new(base),
                        }),
                    },
                ),
            },
            base => (
                true,
                Placement::Maximized {
                    prior: Box::new(base),
                },
            ),
        };
        self.placement = placement;
        changed
    }

    pub fn unmaximize(&mut self) -> bool {
        let placement = std::mem::take(&mut self.placement);
        let (changed, placement) = match placement {
            Placement::Maximized { prior } => (true, *prior),
            Placement::Fullscreen { prior } => match *prior {
                Placement::Maximized { prior: base } => {
                    (true, Placement::Fullscreen { prior: base })
                }
                other => (
                    false,
                    Placement::Fullscreen {
                        prior: Box::new(other),
                    },
                ),
            },
            other => (false, other),
        };
        self.placement = placement;
        changed
    }

    pub fn fullscreen(&mut self, current: Rect) -> bool {
        if self.placement.is_fullscreen() {
            return false;
        }
        self.remember_floating(current);
        let prior = std::mem::take(&mut self.placement);
        self.placement = Placement::Fullscreen {
            prior: Box::new(prior),
        };
        true
    }

    pub fn unfullscreen(&mut self) -> bool {
        match std::mem::take(&mut self.placement) {
            Placement::Fullscreen { prior } => {
                self.placement = *prior;
                true
            }
            other => {
                self.placement = other;
                false
            }
        }
    }

    /// Leave every managed placement; returns the rect to restore, if known.
    pub fn float(&mut self) -> Option<Rect> {
        self.placement = Placement::Floating;
        self.pending = None;
        self.floating
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Direction {
    Left,
    Right,
    Up,
    Down,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum KeyOutcome {
    Tile(TilePosition),
    Maximize,
    /// Return to the placement before maximize.
    Unmaximize,
    /// Leave the tile for the saved floating rect.
    Float,
    Nothing,
}

/// Super+Arrow. Left/Right toggle: pressing the side the window is on, or
/// the opposite half, restores it; quarters slide sideways or grow to the half.
/// Up maximizes; Down steps back one level (maximized → prior, tiled → floating).
pub fn directional_outcome(current: &Placement, direction: Direction) -> KeyOutcome {
    use TilePosition::*;
    match (current, direction) {
        (Placement::Fullscreen { .. }, _) => KeyOutcome::Nothing,
        (Placement::Maximized { .. }, Direction::Up) => KeyOutcome::Nothing,
        (Placement::Maximized { .. }, Direction::Down) => KeyOutcome::Unmaximize,
        (_, Direction::Up) => KeyOutcome::Maximize,
        (Placement::Tiled(_), Direction::Down) => KeyOutcome::Float,
        (Placement::Floating, Direction::Down) => KeyOutcome::Nothing,
        (Placement::Floating | Placement::Maximized { .. }, Direction::Left) => {
            KeyOutcome::Tile(Left)
        }
        (Placement::Floating | Placement::Maximized { .. }, Direction::Right) => {
            KeyOutcome::Tile(Right)
        }
        (Placement::Tiled(tile), Direction::Left) => match tile.position {
            Left | Right => KeyOutcome::Float,
            TopLeft | BottomLeft => KeyOutcome::Tile(Left),
            TopRight => KeyOutcome::Tile(TopLeft),
            BottomRight => KeyOutcome::Tile(BottomLeft),
        },
        (Placement::Tiled(tile), Direction::Right) => match tile.position {
            Left | Right => KeyOutcome::Float,
            TopRight | BottomRight => KeyOutcome::Tile(Right),
            TopLeft => KeyOutcome::Tile(TopRight),
            BottomLeft => KeyOutcome::Tile(BottomRight),
        },
    }
}

/// Quarter shortcuts toggle: the same quarter again restores the window.
pub fn quarter_outcome(current: &Placement, position: TilePosition) -> KeyOutcome {
    match current {
        Placement::Fullscreen { .. } => KeyOutcome::Nothing,
        Placement::Tiled(tile) if tile.position == position => KeyOutcome::Float,
        _ => KeyOutcome::Tile(position),
    }
}

/// The zone for `position`: exact halves/quarters of the work area.
pub fn tile_rect(area: Rect, position: TilePosition) -> Rect {
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
    Rectangle::new(
        (
            area.loc.x + if right { half_width } else { 0 },
            area.loc.y + if bottom { half_height } else { 0 },
        )
            .into(),
        Size::from((width.max(1), height.max(1))),
    )
}

/// Width of the drag zones along output edges.
const EDGE_ZONE: i32 = 40;

/// Output edges select halves; the corner zones take precedence for quarters.
pub fn snap_position(area: Rect, pointer: Point<f64, Logical>) -> Option<TilePosition> {
    if !area.to_f64().contains(pointer) {
        return None;
    }
    let left = pointer.x < (area.loc.x + EDGE_ZONE) as f64;
    let right = pointer.x >= (area.loc.x + area.size.w - EDGE_ZONE) as f64;
    let top = pointer.y < (area.loc.y + EDGE_ZONE) as f64;
    let bottom = pointer.y >= (area.loc.y + area.size.h - EDGE_ZONE) as f64;
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

/// The size to ask for in a zone, honouring the client's min/max hints (a
/// zero hint means none) but never larger than the work area (S5).
pub fn hinted_size(
    zone: Size<i32, Logical>,
    min: Size<i32, Logical>,
    max: Size<i32, Logical>,
    area: Size<i32, Logical>,
) -> Size<i32, Logical> {
    let axis = |zone: i32, min: i32, max: i32, area: i32| {
        let mut value = zone;
        if min > 0 {
            value = value.max(min);
        }
        if max > 0 {
            value = value.min(max);
        }
        value.min(area).max(1)
    };
    Size::from((
        axis(zone.w, min.w, max.w, area.w),
        axis(zone.h, min.h, max.h, area.h),
    ))
}

/// Place a window of `size` in `zone`, anchored to the zone's outer edges and
/// kept inside `area`. A window larger than its zone (minimum size) grows
/// inward rather than off-screen; a smaller one hugs the screen edge (S5).
pub fn fit_to_zone(
    zone: Rect,
    area: Rect,
    position: TilePosition,
    size: Size<i32, Logical>,
) -> Rect {
    let w = size.w.clamp(1, area.size.w.max(1));
    let h = size.h.clamp(1, area.size.h.max(1));
    let area_right = area.loc.x + area.size.w;
    let area_bottom = area.loc.y + area.size.h;
    let x = if position.is_right() {
        zone.loc.x + zone.size.w - w
    } else {
        zone.loc.x
    };
    let y = if position.is_bottom() {
        zone.loc.y + zone.size.h - h
    } else {
        zone.loc.y
    };
    Rectangle::new(
        (
            x.clamp(area.loc.x, (area_right - w).max(area.loc.x)),
            y.clamp(area.loc.y, (area_bottom - h).max(area.loc.y)),
        )
            .into(),
        (w, h).into(),
    )
}

/// The item whose rect overlaps `rect` the most (S3). Ties keep the first.
pub fn largest_overlap<T>(
    rect: Rect,
    candidates: impl IntoIterator<Item = (T, Rect)>,
) -> Option<T> {
    let mut best: Option<(T, i64)> = None;
    for (item, candidate) in candidates {
        let Some(overlap) = rect.intersection(candidate) else {
            continue;
        };
        let area = overlap.size.w as i64 * overlap.size.h as i64;
        if area > 0 && best.as_ref().is_none_or(|(_, best_area)| area > *best_area) {
            best = Some((item, area));
        }
    }
    best.map(|(item, _)| item)
}

/// Where a window un-snapped by a drag lands: the restored `floating` size,
/// with the pointer at the same fraction across the title bar and the same
/// distance below the top edge it had when grabbed (S1).
pub fn drag_out_location(
    snapped: Rect,
    floating: Size<i32, Logical>,
    pointer: Point<f64, Logical>,
) -> Point<i32, Logical> {
    let fraction = if snapped.size.w > 0 {
        ((pointer.x - snapped.loc.x as f64) / snapped.size.w as f64).clamp(0.0, 1.0)
    } else {
        0.5
    };
    let below_top = (pointer.y - snapped.loc.y as f64).clamp(0.0, (floating.h - 1).max(0) as f64);
    Point::from((
        (pointer.x - fraction * floating.w as f64).round() as i32,
        (pointer.y - below_top).round() as i32,
    ))
}

/// Bring a saved floating rect back inside `area`: kept where it was when it
/// still overlaps, otherwise centred; never larger than the area.
pub fn restore_into(floating: Rect, area: Rect) -> Rect {
    let w = floating.size.w.clamp(1, area.size.w.max(1));
    let h = floating.size.h.clamp(1, area.size.h.max(1));
    let (x, y) = if floating.overlaps(area) {
        (floating.loc.x, floating.loc.y)
    } else {
        (
            area.loc.x + (area.size.w - w) / 2,
            area.loc.y + (area.size.h - h) / 2,
        )
    };
    Rectangle::new(
        (
            x.clamp(area.loc.x, area.loc.x + area.size.w - w),
            y.clamp(area.loc.y, area.loc.y + area.size.h - h),
        )
            .into(),
        (w, h).into(),
    )
}

/// A floating rect for a window that has never floated (it mapped maximized).
pub fn default_floating(area: Rect) -> Rect {
    let w = (area.size.w * 3 / 5).max(1);
    let h = (area.size.h * 7 / 10).max(1);
    Rectangle::new(
        (
            area.loc.x + (area.size.w - w) / 2,
            area.loc.y + (area.size.h - h) / 2,
        )
            .into(),
        (w, h).into(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rect(x: i32, y: i32, w: i32, h: i32) -> Rect {
        Rectangle::new((x, y).into(), (w, h).into())
    }

    fn tile(position: TilePosition) -> Tile {
        Tile {
            position,
            output: "eDP-1".into(),
        }
    }

    // A 2419×1571 logical work area below a 30 px top panel, as on the M1 Pro.
    fn work() -> Rect {
        rect(0, 30, 2419, 1541)
    }

    #[test]
    fn edge_zones_respect_offset_output_and_corner_precedence() {
        let area = rect(-1920, 30, 1920, 1080);
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

    #[test]
    fn halves_and_quarters_cover_the_area_without_gaps_on_odd_sizes() {
        let area = work();
        let left = tile_rect(area, TilePosition::Left);
        let right = tile_rect(area, TilePosition::Right);
        assert_eq!(left, rect(0, 30, 1209, 1541));
        assert_eq!(right, rect(1209, 30, 1210, 1541));
        let tl = tile_rect(area, TilePosition::TopLeft);
        let bl = tile_rect(area, TilePosition::BottomLeft);
        assert_eq!(tl.size.h + bl.size.h, area.size.h);
        assert_eq!(bl.loc.y, tl.loc.y + tl.size.h);
    }

    #[test]
    fn degenerate_work_area_still_yields_a_positive_zone() {
        // S12: `1.min(width)` used to allow 0×0 zones.
        let zone = tile_rect(rect(0, 0, 1, 1), TilePosition::Left);
        assert_eq!(zone.size, Size::from((1, 1)));
    }

    #[test]
    fn hinted_size_grows_to_minimum_and_never_exceeds_the_area() {
        let zone = Size::from((1209, 1541));
        let area = work().size;
        assert_eq!(hinted_size(zone, (0, 0).into(), (0, 0).into(), area), zone);
        assert_eq!(
            hinted_size(zone, (1400, 400).into(), (0, 0).into(), area),
            Size::from((1400, 1541))
        );
        assert_eq!(
            hinted_size(zone, (3000, 0).into(), (0, 0).into(), area),
            Size::from((2419, 1541))
        );
        assert_eq!(
            hinted_size(zone, (0, 0).into(), (800, 600).into(), area),
            Size::from((800, 600))
        );
    }

    #[test]
    fn oversized_right_tile_grows_inward_instead_of_running_off_screen() {
        let area = work();
        let zone = tile_rect(area, TilePosition::Right);
        let fitted = fit_to_zone(zone, area, TilePosition::Right, (1400, 1541).into());
        assert_eq!(fitted.loc.x + fitted.size.w, area.loc.x + area.size.w);
        assert_eq!(fitted, rect(1019, 30, 1400, 1541));
    }

    #[test]
    fn undersized_tiles_hug_their_outer_corner() {
        let area = work();
        let br = tile_rect(area, TilePosition::BottomRight);
        let fitted = fit_to_zone(br, area, TilePosition::BottomRight, (600, 400).into());
        assert_eq!(fitted.loc.x + fitted.size.w, 2419);
        assert_eq!(fitted.loc.y + fitted.size.h, 30 + 1541);
        let tl = tile_rect(area, TilePosition::TopLeft);
        let fitted = fit_to_zone(tl, area, TilePosition::TopLeft, (600, 400).into());
        assert_eq!(fitted.loc, Point::from((0, 30)));
    }

    #[test]
    fn exact_fit_is_the_zone() {
        let area = work();
        for position in [
            TilePosition::Left,
            TilePosition::Right,
            TilePosition::TopLeft,
            TilePosition::TopRight,
            TilePosition::BottomLeft,
            TilePosition::BottomRight,
        ] {
            let zone = tile_rect(area, position);
            assert_eq!(
                fit_to_zone(zone, area, position, zone.size),
                zone,
                "{position:?}"
            );
        }
    }

    #[test]
    fn tiled_edges_follow_the_work_area_and_leave_the_split_resizable() {
        assert_eq!(
            TilePosition::Left.tiled_edges(),
            Edges {
                left: true,
                right: false,
                top: true,
                bottom: true
            }
        );
        assert_eq!(
            TilePosition::BottomRight.tiled_edges(),
            Edges {
                left: false,
                right: true,
                top: false,
                bottom: true
            }
        );
    }

    #[test]
    fn largest_overlap_ignores_shadows_spilling_onto_a_neighbour() {
        // S3: a window on the right monitor whose bbox pokes 20 px into the left one.
        let outputs = [
            ("DP-1", rect(0, 0, 1920, 1080)),
            ("eDP-1", rect(1920, 0, 2419, 1571)),
        ];
        assert_eq!(
            largest_overlap(rect(1900, 100, 900, 700), outputs),
            Some("eDP-1")
        );
        assert_eq!(
            largest_overlap(rect(10, 10, 300, 300), outputs),
            Some("DP-1")
        );
        assert_eq!(largest_overlap(rect(-500, -500, 10, 10), outputs), None);
    }

    #[test]
    fn snapping_then_restoring_returns_the_pre_snap_rect() {
        let floating = rect(300, 200, 900, 640);
        let mut record = WindowRecord::default();
        record.tile(tile(TilePosition::Left), floating);
        // Re-tiling elsewhere must not overwrite the floating rect with a zone.
        record.tile(tile(TilePosition::Right), rect(1209, 30, 1210, 1541));
        assert_eq!(
            record.placement,
            Placement::Tiled(tile(TilePosition::Right))
        );
        assert_eq!(record.float(), Some(floating));
        assert!(record.placement.is_floating());
    }

    #[test]
    fn maximize_remembers_a_tile_and_unmaximize_returns_to_it() {
        // S2: maximize and snap used to erase each other.
        let floating = rect(300, 200, 900, 640);
        let mut record = WindowRecord::default();
        record.tile(tile(TilePosition::Left), floating);
        assert!(record.maximize(rect(0, 30, 1209, 1541)));
        assert!(!record.maximize(rect(0, 30, 2419, 1541)));
        assert!(record.unmaximize());
        assert_eq!(record.placement, Placement::Tiled(tile(TilePosition::Left)));
        assert_eq!(record.floating, Some(floating));
    }

    #[test]
    fn fullscreen_nests_over_maximize_and_unwinds_in_order() {
        let mut record = WindowRecord::default();
        record.maximize(rect(10, 10, 800, 600));
        assert!(record.fullscreen(rect(0, 30, 2419, 1541)));
        assert!(!record.fullscreen(rect(0, 0, 2419, 1571)));
        assert!(record.unfullscreen());
        assert!(record.placement.is_maximized());
        assert!(record.unmaximize());
        assert!(record.placement.is_floating());
        assert_eq!(record.floating, Some(rect(10, 10, 800, 600)));
    }

    #[test]
    fn maximize_requests_while_fullscreen_change_only_the_prior() {
        let mut record = WindowRecord::default();
        record.fullscreen(rect(10, 10, 800, 600));
        assert!(record.maximize(rect(0, 0, 2419, 1571)));
        assert_eq!(record.placement.label(), "fullscreen(maximized(floating))");
        assert!(record.unmaximize());
        assert_eq!(record.placement.label(), "fullscreen(floating)");
        // Fullscreen geometry must not replace the floating rect.
        assert_eq!(record.floating, Some(rect(10, 10, 800, 600)));
    }

    #[test]
    fn tiling_a_fullscreen_window_waits_for_fullscreen_to_end() {
        let mut record = WindowRecord::default();
        record.fullscreen(rect(10, 10, 800, 600));
        record.tile(tile(TilePosition::Right), rect(0, 0, 2419, 1571));
        assert!(record.placement.is_fullscreen());
        record.unfullscreen();
        assert_eq!(
            record.placement,
            Placement::Tiled(tile(TilePosition::Right))
        );
    }

    #[test]
    fn retarget_moves_remembered_tiles_with_the_window() {
        let mut placement = Placement::Fullscreen {
            prior: Box::new(Placement::Maximized {
                prior: Box::new(Placement::Tiled(tile(TilePosition::Left))),
            }),
        };
        placement.retarget("DP-1");
        let mut record = WindowRecord {
            placement,
            ..Default::default()
        };
        assert_eq!(
            record
                .placement
                .resting_tile()
                .map(|tile| tile.output.as_str()),
            Some("DP-1")
        );
        record.unfullscreen();
        record.unmaximize();
        assert_eq!(
            record.placement.tile().map(|tile| tile.output.as_str()),
            Some("DP-1")
        );
    }

    #[test]
    fn zero_sized_geometry_is_never_saved_as_the_floating_rect() {
        let mut record = WindowRecord::default();
        record.maximize(rect(0, 0, 0, 0));
        record.unmaximize();
        assert_eq!(record.floating, None);
    }

    #[test]
    fn super_arrows_toggle_and_step_back() {
        use Direction::*;
        use KeyOutcome as K;
        let floating = Placement::Floating;
        let left = Placement::Tiled(tile(TilePosition::Left));
        let right = Placement::Tiled(tile(TilePosition::Right));
        let maximized = Placement::Maximized {
            prior: Box::new(left.clone()),
        };
        let fullscreen = Placement::Fullscreen {
            prior: Box::new(Placement::Floating),
        };
        assert_eq!(
            directional_outcome(&floating, Left),
            K::Tile(TilePosition::Left)
        );
        assert_eq!(
            directional_outcome(&floating, Right),
            K::Tile(TilePosition::Right)
        );
        assert_eq!(directional_outcome(&left, Left), K::Float);
        assert_eq!(directional_outcome(&left, Right), K::Float);
        assert_eq!(directional_outcome(&right, Left), K::Float);
        assert_eq!(directional_outcome(&floating, Up), K::Maximize);
        assert_eq!(directional_outcome(&left, Up), K::Maximize);
        assert_eq!(directional_outcome(&maximized, Up), K::Nothing);
        assert_eq!(directional_outcome(&maximized, Down), K::Unmaximize);
        assert_eq!(
            directional_outcome(&maximized, Left),
            K::Tile(TilePosition::Left)
        );
        assert_eq!(directional_outcome(&left, Down), K::Float);
        assert_eq!(directional_outcome(&floating, Down), K::Nothing);
        for direction in [Left, Right, Up, Down] {
            assert_eq!(directional_outcome(&fullscreen, direction), K::Nothing);
        }
    }

    #[test]
    fn super_arrows_move_quarters_sideways_and_grow_them_to_halves() {
        use Direction::*;
        let at = |position| Placement::Tiled(tile(position));
        assert_eq!(
            directional_outcome(&at(TilePosition::TopRight), Left),
            KeyOutcome::Tile(TilePosition::TopLeft)
        );
        assert_eq!(
            directional_outcome(&at(TilePosition::BottomLeft), Right),
            KeyOutcome::Tile(TilePosition::BottomRight)
        );
        assert_eq!(
            directional_outcome(&at(TilePosition::TopLeft), Left),
            KeyOutcome::Tile(TilePosition::Left)
        );
        assert_eq!(
            directional_outcome(&at(TilePosition::BottomRight), Right),
            KeyOutcome::Tile(TilePosition::Right)
        );
    }

    #[test]
    fn quarter_shortcut_toggles() {
        let tl = Placement::Tiled(tile(TilePosition::TopLeft));
        assert_eq!(
            quarter_outcome(&tl, TilePosition::TopLeft),
            KeyOutcome::Float
        );
        assert_eq!(
            quarter_outcome(&tl, TilePosition::BottomLeft),
            KeyOutcome::Tile(TilePosition::BottomLeft)
        );
        assert_eq!(
            quarter_outcome(&Placement::Floating, TilePosition::TopLeft),
            KeyOutcome::Tile(TilePosition::TopLeft)
        );
    }

    #[test]
    fn drag_out_keeps_the_pointer_at_the_same_point_of_the_title_bar() {
        // Grab a right-half tile 3/4 of the way across, 14 px below its top.
        let snapped = rect(1209, 30, 1200, 1541);
        let pointer = Point::from((1209.0 + 900.0, 44.0));
        let location = drag_out_location(snapped, (800, 600).into(), pointer);
        assert_eq!(location, Point::from((1509, 30)));
        // The pointer is still 3/4 across the restored 800 px window.
        assert_eq!(pointer.x - location.x as f64, 600.0);
    }

    #[test]
    fn drag_out_never_leaves_the_pointer_below_a_short_window() {
        let snapped = rect(0, 30, 1209, 1541);
        let location = drag_out_location(snapped, (400, 300).into(), (100.0, 900.0).into());
        assert!(900 - location.y < 300);
    }

    #[test]
    fn restore_keeps_an_overlapping_rect_and_recentres_a_foreign_one() {
        let area = work();
        assert_eq!(
            restore_into(rect(300, 200, 900, 640), area),
            rect(300, 200, 900, 640)
        );
        // Partly below the dock: pulled back in.
        assert_eq!(
            restore_into(rect(300, 1400, 900, 640), area),
            rect(300, 931, 900, 640)
        );
        // Saved on another monitor: centred here.
        assert_eq!(
            restore_into(rect(-1500, 200, 900, 640), area),
            rect(759, 480, 900, 640)
        );
        // Larger than the area: shrunk to it.
        assert_eq!(restore_into(rect(0, 0, 4000, 3000), area), area);
    }

    #[test]
    fn default_floating_is_centred_inside_the_area() {
        let area = work();
        let floating = default_floating(area);
        assert!(area.contains_rect(floating));
        assert_eq!(
            floating.loc.x - area.loc.x,
            area.loc.x + area.size.w - (floating.loc.x + floating.size.w)
        );
    }
}
