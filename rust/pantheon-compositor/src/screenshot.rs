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

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CaptureTarget {
    AllOutputs,
    Region(Region),
    Window(Region),
}

#[derive(Default, Debug)]
pub struct Selection {
    active: bool,
    anchor: Option<(i32, i32)>,
    pointer: (i32, i32),
}

impl Selection {
    pub fn begin(&mut self, pointer: (i32, i32)) {
        self.active = true;
        self.anchor = None;
        self.pointer = pointer;
    }

    pub fn active(&self) -> bool {
        self.active
    }

    pub fn press(&mut self, point: (i32, i32)) {
        if self.active {
            self.anchor = Some(point);
            self.pointer = point;
        }
    }

    pub fn motion(&mut self, point: (i32, i32)) {
        if self.active {
            self.pointer = point;
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
}
