//! Dragging the shared edge of a snap group resizes both members.

use crate::PantheonCompositor;
use crate::snap_group::{SnapGroupId, dragged_ratio};
use smithay::{
    input::pointer::{
        AxisFrame, ButtonEvent, GestureHoldBeginEvent, GestureHoldEndEvent, GesturePinchBeginEvent,
        GesturePinchEndEvent, GesturePinchUpdateEvent, GestureSwipeBeginEvent,
        GestureSwipeEndEvent, GestureSwipeUpdateEvent, GrabStartData as PointerGrabStartData,
        MotionEvent, PointerGrab, PointerInnerHandle, RelativeMotionEvent,
    },
    reexports::wayland_server::protocol::wl_surface::WlSurface,
    utils::{Logical, Point},
};

pub struct SplitResizeGrab {
    start_data: PointerGrabStartData<PantheonCompositor>,
    group: SnapGroupId,
    start_ratio: f64,
    /// Width of the group's work area, logical pixels.
    total: i32,
}

impl SplitResizeGrab {
    pub fn new(
        start_data: PointerGrabStartData<PantheonCompositor>,
        group: SnapGroupId,
        start_ratio: f64,
        total: i32,
    ) -> Self {
        Self {
            start_data,
            group,
            start_ratio,
            total,
        }
    }
}

impl PointerGrab<PantheonCompositor> for SplitResizeGrab {
    fn motion(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        _focus: Option<(WlSurface, Point<f64, Logical>)>,
        event: &MotionEvent,
    ) {
        handle.motion(data, None, event);
        let dx = event.location.x - self.start_data.location.x;
        data.set_group_ratio(self.group, dragged_ratio(self.start_ratio, dx, self.total));
    }

    fn button(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &ButtonEvent,
    ) {
        handle.button(data, event);
        if !handle.current_pressed().contains(&self.start_data.button) {
            let group = self.group;
            handle.unset_grab(self, data, event.serial, event.time, true);
            data.loop_handle
                .insert_idle(move |state| state.finish_split_resize(group));
        }
    }

    fn relative_motion(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        focus: Option<(WlSurface, Point<f64, Logical>)>,
        event: &RelativeMotionEvent,
    ) {
        handle.relative_motion(data, focus, event);
    }

    fn axis(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        details: AxisFrame,
    ) {
        handle.axis(data, details)
    }

    fn frame(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
    ) {
        handle.frame(data);
    }

    fn gesture_swipe_begin(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &GestureSwipeBeginEvent,
    ) {
        handle.gesture_swipe_begin(data, event)
    }

    fn gesture_swipe_update(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &GestureSwipeUpdateEvent,
    ) {
        handle.gesture_swipe_update(data, event)
    }

    fn gesture_swipe_end(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &GestureSwipeEndEvent,
    ) {
        handle.gesture_swipe_end(data, event)
    }

    fn gesture_pinch_begin(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &GesturePinchBeginEvent,
    ) {
        handle.gesture_pinch_begin(data, event)
    }

    fn gesture_pinch_update(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &GesturePinchUpdateEvent,
    ) {
        handle.gesture_pinch_update(data, event)
    }

    fn gesture_pinch_end(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &GesturePinchEndEvent,
    ) {
        handle.gesture_pinch_end(data, event)
    }

    fn gesture_hold_begin(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &GestureHoldBeginEvent,
    ) {
        handle.gesture_hold_begin(data, event)
    }

    fn gesture_hold_end(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &GestureHoldEndEvent,
    ) {
        handle.gesture_hold_end(data, event)
    }

    fn start_data(&self) -> &PointerGrabStartData<PantheonCompositor> {
        &self.start_data
    }

    fn unset(&mut self, data: &mut PantheonCompositor) {
        data.split_grab_active = false;
    }
}
