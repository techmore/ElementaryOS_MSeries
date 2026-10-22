use gio::{
    Settings, SettingsBackend, SettingsSchemaSource,
    prelude::{SettingsExt, SettingsExtManual},
};
use smithay::{
    backend::input::{
        AbsolutePositionEvent, Axis, AxisSource, ButtonState, Event, GestureBeginEvent,
        GestureEndEvent, GesturePinchUpdateEvent as _, GestureSwipeUpdateEvent as _, InputBackend,
        InputEvent, InputTime, KeyboardKeyEvent, PointerAxisEvent, PointerButtonEvent,
        PointerMotionEvent,
    },
    input::{
        keyboard::{FilterResult, KeyboardTarget, XkbConfig},
        pointer::{
            AxisFrame, ButtonEvent, GestureHoldBeginEvent, GestureHoldEndEvent,
            GesturePinchBeginEvent, GesturePinchEndEvent, GesturePinchUpdateEvent,
            GestureSwipeBeginEvent, GestureSwipeEndEvent, GestureSwipeUpdateEvent, MotionEvent,
            RelativeMotionEvent,
        },
    },
    utils::{Logical, Point, SERIAL_COUNTER},
};

use crate::gestures::ActiveGesture;
use crate::state::PantheonCompositor;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct StartupKeyboardConfig {
    pub model: String,
    pub layout: String,
    pub variant: String,
    pub options: Option<String>,
    pub repeat_delay: i32,
    pub repeat_rate: i32,
}

pub(crate) fn startup_keyboard_config() -> StartupKeyboardConfig {
    let mut config = StartupKeyboardConfig {
        model: String::new(),
        layout: String::new(),
        variant: String::new(),
        options: None,
        repeat_delay: 500,
        repeat_rate: 33,
    };
    let Some(source) = SettingsSchemaSource::default() else {
        return config;
    };

    if let Some(schema) = source.lookup("org.gnome.desktop.input-sources", true) {
        let settings = Settings::new_full(&schema, None::<&SettingsBackend>, None);
        config.model = settings.string("xkb-model").to_string();
        config.options = Some(
            settings
                .strv("xkb-options")
                .iter()
                .map(|option| option.to_string())
                .collect::<Vec<_>>()
                .join(","),
        );
        let sources = settings
            .value("sources")
            .get::<Vec<(String, String)>>()
            .unwrap_or_default();
        let current_index = settings.uint("current") as usize;
        let current = sources.get(current_index);
        let selected = current
            .filter(|(kind, _)| kind == "xkb")
            .or_else(|| sources.iter().find(|(kind, _)| kind == "xkb"));
        if let Some((_, source_id)) = selected {
            if let Some((layout, variant)) = source_id.split_once('+') {
                config.layout = layout.to_owned();
                config.variant = variant.to_owned();
            } else {
                config.layout.clone_from(source_id);
            }
        }
    }

    if let Some(schema) = source.lookup("org.gnome.desktop.peripherals.keyboard", true) {
        let settings = Settings::new_full(&schema, None::<&SettingsBackend>, None);
        if !settings.boolean("repeat") {
            config.repeat_delay = 0;
            config.repeat_rate = 0;
        } else {
            config.repeat_delay = settings.uint("delay").min(i32::MAX as u32) as i32;
            let interval = settings.uint("repeat-interval");
            config.repeat_rate = 1000u32
                .checked_div(interval)
                .unwrap_or(33)
                .min(i32::MAX as u32) as i32;
        }
    }

    config
}

pub(crate) fn xkb_config(config: &StartupKeyboardConfig) -> XkbConfig<'_> {
    XkbConfig {
        model: &config.model,
        layout: &config.layout,
        variant: &config.variant,
        options: config.options.clone(),
        ..XkbConfig::default()
    }
}

impl PantheonCompositor {
    pub fn process_input_event<I: InputBackend>(&mut self, event: InputEvent<I>) {
        if !matches!(
            event,
            InputEvent::DeviceAdded { .. } | InputEvent::DeviceRemoved { .. }
        ) {
            self.note_user_activity();
        }
        match event {
            InputEvent::Keyboard { event, .. } => {
                let serial = SERIAL_COUNTER.next_serial();
                let time = Event::time(&event);
                let key_state = event.state();
                if key_state == smithay::backend::input::KeyState::Pressed {
                    // Lets xdg-activation hold back a raise while the user is typing.
                    self.last_key_press = Some(std::time::Instant::now());
                }
                let x11_focus = self.x11_keyboard_focus.clone();
                let seat = self.seat.clone();

                self.seat.get_keyboard().unwrap().input::<(), _>(
                    self,
                    event.key_code(),
                    event.state(),
                    serial,
                    time,
                    |state, modifiers, keysym| {
                        if key_state == smithay::backend::input::KeyState::Pressed
                            && !state.session_locked && modifiers.logo && modifiers.shift
                            && !modifiers.ctrl && !modifiers.alt
                            && matches!(keysym.modified_sym().raw(),
                                smithay::input::keyboard::xkb::keysyms::KEY_3 |
                                smithay::input::keyboard::xkb::keysyms::KEY_numbersign)
                        {
                            state.screenshot_requested.set(true);
                            state.request_native_redraw();
                            state.request_winit_redraw();
                            return FilterResult::Intercept(());
                        }
                        if key_state == smithay::backend::input::KeyState::Pressed
                            && state.gesture_animation.is_some()
                        {
                            state.cancel_active_gesture(time);
                            if keysym.modified_sym() == smithay::input::keyboard::xkb::keysyms::KEY_Escape.into() {
                                return FilterResult::Intercept(());
                            }
                        }
                        if key_state == smithay::backend::input::KeyState::Pressed
                            && keysym.modified_sym()
                                == smithay::input::keyboard::xkb::keysyms::KEY_Escape.into()
                            && state.handle_overview_key()
                        {
                            return FilterResult::Intercept(());
                        }
                        if key_state == smithay::backend::input::KeyState::Pressed
                            && state.handle_snap_assist_key(keysym.modified_sym(), modifiers)
                        {
                            return FilterResult::Intercept(());
                        }
                        if key_state == smithay::backend::input::KeyState::Pressed
                            && state.move_grab_active
                            && keysym.modified_sym()
                                == smithay::input::keyboard::xkb::keysyms::KEY_Escape.into()
                        {
                            state.cancel_move_snap();
                            return FilterResult::Intercept(());
                        }
                        if key_state == smithay::backend::input::KeyState::Pressed
                            && !state.session_locked
                            && (state.handle_tiling_shortcut(keysym.modified_sym(), modifiers)
                                || state
                                    .shell_compat
                                    .activate_key(keysym.modified_sym(), modifiers))
                        {
                            FilterResult::Intercept(())
                        } else if let Some(focus) = x11_focus.as_ref() {
                            <smithay::xwayland::X11Surface as KeyboardTarget<PantheonCompositor>>::key(
                                focus, &seat, state, keysym, key_state, serial, time,
                            );
                            <smithay::xwayland::X11Surface as KeyboardTarget<PantheonCompositor>>::modifiers(
                                focus, &seat, state, *modifiers, serial,
                            );
                            FilterResult::Intercept(())
                        } else {
                            FilterResult::Forward
                        }
                    },
                );
                self.refresh_panel_visibility();
            }
            InputEvent::PointerMotion { event, .. } => {
                let pointer = self.seat.get_pointer().unwrap();
                let location = pointer.current_location();
                let Some(output_bounds) = self
                    .space
                    .outputs()
                    .filter_map(|output| self.space.output_geometry(output))
                    .reduce(|bounds, output| bounds.merge(output))
                else {
                    return;
                };
                let max_x = (output_bounds.loc.x + output_bounds.size.w - 1) as f64;
                let max_y = (output_bounds.loc.y + output_bounds.size.h - 1) as f64;
                let target = location + event.delta();
                let new_location = smithay::utils::Point::from((
                    target.x.clamp(output_bounds.loc.x as f64, max_x),
                    target.y.clamp(output_bounds.loc.y as f64, max_y),
                ));
                let serial = SERIAL_COUNTER.next_serial();
                let under = self.surface_under(location);

                pointer.relative_motion(
                    self,
                    under.clone(),
                    &RelativeMotionEvent {
                        delta: event.delta(),
                        delta_unaccel: event.delta_unaccel(),
                        time: event.time(),
                    },
                );
                pointer.motion(
                    self,
                    self.surface_under(new_location),
                    &MotionEvent {
                        location: new_location,
                        serial,
                        time: event.time(),
                    },
                );
                self.snap_assist_hover(new_location);
                self.refresh_panel_visibility();
                pointer.frame(self);
            }
            InputEvent::PointerMotionAbsolute { event, .. } => {
                // Absolute devices report normalized coordinates. Map them over
                // the complete logical desktop so a multi-output layout does
                // not constrain the device to whichever output happens to be
                // first in Space's iterator.
                let Some(desktop_bounds) = self
                    .space
                    .outputs()
                    .filter_map(|output| self.space.output_geometry(output))
                    .reduce(|bounds, output| bounds.merge(output))
                else {
                    return;
                };

                let pos =
                    event.position_transformed(desktop_bounds.size) + desktop_bounds.loc.to_f64();

                let serial = SERIAL_COUNTER.next_serial();

                let pointer = self.seat.get_pointer().unwrap();

                let under = self.surface_under(pos);

                pointer.motion(
                    self,
                    under,
                    &MotionEvent {
                        location: pos,
                        serial,
                        time: event.time(),
                    },
                );
                self.snap_assist_hover(pos);
                self.refresh_panel_visibility();
                pointer.frame(self);
            }
            InputEvent::PointerButton { event, .. } => {
                let pointer = self.seat.get_pointer().unwrap();
                let keyboard = self.seat.get_keyboard().unwrap();

                let serial = SERIAL_COUNTER.next_serial();

                let button = event.button_code();

                let button_state = event.state();
                if button_state == ButtonState::Pressed {
                    self.cancel_active_gesture(event.time());
                }

                if !self.session_locked
                    && ButtonState::Pressed == button_state
                    && self.handle_snap_assist_click(pointer.current_location())
                {
                    pointer.frame(self);
                    return;
                }

                if !self.session_locked
                    && ButtonState::Pressed == button_state
                    && self.handle_overview_click(pointer.current_location())
                {
                    pointer.frame(self);
                    return;
                }

                if !self.session_locked
                    && ButtonState::Pressed == button_state
                    && !pointer.is_grabbed()
                {
                    if let Some(window) = self.window_under(pointer.current_location()) {
                        let panel_surface = window
                            .toplevel()
                            .is_some_and(|top| self.is_panel_surface(top.wl_surface()));
                        if panel_surface {
                            self.raise_window(&window, false);
                        } else {
                            self.raise_window(&window, true);
                            self.focus_window_keyboard(&window, serial);
                        }
                        self.space.elements().for_each(|window| {
                            if let Some(toplevel) = window.toplevel() {
                                toplevel.send_pending_configure();
                            }
                        });
                    } else {
                        self.end_popup_grab_unless(None);
                        self.set_x11_keyboard_focus(None, serial);
                        self.space.elements().for_each(|window| {
                            window.set_activated(false);
                            if let Some(toplevel) = window.toplevel() {
                                toplevel.send_pending_configure();
                            }
                        });
                        keyboard.set_focus(self, None, serial);
                    }
                };

                pointer.button(
                    self,
                    &ButtonEvent {
                        button,
                        state: button_state,
                        serial,
                        time: event.time(),
                    },
                );
                self.refresh_panel_visibility();
                pointer.frame(self);
            }
            InputEvent::PointerAxis { event, .. } => {
                let source = event.source();

                let horizontal_amount = event.amount(Axis::Horizontal).unwrap_or_else(|| {
                    event.amount_v120(Axis::Horizontal).unwrap_or(0.0) * 15.0 / 120.
                });
                let vertical_amount = event.amount(Axis::Vertical).unwrap_or_else(|| {
                    event.amount_v120(Axis::Vertical).unwrap_or(0.0) * 15.0 / 120.
                });
                let horizontal_amount_discrete = event.amount_v120(Axis::Horizontal);
                let vertical_amount_discrete = event.amount_v120(Axis::Vertical);

                let mut frame = AxisFrame::new(event.time()).source(source);
                if horizontal_amount != 0.0 {
                    frame = frame.value(Axis::Horizontal, horizontal_amount);
                    if let Some(discrete) = horizontal_amount_discrete {
                        frame = frame.v120(Axis::Horizontal, discrete as i32);
                    }
                }
                if vertical_amount != 0.0 {
                    frame = frame.value(Axis::Vertical, vertical_amount);
                    if let Some(discrete) = vertical_amount_discrete {
                        frame = frame.v120(Axis::Vertical, discrete as i32);
                    }
                }

                if source == AxisSource::Finger {
                    if event.amount(Axis::Horizontal) == Some(0.0) {
                        frame = frame.stop(Axis::Horizontal);
                    }
                    if event.amount(Axis::Vertical) == Some(0.0) {
                        frame = frame.stop(Axis::Vertical);
                    }
                }

                let pointer = self.seat.get_pointer().unwrap();
                pointer.axis(self, frame);
                pointer.frame(self);
            }
            InputEvent::GestureSwipeBegin { event, .. } => {
                self.gesture_swipe_begin(event.fingers(), event.time());
            }
            InputEvent::GestureSwipeUpdate { event, .. } => {
                self.gesture_swipe_update(event.delta(), event.time());
            }
            InputEvent::GestureSwipeEnd { event, .. } => {
                self.gesture_swipe_end(event.cancelled(), event.time());
            }
            InputEvent::GesturePinchBegin { event, .. } => {
                self.gesture_pinch_begin(event.fingers(), event.time());
            }
            InputEvent::GesturePinchUpdate { event, .. } => {
                self.gesture_pinch_update(
                    event.delta(),
                    event.scale(),
                    event.rotation(),
                    event.time(),
                );
            }
            InputEvent::GesturePinchEnd { event, .. } => {
                self.gesture_pinch_end(event.cancelled(), event.time());
            }
            InputEvent::GestureHoldBegin { event, .. } => {
                // Holds always belong to the client (GTK stops kinetic
                // scrolling with them); libinput cancels a hold before a
                // swipe or pinch begins.
                let pointer = self.seat.get_pointer().unwrap();
                pointer.gesture_hold_begin(
                    self,
                    &GestureHoldBeginEvent {
                        serial: SERIAL_COUNTER.next_serial(),
                        time: event.time(),
                        fingers: event.fingers(),
                    },
                );
            }
            InputEvent::GestureHoldEnd { event, .. } => {
                let pointer = self.seat.get_pointer().unwrap();
                pointer.gesture_hold_end(
                    self,
                    &GestureHoldEndEvent {
                        serial: SERIAL_COUNTER.next_serial(),
                        time: event.time(),
                        cancelled: event.cancelled(),
                    },
                );
            }
            _ => {}
        }
    }
}

impl PantheonCompositor {
    /// The compositor only claims gestures when no grab, lock or overview
    /// state could be confused by them; otherwise they go to the client.
    fn gestures_available(&self) -> bool {
        !self.session_locked
            && !self
                .seat
                .get_pointer()
                .is_some_and(|pointer| pointer.is_grabbed())
    }

    pub(crate) fn gesture_swipe_begin(&mut self, fingers: u32, time: InputTime) {
        self.discard_gesture_animation();
        let owned = self
            .gestures_available()
            .then(|| {
                crate::gestures::SwipeGestureState::begin(
                    &self.gesture_bindings,
                    fingers,
                    self.overview_active(),
                )
            })
            .flatten();
        if let Some(gesture) = owned {
            self.active_gesture = Some(ActiveGesture::Swipe(gesture));
            return;
        }
        self.active_gesture = Some(ActiveGesture::ForwardedSwipe);
        let pointer = self.seat.get_pointer().unwrap();
        pointer.gesture_swipe_begin(
            self,
            &GestureSwipeBeginEvent {
                serial: SERIAL_COUNTER.next_serial(),
                time,
                fingers,
            },
        );
    }

    pub(crate) fn gesture_swipe_update(&mut self, delta: Point<f64, Logical>, time: InputTime) {
        if !self.gestures_available()
            && matches!(self.active_gesture, Some(ActiveGesture::Swipe(_)))
        {
            self.active_gesture = None;
            self.discard_gesture_animation();
        }
        match self.active_gesture.as_mut() {
            Some(ActiveGesture::Swipe(gesture)) => gesture.update(delta),
            Some(ActiveGesture::ForwardedSwipe) => {
                let pointer = self.seat.get_pointer().unwrap();
                pointer.gesture_swipe_update(self, &GestureSwipeUpdateEvent { time, delta });
            }
            _ => {}
        }
        if let Some(ActiveGesture::Swipe(gesture)) = self.active_gesture {
            self.update_gesture_animation(gesture);
        }
    }

    pub(crate) fn gesture_swipe_end(&mut self, cancelled: bool, time: InputTime) {
        match self.active_gesture.take() {
            Some(ActiveGesture::Swipe(gesture)) => {
                let cancelled = cancelled || !self.gestures_available();
                if !self.release_gesture_animation(cancelled) {
                    self.apply_gesture_outcome(gesture.finish(cancelled));
                }
            }
            Some(ActiveGesture::ForwardedSwipe) => {
                let pointer = self.seat.get_pointer().unwrap();
                pointer.gesture_swipe_end(
                    self,
                    &GestureSwipeEndEvent {
                        serial: SERIAL_COUNTER.next_serial(),
                        time,
                        cancelled,
                    },
                );
            }
            other => self.active_gesture = other,
        }
    }

    fn gesture_pinch_begin(&mut self, fingers: u32, time: InputTime) {
        self.discard_gesture_animation();
        let owned = self
            .gestures_available()
            .then(|| crate::gestures::PinchGestureState::begin(&self.gesture_bindings, fingers))
            .flatten();
        if let Some(gesture) = owned {
            self.active_gesture = Some(ActiveGesture::Pinch(gesture));
            return;
        }
        self.active_gesture = Some(ActiveGesture::ForwardedPinch);
        let pointer = self.seat.get_pointer().unwrap();
        pointer.gesture_pinch_begin(
            self,
            &GesturePinchBeginEvent {
                serial: SERIAL_COUNTER.next_serial(),
                time,
                fingers,
            },
        );
    }

    fn gesture_pinch_update(
        &mut self,
        delta: Point<f64, Logical>,
        scale: f64,
        rotation: f64,
        time: InputTime,
    ) {
        if !self.gestures_available()
            && matches!(self.active_gesture, Some(ActiveGesture::Pinch(_)))
        {
            self.active_gesture = None;
            self.discard_gesture_animation();
        }
        match self.active_gesture.as_mut() {
            Some(ActiveGesture::Pinch(gesture)) => gesture.update(scale),
            Some(ActiveGesture::ForwardedPinch) => {
                let pointer = self.seat.get_pointer().unwrap();
                pointer.gesture_pinch_update(
                    self,
                    &GesturePinchUpdateEvent {
                        time,
                        delta,
                        scale,
                        rotation,
                    },
                );
            }
            _ => {}
        }
    }

    fn gesture_pinch_end(&mut self, cancelled: bool, time: InputTime) {
        match self.active_gesture.take() {
            Some(ActiveGesture::Pinch(gesture)) => {
                self.apply_gesture_outcome(gesture.finish(cancelled || !self.gestures_available()));
            }
            Some(ActiveGesture::ForwardedPinch) => {
                let pointer = self.seat.get_pointer().unwrap();
                pointer.gesture_pinch_end(
                    self,
                    &GesturePinchEndEvent {
                        serial: SERIAL_COUNTER.next_serial(),
                        time,
                        cancelled,
                    },
                );
            }
            other => self.active_gesture = other,
        }
    }

    /// End client sequences before focus moves to the lock surface, and discard
    /// compositor sequences so unlocking cannot complete an old gesture.
    pub(crate) fn cancel_active_gesture(&mut self, time: InputTime) {
        self.discard_gesture_animation();
        match self.active_gesture {
            Some(ActiveGesture::Swipe(_) | ActiveGesture::ForwardedSwipe) => {
                self.gesture_swipe_end(true, time);
            }
            Some(ActiveGesture::Pinch(_) | ActiveGesture::ForwardedPinch) => {
                self.gesture_pinch_end(true, time);
            }
            None => {}
        }
    }

    fn apply_gesture_outcome(&mut self, outcome: crate::gestures::GestureOutcome) {
        if let Err(error) = self.apply_swipe_outcome(outcome) {
            tracing::debug!(%error, ?outcome, "touchpad gesture had no effect");
        }
    }
}
