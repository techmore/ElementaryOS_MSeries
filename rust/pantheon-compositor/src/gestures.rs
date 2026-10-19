//! Touchpad gesture recognition for the Pantheon session.
//!
//! The native libinput backend forwards raw gesture events here. This module
//! keeps the small amount of state needed to turn a swipe sequence into a
//! single action: a gesture only fires when it is not cancelled, uses at least
//! three fingers, and is dominated by one axis past a distance threshold.
//! Swipe direction follows the content: moving three fingers left reveals the
//! workspace to the right and selects the next workspace; moving three fingers
//! up toggles the grid overview (the explicit replacement for Gala's
//! multitasking view).
//!
//! Pinch gestures are deliberately ignored until the compositor has an
//! overview surface that zoom actions could drive.

use smithay::utils::{Logical, Point};

/// Swipes with fewer fingers are treated as pointer input, matching GNOME.
pub(crate) const SWIPE_MIN_FINGERS: u32 = 3;
/// Logical pixels a gesture must travel before it switches a workspace.
/// Aimed at trackpad-sized gestures; a physical-panel qualification can tune
/// this once the native session is measured.
pub(crate) const SWIPE_THRESHOLD: f64 = 90.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum SwipeOutcome {
    None,
    PreviousWorkspace,
    NextWorkspace,
    ToggleOverview,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub(crate) struct SwipeGestureState {
    fingers: u32,
    delta: Point<f64, Logical>,
    cancelled: bool,
}

impl SwipeGestureState {
    pub(crate) fn begin(fingers: u32) -> Self {
        Self {
            fingers,
            delta: (0.0, 0.0).into(),
            cancelled: false,
        }
    }

    pub(crate) fn update(&mut self, delta: Point<f64, Logical>) {
        self.delta += delta;
    }

    pub(crate) fn finish(self, cancelled: bool) -> SwipeOutcome {
        if cancelled || self.cancelled || self.fingers < SWIPE_MIN_FINGERS {
            return SwipeOutcome::None;
        }
        let (dx, dy) = (self.delta.x, self.delta.y);
        if dx.abs() >= SWIPE_THRESHOLD && dx.abs() > dy.abs() {
            return if dx < 0.0 {
                SwipeOutcome::NextWorkspace
            } else {
                SwipeOutcome::PreviousWorkspace
            };
        }
        // An upward swipe opens or closes the grid overview, mirroring the
        // installed Gala overlay gesture mapping to PerformAction(1).
        if dy <= -SWIPE_THRESHOLD && dy.abs() > dx.abs() {
            return SwipeOutcome::ToggleOverview;
        }
        SwipeOutcome::None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn horizontal_swipe_selects_adjacent_workspace() {
        let mut gesture = SwipeGestureState::begin(3);
        gesture.update((-40.0, 8.0).into());
        gesture.update((-60.0, -4.0).into());
        assert_eq!(gesture.finish(false), SwipeOutcome::NextWorkspace);

        let mut gesture = SwipeGestureState::begin(3);
        gesture.update((120.0, 0.0).into());
        assert_eq!(gesture.finish(false), SwipeOutcome::PreviousWorkspace);
    }

    #[test]
    fn upward_swipe_toggles_the_overview() {
        let mut gesture = SwipeGestureState::begin(3);
        gesture.update((-5.0, -60.0).into());
        gesture.update((4.0, -70.0).into());
        assert_eq!(gesture.finish(false), SwipeOutcome::ToggleOverview);

        // Downward swipes are not bound yet.
        let mut gesture = SwipeGestureState::begin(3);
        gesture.update((0.0, 140.0).into());
        assert_eq!(gesture.finish(false), SwipeOutcome::None);
    }

    #[test]
    fn short_or_diagonal_swipes_do_nothing() {
        let mut gesture = SwipeGestureState::begin(3);
        gesture.update((40.0, 0.0).into());
        assert_eq!(gesture.finish(false), SwipeOutcome::None);

        let mut gesture = SwipeGestureState::begin(4);
        gesture.update((100.0, 120.0).into());
        assert_eq!(gesture.finish(false), SwipeOutcome::None);
    }

    #[test]
    fn two_finger_and_cancelled_swipes_do_nothing() {
        let mut gesture = SwipeGestureState::begin(2);
        gesture.update((-200.0, 0.0).into());
        assert_eq!(gesture.finish(false), SwipeOutcome::None);

        let mut gesture = SwipeGestureState::begin(3);
        gesture.update((-200.0, 0.0).into());
        assert_eq!(gesture.finish(true), SwipeOutcome::None);
    }
}
