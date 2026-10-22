//! Move grab is the state of a composer during which the client window is being dragged around.
//!
//! eg. Usually whenever a user clicks on the app's titlebar and starts dragging, the compositors
//! enters a MoveSurfaceGrab state.

use crate::PantheonCompositor;
use smithay::{
    desktop::Window,
    input::pointer::{
        AxisFrame, ButtonEvent, GestureHoldBeginEvent, GestureHoldEndEvent, GesturePinchBeginEvent,
        GesturePinchEndEvent, GesturePinchUpdateEvent, GestureSwipeBeginEvent,
        GestureSwipeEndEvent, GestureSwipeUpdateEvent, GrabStartData as PointerGrabStartData,
        MotionEvent, PointerGrab, PointerInnerHandle, RelativeMotionEvent,
    },
    reexports::wayland_server::protocol::wl_surface::WlSurface,
    utils::{Logical, Point, Rectangle},
};

/// Pointer travel before a snapped or maximized window un-snaps, so a click
/// on its title bar never moves it.
const DETACH_DISTANCE: f64 = 8.0;

pub struct MoveSurfaceGrab {
    start_data: PointerGrabStartData<PantheonCompositor>,
    window: Window,
    /// Window location minus pointer location; constant while dragging.
    offset: Point<f64, Logical>,
    /// The window is snapped or maximized and has not been pulled out yet.
    pending_detach: bool,
    detached: bool,
    /// Floating rect to return to if the drag ends in a snap.
    restore: Option<Rectangle<i32, Logical>>,
}

impl MoveSurfaceGrab {
    pub fn new(
        start_data: PointerGrabStartData<PantheonCompositor>,
        window: Window,
        initial_window_location: Point<i32, Logical>,
        detach: bool,
        restore: Option<Rectangle<i32, Logical>>,
    ) -> Self {
        let offset = initial_window_location.to_f64() - start_data.location;
        Self {
            start_data,
            window,
            offset,
            pending_detach: detach,
            detached: false,
            restore,
        }
    }
}

impl PointerGrab<PantheonCompositor> for MoveSurfaceGrab {
    fn motion(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        _focus: Option<(WlSurface, Point<f64, Logical>)>,
        event: &MotionEvent,
    ) {
        // While the grab is active, no client has pointer focus
        handle.motion(data, None, event);

        if self.pending_detach {
            let travel = event.location - self.start_data.location;
            if travel.x.hypot(travel.y) < DETACH_DISTANCE {
                return;
            }
            self.pending_detach = false;
            // Restore the floating size under the pointer (S1).
            if let Some(location) = data.detach_for_drag(&self.window, event.location) {
                self.offset = location.to_f64() - event.location;
                self.detached = true;
            }
        }
        let new_location = event.location + self.offset;
        data.space
            .map_element(self.window.clone(), new_location.to_i32_round(), true);
        // Hard stop at the top of the taskbar.
        data.keep_clear_of_bottom_panels(&self.window);
        data.update_corner_snap_preview(&self.window, event.location);
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

    fn button(
        &mut self,
        data: &mut PantheonCompositor,
        handle: &mut PointerInnerHandle<'_, PantheonCompositor>,
        event: &ButtonEvent,
    ) {
        handle.button(data, event);

        // The button is a button code as defined in the
        // Linux kernel's linux/input-event-codes.h header file, e.g. BTN_LEFT.
        const BTN_LEFT: u32 = 0x110;

        if !handle.current_pressed().contains(&BTN_LEFT) {
            let snap = (!data.corner_snap_cancelled)
                .then(|| data.corner_snap_preview.clone())
                .flatten();
            let window = self.window.clone();
            let (detached, restore) = (self.detached, self.restore);
            // No more buttons are pressed, release the grab.
            handle.unset_grab(self, data, event.serial, event.time, true);
            data.finish_move_snap();
            // Snapping reads the pointer (panel visibility), which is locked
            // while this grab runs.
            data.loop_handle
                .insert_idle(move |state| state.end_move(&window, snap, detached, restore));
        }
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
        data.finish_move_snap();
    }
}
