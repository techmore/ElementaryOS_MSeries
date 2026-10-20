//! Render-only gesture previews. Real workspace/focus/geometry changes happen
//! once the release spring reaches its endpoint, never on touchpad updates.
use crate::{
    PantheonCompositor,
    gestures::{GestureOutcome, HorizontalAction, SwipeGestureState, UpAction},
};
use gio::{Settings, SettingsSchemaSource, prelude::SettingsExt};
use smithay::{
    desktop::Window,
    utils::{Logical, Point, Rectangle},
};
use std::time::{Duration, Instant};

const TRAVEL: f64 = 360.0;
const AXIS_LOCK: f64 = 8.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum PreviewKind {
    Workspace,
    Overview { closing: bool },
}

pub(crate) struct PreviewWindow {
    pub window: Window,
    pub from: Rectangle<i32, Logical>,
    pub to: Rectangle<i32, Logical>,
}

#[derive(Clone, Copy, Debug)]
struct Spring {
    from: f64,
    velocity: f64,
    target: f64,
    started: Instant,
}
impl Spring {
    fn sample(self, now: Instant) -> (f64, bool) {
        spring(
            self.from,
            self.velocity,
            self.target,
            now.saturating_duration_since(self.started).as_secs_f64(),
        )
    }
}

/// Exact critically damped spring; bounded completion avoids perpetual redraw.
fn spring(from: f64, velocity: f64, target: f64, seconds: f64) -> (f64, bool) {
    let omega = 24.0;
    let displacement = from - target;
    let coefficient = velocity + omega * displacement;
    let decay = (-omega * seconds).exp();
    let position = target + (displacement + coefficient * seconds) * decay;
    let speed = (velocity - omega * coefficient * seconds) * decay;
    let done = seconds >= 0.6 || ((position - target).abs() < 0.001 && speed.abs() < 0.01);
    (if done { target } else { position }, done)
}

fn resisted(raw: f64, previous: bool, next: bool) -> f64 {
    let available = if raw < 0.0 { next } else { previous };
    if available {
        raw.clamp(-1.0, 1.0)
    } else {
        raw.signum() * 0.12 * (1.0 - (-raw.abs()).exp())
    }
}

fn snap(progress: f64, velocity: f64, cancelled: bool) -> f64 {
    if cancelled {
        return 0.0;
    }
    let projected = progress + velocity.clamp(-4.0, 4.0) * 0.12;
    if projected.abs() >= 0.25 {
        projected.signum()
    } else {
        0.0
    }
}

pub(crate) struct GestureAnimation {
    pub kind: PreviewKind,
    pub workspace: usize,
    pub windows: Vec<PreviewWindow>,
    pub progress: f64,
    velocity: f64,
    last: Instant,
    previous: bool,
    next: bool,
    spring: Option<Spring>,
    outcome: GestureOutcome,
}

impl GestureAnimation {
    fn update(&mut self, delta: Point<f64, Logical>, now: Instant) {
        let raw = match self.kind {
            PreviewKind::Workspace => resisted(delta.x / TRAVEL, self.previous, self.next),
            PreviewKind::Overview { closing } => {
                let movement = if closing { delta.y.abs() } else { -delta.y };
                (movement / TRAVEL).clamp(0.0, 1.0)
            }
        };
        let dt = now.saturating_duration_since(self.last).as_secs_f64();
        self.velocity = if dt >= 0.001 {
            ((raw - self.progress) / dt).clamp(-8.0, 8.0)
        } else {
            0.0
        };
        self.progress = raw;
        self.last = now;
    }

    fn release(&mut self, cancelled: bool, now: Instant) {
        // A paused finger must not retain a previous flick velocity.
        if now.saturating_duration_since(self.last) > Duration::from_millis(100) {
            self.velocity = 0.0;
        }
        let mut target = snap(self.progress, self.velocity, cancelled);
        self.outcome = match self.kind {
            PreviewKind::Workspace => {
                if (target < 0.0 && !self.next) || (target > 0.0 && !self.previous) {
                    target = 0.0;
                }
                if target == 0.0 {
                    GestureOutcome::None
                } else {
                    GestureOutcome::SwitchWorkspace(if target < 0.0 { 1 } else { -1 })
                }
            }
            PreviewKind::Overview { closing } => {
                target = target.clamp(0.0, 1.0);
                if target == 0.0 {
                    GestureOutcome::None
                } else if closing {
                    GestureOutcome::CloseOverview
                } else {
                    GestureOutcome::ToggleOverview
                }
            }
        };
        self.spring = Some(Spring {
            from: self.progress,
            velocity: self.velocity,
            target,
            started: now,
        });
    }
}

impl PantheonCompositor {
    pub(crate) fn update_gesture_animation(&mut self, swipe: SwipeGestureState) {
        let (delta, bindings, overview) = swipe.preview();
        if self.gesture_animation.is_none() && delta.x.abs().max(delta.y.abs()) >= AXIS_LOCK {
            let kind = if delta.x.abs() > delta.y.abs()
                && !overview
                && bindings.horizontal == HorizontalAction::SwitchToWorkspace
            {
                Some(PreviewKind::Workspace)
            } else if delta.y.abs() > delta.x.abs()
                && (overview || (delta.y < 0.0 && bindings.up == UpAction::MultitaskingView))
            {
                Some(PreviewKind::Overview { closing: overview })
            } else {
                None
            };
            if let Some(kind) = kind {
                let workspace = self.workspace_manager.active();
                let windows = if matches!(kind, PreviewKind::Overview { .. }) {
                    self.overview_preview_windows()
                } else {
                    Vec::new()
                };
                if matches!(kind, PreviewKind::Overview { .. }) && windows.is_empty() {
                    return;
                }
                self.gesture_animation = Some(GestureAnimation {
                    kind,
                    workspace,
                    windows,
                    progress: 0.0,
                    velocity: 0.0,
                    last: Instant::now(),
                    previous: workspace > 0,
                    next: workspace + 1 < self.workspace_manager.workspace_count(),
                    spring: None,
                    outcome: GestureOutcome::None,
                });
            }
        }
        if let Some(animation) = self.gesture_animation.as_mut() {
            animation.update(delta, Instant::now());
            self.request_native_redraw();
        }
    }

    /// Returns true if the visual transition owns the release action.
    pub(crate) fn release_gesture_animation(&mut self, cancelled: bool) -> bool {
        let Some(animation) = self.gesture_animation.as_mut() else {
            return false;
        };
        animation.release(cancelled, Instant::now());
        let animations = SettingsSchemaSource::default()
            .and_then(|source| source.lookup("org.gnome.desktop.interface", true))
            .filter(|schema| schema.has_key("enable-animations"))
            .is_none_or(|schema| {
                Settings::new_full(&schema, None::<&gio::SettingsBackend>, None)
                    .boolean("enable-animations")
            });
        if !animations {
            let outcome = self.gesture_animation.take().unwrap().outcome;
            let _ = self.apply_swipe_outcome(outcome);
            self.request_native_redraw();
            return true;
        }
        // A short-lived source exists only while settling, never while idle.
        let identity = self
            .gesture_animation
            .as_ref()
            .and_then(|animation| animation.spring)
            .unwrap()
            .started;
        let inserted = self.loop_handle.insert_source(
            smithay::reexports::calloop::timer::Timer::immediate(),
            move |_, _, state| {
                use smithay::reexports::calloop::timer::TimeoutAction;
                if state
                    .gesture_animation
                    .as_ref()
                    .and_then(|animation| animation.spring)
                    .is_none_or(|spring| spring.started != identity)
                {
                    return TimeoutAction::Drop;
                }
                if state.advance_gesture_animation(Instant::now()) {
                    TimeoutAction::ToDuration(Duration::from_millis(8))
                } else {
                    TimeoutAction::Drop
                }
            },
        );
        if let Err(error) = inserted {
            tracing::warn!(?error, "could not schedule gesture animation");
            self.discard_gesture_animation();
        }
        true
    }

    fn advance_gesture_animation(&mut self, now: Instant) -> bool {
        if self.session_locked
            || self
                .seat
                .get_pointer()
                .is_some_and(|pointer| pointer.is_grabbed())
            || self
                .gesture_animation
                .as_ref()
                .is_some_and(|animation| animation.workspace != self.workspace_manager.active())
        {
            self.discard_gesture_animation();
            return false;
        }
        let Some(animation) = self.gesture_animation.as_mut() else {
            return false;
        };
        let Some(spring) = animation.spring else {
            return false;
        };
        let (progress, done) = spring.sample(now);
        animation.progress = progress;
        if done {
            let outcome = self.gesture_animation.take().unwrap().outcome;
            if let Err(error) = self.apply_swipe_outcome(outcome) {
                tracing::debug!(%error, "gesture transition could not commit");
            }
        }
        self.request_native_redraw();
        !done
    }

    /// Hidden neighbors also need frame callbacks while their buffers are
    /// visible in a swipe, otherwise animated clients freeze in the preview.
    pub(crate) fn gesture_frame_windows(&self) -> Vec<Window> {
        let mut windows = self.space.elements().cloned().collect::<Vec<_>>();
        if let Some(animation) = &self.gesture_animation
            && animation.kind == PreviewKind::Workspace
        {
            for step in [-1_i32, 1] {
                let index = animation.workspace as i32 + step;
                if index < 0 {
                    continue;
                }
                windows.extend(
                    self.workspace_manager
                        .windows_in(index as usize)
                        .into_iter()
                        .map(|(window, _)| window)
                        .filter(|window| {
                            !self
                                .minimized_windows
                                .values()
                                .any(|(known, _)| known == window)
                                && !self
                                    .x11_minimized_windows
                                    .values()
                                    .any(|(known, _)| known == window)
                        }),
                );
            }
        }
        windows
    }

    pub(crate) fn discard_gesture_animation(&mut self) {
        if self.gesture_animation.take().is_some() {
            self.request_native_redraw();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn flicks_distance_reversal_and_cancellation() {
        assert_eq!(snap(-0.4, 0.0, false), -1.0);
        assert_eq!(snap(-0.1, -2.0, false), -1.0);
        assert_eq!(snap(-0.3, 2.0, false), 0.0);
        assert_eq!(snap(-0.8, -2.0, true), 0.0);
        assert_eq!(snap(0.05, 0.0, false), 0.0);
    }
    #[test]
    fn edges_resist_and_direction_reversal_recovers() {
        assert_eq!(resisted(-0.5, false, true), -0.5);
        assert!(resisted(1.0, false, true) > 0.0 && resisted(1.0, false, true) < 0.12);
        assert!(resisted(-1.0, true, false) < 0.0 && resisted(-1.0, true, false) > -0.12);
        assert_eq!(resisted(0.0, false, false), 0.0);
    }
    fn animation(now: Instant) -> GestureAnimation {
        GestureAnimation {
            kind: PreviewKind::Workspace,
            workspace: 0,
            windows: Vec::new(),
            progress: 0.0,
            velocity: 0.0,
            last: now,
            previous: false,
            next: true,
            spring: None,
            outcome: GestureOutcome::None,
        }
    }

    #[test]
    fn stale_velocity_and_unavailable_edges_cannot_commit() {
        let now = Instant::now();
        let mut preview = animation(now);
        preview.progress = -0.1;
        preview.velocity = -4.0;
        preview.release(false, now + Duration::from_millis(101));
        assert_eq!(preview.outcome, GestureOutcome::None);
        let mut preview = animation(now);
        preview.progress = 0.1;
        preview.velocity = 4.0;
        preview.release(false, now);
        assert_eq!(preview.outcome, GestureOutcome::None);
        assert_eq!(preview.spring.unwrap().target, 0.0);
    }

    #[test]
    fn reversal_and_cancel_return_the_original_workspace() {
        let now = Instant::now();
        let mut preview = animation(now);
        preview.update((-180.0, 0.0).into(), now + Duration::from_millis(100));
        assert_eq!(preview.progress, -0.5);
        preview.update((-10.0, 0.0).into(), now + Duration::from_millis(200));
        preview.release(true, now + Duration::from_millis(201));
        assert_eq!(preview.outcome, GestureOutcome::None);
        assert_eq!(preview.spring.unwrap().target, 0.0);
        let mut preview = animation(now);
        preview.update((-180.0, 0.0).into(), now + Duration::from_millis(100));
        preview.release(false, now + Duration::from_millis(101));
        assert_eq!(preview.outcome, GestureOutcome::SwitchWorkspace(1));
    }

    #[test]
    fn spring_is_continuous_and_finishes_at_exact_endpoint() {
        assert_eq!(spring(0.4, 1.0, 1.0, 0.0), (0.4, false));
        let (middle, done) = spring(0.4, 1.0, 1.0, 0.05);
        assert!(middle > 0.4 && middle < 1.0 && !done);
        assert_eq!(spring(0.4, 1.0, 1.0, 0.6), (1.0, true));
        assert_eq!(spring(-0.4, -2.0, 0.0, 0.6), (0.0, true));
    }
}
