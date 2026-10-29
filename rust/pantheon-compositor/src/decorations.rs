//! Server-side frames for X11 windows that ask the window manager to decorate them.
//!
//! XWayland apps such as Electron windows created with `frame: true`, xterm or a
//! plain GTK 3 window on X11 draw no title bar of their own: they expect the window
//! manager to add one (no `_MOTIF_WM_HINTS`, or hints that ask for decorations).
//! Without it they cannot be moved, resized or closed with the pointer.
//!
//! The frame is drawn by the compositor outside the client: a title bar above the
//! X11 window and an invisible resize band around both. The X11 window keeps its
//! own geometry (the space location is the client's top-left corner), so
//! configure requests, `xdotool` and the X11 clients' own coordinates are unchanged.
//! Snapped and maximized windows are configured below the title bar
//! ([`content_rect`]); fullscreen windows have no frame.
//!
//! This module holds the pure parts: which windows get a frame, the frame geometry
//! and hit test, the button layout from `org.gnome.desktop.wm.preferences`, and the
//! title-bar painting (cairo + pango, cached per window).

use std::{cell::RefCell, collections::HashMap};

use pangocairo::{cairo, pango};
use smithay::{
    backend::{allocator::Fourcc, renderer::element::memory::MemoryRenderBuffer},
    input::pointer::CursorIcon,
    utils::{Logical, Point, Rectangle, Size, Transform},
    xwayland::{
        X11Surface,
        xwm::{MwmDecorationsHint, MwmFunctionsHint, WmWindowType},
    },
};

use crate::grabs::resize_grab::ResizeEdge;

type Rect = Rectangle<i32, Logical>;

/// A window's frame for one output: its outer rect (space coordinates) and title bar.
pub type FrameElements<R> = (
    Rect,
    Vec<smithay::backend::renderer::element::memory::MemoryRenderBufferRenderElement<R>>,
);

/// Builds a window's [`FrameElements`] from its own geometry rect.
pub type FrameSource<'a, R> =
    dyn FnMut(&mut R, &smithay::desktop::Window, Rect) -> Option<FrameElements<R>> + 'a;

/// Title bar height in logical pixels (elementary's Gala SSD title bar).
pub const TITLE_HEIGHT: i32 = 34;
/// Invisible resize band outside the frame.
pub const RESIZE_BORDER: i32 = 8;
/// Distance from a corner along an edge that still resizes both directions.
const CORNER_GRAB: i32 = 20;
/// The top few pixels of the title bar resize too, as in Mutter.
const TOP_INNER_GRAB: i32 = 3;
/// Title-bar button box (the circle drawn on hover) and spacing.
const BUTTON_SIZE: i32 = 24;
const BUTTON_GAP: i32 = 4;
const BUTTON_PAD: i32 = 7;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ButtonKind {
    Close,
    Minimize,
    Maximize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FrameHit {
    Title,
    Button(ButtonKind),
    Edge(ResizeEdge),
}

/// `org.gnome.desktop.wm.preferences button-layout`: `left:right`, comma separated.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ButtonLayout {
    pub left: Vec<ButtonKind>,
    pub right: Vec<ButtonKind>,
}

impl Default for ButtonLayout {
    /// elementary's default.
    fn default() -> Self {
        Self::parse("close:maximize")
    }
}

impl ButtonLayout {
    pub fn parse(layout: &str) -> Self {
        let side = |text: &str| {
            text.split(',')
                .filter_map(|name| match name.trim() {
                    "close" => Some(ButtonKind::Close),
                    "minimize" => Some(ButtonKind::Minimize),
                    "maximize" => Some(ButtonKind::Maximize),
                    _ => None,
                })
                .collect::<Vec<_>>()
        };
        let (left, right) = layout.split_once(':').unwrap_or((layout, ""));
        Self {
            left: side(left),
            right: side(right),
        }
    }
}

/// Theme inputs for the title bar, read from GSettings.
#[derive(Clone, Debug, PartialEq)]
pub struct FrameStyle {
    pub dark: bool,
    pub font: String,
    pub layout: ButtonLayout,
}

impl Default for FrameStyle {
    fn default() -> Self {
        Self {
            dark: false,
            font: "Inter Bold 9".into(),
            layout: ButtonLayout::default(),
        }
    }
}

impl FrameStyle {
    pub const SETTINGS_SCHEMAS: &'static [&'static str] = &[
        "org.gnome.desktop.wm.preferences",
        "org.gnome.desktop.interface",
    ];

    pub fn load() -> Self {
        use gio::prelude::SettingsExt;
        let mut style = Self::default();
        let string = |schema: &str, key: &str| -> Option<String> {
            let source = gio::SettingsSchemaSource::default()?;
            let found = source.lookup(schema, true)?;
            if !found.has_key(key) {
                return None;
            }
            let settings = gio::Settings::new_full(&found, None::<&gio::SettingsBackend>, None);
            Some(settings.string(key).to_string())
        };
        if let Some(layout) = string("org.gnome.desktop.wm.preferences", "button-layout") {
            style.layout = ButtonLayout::parse(&layout);
        }
        if let Some(font) = string("org.gnome.desktop.wm.preferences", "titlebar-font")
            .filter(|font| !font.trim().is_empty())
        {
            style.font = font;
        }
        style.dark = string("org.gnome.desktop.interface", "color-scheme")
            .is_some_and(|scheme| scheme == "prefer-dark");
        style
    }
}

/// Whether the window manager should frame this X11 window.
pub fn wants_frame(surface: &X11Surface) -> bool {
    if surface.is_override_redirect() {
        return false;
    }
    let window_type_ok = matches!(
        surface.window_type(),
        None | Some(WmWindowType::Normal)
            | Some(WmWindowType::Dialog)
            | Some(WmWindowType::Utility)
    );
    window_type_ok && motif_wants_title(surface.motif_hints().decorations)
}

/// Motif decorations: `None` means "all"; `ALL` means all except the listed bits.
pub fn motif_wants_title(decorations: Option<MwmDecorationsHint>) -> bool {
    match decorations {
        None => true,
        Some(flags) if flags.contains(MwmDecorationsHint::ALL) => {
            !flags.contains(MwmDecorationsHint::TITLE)
        }
        Some(flags) => flags.contains(MwmDecorationsHint::TITLE),
    }
}

/// Motif functions: `None` means "all"; `ALL` means all except the listed bits.
pub fn motif_allows(functions: Option<MwmFunctionsHint>, function: MwmFunctionsHint) -> bool {
    match functions {
        None => true,
        Some(flags) if flags.contains(MwmFunctionsHint::ALL) => !flags.contains(function),
        Some(flags) => flags.contains(function),
    }
}

/// Everything about one window's frame that geometry, hit test and paint need.
#[derive(Clone, Debug, PartialEq)]
pub struct FrameSpec {
    /// The X11 window's own rectangle in space coordinates.
    pub content: Rect,
    pub resizable: bool,
    pub can_close: bool,
    pub can_minimize: bool,
    pub can_maximize: bool,
    pub maximized: bool,
}

impl FrameSpec {
    pub fn outer(&self) -> Rect {
        Rectangle::new(
            (self.content.loc.x, self.content.loc.y - TITLE_HEIGHT).into(),
            (self.content.size.w, self.content.size.h + TITLE_HEIGHT).into(),
        )
    }

    pub fn title_bar(&self) -> Rect {
        Rectangle::new(
            (self.content.loc.x, self.content.loc.y - TITLE_HEIGHT).into(),
            (self.content.size.w, TITLE_HEIGHT).into(),
        )
    }

    fn allows(&self, kind: ButtonKind) -> bool {
        match kind {
            ButtonKind::Close => self.can_close,
            ButtonKind::Minimize => self.can_minimize,
            ButtonKind::Maximize => self.can_maximize,
        }
    }

    /// Button boxes relative to the title bar's top-left corner.
    pub fn buttons(&self, layout: &ButtonLayout) -> Vec<(ButtonKind, Rect)> {
        let y = (TITLE_HEIGHT - BUTTON_SIZE) / 2;
        let size = Size::from((BUTTON_SIZE, BUTTON_SIZE));
        let mut out = Vec::new();
        let mut x = BUTTON_PAD;
        for kind in layout
            .left
            .iter()
            .copied()
            .filter(|kind| self.allows(*kind))
        {
            out.push((kind, Rectangle::new((x, y).into(), size)));
            x += BUTTON_SIZE + BUTTON_GAP;
        }
        let mut x = self.content.size.w - BUTTON_PAD - BUTTON_SIZE;
        for kind in layout
            .right
            .iter()
            .rev()
            .copied()
            .filter(|kind| self.allows(*kind))
        {
            out.push((kind, Rectangle::new((x, y).into(), size)));
            x -= BUTTON_SIZE + BUTTON_GAP;
        }
        out
    }

    /// What the pointer at `point` (space coordinates) is over, if it is on the frame.
    pub fn hit(&self, layout: &ButtonLayout, point: Point<f64, Logical>) -> Option<FrameHit> {
        let outer = self.outer();
        let border = if self.resizable { RESIZE_BORDER } else { 0 };
        let reach = Rectangle::new(
            (outer.loc.x - border, outer.loc.y - border).into(),
            (outer.size.w + 2 * border, outer.size.h + 2 * border).into(),
        );
        if !reach.to_f64().contains(point) || self.content.to_f64().contains(point) {
            return None;
        }
        let (x, y) = (point.x, point.y);
        let (left, top) = (outer.loc.x as f64, outer.loc.y as f64);
        let right = (outer.loc.x + outer.size.w) as f64;
        let bottom = (outer.loc.y + outer.size.h) as f64;
        if self.resizable {
            let in_left = x < left;
            let in_right = x >= right;
            let in_top = y < top + TOP_INNER_GRAB as f64;
            let in_bottom = y >= bottom;
            let corner = CORNER_GRAB as f64;
            let mut edges = ResizeEdge::empty();
            if in_top || in_bottom {
                edges |= if in_top {
                    ResizeEdge::TOP
                } else {
                    ResizeEdge::BOTTOM
                };
                if x < left + corner {
                    edges |= ResizeEdge::LEFT;
                } else if x >= right - corner {
                    edges |= ResizeEdge::RIGHT;
                }
            }
            if in_left || in_right {
                edges |= if in_left {
                    ResizeEdge::LEFT
                } else {
                    ResizeEdge::RIGHT
                };
                if y < top + corner {
                    edges |= ResizeEdge::TOP;
                } else if y >= bottom - corner {
                    edges |= ResizeEdge::BOTTOM;
                }
            }
            if !edges.is_empty() {
                return Some(FrameHit::Edge(edges));
            }
        }
        let title = self.title_bar();
        if !title.to_f64().contains(point) {
            return None;
        }
        let local = Point::<f64, Logical>::from((x - left, y - top));
        for (kind, rect) in self.buttons(layout) {
            if rect.to_f64().contains(local) {
                return Some(FrameHit::Button(kind));
            }
        }
        Some(FrameHit::Title)
    }
}

/// The rect to configure a snapped or maximized framed window to, so its title bar
/// fits inside `zone` too.
pub fn content_rect(zone: Rect) -> Rect {
    Rectangle::new(
        (zone.loc.x, zone.loc.y + TITLE_HEIGHT).into(),
        (zone.size.w, (zone.size.h - TITLE_HEIGHT).max(1)).into(),
    )
}

pub fn edge_cursor(edges: ResizeEdge) -> CursorIcon {
    match edges {
        ResizeEdge::TOP => CursorIcon::NResize,
        ResizeEdge::BOTTOM => CursorIcon::SResize,
        ResizeEdge::LEFT => CursorIcon::WResize,
        ResizeEdge::RIGHT => CursorIcon::EResize,
        ResizeEdge::TOP_LEFT => CursorIcon::NwResize,
        ResizeEdge::TOP_RIGHT => CursorIcon::NeResize,
        ResizeEdge::BOTTOM_LEFT => CursorIcon::SwResize,
        ResizeEdge::BOTTOM_RIGHT => CursorIcon::SeResize,
        _ => CursorIcon::Default,
    }
}

/// What a painted title bar depends on.
#[derive(Clone, Debug, PartialEq)]
pub struct PaintKey {
    pub width: i32,
    pub scale: i32,
    pub title: String,
    pub active: bool,
    pub hovered: Option<ButtonKind>,
    pub buttons: Vec<(ButtonKind, Rect)>,
    pub maximized: bool,
    pub style: FrameStyle,
}

struct Palette {
    top: (f64, f64, f64),
    bottom: (f64, f64, f64),
    highlight: (f64, f64, f64, f64),
    separator: (f64, f64, f64, f64),
    fg: (f64, f64, f64, f64),
}

fn palette(dark: bool, active: bool) -> Palette {
    match (dark, active) {
        (false, true) => Palette {
            top: (0.980, 0.980, 0.980),
            bottom: (0.925, 0.925, 0.925),
            highlight: (1.0, 1.0, 1.0, 0.9),
            separator: (0.0, 0.0, 0.0, 0.16),
            fg: (0.20, 0.20, 0.20, 1.0),
        },
        (false, false) => Palette {
            top: (0.957, 0.957, 0.957),
            bottom: (0.957, 0.957, 0.957),
            highlight: (1.0, 1.0, 1.0, 0.6),
            separator: (0.0, 0.0, 0.0, 0.12),
            fg: (0.20, 0.20, 0.20, 0.5),
        },
        (true, true) => Palette {
            top: (0.235, 0.235, 0.247),
            bottom: (0.200, 0.200, 0.212),
            highlight: (1.0, 1.0, 1.0, 0.07),
            separator: (0.0, 0.0, 0.0, 0.5),
            fg: (0.98, 0.98, 0.98, 1.0),
        },
        (true, false) => Palette {
            top: (0.188, 0.188, 0.200),
            bottom: (0.188, 0.188, 0.200),
            highlight: (1.0, 1.0, 1.0, 0.04),
            separator: (0.0, 0.0, 0.0, 0.45),
            fg: (0.98, 0.98, 0.98, 0.5),
        },
    }
}

/// Paint a title bar; premultiplied ARGB8888 rows of `width * scale` pixels.
pub fn paint(key: &PaintKey) -> Option<(Vec<u8>, Size<i32, smithay::utils::Buffer>)> {
    let scale = key.scale.max(1);
    let (w, h) = (key.width.max(1) * scale, TITLE_HEIGHT * scale);
    let mut surface = cairo::ImageSurface::create(cairo::Format::ARgb32, w, h).ok()?;
    {
        let cr = cairo::Context::new(&surface).ok()?;
        cr.scale(scale as f64, scale as f64);
        let width = key.width as f64;
        let height = TITLE_HEIGHT as f64;
        let colors = palette(key.style.dark, key.active);

        let gradient = cairo::LinearGradient::new(0.0, 0.0, 0.0, height);
        gradient.add_color_stop_rgb(0.0, colors.top.0, colors.top.1, colors.top.2);
        gradient.add_color_stop_rgb(1.0, colors.bottom.0, colors.bottom.1, colors.bottom.2);
        cr.set_source(&gradient).ok()?;
        cr.paint().ok()?;
        let (r, g, b, a) = colors.highlight;
        cr.set_source_rgba(r, g, b, a);
        cr.rectangle(0.0, 0.0, width, 1.0);
        cr.fill().ok()?;
        let (r, g, b, a) = colors.separator;
        cr.set_source_rgba(r, g, b, a);
        cr.rectangle(0.0, height - 1.0, width, 1.0);
        cr.fill().ok()?;

        let (fr, fg, fb, fa) = colors.fg;
        for (kind, rect) in &key.buttons {
            let cx = rect.loc.x as f64 + rect.size.w as f64 / 2.0;
            let cy = rect.loc.y as f64 + rect.size.h as f64 / 2.0;
            if key.hovered == Some(*kind) {
                cr.set_source_rgba(fr, fg, fb, 0.14 * fa.max(0.5));
                cr.arc(cx, cy, rect.size.w as f64 / 2.0, 0.0, std::f64::consts::TAU);
                cr.fill().ok()?;
            }
            cr.set_source_rgba(fr, fg, fb, fa * 0.85);
            cr.set_line_width(1.5);
            cr.set_line_cap(cairo::LineCap::Round);
            cr.set_line_join(cairo::LineJoin::Round);
            match kind {
                ButtonKind::Close => {
                    let d = 4.0;
                    cr.move_to(cx - d, cy - d);
                    cr.line_to(cx + d, cy + d);
                    cr.move_to(cx + d, cy - d);
                    cr.line_to(cx - d, cy + d);
                }
                ButtonKind::Minimize => {
                    cr.move_to(cx - 4.5, cy + 3.0);
                    cr.line_to(cx + 4.5, cy + 3.0);
                }
                ButtonKind::Maximize => {
                    // elementary's window-maximize/restore: two diagonal arrows.
                    let (tip, base) = if key.maximized {
                        (1.0, 5.0)
                    } else {
                        (5.0, 1.0)
                    };
                    for sign in [1.0, -1.0] {
                        let (tx, ty) = (cx + sign * tip, cy - sign * tip);
                        let (bx, by) = (cx + sign * base, cy - sign * base);
                        let toward = if key.maximized { -sign } else { sign };
                        cr.move_to(bx, by);
                        cr.line_to(tx, ty);
                        cr.move_to(tx - toward * 3.0, ty);
                        cr.line_to(tx, ty);
                        cr.line_to(tx, ty + toward * 3.0);
                    }
                }
            }
            cr.stroke().ok()?;
        }

        // The title is centred on the whole bar, kept clear of the buttons.
        let left_end = key
            .buttons
            .iter()
            .filter(|(_, rect)| rect.loc.x < key.width / 2)
            .map(|(_, rect)| rect.loc.x + rect.size.w)
            .max()
            .unwrap_or(0)
            + 8;
        let right_start = key
            .buttons
            .iter()
            .filter(|(_, rect)| rect.loc.x >= key.width / 2)
            .map(|(_, rect)| rect.loc.x)
            .min()
            .unwrap_or(key.width)
            - 8;
        let room = (right_start - left_end).max(0);
        if room > 0 && !key.title.is_empty() {
            let layout = pangocairo::functions::create_layout(&cr);
            layout
                .set_font_description(Some(&pango::FontDescription::from_string(&key.style.font)));
            layout.set_text(&key.title);
            layout.set_ellipsize(pango::EllipsizeMode::End);
            layout.set_single_paragraph_mode(true);
            layout.set_width(room * pango::SCALE);
            let (_, logical) = layout.pixel_extents();
            let text_w = logical.width().min(room);
            let centred = (key.width - text_w) / 2;
            let x = centred.clamp(left_end, (right_start - text_w).max(left_end));
            let y = (height - logical.height() as f64) / 2.0;
            cr.set_source_rgba(fr, fg, fb, fa);
            cr.move_to(x as f64, y.round());
            pangocairo::functions::show_layout(&cr, &layout);
        }
    }
    surface.flush();
    let stride = surface.stride() as usize;
    let data = surface.data().ok()?;
    let row = w as usize * 4;
    let mut pixels = Vec::with_capacity(row * h as usize);
    for y in 0..h as usize {
        pixels.extend_from_slice(&data[y * stride..y * stride + row]);
    }
    Some((pixels, Size::from((w, h))))
}

/// Painted title bars kept across frames: an unchanged frame keeps its buffer, so
/// the damage tracker repaints nothing.
#[derive(Default)]
pub struct FrameBuffers(RefCell<HashMap<(usize, i32), (PaintKey, MemoryRenderBuffer)>>);

impl FrameBuffers {
    pub fn get(&self, window: usize, key: PaintKey) -> Option<MemoryRenderBuffer> {
        let mut cache = self.0.borrow_mut();
        let slot = (window, key.scale);
        if let Some((cached, buffer)) = cache.get(&slot)
            && *cached == key
        {
            return Some(buffer.clone());
        }
        let (pixels, size) = paint(&key)?;
        let buffer = MemoryRenderBuffer::from_slice(
            &pixels,
            Fourcc::Argb8888,
            (size.w, size.h),
            key.scale.max(1),
            Transform::Normal,
            None,
        );
        cache.insert(slot, (key, buffer.clone()));
        Some(buffer)
    }

    pub fn forget(&self, window: usize) {
        self.0.borrow_mut().retain(|(id, _), _| *id != window);
    }

    pub fn clear(&self) {
        self.0.borrow_mut().clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spec() -> FrameSpec {
        FrameSpec {
            content: Rectangle::new((100, 200).into(), (420, 460).into()),
            resizable: true,
            can_close: true,
            can_minimize: true,
            can_maximize: true,
            maximized: false,
        }
    }

    fn at(x: f64, y: f64) -> Point<f64, Logical> {
        Point::from((x, y))
    }

    #[test]
    fn button_layout_parses_both_sides() {
        let layout = ButtonLayout::parse("close,minimize,maximize:");
        assert_eq!(
            layout.left,
            vec![
                ButtonKind::Close,
                ButtonKind::Minimize,
                ButtonKind::Maximize
            ]
        );
        assert!(layout.right.is_empty());
        let layout = ButtonLayout::parse("appmenu:minimize,maximize,close");
        assert!(layout.left.is_empty());
        assert_eq!(layout.right.len(), 3);
        assert_eq!(ButtonLayout::default().left, vec![ButtonKind::Close]);
        assert_eq!(ButtonLayout::default().right, vec![ButtonKind::Maximize]);
    }

    #[test]
    fn motif_hints_decide_the_frame() {
        // WiFiman Desktop: flags=DECORATIONS, decorations=ALL.
        assert!(motif_wants_title(Some(MwmDecorationsHint::ALL)));
        assert!(motif_wants_title(None));
        // Client-side decorated (Electron frame:false, GTK CSD on X11).
        assert!(!motif_wants_title(Some(MwmDecorationsHint::empty())));
        assert!(!motif_wants_title(Some(MwmDecorationsHint::BORDER)));
        assert!(motif_wants_title(Some(MwmDecorationsHint::TITLE)));
        assert!(!motif_wants_title(Some(
            MwmDecorationsHint::ALL | MwmDecorationsHint::TITLE
        )));
        assert!(motif_allows(None, MwmFunctionsHint::RESIZE));
        assert!(!motif_allows(
            Some(MwmFunctionsHint::MOVE),
            MwmFunctionsHint::RESIZE
        ));
        assert!(!motif_allows(
            Some(MwmFunctionsHint::ALL | MwmFunctionsHint::MAXIMIZE),
            MwmFunctionsHint::MAXIMIZE
        ));
    }

    #[test]
    fn title_bar_sits_above_the_client() {
        let spec = spec();
        assert_eq!(
            spec.title_bar(),
            Rectangle::new((100, 166).into(), (420, 34).into())
        );
        assert_eq!(spec.outer().size.h, 460 + TITLE_HEIGHT);
        let layout = ButtonLayout::parse("close:maximize");
        assert_eq!(spec.hit(&layout, at(300.0, 185.0)), Some(FrameHit::Title));
        // Inside the client: the app gets the pointer.
        assert_eq!(spec.hit(&layout, at(300.0, 300.0)), None);
        // Far away.
        assert_eq!(spec.hit(&layout, at(10.0, 10.0)), None);
    }

    #[test]
    fn buttons_follow_the_layout() {
        let spec = spec();
        let layout = ButtonLayout::parse("close:maximize");
        let close = 100.0 + (BUTTON_PAD + BUTTON_SIZE / 2) as f64;
        let maximize = 520.0 - (BUTTON_PAD + BUTTON_SIZE / 2) as f64;
        assert_eq!(
            spec.hit(&layout, at(close, 183.0)),
            Some(FrameHit::Button(ButtonKind::Close))
        );
        assert_eq!(
            spec.hit(&layout, at(maximize, 183.0)),
            Some(FrameHit::Button(ButtonKind::Maximize))
        );
        let mac = ButtonLayout::parse("close,minimize,maximize:");
        let second = close + (BUTTON_SIZE + BUTTON_GAP) as f64;
        assert_eq!(
            spec.hit(&mac, at(second, 183.0)),
            Some(FrameHit::Button(ButtonKind::Minimize))
        );
        // A window that cannot maximize shows no maximize button.
        let fixed = FrameSpec {
            can_maximize: false,
            ..spec.clone()
        };
        assert_eq!(fixed.buttons(&layout).len(), 1);
        assert_eq!(
            fixed.hit(&layout, at(maximize, 183.0)),
            Some(FrameHit::Title)
        );
    }

    #[test]
    fn edges_and_corners_resize() {
        let spec = spec();
        let layout = ButtonLayout::default();
        let edge = |x, y| spec.hit(&layout, at(x, y));
        assert_eq!(edge(96.0, 400.0), Some(FrameHit::Edge(ResizeEdge::LEFT)));
        assert_eq!(edge(523.0, 400.0), Some(FrameHit::Edge(ResizeEdge::RIGHT)));
        assert_eq!(edge(300.0, 663.0), Some(FrameHit::Edge(ResizeEdge::BOTTOM)));
        assert_eq!(edge(300.0, 162.0), Some(FrameHit::Edge(ResizeEdge::TOP)));
        // The top pixels of the title bar resize too.
        assert_eq!(edge(300.0, 167.0), Some(FrameHit::Edge(ResizeEdge::TOP)));
        assert_eq!(
            edge(525.0, 665.0),
            Some(FrameHit::Edge(ResizeEdge::BOTTOM_RIGHT))
        );
        assert_eq!(
            edge(95.0, 163.0),
            Some(FrameHit::Edge(ResizeEdge::TOP_LEFT))
        );
        assert_eq!(
            edge(510.0, 664.0),
            Some(FrameHit::Edge(ResizeEdge::BOTTOM_RIGHT))
        );
        // Beyond the band.
        assert_eq!(edge(300.0, 670.0), None);
        // A fixed-size window has no resize band.
        let fixed = FrameSpec {
            resizable: false,
            ..spec.clone()
        };
        assert_eq!(fixed.hit(&layout, at(96.0, 400.0)), None);
        assert_eq!(fixed.hit(&layout, at(300.0, 167.0)), Some(FrameHit::Title));
    }

    #[test]
    fn snapped_content_leaves_room_for_the_title_bar() {
        let zone = Rectangle::new((0, 32).into(), (1512, 950).into());
        let content = content_rect(zone);
        assert_eq!(content.loc.y, 32 + TITLE_HEIGHT);
        assert_eq!(content.size.h, 950 - TITLE_HEIGHT);
        let outer = FrameSpec { content, ..spec() }.outer();
        assert_eq!(outer, zone);
    }

    #[test]
    fn paint_fills_the_whole_bar_at_scale() {
        let spec = spec();
        let style = FrameStyle::default();
        let key = PaintKey {
            width: 420,
            scale: 2,
            title: "WiFiman Desktop".into(),
            active: true,
            hovered: Some(ButtonKind::Close),
            buttons: spec.buttons(&style.layout),
            maximized: false,
            style,
        };
        let (pixels, size) = paint(&key).expect("cairo paints");
        assert_eq!((size.w, size.h), (840, 68));
        assert_eq!(pixels.len(), 840 * 68 * 4);
        // Opaque background in the middle of the bar.
        let middle = (34 * 840 + 100) * 4;
        assert_eq!(pixels[middle + 3], 255);
        let cache = FrameBuffers::default();
        assert!(cache.get(7, key.clone()).is_some());
        cache.forget(7);
        assert!(cache.0.borrow().is_empty());
    }
}
