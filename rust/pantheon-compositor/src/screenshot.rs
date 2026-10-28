//! Logical-coordinate selection core for compositor-owned screenshots.
//! Rendering, input routing and file publication are wired separately.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Region {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

impl Region {
    pub fn between(a: (i32, i32), b: (i32, i32)) -> Option<Self> {
        let width = a.0.abs_diff(b.0);
        let height = a.1.abs_diff(b.1);
        (width > 0 && height > 0).then_some(Self {
            x: a.0.min(b.0),
            y: a.1.min(b.1),
            width,
            height,
        })
    }
}

/// Integer rectangle used by the selection overlay geometry (logical pixels).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Px {
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
}

impl Px {
    pub const fn new(x: i32, y: i32, w: i32, h: i32) -> Self {
        Self { x, y, w, h }
    }

    pub fn from_region(region: Region) -> Self {
        Self::new(
            region.x,
            region.y,
            region.width.min(i32::MAX as u32) as i32,
            region.height.min(i32::MAX as u32) as i32,
        )
    }

    pub fn intersect(self, other: Px) -> Option<Px> {
        let x0 = self.x.max(other.x);
        let y0 = self.y.max(other.y);
        let x1 =
            (i64::from(self.x) + i64::from(self.w)).min(i64::from(other.x) + i64::from(other.w));
        let y1 =
            (i64::from(self.y) + i64::from(self.h)).min(i64::from(other.y) + i64::from(other.h));
        let (w, h) = (x1 - i64::from(x0), y1 - i64::from(y0));
        (w > 0 && h > 0).then_some(Px::new(x0, y0, w as i32, h as i32))
    }

    pub fn right(self) -> i32 {
        self.x.saturating_add(self.w)
    }

    pub fn bottom(self) -> i32 {
        self.y.saturating_add(self.h)
    }
}

/// Logical border thickness that is about two device pixels at any scale.
pub fn border_thickness(scale: f64) -> i32 {
    if scale >= 1.75 { 1 } else { 2 }
}

/// Four bars (top, bottom, left, right) of a ring of `t` pixels inside `rect`.
pub fn ring_inside(rect: Px, t: i32) -> [Px; 4] {
    let t = t.min(rect.w / 2).min(rect.h / 2).max(0);
    [
        Px::new(rect.x, rect.y, rect.w, t),
        Px::new(rect.x, rect.bottom() - t, rect.w, t),
        Px::new(rect.x, rect.y + t, t, rect.h - 2 * t),
        Px::new(rect.right() - t, rect.y + t, t, rect.h - 2 * t),
    ]
}

/// Four bars of a ring of `t` pixels just outside `rect`.
pub fn ring_outside(rect: Px, t: i32) -> [Px; 4] {
    ring_inside(
        Px::new(rect.x - t, rect.y - t, rect.w + 2 * t, rect.h + 2 * t),
        t,
    )
}

/// The part of `area` outside `hole` as four bars (top, bottom, left, right).
/// A hole that misses the area dims all of it (in the first bar).
pub fn dim_bands(area: Px, hole: Px) -> [Option<Px>; 4] {
    let Some(hole) = hole.intersect(area) else {
        return [Some(area), None, None, None];
    };
    let keep = |r: Px| (r.w > 0 && r.h > 0).then_some(r);
    [
        keep(Px::new(area.x, area.y, area.w, hole.y - area.y)),
        keep(Px::new(
            area.x,
            hole.bottom(),
            area.w,
            area.bottom() - hole.bottom(),
        )),
        keep(Px::new(area.x, hole.y, hole.x - area.x, hole.h)),
        keep(Px::new(
            hole.right(),
            hole.y,
            area.right() - hole.right(),
            hole.h,
        )),
    ]
}

/// Device-pixel size of a logical region at a (possibly fractional) scale.
pub fn physical_size(region: Region, scale: f64) -> (u32, u32) {
    let conv = |v: u32| (f64::from(v) * scale).round().max(1.0) as u32;
    (conv(region.width), conv(region.height))
}

pub const DIGIT_W: i32 = 8;
pub const DIGIT_H: i32 = 14;
pub const SEG: i32 = 2;
pub const GLYPH_GAP: i32 = 4;
pub const X_W: i32 = 6;
pub const LABEL_PAD: i32 = 5;

/// Seven-segment lit masks (a,b,c,d,e,f,g = bits 0..6) for digits 0-9.
const SEGMENTS: [u8; 10] = [
    0b0111111, 0b0000110, 0b1011011, 0b1001111, 0b1100110, 0b1101101, 0b1111101, 0b0000111,
    0b1111111, 0b1101111,
];

fn digit_rects(digit: u8, ox: i32, oy: i32, out: &mut Vec<Px>) {
    let mask = SEGMENTS[usize::from(digit % 10)];
    let mid = (DIGIT_H - SEG) / 2;
    let rects = [
        Px::new(0, 0, DIGIT_W, SEG),
        Px::new(DIGIT_W - SEG, 0, SEG, DIGIT_H / 2 + SEG / 2),
        Px::new(
            DIGIT_W - SEG,
            DIGIT_H / 2 - SEG / 2,
            SEG,
            DIGIT_H / 2 + SEG / 2,
        ),
        Px::new(0, DIGIT_H - SEG, DIGIT_W, SEG),
        Px::new(0, DIGIT_H / 2 - SEG / 2, SEG, DIGIT_H / 2 + SEG / 2),
        Px::new(0, 0, SEG, DIGIT_H / 2 + SEG / 2),
        Px::new(0, mid, DIGIT_W, SEG),
    ];
    for (bit, r) in rects.into_iter().enumerate() {
        if mask & (1 << bit) != 0 {
            out.push(Px::new(ox + r.x, oy + r.y, r.w, r.h));
        }
    }
}

fn decimal(mut n: u32) -> Vec<u8> {
    let mut d = Vec::new();
    loop {
        d.push((n % 10) as u8);
        n /= 10;
        if n == 0 {
            break;
        }
    }
    d.reverse();
    d
}

/// Label "W x H" drawn from solid rectangles: (background, glyph rectangles),
/// positioned so the label's top-left is at `origin`.
pub fn size_label(width: u32, height: u32, origin: (i32, i32)) -> (Px, Vec<Px>) {
    let (w_digits, h_digits) = (decimal(width), decimal(height));
    let glyphs = (w_digits.len() + h_digits.len()) as i32;
    let inner_w = glyphs * DIGIT_W + (glyphs - 1) * GLYPH_GAP + 2 * GLYPH_GAP + X_W;
    let bg = Px::new(
        origin.0,
        origin.1,
        inner_w + 2 * LABEL_PAD,
        DIGIT_H + 2 * LABEL_PAD,
    );
    let mut rects = Vec::new();
    let mut x = origin.0 + LABEL_PAD;
    let y = origin.1 + LABEL_PAD;
    for d in &w_digits {
        digit_rects(*d, x, y, &mut rects);
        x += DIGIT_W + GLYPH_GAP;
    }
    let cy = y + (DIGIT_H - X_W) / 2;
    for (dx, dy) in [(0, 0), (4, 0), (2, 2), (0, 4), (4, 4)] {
        rects.push(Px::new(x + dx, cy + dy, 2, 2));
    }
    x += X_W + GLYPH_GAP;
    for d in &h_digits {
        digit_rects(*d, x, y, &mut rects);
        x += DIGIT_W + GLYPH_GAP;
    }
    (bg, rects)
}

/// Where the label's top-left goes: below the region's bottom-right corner,
/// flipped inside when it would leave `area`, and clamped horizontally.
pub fn label_origin(region: Px, area: Px, label_w: i32, label_h: i32) -> (i32, i32) {
    let margin = 6;
    let mut y = region.bottom() + margin;
    if y + label_h > area.bottom() {
        y = region.bottom() - margin - label_h;
    }
    let y = y.clamp(area.y, (area.bottom() - label_h).max(area.y));
    let x = (region.right() - label_w).clamp(area.x, (area.right() - label_w).max(area.x));
    (x, y)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CaptureTarget {
    AllOutputs,
    Region(Region),
    Window(Region),
}

/// With no input for this long, selecting cancels itself.
pub const IDLE_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(60);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Idle,
    Selecting,
    Dragging,
}

#[derive(Default, Debug)]
pub struct Selection {
    active: bool,
    anchor: Option<(i32, i32)>,
    pointer: (i32, i32),
    last_input: Option<std::time::Instant>,
    outputs: u64,
}

impl Selection {
    pub fn begin(&mut self, pointer: (i32, i32)) {
        self.active = true;
        self.anchor = None;
        self.pointer = pointer;
        self.last_input = Some(std::time::Instant::now());
    }

    pub fn phase(&self) -> Phase {
        match (self.active, self.anchor) {
            (false, _) => Phase::Idle,
            (true, None) => Phase::Selecting,
            (true, Some(_)) => Phase::Dragging,
        }
    }

    /// Remember the output layout the selection started on.
    pub fn set_outputs(&mut self, signature: u64) {
        self.outputs = signature;
    }

    /// Cancel and report true when the output layout is not the one the
    /// selection started on.
    pub fn cancel_if_outputs_changed(&mut self, signature: u64) -> bool {
        if self.active && self.outputs != signature {
            self.cancel();
            return true;
        }
        false
    }

    /// Time left before the idle timeout, or None when not selecting.
    pub fn idle_remaining(&self, now: std::time::Instant) -> Option<std::time::Duration> {
        if !self.active {
            return None;
        }
        let last = self.last_input?;
        Some(IDLE_TIMEOUT.saturating_sub(now.saturating_duration_since(last)))
    }

    /// Cancel and report true when idle for the whole timeout.
    pub fn cancel_if_idle(&mut self, now: std::time::Instant) -> bool {
        if self.idle_remaining(now) == Some(std::time::Duration::ZERO) {
            self.cancel();
            return true;
        }
        false
    }

    pub fn active(&self) -> bool {
        self.active
    }

    pub fn press(&mut self, point: (i32, i32)) {
        if self.active {
            self.anchor = Some(point);
            self.pointer = point;
            self.last_input = Some(std::time::Instant::now());
        }
    }

    pub fn motion(&mut self, point: (i32, i32)) {
        if self.active {
            self.pointer = point;
            self.last_input = Some(std::time::Instant::now());
        }
    }

    pub fn preview(&self) -> Option<Region> {
        self.anchor
            .and_then(|anchor| Region::between(anchor, self.pointer))
    }

    pub fn release(&mut self, point: (i32, i32)) -> Option<CaptureTarget> {
        if !self.active {
            return None;
        }
        self.motion(point);
        let target = self.preview().map(CaptureTarget::Region);
        self.cancel();
        target
    }

    pub fn capture_hovered_window(&mut self, bounds: Option<Region>) -> Option<CaptureTarget> {
        if !self.active {
            return None;
        }
        let bounds = bounds.filter(|bounds| bounds.width > 0 && bounds.height > 0)?;
        self.cancel();
        Some(CaptureTarget::Window(bounds))
    }

    pub fn cancel(&mut self) {
        self.active = false;
        self.anchor = None;
        self.last_input = None;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reverse_drag_preserves_negative_desktop_coordinates() {
        let mut selection = Selection::default();
        selection.begin((10, 20));
        selection.press((10, 20));
        selection.motion((-90, -30));
        let expected = Region {
            x: -90,
            y: -30,
            width: 100,
            height: 50,
        };
        assert_eq!(selection.preview(), Some(expected));
        assert_eq!(
            selection.release((-90, -30)),
            Some(CaptureTarget::Region(expected))
        );
        assert!(!selection.active());
        assert_eq!(selection.release((5, 5)), None);
    }

    #[test]
    fn click_and_cancel_do_not_capture_pixels() {
        let mut selection = Selection::default();
        selection.begin((0, 0));
        selection.press((0, 0));
        assert_eq!(selection.release((0, 0)), None);
        selection.begin((5, 5));
        selection.press((5, 5));
        selection.cancel();
        assert_eq!(selection.release((20, 20)), None);
    }

    #[test]
    fn space_without_a_window_keeps_selection_available() {
        let mut selection = Selection::default();
        selection.begin((0, 0));
        assert_eq!(selection.capture_hovered_window(None), None);
        assert!(selection.active());
        let window = Region {
            x: 10,
            y: 20,
            width: 300,
            height: 200,
        };
        assert_eq!(
            selection.capture_hovered_window(Some(window)),
            Some(CaptureTarget::Window(window))
        );
        assert!(!selection.active());
    }

    #[test]
    fn dim_bands_tile_the_area_minus_the_hole() {
        let area = Px::new(-100, 0, 400, 300);
        let hole = Px::new(0, 50, 100, 100);
        let covered: i64 = dim_bands(area, hole)
            .iter()
            .flatten()
            .map(|r| i64::from(r.w) * i64::from(r.h))
            .sum();
        assert_eq!(covered, 400 * 300 - 100 * 100);
        for band in dim_bands(area, hole).iter().flatten() {
            assert_eq!(band.intersect(hole), None);
        }
    }

    #[test]
    fn hole_clipped_to_one_monitor_and_missing_monitor() {
        let left = Px::new(0, 0, 100, 100);
        let hole = Px::new(60, 20, 200, 40); // spans onto the next monitor
        let covered: i64 = dim_bands(left, hole)
            .iter()
            .flatten()
            .map(|r| i64::from(r.w) * i64::from(r.h))
            .sum();
        assert_eq!(covered, 100 * 100 - 40 * 40);
        let far = Px::new(500, 500, 10, 10);
        assert_eq!(dim_bands(left, far), [Some(left), None, None, None]);
    }

    #[test]
    fn rings_hug_the_rectangle() {
        let r = Px::new(10, 10, 50, 30);
        let inside: i64 = ring_inside(r, 2).iter().map(|b| i64::from(b.w * b.h)).sum();
        assert_eq!(inside, 50 * 30 - 46 * 26);
        let out = ring_outside(r, 1);
        assert!(out.iter().all(|b| b.intersect(r).is_none()));
        assert!(
            ring_inside(Px::new(0, 0, 2, 2), 2)
                .iter()
                .all(|b| b.w >= 0 && b.h >= 0)
        );
    }

    #[test]
    fn thickness_and_physical_size_follow_scale() {
        assert_eq!(border_thickness(1.0), 2);
        assert_eq!(border_thickness(2.0), 1);
        let r = Region {
            x: 0,
            y: 0,
            width: 101,
            height: 50,
        };
        assert_eq!(physical_size(r, 1.0), (101, 50));
        assert_eq!(physical_size(r, 1.5), (152, 75));
        assert_eq!(physical_size(r, 2.0), (202, 100));
    }

    #[test]
    fn label_has_glyphs_inside_its_background_and_flips_at_the_edge() {
        let (bg, glyphs) = size_label(1280, 720, (0, 0));
        assert!(!glyphs.is_empty());
        assert!(glyphs.iter().all(|g| g.intersect(bg) == Some(*g)));
        let (_, eight) = size_label(8, 8, (0, 0));
        let (_, one) = size_label(1, 1, (0, 0));
        assert_eq!(eight.len() - one.len(), 2 * (7 - 2));
        let area = Px::new(0, 0, 800, 600);
        let normal = label_origin(Px::new(100, 100, 200, 100), area, bg.w, bg.h);
        assert_eq!(normal.1, 206);
        let flipped = label_origin(Px::new(100, 300, 200, 300), area, bg.w, bg.h);
        assert!(flipped.1 + bg.h <= 600);
        let clamped = label_origin(Px::new(0, 0, 20, 20), area, bg.w, bg.h);
        assert_eq!(clamped.0, 0);
    }

    #[test]
    fn every_exit_returns_to_idle() {
        let mut s = Selection::default();
        assert_eq!(s.phase(), Phase::Idle);
        s.begin((0, 0));
        assert_eq!(s.phase(), Phase::Selecting);
        s.press((1, 1));
        assert_eq!(s.phase(), Phase::Dragging);
        // Cancel (Esc, right-click, repeat shortcut, lock) at any phase.
        s.cancel();
        assert_eq!(s.phase(), Phase::Idle);
        s.begin((0, 0));
        s.cancel();
        assert_eq!(s.phase(), Phase::Idle);
        // Zero-size click, real drag and window pick all end idle.
        s.begin((0, 0));
        s.press((3, 3));
        assert_eq!(s.release((3, 3)), None);
        assert_eq!(s.phase(), Phase::Idle);
        s.begin((0, 0));
        s.press((3, 3));
        assert!(s.release((9, 9)).is_some());
        assert_eq!(s.phase(), Phase::Idle);
        s.begin((0, 0));
        let w = Region {
            x: 0,
            y: 0,
            width: 5,
            height: 5,
        };
        assert!(s.capture_hovered_window(Some(w)).is_some());
        assert_eq!(s.phase(), Phase::Idle);
        // Input after cancel does nothing.
        s.press((1, 1));
        s.motion((2, 2));
        assert_eq!(s.phase(), Phase::Idle);
        assert_eq!(s.preview(), None);
    }

    #[test]
    fn idle_timeout_cancels_only_after_sixty_quiet_seconds() {
        let mut s = Selection::default();
        let now = std::time::Instant::now();
        assert_eq!(s.idle_remaining(now), None);
        s.begin((0, 0));
        assert!(!s.cancel_if_idle(now + std::time::Duration::from_secs(59)));
        assert!(s.active());
        assert!(s.cancel_if_idle(now + IDLE_TIMEOUT + std::time::Duration::from_secs(1)));
        assert_eq!(s.phase(), Phase::Idle);
        assert!(!s.cancel_if_idle(now + std::time::Duration::from_secs(500)));
    }

    #[test]
    fn output_change_cancels_an_active_selection_only() {
        let mut s = Selection::default();
        assert!(!s.cancel_if_outputs_changed(7));
        s.begin((0, 0));
        s.set_outputs(1);
        assert!(!s.cancel_if_outputs_changed(1));
        assert!(s.active());
        assert!(s.cancel_if_outputs_changed(2));
        assert_eq!(s.phase(), Phase::Idle);
    }
}
