//! Touchpad gesture recognition for the Pantheon session.
//!
//! The native libinput backend forwards raw gesture events here. At the start
//! of each gesture the compositor decides whether it owns the sequence (a
//! bound three-or-more-finger swipe or pinch) or forwards it unchanged to the
//! focused client through `zwp_pointer_gestures_v1`, so applications receive
//! two-finger pinch-to-zoom and hold gestures the way they do on macOS.
//!
//! Owned gestures fire a single action on release: a gesture only fires when
//! it is not cancelled and is dominated by one axis past a distance threshold
//! (swipes) or a scale threshold (pinches). Swipe direction follows the
//! content: moving fingers left reveals the workspace to the right and selects
//! the next workspace.
//!
//! Bindings come from elementary's `io.elementary.desktop.wm.gestures` schema
//! (the Switchboard Mouse & Touchpad plug writes it), plus the M-series
//! `org.techmore.mseries.gestures` schema for the macOS-style pinch that
//! elementary's schema has no value for (thumb-and-three-finger pinch opens
//! the application launcher, like Launchpad).

use gio::{Settings, SettingsBackend, SettingsSchemaSource, prelude::SettingsExt};
use smithay::utils::{Logical, Point};

/// Swipes and pinches with fewer fingers are application input.
pub(crate) const COMPOSITOR_MIN_FINGERS: u32 = 3;
/// Logical pixels a gesture must travel before it fires an action.
/// Aimed at trackpad-sized gestures; a physical-panel qualification can tune
/// this once the native session is measured.
pub(crate) const SWIPE_THRESHOLD: f64 = 90.0;
/// A pinch must shrink to this scale (fingers drawn together) to fire.
pub(crate) const PINCH_IN_SCALE: f64 = 0.7;

const ELEMENTARY_SCHEMA: &str = "io.elementary.desktop.wm.gestures";
const MSERIES_SCHEMA: &str = "org.techmore.mseries.gestures";
/// Schemas whose changes reload [`GestureBindings`].
pub(crate) const SETTINGS_SCHEMAS: &[&str] = &[ELEMENTARY_SCHEMA, MSERIES_SCHEMA];

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) enum HorizontalAction {
    #[default]
    None,
    SwitchToWorkspace,
    MoveToWorkspace,
    SwitchWindows,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) enum UpAction {
    #[default]
    None,
    MultitaskingView,
    ToggleMaximized,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) enum PinchAction {
    #[default]
    None,
    Launcher,
    MultitaskingView,
}

/// Actions for one finger count. Five-finger gestures use the four-finger row.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct FingerBindings {
    pub horizontal: HorizontalAction,
    pub up: UpAction,
    pub pinch_in: PinchAction,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct GestureBindings {
    pub three: FingerBindings,
    pub four: FingerBindings,
}

impl Default for GestureBindings {
    /// elementary's schema defaults plus the Launchpad-style pinch.
    fn default() -> Self {
        Self {
            three: FingerBindings {
                horizontal: HorizontalAction::SwitchToWorkspace,
                up: UpAction::MultitaskingView,
                pinch_in: PinchAction::None,
            },
            four: FingerBindings {
                pinch_in: PinchAction::Launcher,
                ..FingerBindings::default()
            },
        }
    }
}

impl GestureBindings {
    /// Read both schemas; a missing schema keeps that part of the defaults.
    pub(crate) fn load() -> Self {
        let mut bindings = Self::default();
        let Some(source) = SettingsSchemaSource::default() else {
            return bindings;
        };
        if let Some(schema) = source.lookup(ELEMENTARY_SCHEMA, true) {
            let settings = Settings::new_full(&schema, None::<&SettingsBackend>, None);
            for (prefix, row) in [("three", &mut bindings.three), ("four", &mut bindings.four)] {
                row.horizontal = parse_horizontal(
                    &settings.string(&format!("{prefix}-finger-swipe-horizontal")),
                );
                row.up = parse_up(&settings.string(&format!("{prefix}-finger-swipe-up")));
            }
        }
        if let Some(schema) = source.lookup(MSERIES_SCHEMA, true) {
            let settings = Settings::new_full(&schema, None::<&SettingsBackend>, None);
            for (prefix, row) in [("three", &mut bindings.three), ("four", &mut bindings.four)] {
                row.pinch_in = parse_pinch(&settings.string(&format!("{prefix}-finger-pinch-in")));
            }
        }
        bindings
    }

    pub(crate) fn for_fingers(&self, fingers: u32) -> FingerBindings {
        match fingers {
            0..COMPOSITOR_MIN_FINGERS => FingerBindings::default(),
            COMPOSITOR_MIN_FINGERS => self.three,
            _ => self.four,
        }
    }
}

fn parse_horizontal(value: &str) -> HorizontalAction {
    match value {
        "switch-to-workspace" => HorizontalAction::SwitchToWorkspace,
        "move-to-workspace" => HorizontalAction::MoveToWorkspace,
        "switch-windows" => HorizontalAction::SwitchWindows,
        _ => HorizontalAction::None,
    }
}

fn parse_up(value: &str) -> UpAction {
    match value {
        "multitasking-view" => UpAction::MultitaskingView,
        "toggle-maximized" => UpAction::ToggleMaximized,
        _ => UpAction::None,
    }
}

fn parse_pinch(value: &str) -> PinchAction {
    match value {
        "launcher" => PinchAction::Launcher,
        "multitasking-view" => PinchAction::MultitaskingView,
        _ => PinchAction::None,
    }
}

/// What a finished gesture asks the compositor to do.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum GestureOutcome {
    None,
    /// Select the workspace `delta` steps away (stops at the ends).
    SwitchWorkspace(i32),
    /// Take the focused window to the adjacent workspace and follow it.
    MoveWindowToWorkspace(i32),
    /// Focus the next (`true`) or previous window on this workspace.
    CycleWindows(bool),
    ToggleOverview,
    CloseOverview,
    ToggleMaximized,
    OpenLauncher,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct SwipeGestureState {
    bindings: FingerBindings,
    overview_open: bool,
    delta: Point<f64, Logical>,
}

impl SwipeGestureState {
    /// Start tracking a swipe the compositor owns, or return `None` so the
    /// caller forwards it to the focused client.
    pub(crate) fn begin(
        bindings: &GestureBindings,
        fingers: u32,
        overview_open: bool,
    ) -> Option<Self> {
        if fingers < COMPOSITOR_MIN_FINGERS {
            return None;
        }
        let row = bindings.for_fingers(fingers);
        let owned =
            overview_open || row.horizontal != HorizontalAction::None || row.up != UpAction::None;
        owned.then_some(Self {
            bindings: row,
            overview_open,
            delta: (0.0, 0.0).into(),
        })
    }

    pub(crate) fn update(&mut self, delta: Point<f64, Logical>) {
        self.delta += delta;
    }

    pub(crate) fn finish(self, cancelled: bool) -> GestureOutcome {
        if cancelled {
            return GestureOutcome::None;
        }
        let (dx, dy) = (self.delta.x, self.delta.y);
        if dx.abs() >= SWIPE_THRESHOLD && dx.abs() > dy.abs() {
            let step = if dx < 0.0 { 1 } else { -1 };
            return match self.bindings.horizontal {
                HorizontalAction::None => GestureOutcome::None,
                HorizontalAction::SwitchToWorkspace => GestureOutcome::SwitchWorkspace(step),
                HorizontalAction::MoveToWorkspace => GestureOutcome::MoveWindowToWorkspace(step),
                HorizontalAction::SwitchWindows => GestureOutcome::CycleWindows(step > 0),
            };
        }
        if dy.abs() < SWIPE_THRESHOLD || dy.abs() <= dx.abs() {
            return GestureOutcome::None;
        }
        // As on macOS, swiping down dismisses the overview whichever finger
        // count opened it; swiping up again also closes it.
        if self.overview_open {
            return GestureOutcome::CloseOverview;
        }
        if dy > 0.0 {
            return GestureOutcome::None;
        }
        match self.bindings.up {
            UpAction::None => GestureOutcome::None,
            UpAction::MultitaskingView => GestureOutcome::ToggleOverview,
            UpAction::ToggleMaximized => GestureOutcome::ToggleMaximized,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct PinchGestureState {
    action: PinchAction,
    scale: f64,
}

impl PinchGestureState {
    /// Start tracking a pinch the compositor owns, or return `None` so the
    /// caller forwards it (two-finger pinch-to-zoom stays with applications).
    pub(crate) fn begin(bindings: &GestureBindings, fingers: u32) -> Option<Self> {
        let action = bindings.for_fingers(fingers).pinch_in;
        (action != PinchAction::None).then_some(Self { action, scale: 1.0 })
    }

    /// libinput reports the absolute scale relative to the gesture start.
    pub(crate) fn update(&mut self, scale: f64) {
        self.scale = scale;
    }

    pub(crate) fn finish(self, cancelled: bool) -> GestureOutcome {
        if cancelled || self.scale > PINCH_IN_SCALE {
            return GestureOutcome::None;
        }
        match self.action {
            PinchAction::None => GestureOutcome::None,
            PinchAction::Launcher => GestureOutcome::OpenLauncher,
            PinchAction::MultitaskingView => GestureOutcome::ToggleOverview,
        }
    }
}

/// The gesture currently on the touchpad and who receives it.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum ActiveGesture {
    Swipe(SwipeGestureState),
    Pinch(PinchGestureState),
    /// Sent to the focused client through `zwp_pointer_gestures_v1`.
    ForwardedSwipe,
    ForwardedPinch,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn swipe(fingers: u32, overview_open: bool, deltas: &[(f64, f64)]) -> GestureOutcome {
        let bindings = GestureBindings::default();
        let mut gesture = SwipeGestureState::begin(&bindings, fingers, overview_open)
            .expect("swipe should be owned");
        for delta in deltas {
            gesture.update((*delta).into());
        }
        gesture.finish(false)
    }

    #[test]
    fn horizontal_swipe_selects_adjacent_workspace() {
        assert_eq!(
            swipe(3, false, &[(-40.0, 8.0), (-60.0, -4.0)]),
            GestureOutcome::SwitchWorkspace(1)
        );
        assert_eq!(
            swipe(3, false, &[(120.0, 0.0)]),
            GestureOutcome::SwitchWorkspace(-1)
        );
    }

    #[test]
    fn upward_swipe_toggles_and_downward_swipe_closes_the_overview() {
        assert_eq!(
            swipe(3, false, &[(-5.0, -60.0), (4.0, -70.0)]),
            GestureOutcome::ToggleOverview
        );
        assert_eq!(swipe(3, false, &[(0.0, 140.0)]), GestureOutcome::None);
        assert_eq!(
            swipe(3, true, &[(0.0, 140.0)]),
            GestureOutcome::CloseOverview
        );
        assert_eq!(
            swipe(3, true, &[(0.0, -140.0)]),
            GestureOutcome::CloseOverview
        );
    }

    #[test]
    fn short_or_diagonal_swipes_do_nothing() {
        assert_eq!(swipe(3, false, &[(40.0, 0.0)]), GestureOutcome::None);
        assert_eq!(swipe(3, false, &[(100.0, 120.0)]), GestureOutcome::None);
    }

    #[test]
    fn unbound_and_two_finger_swipes_are_forwarded() {
        let bindings = GestureBindings::default();
        assert!(SwipeGestureState::begin(&bindings, 2, false).is_none());
        // Four-finger swipes default to "none", so applications receive them.
        assert!(SwipeGestureState::begin(&bindings, 4, false).is_none());
        // While the overview is open any multi-finger swipe can dismiss it.
        assert!(SwipeGestureState::begin(&bindings, 4, true).is_some());
    }

    #[test]
    fn cancelled_swipes_do_nothing() {
        let bindings = GestureBindings::default();
        let mut gesture = SwipeGestureState::begin(&bindings, 3, false).unwrap();
        gesture.update((-200.0, 0.0).into());
        assert_eq!(gesture.finish(true), GestureOutcome::None);
    }

    #[test]
    fn configured_actions_are_honoured() {
        let mut bindings = GestureBindings::default();
        bindings.four.horizontal = HorizontalAction::MoveToWorkspace;
        bindings.three.horizontal = HorizontalAction::SwitchWindows;
        bindings.three.up = UpAction::ToggleMaximized;

        let mut gesture = SwipeGestureState::begin(&bindings, 5, false).unwrap();
        gesture.update((-150.0, 0.0).into());
        assert_eq!(
            gesture.finish(false),
            GestureOutcome::MoveWindowToWorkspace(1)
        );

        let mut gesture = SwipeGestureState::begin(&bindings, 3, false).unwrap();
        gesture.update((150.0, 0.0).into());
        assert_eq!(gesture.finish(false), GestureOutcome::CycleWindows(false));

        let mut gesture = SwipeGestureState::begin(&bindings, 3, false).unwrap();
        gesture.update((0.0, -150.0).into());
        assert_eq!(gesture.finish(false), GestureOutcome::ToggleMaximized);
    }

    #[test]
    fn four_finger_pinch_opens_the_launcher() {
        let bindings = GestureBindings::default();
        let mut pinch = PinchGestureState::begin(&bindings, 4).unwrap();
        pinch.update(0.85);
        pinch.update(0.55);
        assert_eq!(pinch.finish(false), GestureOutcome::OpenLauncher);

        // A spread or a small pinch does nothing.
        let mut pinch = PinchGestureState::begin(&bindings, 4).unwrap();
        pinch.update(1.6);
        assert_eq!(pinch.finish(false), GestureOutcome::None);
        let mut pinch = PinchGestureState::begin(&bindings, 4).unwrap();
        pinch.update(0.8);
        assert_eq!(pinch.finish(false), GestureOutcome::None);
    }

    #[test]
    fn two_and_three_finger_pinches_stay_with_applications() {
        let bindings = GestureBindings::default();
        assert!(PinchGestureState::begin(&bindings, 2).is_none());
        assert!(PinchGestureState::begin(&bindings, 3).is_none());
    }

    #[test]
    fn setting_values_parse_like_the_schema_nicks() {
        assert_eq!(
            parse_horizontal("switch-windows"),
            HorizontalAction::SwitchWindows
        );
        assert_eq!(parse_horizontal("bogus"), HorizontalAction::None);
        assert_eq!(parse_up("toggle-maximized"), UpAction::ToggleMaximized);
        assert_eq!(parse_pinch("launcher"), PinchAction::Launcher);
        assert_eq!(parse_pinch("none"), PinchAction::None);
    }
}
