//! Snap groups and Snap Assist (snapping phase 1).
//!
//! Snapping a window to a half either joins the window already on the other
//! half (a two-member [`SnapGroup`]) or, when that half is empty, offers the
//! other windows on the output as live thumbnails in it. Group members share
//! their inner edge: dragging it resizes both.

use smithay::{
    backend::renderer::element::solid::SolidColorBuffer,
    desktop::Window,
    input::{
        keyboard::{Keysym, ModifiersState, keysyms},
        pointer::{Focus, GrabStartData as PointerGrabStartData, PointerHandle},
    },
    output::Output,
    reexports::wayland_protocols::xdg::shell::server::xdg_toplevel,
    utils::{Logical, Point, Rectangle, SERIAL_COUNTER, Serial, Size},
};

use crate::grabs::{SplitResizeGrab, resize_grab::ResizeEdge};
use crate::placement::{Placement, TilePosition, WindowKey};
use crate::snap_group::{Axis, SnapGroup, SnapGroupId, SnapNode};
use crate::state::PantheonCompositor;

type Rect = Rectangle<i32, Logical>;

/// Space between a thumbnail and its plate.
const PLATE_PADDING: i32 = 10;
/// The selection ring hugs the plate.
const RING_WIDTH: i32 = 3;
/// Thumbnails never take more of the empty zone than this, per axis.
const MAX_CELL_FRACTION: f64 = 0.42;
const CELL_GAP: i32 = 24;

/// elementary's accent ("blueberry 500", #3689e6).
pub(crate) const ACCENT: [f32; 4] = [0.212, 0.537, 0.902, 1.0];
pub(crate) const BACKDROP: [f32; 4] = [0.0, 0.0, 0.0, 1.0];
pub(crate) const BACKDROP_ALPHA: f32 = 0.45;
pub(crate) const PLATE: [f32; 4] = [1.0, 1.0, 1.0, 1.0];
pub(crate) const PLATE_ALPHA: f32 = 0.14;

/// An open Snap Assist: thumbnails of `candidates` in the empty `zone`.
pub(crate) struct SnapAssist {
    pub output: Output,
    pub zone: Rect,
    /// Where the chosen window goes.
    pub position: TilePosition,
    pub anchor: WindowKey,
    pub candidates: Vec<Window>,
    pub selected: usize,
    /// Hit targets, one per candidate.
    pub cells: Vec<Rect>,
    /// Thumbnail rects (aspect kept, never enlarged) and the plates behind them.
    pub thumbs: Vec<Rect>,
    pub plate_rects: Vec<Rect>,
    /// Kept across frames so damage tracking sees stable elements.
    pub backdrop: SolidColorBuffer,
    pub plates: Vec<SolidColorBuffer>,
    /// Top, bottom, left and right bars of the selection ring.
    pub ring: [SolidColorBuffer; 4],
}

impl SnapAssist {
    fn new(
        output: Output,
        zone: Rect,
        position: TilePosition,
        anchor: WindowKey,
        candidates: Vec<Window>,
    ) -> Self {
        let mut assist = Self {
            output,
            zone,
            position,
            anchor,
            candidates,
            selected: 0,
            cells: Vec::new(),
            thumbs: Vec::new(),
            plate_rects: Vec::new(),
            backdrop: SolidColorBuffer::new(zone.size, BACKDROP),
            plates: Vec::new(),
            ring: Default::default(),
        };
        assist.relayout();
        assist
    }

    /// Recompute cells, thumbnails and plates for the current candidates.
    fn relayout(&mut self) {
        self.cells = assist_cells(self.zone, self.candidates.len());
        self.thumbs = self
            .candidates
            .iter()
            .zip(&self.cells)
            .map(|(window, cell)| {
                crate::overview::fit_overview_rect(
                    inset(*cell, PLATE_PADDING),
                    window.geometry().size,
                )
            })
            .collect();
        self.plate_rects = self
            .thumbs
            .iter()
            .map(|thumb| inset(*thumb, -PLATE_PADDING))
            .collect();
        self.plates = self
            .plate_rects
            .iter()
            .map(|plate| SolidColorBuffer::new(plate.size, PLATE))
            .collect();
        self.selected = self.selected.min(self.candidates.len().saturating_sub(1));
        self.update_ring();
    }

    fn update_ring(&mut self) {
        let Some(plate) = self.plate_rects.get(self.selected) else {
            return;
        };
        for (buffer, bar) in self.ring.iter_mut().zip(ring_rects(*plate)) {
            buffer.update(bar.size, ACCENT);
        }
    }

    fn select(&mut self, index: usize) {
        if index != self.selected && index < self.candidates.len() {
            self.selected = index;
            self.update_ring();
        }
    }

    /// Each candidate with its thumbnail rect.
    pub(crate) fn thumbnails(&self) -> Vec<(Window, Rect)> {
        self.candidates
            .iter()
            .cloned()
            .zip(self.thumbs.iter().copied())
            .collect()
    }

    /// Where the selection ring's bars go.
    pub(crate) fn ring_bars(&self) -> Option<[Rect; 4]> {
        self.plate_rects
            .get(self.selected)
            .map(|plate| ring_rects(*plate))
    }
}

/// Shrink (or, with a negative `by`, grow) a rect on every side.
fn inset(rect: Rect, by: i32) -> Rect {
    Rectangle::new(
        (rect.loc.x + by, rect.loc.y + by).into(),
        ((rect.size.w - 2 * by).max(1), (rect.size.h - 2 * by).max(1)).into(),
    )
}

/// Four bars of a [`RING_WIDTH`] ring just outside `plate`: top, bottom, left, right.
pub(crate) fn ring_rects(plate: Rect) -> [Rect; 4] {
    let outer = inset(plate, -RING_WIDTH);
    let side_h = (outer.size.h - 2 * RING_WIDTH).max(1);
    [
        Rectangle::new(outer.loc, (outer.size.w, RING_WIDTH).into()),
        Rectangle::new(
            (outer.loc.x, outer.loc.y + outer.size.h - RING_WIDTH).into(),
            (outer.size.w, RING_WIDTH).into(),
        ),
        Rectangle::new(
            (outer.loc.x, outer.loc.y + RING_WIDTH).into(),
            (RING_WIDTH, side_h).into(),
        ),
        Rectangle::new(
            (
                outer.loc.x + outer.size.w - RING_WIDTH,
                outer.loc.y + RING_WIDTH,
            )
                .into(),
            (RING_WIDTH, side_h).into(),
        ),
    ]
}

/// A centred grid of equal cells for `count` thumbnails in `zone`, each at
/// most [`MAX_CELL_FRACTION`] of the zone so a lone window stays a thumbnail.
pub(crate) fn assist_cells(zone: Rect, count: usize) -> Vec<Rect> {
    if count == 0 {
        return Vec::new();
    }
    let columns = (count as f64).sqrt().ceil().max(1.0) as i32;
    let rows = (count as i32 + columns - 1) / columns;
    let margin = CELL_GAP * 2;
    let fit_w = (zone.size.w - 2 * margin - CELL_GAP * (columns - 1)) / columns;
    let fit_h = (zone.size.h - 2 * margin - CELL_GAP * (rows - 1)) / rows;
    let cap_w = (zone.size.w as f64 * MAX_CELL_FRACTION) as i32;
    let cap_h = (zone.size.h as f64 * MAX_CELL_FRACTION) as i32;
    let w = fit_w.min(cap_w).max(1);
    let h = fit_h.min(cap_h).max(1);
    let grid_h = rows * h + CELL_GAP * (rows - 1);
    let top = zone.loc.y + (zone.size.h - grid_h) / 2;
    (0..count as i32)
        .map(|index| {
            let row = index / columns;
            let column = index % columns;
            let in_row = (count as i32 - row * columns).min(columns);
            let row_w = in_row * w + CELL_GAP * (in_row - 1);
            let left = zone.loc.x + (zone.size.w - row_w) / 2;
            Rectangle::new(
                (left + column * (w + CELL_GAP), top + row * (h + CELL_GAP)).into(),
                (w, h).into(),
            )
        })
        .collect()
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum AssistKey {
    Next,
    Previous,
    Choose,
    Dismiss,
    /// Modifiers alone: keep Assist open, let the key through.
    Ignore,
    /// Anything else: close Assist and handle the key normally.
    PassThrough,
}

pub(crate) fn assist_key(keysym: u32, shift: bool) -> AssistKey {
    match keysym {
        keysyms::KEY_Right | keysyms::KEY_Down => AssistKey::Next,
        keysyms::KEY_Left | keysyms::KEY_Up => AssistKey::Previous,
        keysyms::KEY_Tab if shift => AssistKey::Previous,
        keysyms::KEY_ISO_Left_Tab => AssistKey::Previous,
        keysyms::KEY_Tab => AssistKey::Next,
        keysyms::KEY_Return | keysyms::KEY_KP_Enter | keysyms::KEY_space => AssistKey::Choose,
        keysyms::KEY_Escape => AssistKey::Dismiss,
        keysyms::KEY_Shift_L
        | keysyms::KEY_Shift_R
        | keysyms::KEY_Super_L
        | keysyms::KEY_Super_R
        | keysyms::KEY_Control_L
        | keysyms::KEY_Control_R
        | keysyms::KEY_Alt_L
        | keysyms::KEY_Alt_R
        | keysyms::KEY_Meta_L
        | keysyms::KEY_Meta_R => AssistKey::Ignore,
        _ => AssistKey::PassThrough,
    }
}

fn opposite(position: TilePosition) -> Option<TilePosition> {
    match position {
        TilePosition::Left => Some(TilePosition::Right),
        TilePosition::Right => Some(TilePosition::Left),
        _ => None,
    }
}

impl PantheonCompositor {
    fn window_by_key(&self, key: WindowKey) -> Option<Window> {
        self.space
            .elements()
            .find(|window| window.id() == key)
            .cloned()
            .or_else(|| {
                self.workspace_manager
                    .windows()
                    .into_iter()
                    .map(|(window, _, _)| window)
                    .find(|window| window.id() == key)
            })
    }

    fn min_size_of(&self, key: WindowKey) -> Size<i32, Logical> {
        self.window_by_key(key)
            .map(|window| Self::size_hints(&window).0)
            .unwrap_or_default()
    }

    fn workspace_of(&self, key: WindowKey) -> usize {
        self.workspace_manager
            .workspace_for(key)
            .unwrap_or_else(|| self.workspace_manager.active())
    }

    pub(crate) fn group_of(&self, key: WindowKey) -> Option<&SnapGroup> {
        self.snap_groups
            .values()
            .find(|group| group.root.contains(key))
    }

    /// The zone a grouped tile gets instead of its plain half.
    pub(crate) fn group_zone(&self, key: WindowKey, output: &str, area: Rect) -> Option<Rect> {
        let group = self.group_of(key)?;
        if group.output != output {
            return None;
        }
        group.member_rect(key, area, &|member| self.min_size_of(member))
    }

    /// A pair is valid while its left leaf rests on the left half and its
    /// right leaf on the right half of the group's output and workspace.
    fn group_is_valid(&self, group: &SnapGroup) -> bool {
        let SnapNode::Split {
            axis: Axis::Horizontal,
            a,
            b,
            ..
        } = &group.root
        else {
            return false;
        };
        let rests_at = |node: &SnapNode, position: TilePosition| {
            let SnapNode::Leaf(Some(key)) = node else {
                return false;
            };
            self.placements.get(key).is_some_and(|record| {
                record
                    .placement
                    .resting_tile()
                    .is_some_and(|tile| tile.position == position && tile.output == group.output)
            }) && self.workspace_of(*key) == group.workspace
        };
        rests_at(a, TilePosition::Left) && rests_at(b, TilePosition::Right)
    }

    /// Dissolve groups that no longer hold; their remaining members go back
    /// to plain halves.
    pub(crate) fn prune_snap_groups(&mut self) {
        // The overview holds placements aside until it closes.
        if self.overview_active() {
            return;
        }
        let broken = self
            .snap_groups
            .values()
            .filter(|group| !self.group_is_valid(group))
            .map(|group| group.id)
            .collect::<Vec<_>>();
        for id in broken {
            for key in self.remove_snap_group(id) {
                if let Some(window) = self.window_by_key(key)
                    && self.placement_of(&window).tile().is_some()
                    && self.space.elements().any(|mapped| *mapped == window)
                {
                    self.apply_placement(&window);
                }
            }
        }
    }

    fn remove_snap_group(&mut self, id: SnapGroupId) -> Vec<WindowKey> {
        let members = self
            .snap_groups
            .remove(&id)
            .map(|group| group.root.members())
            .unwrap_or_default();
        if !members.is_empty() {
            tracing::info!(group = id, "snap group dissolved");
        }
        members
    }

    /// After a user snap: join the window on the other half into a group,
    /// or offer Snap Assist when that half is empty.
    pub(crate) fn after_user_tile(&mut self, window: &Window, offer_assist: bool) {
        self.prune_snap_groups();
        let key = window.id();
        let Some(tile) = self.placement_of(window).tile().cloned() else {
            return;
        };
        let Some(other_side) = opposite(tile.position) else {
            return;
        };
        let workspace = self.workspace_of(key);
        let partner = self
            .space
            .elements()
            .rev()
            .find(|candidate| {
                candidate.id() != key
                    && self.workspace_of(candidate.id()) == workspace
                    && self.placement_of(candidate).tile().is_some_and(|other| {
                        other.position == other_side && other.output == tile.output
                    })
            })
            .cloned();
        let Some(partner) = partner else {
            if offer_assist {
                self.open_snap_assist(window, &tile.output, other_side);
            }
            return;
        };
        // The partner may be grouped with a window this one now covers; the
        // new pair keeps that split.
        let ratio = self
            .group_of(partner.id())
            .and_then(SnapGroup::ratio)
            .unwrap_or(0.5);
        let mut displaced = Vec::new();
        for member in [partner.id(), key] {
            if let Some(id) = self.group_of(member).map(|group| group.id) {
                displaced.extend(self.remove_snap_group(id));
            }
        }
        let (left, right) = if tile.position == TilePosition::Left {
            (key, partner.id())
        } else {
            (partner.id(), key)
        };
        let id = self.next_snap_group;
        self.next_snap_group += 1;
        let mut root = SnapNode::pair(Axis::Horizontal, left, right);
        if let SnapNode::Split { ratio: split, .. } = &mut root {
            *split = ratio;
        }
        self.snap_groups.insert(
            id,
            SnapGroup {
                id,
                output: tile.output.clone(),
                workspace,
                root,
            },
        );
        tracing::info!(group = id, left, right, "snap group formed");
        for member in displaced
            .into_iter()
            .filter(|member| *member != left && *member != right)
            .chain([partner.id(), key])
        {
            if let Some(window) = self.window_by_key(member)
                && self.placement_of(&window).tile().is_some()
            {
                self.apply_placement(&window);
            }
        }
    }

    /// Raise a window's group siblings just below it.
    pub(crate) fn raise_group_siblings(&mut self, window: &Window) {
        let Some(siblings) = self
            .group_of(window.id())
            .map(|group| group.siblings(window.id()))
        else {
            return;
        };
        let siblings = self
            .space
            .elements()
            .filter(|candidate| siblings.contains(&candidate.id()))
            .cloned()
            .collect::<Vec<_>>();
        for sibling in siblings {
            self.space.raise_element(&sibling, false);
        }
    }

    /// Move a group's split; members are reconfigured (and move on ack).
    pub(crate) fn set_group_ratio(&mut self, id: SnapGroupId, ratio: f64) {
        let Some(group) = self.snap_groups.get(&id) else {
            return;
        };
        let Some(area) = self
            .space
            .outputs()
            .find(|output| output.name() == group.output)
            .and_then(|output| self.space.output_geometry(output))
            .map(|geometry| self.work_area_for_output(geometry))
        else {
            return;
        };
        let mins = group
            .root
            .members()
            .into_iter()
            .map(|key| (key, self.min_size_of(key)))
            .collect::<Vec<_>>();
        let lookup = |key: WindowKey| {
            mins.iter()
                .find(|(member, _)| *member == key)
                .map(|(_, size)| *size)
                .unwrap_or_default()
        };
        let Some(group) = self.snap_groups.get_mut(&id) else {
            return;
        };
        if !group.set_ratio(ratio, area, &lookup) {
            return;
        }
        let members = group.root.members();
        let windows = self
            .space
            .elements()
            .filter(|window| members.contains(&window.id()))
            .cloned()
            .collect::<Vec<_>>();
        for window in windows {
            self.apply_placement(&window);
        }
    }

    /// A resize from a group member's inner edge moves the shared split
    /// instead of un-snapping. Returns whether the split grab started.
    pub(crate) fn try_start_split_resize(
        &mut self,
        pointer: &PointerHandle<Self>,
        start_data: PointerGrabStartData<Self>,
        window: &Window,
        edges: ResizeEdge,
        serial: Serial,
    ) -> bool {
        let key = window.id();
        let Some(group) = self.group_of(key) else {
            return false;
        };
        let SnapNode::Split {
            axis: Axis::Horizontal,
            a,
            ratio,
            ..
        } = &group.root
        else {
            return false;
        };
        let is_left = matches!(**a, SnapNode::Leaf(Some(left)) if left == key);
        let inner = if is_left {
            ResizeEdge::RIGHT
        } else {
            ResizeEdge::LEFT
        };
        if !edges.contains(inner) || !self.placement_of(window).tile().is_some() {
            return false;
        }
        let (id, start_ratio, output) = (group.id, *ratio, group.output.clone());
        let Some(total) = self
            .space
            .outputs()
            .find(|candidate| candidate.name() == output)
            .and_then(|output| self.space.output_geometry(output))
            .map(|geometry| self.work_area_for_output(geometry).size.w)
        else {
            return false;
        };
        let members = self.snap_groups[&id].root.members();
        for member in &members {
            if let Some(toplevel) = self
                .window_by_key(*member)
                .and_then(|window| window.toplevel().cloned())
            {
                toplevel.with_pending_state(|state| {
                    state.states.set(xdg_toplevel::State::Resizing);
                });
            }
        }
        self.dismiss_snap_assist();
        self.split_grab_active = true;
        let grab = SplitResizeGrab::new(start_data, id, start_ratio, total);
        pointer.set_grab(self, grab, serial, Focus::Clear);
        true
    }

    /// Called after the split grab ends, outside the pointer grab.
    pub(crate) fn finish_split_resize(&mut self, id: SnapGroupId) {
        self.split_grab_active = false;
        let Some(group) = self.snap_groups.get(&id) else {
            return;
        };
        for member in group.root.members() {
            if let Some(window) = self.window_by_key(member) {
                if let Some(toplevel) = window.toplevel() {
                    toplevel.with_pending_state(|state| {
                        state.states.unset(xdg_toplevel::State::Resizing);
                    });
                }
                if self.space.elements().any(|mapped| *mapped == window) {
                    self.apply_placement(&window);
                }
            }
        }
    }

    fn open_snap_assist(&mut self, anchor: &Window, output_name: &str, position: TilePosition) {
        let Some(output) = self
            .space
            .outputs()
            .find(|output| output.name() == output_name)
            .cloned()
        else {
            return;
        };
        let Some(area) = self
            .space
            .output_geometry(&output)
            .map(|geometry| self.work_area_for_output(geometry))
        else {
            return;
        };
        let workspace = self.workspace_of(anchor.id());
        let candidates = self
            .space
            .elements()
            .rev()
            .filter(|candidate| {
                *candidate != anchor
                    && self.workspace_of(candidate.id()) == workspace
                    && self.is_assist_candidate(candidate)
                    && self.primary_output_for(candidate).as_ref() == Some(&output)
            })
            .cloned()
            .collect::<Vec<_>>();
        if candidates.is_empty() {
            return;
        }
        let zone = crate::placement::tile_rect(area, position);
        tracing::info!(
            candidates = candidates.len(),
            ?position,
            "snap assist opened"
        );
        self.snap_assist = Some(SnapAssist::new(
            output,
            zone,
            position,
            anchor.id(),
            candidates,
        ));
        self.request_native_redraw();
    }

    fn is_assist_candidate(&self, window: &Window) -> bool {
        if let Some(toplevel) = window.toplevel() {
            if self.is_panel_surface(toplevel.wl_surface()) || toplevel.parent().is_some() {
                return false;
            }
        } else if window
            .x11_surface()
            .is_none_or(|surface| surface.is_override_redirect())
        {
            return false;
        }
        !matches!(self.placement_of(window), Placement::Fullscreen { .. })
    }

    pub(crate) fn dismiss_snap_assist(&mut self) {
        if self.snap_assist.take().is_some() {
            tracing::info!("snap assist closed");
            self.request_native_redraw();
        }
    }

    /// Keys while Assist is open. Returns true when the key was consumed.
    pub(crate) fn handle_snap_assist_key(
        &mut self,
        keysym: Keysym,
        modifiers: &ModifiersState,
    ) -> bool {
        if self.snap_assist.is_none() {
            return false;
        }
        match assist_key(keysym.raw(), modifiers.shift) {
            AssistKey::Ignore => false,
            AssistKey::PassThrough => {
                self.dismiss_snap_assist();
                false
            }
            action => {
                self.snap_assist_action(action);
                true
            }
        }
    }

    pub(crate) fn snap_assist_action(&mut self, action: AssistKey) {
        let Some(assist) = self.snap_assist.as_mut() else {
            return;
        };
        let count = assist.candidates.len().max(1);
        match action {
            AssistKey::Next => assist.select((assist.selected + 1) % count),
            AssistKey::Previous => assist.select((assist.selected + count - 1) % count),
            AssistKey::Choose => return self.choose_snap_assist(),
            AssistKey::Dismiss => return self.dismiss_snap_assist(),
            AssistKey::Ignore | AssistKey::PassThrough => return,
        }
        self.request_native_redraw();
    }

    fn assist_cell_at(&self, location: Point<f64, Logical>) -> Option<usize> {
        let assist = self.snap_assist.as_ref()?;
        assist
            .cells
            .iter()
            .position(|cell| cell.to_f64().contains(location))
    }

    /// A press while Assist is open: a thumbnail is chosen; anywhere else
    /// closes Assist and the press goes on as usual.
    pub(crate) fn handle_snap_assist_click(&mut self, location: Point<f64, Logical>) -> bool {
        if self.snap_assist.is_none() {
            return false;
        }
        if let Some(index) = self.assist_cell_at(location) {
            if let Some(assist) = self.snap_assist.as_mut() {
                assist.select(index);
            }
            self.choose_snap_assist();
            return true;
        }
        self.dismiss_snap_assist();
        false
    }

    /// Pointer hover selects the thumbnail under it.
    pub(crate) fn snap_assist_hover(&mut self, location: Point<f64, Logical>) {
        let Some(index) = self.assist_cell_at(location) else {
            return;
        };
        if let Some(assist) = self.snap_assist.as_mut()
            && assist.selected != index
        {
            assist.select(index);
            self.request_native_redraw();
        }
    }

    fn choose_snap_assist(&mut self) {
        let Some(assist) = self.snap_assist.take() else {
            return;
        };
        self.request_native_redraw();
        let Some(window) = assist.candidates.get(assist.selected).cloned() else {
            return;
        };
        if !self.space.elements().any(|mapped| *mapped == window) {
            return;
        }
        tracing::info!(window = window.id(), "snap assist chose a window");
        self.tile_window(&window, &assist.output, assist.position, None, false);
        self.raise_window(&window, true);
        self.focus_window_keyboard(&window, SERIAL_COUNTER.next_serial());
    }

    /// Keep Assist consistent when a window goes away.
    pub(crate) fn snap_assist_forget(&mut self, key: WindowKey) {
        let Some(assist) = self.snap_assist.as_mut() else {
            return;
        };
        if assist.anchor == key {
            self.dismiss_snap_assist();
            return;
        }
        if let Some(index) = assist
            .candidates
            .iter()
            .position(|window| window.id() == key)
        {
            assist.candidates.remove(index);
            if assist.candidates.is_empty() {
                self.dismiss_snap_assist();
                return;
            }
            assist.relayout();
            self.request_native_redraw();
        }
    }

    /// Probe and log summary of a window's group.
    #[cfg(feature = "gesture-probe")]
    pub(crate) fn group_summary(&self, window: &Window) -> String {
        self.group_of(window.id()).map_or("-".into(), |group| {
            format!("{}:{:.3}", group.id, group.ratio().unwrap_or(0.0))
        })
    }

    #[cfg(feature = "gesture-probe")]
    pub(crate) fn assist_summary(&self) -> String {
        self.snap_assist
            .as_ref()
            .map_or("open=false".into(), |assist| {
                format!(
                    "open=true candidates={} selected={} zone={},{},{},{} cells={}",
                    assist.candidates.len(),
                    assist.selected,
                    assist.zone.loc.x,
                    assist.zone.loc.y,
                    assist.zone.size.w,
                    assist.zone.size.h,
                    assist
                        .cells
                        .iter()
                        .map(|cell| format!(
                            "{},{},{},{}",
                            cell.loc.x, cell.loc.y, cell.size.w, cell.size.h
                        ))
                        .collect::<Vec<_>>()
                        .join(";"),
                )
            })
    }

    /// The edge a probe drag should grab to move a group's split.
    #[cfg(feature = "gesture-probe")]
    pub(crate) fn inner_edge_of(&self, window: &Window) -> ResizeEdge {
        let left = self.group_of(window.id()).is_some_and(|group| {
            matches!(&group.root, SnapNode::Split { a, .. } if **a == SnapNode::Leaf(Some(window.id())))
        });
        if left {
            ResizeEdge::RIGHT
        } else {
            ResizeEdge::LEFT
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rect(x: i32, y: i32, w: i32, h: i32) -> Rect {
        Rectangle::new((x, y).into(), (w, h).into())
    }

    #[test]
    fn a_lone_candidate_stays_a_thumbnail_centred_in_the_zone() {
        let zone = rect(1209, 30, 1210, 1541);
        let cells = assist_cells(zone, 1);
        assert_eq!(cells.len(), 1);
        let cell = cells[0];
        assert!(cell.size.w <= (1210.0 * MAX_CELL_FRACTION) as i32);
        assert!(cell.size.h <= (1541.0 * MAX_CELL_FRACTION) as i32);
        let centre_x = cell.loc.x + cell.size.w / 2;
        let centre_y = cell.loc.y + cell.size.h / 2;
        assert!((centre_x - (1209 + 605)).abs() <= 1);
        assert!((centre_y - (30 + 770)).abs() <= 1);
    }

    #[test]
    fn cells_fit_inside_the_zone_without_overlapping() {
        let zone = rect(0, 30, 1209, 1541);
        for count in 1..=9 {
            let cells = assist_cells(zone, count);
            assert_eq!(cells.len(), count);
            for (index, cell) in cells.iter().enumerate() {
                assert!(zone.contains_rect(*cell), "{count}: {cell:?}");
                for other in &cells[index + 1..] {
                    assert!(!cell.overlaps(*other), "{count}: {cell:?} {other:?}");
                }
            }
        }
    }

    #[test]
    fn a_short_last_row_is_centred() {
        let cells = assist_cells(rect(0, 0, 1200, 1200), 3);
        // Two columns: the third cell sits alone, centred.
        let last = cells[2];
        assert_eq!(last.loc.x + last.size.w / 2, 600);
    }

    #[test]
    fn the_ring_surrounds_the_plate_without_covering_it() {
        let plate = rect(100, 100, 300, 200);
        let bars = ring_rects(plate);
        for bar in bars {
            assert!(!bar.overlaps(plate), "{bar:?}");
        }
        let outer = bars.iter().fold(bars[0], |acc, bar| acc.merge(*bar));
        assert_eq!(outer, rect(97, 97, 306, 206));
        // The bars tile the ring exactly: area of outer minus plate.
        let ring_area: i32 = bars.iter().map(|bar| bar.size.w * bar.size.h).sum();
        assert_eq!(ring_area, 306 * 206 - 300 * 200);
    }

    #[test]
    fn keys_navigate_choose_and_dismiss() {
        assert_eq!(assist_key(keysyms::KEY_Right, false), AssistKey::Next);
        assert_eq!(assist_key(keysyms::KEY_Tab, false), AssistKey::Next);
        assert_eq!(assist_key(keysyms::KEY_Tab, true), AssistKey::Previous);
        assert_eq!(
            assist_key(keysyms::KEY_ISO_Left_Tab, true),
            AssistKey::Previous
        );
        assert_eq!(assist_key(keysyms::KEY_Up, false), AssistKey::Previous);
        assert_eq!(assist_key(keysyms::KEY_Return, false), AssistKey::Choose);
        assert_eq!(assist_key(keysyms::KEY_Escape, false), AssistKey::Dismiss);
        assert_eq!(assist_key(keysyms::KEY_Super_L, false), AssistKey::Ignore);
        assert_eq!(assist_key(keysyms::KEY_a, false), AssistKey::PassThrough);
    }

    #[test]
    fn only_halves_have_an_opposite() {
        assert_eq!(opposite(TilePosition::Left), Some(TilePosition::Right));
        assert_eq!(opposite(TilePosition::Right), Some(TilePosition::Left));
        assert_eq!(opposite(TilePosition::TopLeft), None);
    }
}
