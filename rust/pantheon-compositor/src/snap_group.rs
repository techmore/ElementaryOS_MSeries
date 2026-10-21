//! Snap groups: windows tiled together share edges, raise together and resize
//! together. The tree is general (halves, quarters, 1+2 and thirds are all
//! shapes of it); phase 1 forms two-member side-by-side groups. Pure and
//! unit-tested, like [`crate::placement`].

use smithay::utils::{Logical, Rectangle, Size};

use crate::placement::WindowKey;

type Rect = Rectangle<i32, Logical>;

pub type SnapGroupId = u64;

/// The narrowest a zone may get from a split drag, whatever the client allows.
pub const MIN_ZONE: i32 = 240;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Axis {
    /// Children side by side; the ratio splits the width.
    Horizontal,
    /// Children stacked; the ratio splits the height.
    #[allow(dead_code)]
    // Stacked splits (quarters, 1+2) are phase 2; the solver handles them now.
    Vertical,
}

#[derive(Clone, Debug, PartialEq)]
pub enum SnapNode {
    /// `None` is an empty zone (offered by Snap Assist).
    Leaf(Option<WindowKey>),
    Split {
        axis: Axis,
        /// Share of the first child, 0..1.
        ratio: f64,
        a: Box<SnapNode>,
        b: Box<SnapNode>,
    },
}

/// Which child to take at each split, from the root: `false` = a, `true` = b.
pub type ZonePath = Vec<bool>;

impl SnapNode {
    pub fn pair(axis: Axis, a: WindowKey, b: WindowKey) -> Self {
        Self::Split {
            axis,
            ratio: 0.5,
            a: Box::new(Self::Leaf(Some(a))),
            b: Box::new(Self::Leaf(Some(b))),
        }
    }

    pub fn members(&self) -> Vec<WindowKey> {
        match self {
            Self::Leaf(key) => key.iter().copied().collect(),
            Self::Split { a, b, .. } => {
                let mut members = a.members();
                members.extend(b.members());
                members
            }
        }
    }

    pub fn contains(&self, key: WindowKey) -> bool {
        match self {
            Self::Leaf(member) => *member == Some(key),
            Self::Split { a, b, .. } => a.contains(key) || b.contains(key),
        }
    }

    /// Smallest extent this subtree can take along `axis`.
    fn min_extent(&self, axis: Axis, mins: &dyn Fn(WindowKey) -> Size<i32, Logical>) -> i32 {
        match self {
            Self::Leaf(key) => {
                let min = key.map(mins).unwrap_or_default();
                let hint = match axis {
                    Axis::Horizontal => min.w,
                    Axis::Vertical => min.h,
                };
                hint.max(MIN_ZONE)
            }
            Self::Split {
                axis: split, a, b, ..
            } => {
                let (a, b) = (a.min_extent(axis, mins), b.min_extent(axis, mins));
                if *split == axis { a + b } else { a.max(b) }
            }
        }
    }
}

/// Clamp a split so both sides keep at least their minimum. When the minimums
/// cannot both fit, the space is shared in proportion to them.
pub fn clamp_ratio(ratio: f64, total: i32, min_a: i32, min_b: i32) -> f64 {
    if total <= 0 {
        return 0.5;
    }
    if min_a + min_b > total {
        return min_a as f64 / (min_a + min_b).max(1) as f64;
    }
    split_point(ratio, total).clamp(min_a, total - min_b) as f64 / total as f64
}

/// Pixels given to the first child. Floors like `placement::tile_rect`, so a
/// fresh pair matches the plain halves exactly; the epsilon keeps stored
/// `first / total` ratios from flooring one pixel short.
fn split_point(ratio: f64, total: i32) -> i32 {
    ((ratio * total as f64 + 1e-6).floor() as i32).clamp(0, total.max(0))
}

/// Lay a tree out in `area`: one rect per leaf, gap-free, in tree order.
/// Ratios are clamped to the members' minimum sizes.
pub fn layout(
    node: &SnapNode,
    area: Rect,
    mins: &dyn Fn(WindowKey) -> Size<i32, Logical>,
) -> Vec<(ZonePath, Option<WindowKey>, Rect)> {
    let mut out = Vec::new();
    layout_into(node, area, mins, &mut Vec::new(), &mut out);
    out
}

fn layout_into(
    node: &SnapNode,
    area: Rect,
    mins: &dyn Fn(WindowKey) -> Size<i32, Logical>,
    path: &mut ZonePath,
    out: &mut Vec<(ZonePath, Option<WindowKey>, Rect)>,
) {
    match node {
        SnapNode::Leaf(key) => out.push((path.clone(), *key, area)),
        SnapNode::Split { axis, ratio, a, b } => {
            let total = match axis {
                Axis::Horizontal => area.size.w,
                Axis::Vertical => area.size.h,
            };
            let ratio = clamp_ratio(
                *ratio,
                total,
                a.min_extent(*axis, mins),
                b.min_extent(*axis, mins),
            );
            let first = split_point(ratio, total);
            let (rect_a, rect_b) = match axis {
                Axis::Horizontal => (
                    Rectangle::new(area.loc, (first, area.size.h).into()),
                    Rectangle::new(
                        (area.loc.x + first, area.loc.y).into(),
                        (total - first, area.size.h).into(),
                    ),
                ),
                Axis::Vertical => (
                    Rectangle::new(area.loc, (area.size.w, first).into()),
                    Rectangle::new(
                        (area.loc.x, area.loc.y + first).into(),
                        (area.size.w, total - first).into(),
                    ),
                ),
            };
            path.push(false);
            layout_into(a, rect_a, mins, path, out);
            path.pop();
            path.push(true);
            layout_into(b, rect_b, mins, path, out);
            path.pop();
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct SnapGroup {
    pub id: SnapGroupId,
    /// Output (connector) name.
    pub output: String,
    pub workspace: usize,
    pub root: SnapNode,
}

impl SnapGroup {
    /// The rect `key` gets in `area`, if it is a member.
    pub fn member_rect(
        &self,
        key: WindowKey,
        area: Rect,
        mins: &dyn Fn(WindowKey) -> Size<i32, Logical>,
    ) -> Option<Rect> {
        layout(&self.root, area, mins)
            .into_iter()
            .find(|(_, member, _)| *member == Some(key))
            .map(|(_, _, rect)| rect)
    }

    /// The other members.
    pub fn siblings(&self, key: WindowKey) -> Vec<WindowKey> {
        self.root
            .members()
            .into_iter()
            .filter(|member| *member != key)
            .collect()
    }

    /// Ratio of the root split.
    pub fn ratio(&self) -> Option<f64> {
        match &self.root {
            SnapNode::Split { ratio, .. } => Some(*ratio),
            SnapNode::Leaf(_) => None,
        }
    }

    /// Set the root split, clamped to the members' minimums in `area`.
    /// Returns whether the laid-out split moved.
    pub fn set_ratio(
        &mut self,
        ratio: f64,
        area: Rect,
        mins: &dyn Fn(WindowKey) -> Size<i32, Logical>,
    ) -> bool {
        let before = layout(&self.root, area, mins);
        if let SnapNode::Split { ratio: current, .. } = &mut self.root {
            *current = ratio.clamp(0.0, 1.0);
        }
        // Store the clamped value so a drag past a minimum does not overshoot.
        if let SnapNode::Split { axis, ratio, a, b } = &mut self.root {
            let total = match axis {
                Axis::Horizontal => area.size.w,
                Axis::Vertical => area.size.h,
            };
            *ratio = clamp_ratio(
                *ratio,
                total,
                a.min_extent(*axis, mins),
                b.min_extent(*axis, mins),
            );
        }
        before != layout(&self.root, area, mins)
    }
}

/// The root ratio after dragging the shared edge `dx` logical pixels.
pub fn dragged_ratio(start: f64, dx: f64, total: i32) -> f64 {
    if total <= 0 {
        return start;
    }
    (start + dx / total as f64).clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rect(x: i32, y: i32, w: i32, h: i32) -> Rect {
        Rectangle::new((x, y).into(), (w, h).into())
    }

    fn no_mins(_: WindowKey) -> Size<i32, Logical> {
        Size::default()
    }

    fn area() -> Rect {
        rect(0, 30, 2419, 1541)
    }

    #[test]
    fn a_pair_splits_into_gap_free_halves() {
        let zones = layout(&SnapNode::pair(Axis::Horizontal, 1, 2), area(), &no_mins);
        assert_eq!(zones.len(), 2);
        // Identical to placement::tile_rect's Left/Right halves.
        assert_eq!(zones[0], (vec![false], Some(1), rect(0, 30, 1209, 1541)));
        assert_eq!(zones[1], (vec![true], Some(2), rect(1209, 30, 1210, 1541)));
    }

    #[test]
    fn layout_never_leaves_a_gap_or_overlap_for_any_ratio() {
        let mut node = SnapNode::pair(Axis::Horizontal, 1, 2);
        for step in 0..=20 {
            if let SnapNode::Split { ratio, .. } = &mut node {
                *ratio = step as f64 / 20.0;
            }
            let zones = layout(&node, area(), &no_mins);
            let (a, b) = (zones[0].2, zones[1].2);
            assert_eq!(a.loc.x + a.size.w, b.loc.x);
            assert_eq!(a.size.w + b.size.w, area().size.w);
            assert!(a.size.w >= MIN_ZONE && b.size.w >= MIN_ZONE);
        }
    }

    #[test]
    fn minimum_sizes_limit_the_split() {
        let mins = |key: WindowKey| -> Size<i32, Logical> {
            if key == 1 {
                (900, 0).into()
            } else {
                (0, 0).into()
            }
        };
        let mut group = SnapGroup {
            id: 1,
            output: "eDP-1".into(),
            workspace: 0,
            root: SnapNode::pair(Axis::Horizontal, 1, 2),
        };
        group.set_ratio(0.1, area(), &mins);
        assert_eq!(group.member_rect(1, area(), &mins).unwrap().size.w, 900);
        group.set_ratio(0.99, area(), &mins);
        assert_eq!(
            group.member_rect(2, area(), &mins).unwrap().size.w,
            MIN_ZONE
        );
        // The stored ratio is clamped, so dragging back moves the edge at once.
        let stored = group.ratio().unwrap();
        assert!((stored - (2419 - MIN_ZONE) as f64 / 2419.0).abs() < 1e-9);
    }

    #[test]
    fn impossible_minimums_share_space_proportionally() {
        assert!((clamp_ratio(0.5, 1000, 900, 300) - 0.75).abs() < 1e-9);
    }

    #[test]
    fn set_ratio_reports_only_real_moves() {
        let mut group = SnapGroup {
            id: 1,
            output: "eDP-1".into(),
            workspace: 0,
            root: SnapNode::pair(Axis::Horizontal, 1, 2),
        };
        assert!(!group.set_ratio(0.5, area(), &no_mins));
        assert!(group.set_ratio(0.6, area(), &no_mins));
        assert!(!group.set_ratio(0.6000001, area(), &no_mins));
    }

    #[test]
    fn dragging_the_shared_edge_moves_the_ratio_by_the_pointer_travel() {
        assert!((dragged_ratio(0.5, 241.9, 2419) - 0.6).abs() < 1e-9);
        assert_eq!(dragged_ratio(0.5, -5000.0, 2419), 0.0);
    }

    #[test]
    fn nested_trees_lay_out_quarters_and_one_plus_two() {
        // Left half + right column of two: the "1+2" shape.
        let node = SnapNode::Split {
            axis: Axis::Horizontal,
            ratio: 0.5,
            a: Box::new(SnapNode::Leaf(Some(1))),
            b: Box::new(SnapNode::Split {
                axis: Axis::Vertical,
                ratio: 0.5,
                a: Box::new(SnapNode::Leaf(Some(2))),
                b: Box::new(SnapNode::Leaf(None)),
            }),
        };
        let zones = layout(&node, rect(0, 0, 1000, 800), &no_mins);
        assert_eq!(
            zones,
            vec![
                (vec![false], Some(1), rect(0, 0, 500, 800)),
                (vec![true, false], Some(2), rect(500, 0, 500, 400)),
                (vec![true, true], None, rect(500, 400, 500, 400)),
            ]
        );
        assert_eq!(node.members(), vec![1, 2]);
        assert!(node.contains(2) && !node.contains(3));
    }

    #[test]
    fn siblings_exclude_the_window_itself() {
        let group = SnapGroup {
            id: 7,
            output: "eDP-1".into(),
            workspace: 0,
            root: SnapNode::pair(Axis::Horizontal, 4, 9),
        };
        assert_eq!(group.siblings(4), vec![9]);
        assert_eq!(group.siblings(9), vec![4]);
    }
}
