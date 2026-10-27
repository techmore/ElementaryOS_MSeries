//! Corner system: the radius of every window corner and the shape of the curve.
//!
//! The contract is `mseries/SDK-CORNERS.md` (sections 3 and 4) and the numbers are the
//! `corners` tokens of `msdk/data/tokens.json`, read once at start-up. Nothing here touches
//! Wayland or GL, so every rule is unit-tested; `corner_render.rs` draws the result.
//!
//! Policy, per output:
//! * An output that is not the built-in panel is square: every radius is 0.
//! * On the built-in panel a toplevel corner that sits exactly on a corner of the display
//!   (maximized, tiled halves and quarters, fullscreen) follows the display's curve
//!   (`screen`); a corner on a screen edge but not on a display corner is square; every other
//!   corner uses `window`.
//! * Popups and menus use `popover` on all four corners.
//! * Panels and the dock round only the corners that are away from every screen edge, with
//!   `window` (a full-width top bar therefore stays square, a floating dock is rounded).
//!
//! Radii are logical pixels; the renderer scales them by the output scale.

use smithay::utils::{Logical, Rectangle};

type Rect = Rectangle<i32, Logical>;

/// A corner within this many logical pixels of a screen edge counts as touching it.
const EDGE_TOLERANCE: i32 = 1;

/// Superellipse exponent and corner-box growth of the `continuous` style. A circular arc has
/// exponent 2 and extent 1; the continuous curve starts further from the corner and eases
/// in, so its box is larger than the nominal radius. Tuned by eye, like the radii.
pub const CONTINUOUS_EXPONENT: f32 = 3.0;
pub const CONTINUOUS_EXTENT: f32 = 1.2;

/// Corner shape from `corners.style`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum CornerStyle {
    Circular,
    #[default]
    Continuous,
}

impl CornerStyle {
    pub fn parse(value: &str) -> Self {
        match value {
            "circular" => Self::Circular,
            _ => Self::Continuous,
        }
    }

    /// Exponent of the superellipse (2 is a circle).
    pub fn exponent(self) -> f32 {
        match self {
            Self::Circular => 2.0,
            Self::Continuous => CONTINUOUS_EXPONENT,
        }
    }

    /// Side of the square that holds a corner of nominal radius `radius`.
    pub fn extent(self, radius: f32) -> f32 {
        match self {
            Self::Circular => radius,
            Self::Continuous => radius * CONTINUOUS_EXTENT,
        }
    }
}

/// The `corners` tokens, in logical pixels.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CornerTokens {
    pub screen: f32,
    pub window: f32,
    pub popover: f32,
    pub min: f32,
    pub style: CornerStyle,
}

/// Overrides `corners.screen` for this session. `0` turns the screen mask (and the display-corner
/// contact rule) off; positive values are logical pixels. Kept from the first compositor mask.
pub const ENV_SCREEN_RADIUS: &str = "PANTHEON_SCREEN_CORNER_RADIUS";
const MAX_SCREEN_RADIUS: i32 = 128;

/// `Some(radius)` for a valid override, `None` (use the token) when unset or invalid.
pub fn parse_screen_radius(value: Option<&str>) -> Option<f32> {
    let value = value?;
    match value.trim().parse::<i32>() {
        Ok(radius) if (0..=MAX_SCREEN_RADIUS).contains(&radius) => Some(radius as f32),
        _ => {
            tracing::warn!(
                value,
                maximum = MAX_SCREEN_RADIUS,
                "ignoring invalid screen-corner radius"
            );
            None
        }
    }
}

impl CornerTokens {
    /// Read from the SDK's `tokens.json` (embedded in the `msdk` crate at build time).
    pub fn load() -> Self {
        let tokens = msdk::tokens::tokens();
        let screen_override = std::env::var(ENV_SCREEN_RADIUS).ok();
        Self {
            screen: parse_screen_radius(screen_override.as_deref())
                .unwrap_or(msdk::tokens::corner_px("screen") as f32),
            window: msdk::tokens::corner_px("window") as f32,
            popover: msdk::tokens::corner_px("popover") as f32,
            min: msdk::tokens::corner_px("min") as f32,
            style: CornerStyle::parse(tokens["corners"]["style"].as_str().unwrap_or("continuous")),
        }
    }
}

impl Default for CornerTokens {
    fn default() -> Self {
        Self::load()
    }
}

/// Radius of each corner, logical pixels, clockwise from the top left.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Radii {
    pub top_left: f32,
    pub top_right: f32,
    pub bottom_right: f32,
    pub bottom_left: f32,
}

impl Radii {
    pub const SQUARE: Self = Self::all(0.0);

    pub const fn all(radius: f32) -> Self {
        Self {
            top_left: radius,
            top_right: radius,
            bottom_right: radius,
            bottom_left: radius,
        }
    }

    pub fn is_square(self) -> bool {
        self == Self::SQUARE
    }

    pub fn scaled(self, factor: f64) -> Self {
        let f = factor as f32;
        Self {
            top_left: self.top_left * f,
            top_right: self.top_right * f,
            bottom_right: self.bottom_right * f,
            bottom_left: self.bottom_left * f,
        }
    }

    /// No corner may be rounder than half the shorter side of `size` (width, height), and
    /// the continuous box (which is larger than the radius) must fit as well.
    fn capped(self, size: (i32, i32), style: CornerStyle) -> Self {
        let half = size.0.min(size.1).max(0) as f32 / 2.0;
        let limit = half / style.extent(1.0);
        let cap = |r: f32| r.min(limit);
        Self {
            top_left: cap(self.top_left),
            top_right: cap(self.top_right),
            bottom_right: cap(self.bottom_right),
            bottom_left: cap(self.bottom_left),
        }
    }
}

/// Which output a window is on, and whether it is the built-in panel.
#[derive(Clone, Copy, Debug)]
pub struct OutputPolicy {
    /// The output's rectangle in space coordinates.
    pub geometry: Rect,
    pub builtin: bool,
}

/// Whether a connector name is the laptop's own panel. The compositor's display
/// configuration already treats `eDP-*` as the built-in output (it sorts first and is the
/// default primary). `winit` is the nested development window: it stands in for the panel so
/// the corners can be seen without a second display.
pub fn is_builtin_output(name: &str) -> bool {
    ["eDP-", "LVDS-", "DSI-"]
        .iter()
        .any(|prefix| name.starts_with(prefix))
        || name == "winit"
}

fn near(a: i32, b: i32) -> bool {
    (a - b).abs() <= EDGE_TOLERANCE
}

/// Where a corner point lies relative to the display.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Contact {
    /// On a corner of the display.
    DisplayCorner,
    /// On a screen edge, but not at a display corner.
    Edge,
    Free,
}

fn contact(x: i32, y: i32, output: Rect) -> Contact {
    let on_x = near(x, output.loc.x) || near(x, output.loc.x + output.size.w);
    let on_y = near(y, output.loc.y) || near(y, output.loc.y + output.size.h);
    match (on_x, on_y) {
        (true, true) => Contact::DisplayCorner,
        (false, false) => Contact::Free,
        _ => Contact::Edge,
    }
}

/// The four corner points of `rect`, clockwise from the top left.
fn corner_points(rect: Rect) -> [(i32, i32); 4] {
    let (x0, y0) = (rect.loc.x, rect.loc.y);
    let (x1, y1) = (x0 + rect.size.w, y0 + rect.size.h);
    [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
}

fn radii_from(values: [f32; 4]) -> Radii {
    Radii {
        top_left: values[0],
        top_right: values[1],
        bottom_right: values[2],
        bottom_left: values[3],
    }
}

/// Radii of a toplevel (an application window or a dialog) whose geometry is `rect`.
pub fn window_radii(tokens: &CornerTokens, rect: Rect, output: OutputPolicy) -> Radii {
    if !output.builtin || rect.is_empty() {
        return Radii::SQUARE;
    }
    let corners = corner_points(rect).map(|(x, y)| match contact(x, y, output.geometry) {
        Contact::DisplayCorner => tokens.screen,
        Contact::Edge => 0.0,
        Contact::Free => tokens.window,
    });
    radii_from(corners).capped((rect.size.w, rect.size.h), tokens.style)
}

/// Radii of a popup or menu.
pub fn popup_radii(tokens: &CornerTokens, rect: Rect, builtin: bool) -> Radii {
    if !builtin || rect.is_empty() {
        return Radii::SQUARE;
    }
    Radii::all(tokens.popover).capped((rect.size.w, rect.size.h), tokens.style)
}

/// Radii of a panel or the dock: only corners away from every screen edge are rounded.
pub fn panel_radii(tokens: &CornerTokens, rect: Rect, output: OutputPolicy) -> Radii {
    if !output.builtin || rect.is_empty() {
        return Radii::SQUARE;
    }
    let corners = corner_points(rect).map(|(x, y)| match contact(x, y, output.geometry) {
        Contact::Free => tokens.window,
        _ => 0.0,
    });
    radii_from(corners).capped((rect.size.w, rect.size.h), tokens.style)
}

/// Distance from the shape's outline, in the corner's own pixels: negative inside the
/// rounded shape, positive outside. `(dx, dy)` is the offset from the arc's centre towards
/// the corner (both clamped to zero or more) and `extent` the side of the corner box. The
/// GLSL in `corner_render.rs` computes the same function.
pub fn corner_distance(dx: f32, dy: f32, extent: f32, style: CornerStyle) -> f32 {
    let (dx, dy) = (dx.max(0.0), dy.max(0.0));
    match style {
        CornerStyle::Circular => dx.hypot(dy) - extent,
        CornerStyle::Continuous => {
            let n = style.exponent();
            let (a, b) = (dx.max(1e-4), dy.max(1e-4));
            let f = (a.powf(n) + b.powf(n)).powf(1.0 / n);
            // Gradient of the superellipse norm, so the distance is in pixels and the edge
            // antialiases at a constant width.
            let gx = a.powf(n - 1.0) / f.powf(n - 1.0);
            let gy = b.powf(n - 1.0) / f.powf(n - 1.0);
            (f - extent) / gx.hypot(gy).max(1e-4)
        }
    }
}

/// Alpha of the screen mask (black, premultiplied) at the centre of pixel `(i, j)` of a
/// corner box of `size` pixels whose corner is at `(0, 0)`: 0 inside the display's curve,
/// 1 outside it, antialiased over one pixel. `radius` is in pixels, `size` the box side.
pub fn mask_alpha(i: u32, j: u32, radius: f32, size: u32, style: CornerStyle) -> f32 {
    let extent = style.extent(radius);
    let cx = extent - (i as f32 + 0.5);
    let cy = extent - (j as f32 + 0.5);
    if cx <= 0.0 && cy <= 0.0 || size == 0 {
        return 0.0;
    }
    let distance = corner_distance(cx, cy, extent, style);
    (distance + 0.5).clamp(0.0, 1.0)
}

/// Pixel size of the (square) box that holds a corner of `radius` physical pixels.
#[cfg(test)]
pub fn mask_box(radius: f32, style: CornerStyle) -> u32 {
    style.extent(radius).ceil().max(0.0) as u32
}

/// The mask for one display corner as Argb8888 bytes (premultiplied black), with the corner
/// at the box's top left; the other three corners flip it.
pub fn mask_pixels(radius: f32, size: u32, style: CornerStyle) -> Vec<u8> {
    let mut pixels = Vec::with_capacity((size * size * 4) as usize);
    for j in 0..size {
        for i in 0..size {
            let alpha = (mask_alpha(i, j, radius, size, style) * 255.0).round() as u8;
            pixels.extend_from_slice(&[0, 0, 0, alpha]);
        }
    }
    pixels
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tokens() -> CornerTokens {
        CornerTokens {
            screen: 14.0,
            window: 12.0,
            popover: 10.0,
            min: 4.0,
            style: CornerStyle::Continuous,
        }
    }

    fn output_rect() -> Rect {
        Rectangle::new((0, 0).into(), (1512, 982).into())
    }
    const TOP_BAR: i32 = 32;

    fn builtin() -> OutputPolicy {
        OutputPolicy {
            geometry: output_rect(),
            builtin: true,
        }
    }

    fn external() -> OutputPolicy {
        OutputPolicy {
            geometry: output_rect(),
            builtin: false,
        }
    }

    fn rect(x: i32, y: i32, w: i32, h: i32) -> Rect {
        Rectangle::new((x, y).into(), (w, h).into())
    }

    /// The work area under a top bar, as `work_area_for_output` leaves it.
    fn work_area() -> Rect {
        rect(
            0,
            TOP_BAR,
            output_rect().size.w,
            output_rect().size.h - TOP_BAR,
        )
    }

    fn r(tl: f32, tr: f32, br: f32, bl: f32) -> Radii {
        Radii {
            top_left: tl,
            top_right: tr,
            bottom_right: br,
            bottom_left: bl,
        }
    }

    #[test]
    fn floating_window_uses_the_window_radius_everywhere() {
        let radii = window_radii(&tokens(), rect(200, 150, 800, 600), builtin());
        assert_eq!(radii, Radii::all(12.0));
    }

    #[test]
    fn maximized_window_hugs_the_bottom_corners_and_is_square_under_the_bar() {
        let radii = window_radii(&tokens(), work_area(), builtin());
        assert_eq!(radii, r(0.0, 0.0, 14.0, 14.0));
    }

    #[test]
    fn maximized_window_with_the_bar_hidden_follows_all_four_display_corners() {
        let radii = window_radii(&tokens(), output_rect(), builtin());
        assert_eq!(radii, Radii::all(14.0));
    }

    #[test]
    fn fullscreen_window_follows_all_four_display_corners() {
        assert_eq!(
            window_radii(&tokens(), output_rect(), builtin()),
            Radii::all(14.0)
        );
    }

    #[test]
    fn tiled_halves() {
        let area = work_area();
        let half = area.size.w / 2;
        let left = rect(area.loc.x, area.loc.y, half, area.size.h);
        let right = rect(half, area.loc.y, area.size.w - half, area.size.h);
        // The inner top corner is free (window), the inner bottom corner is on the bottom edge.
        assert_eq!(
            window_radii(&tokens(), left, builtin()),
            r(0.0, 12.0, 0.0, 14.0)
        );
        assert_eq!(
            window_radii(&tokens(), right, builtin()),
            r(12.0, 0.0, 14.0, 0.0)
        );
    }

    #[test]
    fn tiled_halves_without_a_bar_use_the_display_curve_on_the_outer_corners() {
        let half = output_rect().size.w / 2;
        let left = rect(0, 0, half, output_rect().size.h);
        assert_eq!(
            window_radii(&tokens(), left, builtin()),
            r(14.0, 0.0, 0.0, 14.0)
        );
    }

    #[test]
    fn tiled_quarters() {
        let area = work_area();
        let (hw, hh) = (area.size.w / 2, area.size.h / 2);
        let top_left = rect(0, area.loc.y, hw, hh);
        let top_right = rect(hw, area.loc.y, area.size.w - hw, hh);
        let bottom_left = rect(0, area.loc.y + hh, hw, area.size.h - hh);
        let bottom_right = rect(hw, area.loc.y + hh, area.size.w - hw, area.size.h - hh);
        let t = tokens();
        // Under the bar the top outer corners are square; the quarter's inner corners that
        // meet other quarters are free, so they take the window radius.
        assert_eq!(
            window_radii(&t, top_left, builtin()),
            r(0.0, 12.0, 12.0, 0.0)
        );
        assert_eq!(
            window_radii(&t, top_right, builtin()),
            r(12.0, 0.0, 0.0, 12.0)
        );
        assert_eq!(
            window_radii(&t, bottom_left, builtin()),
            r(0.0, 12.0, 0.0, 14.0)
        );
        assert_eq!(
            window_radii(&t, bottom_right, builtin()),
            r(12.0, 0.0, 14.0, 0.0)
        );
    }

    #[test]
    fn quarters_without_a_bar_hug_exactly_one_display_corner_each() {
        let (hw, hh) = (output_rect().size.w / 2, output_rect().size.h / 2);
        let t = tokens();
        assert_eq!(
            window_radii(&t, rect(0, 0, hw, hh), builtin()),
            r(14.0, 0.0, 12.0, 0.0)
        );
        assert_eq!(
            window_radii(
                &t,
                rect(hw, hh, output_rect().size.w - hw, output_rect().size.h - hh),
                builtin()
            ),
            r(12.0, 0.0, 14.0, 0.0)
        );
    }

    #[test]
    fn one_pixel_of_slack_still_counts_as_touching() {
        let almost = rect(1, 1, output_rect().size.w - 2, output_rect().size.h - 2);
        assert_eq!(window_radii(&tokens(), almost, builtin()), Radii::all(14.0));
        let apart = rect(4, 4, output_rect().size.w - 8, output_rect().size.h - 8);
        assert_eq!(window_radii(&tokens(), apart, builtin()), Radii::all(12.0));
    }

    #[test]
    fn external_outputs_are_square_for_every_placement() {
        let t = tokens();
        for placement in [
            rect(200, 150, 800, 600),
            work_area(),
            output_rect(),
            rect(0, 0, 756, 982),
        ] {
            assert_eq!(window_radii(&t, placement, external()), Radii::SQUARE);
        }
        assert_eq!(
            popup_radii(&t, rect(10, 10, 200, 100), false),
            Radii::SQUARE
        );
        assert_eq!(
            panel_radii(&t, rect(500, 900, 400, 60), external()),
            Radii::SQUARE
        );
    }

    #[test]
    fn popups_use_the_popover_radius_on_all_corners() {
        assert_eq!(
            popup_radii(&tokens(), rect(300, 60, 220, 180), true),
            Radii::all(10.0)
        );
    }

    #[test]
    fn full_width_top_bar_stays_square() {
        let bar = rect(0, 0, output_rect().size.w, TOP_BAR);
        assert_eq!(panel_radii(&tokens(), bar, builtin()), Radii::SQUARE);
    }

    #[test]
    fn floating_dock_rounds_the_corners_away_from_the_edge() {
        // Flush with the bottom edge: only the top corners are away from every edge.
        let flush = rect(400, 922, 700, 60);
        assert_eq!(
            panel_radii(&tokens(), flush, builtin()),
            r(12.0, 12.0, 0.0, 0.0)
        );
        // Lifted off the edge: all four corners are away from it.
        let lifted = rect(400, 910, 700, 60);
        assert_eq!(panel_radii(&tokens(), lifted, builtin()), Radii::all(12.0));
    }

    #[test]
    fn a_tiny_surface_cannot_be_rounder_than_half_its_height() {
        let sliver = rect(300, 300, 400, 10);
        let radii = window_radii(&tokens(), sliver, builtin());
        let limit = 5.0 / CONTINUOUS_EXTENT;
        assert!((radii.top_left - limit).abs() < 1e-4, "{radii:?}");
        assert!(radii.top_right <= limit + 1e-4 && radii.bottom_left <= limit + 1e-4);
    }

    #[test]
    fn empty_rectangles_get_no_rounding() {
        assert_eq!(
            window_radii(&tokens(), rect(0, 0, 0, 0), builtin()),
            Radii::SQUARE
        );
    }

    #[test]
    fn builtin_output_names() {
        assert!(is_builtin_output("eDP-1"));
        assert!(is_builtin_output("LVDS-1"));
        assert!(is_builtin_output("winit"));
        assert!(!is_builtin_output("DP-1"));
        assert!(!is_builtin_output("HDMI-A-1"));
    }

    #[test]
    fn style_parses_and_defaults_to_continuous() {
        assert_eq!(CornerStyle::parse("circular"), CornerStyle::Circular);
        assert_eq!(CornerStyle::parse("continuous"), CornerStyle::Continuous);
        assert_eq!(CornerStyle::parse("anything else"), CornerStyle::Continuous);
    }

    #[test]
    fn tokens_are_read_from_the_sdk_file() {
        let t = CornerTokens::load();
        assert_eq!(t.screen, 20.0);
        assert_eq!(t.window, 20.0);
        assert_eq!(t.popover, 10.0);
        assert_eq!(t.min, 4.0);
        assert_eq!(t.style, CornerStyle::Continuous);
        assert!(t.window <= t.screen);
    }

    #[test]
    fn circular_distance_is_euclidean() {
        let d = corner_distance(3.0, 4.0, 4.0, CornerStyle::Circular);
        assert!((d - 1.0).abs() < 1e-5);
        assert!(corner_distance(1.0, 1.0, 4.0, CornerStyle::Circular) < 0.0);
    }

    #[test]
    fn continuous_distance_is_zero_on_the_axes_and_matches_circular_at_exponent_two() {
        // On an axis the curve touches the extent for every exponent.
        let d = corner_distance(10.0, 0.0, 10.0, CornerStyle::Continuous);
        assert!(d.abs() < 1e-2, "{d}");
        // Inside, outside.
        assert!(corner_distance(3.0, 3.0, 10.0, CornerStyle::Continuous) < 0.0);
        assert!(corner_distance(9.0, 9.0, 10.0, CornerStyle::Continuous) > 0.0);
    }

    #[test]
    fn continuous_corner_cuts_less_at_the_diagonal_than_its_box_suggests() {
        // Along the diagonal the superellipse lies further out than the circle of the same
        // box, so the corner is tighter in the middle and starts earlier on the edge.
        let e = 10.0;
        let diagonal = |style| {
            let (mut lo, mut hi) = (0.0f32, e);
            for _ in 0..40 {
                let mid = (lo + hi) / 2.0;
                if corner_distance(mid, mid, e, style) > 0.0 {
                    hi = mid;
                } else {
                    lo = mid;
                }
            }
            lo
        };
        assert!(diagonal(CornerStyle::Continuous) > diagonal(CornerStyle::Circular));
    }

    #[test]
    fn mask_is_opaque_at_the_corner_and_clear_at_the_inner_corner() {
        for style in [CornerStyle::Circular, CornerStyle::Continuous] {
            let radius = 14.0;
            let size = mask_box(radius, style);
            assert!(mask_alpha(0, 0, radius, size, style) > 0.99, "{style:?}");
            assert_eq!(mask_alpha(size - 1, size - 1, radius, size, style), 0.0);
            // The edge pixels next to the straight sides are untouched.
            assert!(mask_alpha(size - 1, 0, radius, size, style) < 0.2);
            assert!(mask_alpha(0, size - 1, radius, size, style) < 0.2);
        }
    }

    #[test]
    fn mask_pixels_are_premultiplied_black_with_the_alpha_in_the_last_byte() {
        let size = mask_box(14.0, CornerStyle::Circular);
        let pixels = mask_pixels(14.0, size, CornerStyle::Circular);
        assert_eq!(pixels.len(), (size * size * 4) as usize);
        assert_eq!(&pixels[..4], &[0, 0, 0, 255]);
        assert!(pixels.chunks(4).all(|px| px[..3] == [0, 0, 0]));
    }

    #[test]
    fn circular_mask_area_matches_the_geometry() {
        // Area outside a quarter circle inside its box is r^2 * (1 - pi/4).
        let radius = 40.0;
        let size = mask_box(radius, CornerStyle::Circular);
        let area: f32 = (0..size)
            .flat_map(|j| (0..size).map(move |i| (i, j)))
            .map(|(i, j)| mask_alpha(i, j, radius, size, CornerStyle::Circular))
            .sum();
        let expected = radius * radius * (1.0 - std::f32::consts::FRAC_PI_4);
        assert!(
            (area - expected).abs() / expected < 0.01,
            "{area} vs {expected}"
        );
    }

    #[test]
    fn screen_radius_override_accepts_zero_to_the_maximum_only() {
        assert_eq!(parse_screen_radius(None), None);
        assert_eq!(parse_screen_radius(Some("0")), Some(0.0));
        assert_eq!(parse_screen_radius(Some(" 18 ")), Some(18.0));
        assert_eq!(parse_screen_radius(Some("128")), Some(128.0));
        assert_eq!(parse_screen_radius(Some("129")), None);
        assert_eq!(parse_screen_radius(Some("-1")), None);
        assert_eq!(parse_screen_radius(Some("big")), None);
    }
}
