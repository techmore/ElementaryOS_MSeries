use gio::{
    Settings, SettingsBackend, SettingsSchemaSource,
    prelude::{SettingsExt, SettingsExtManual},
};
use smithay::{
    backend::input::{
        AbsolutePositionEvent, Axis, AxisSource, ButtonState, Event, InputBackend, InputEvent,
        KeyboardKeyEvent, PointerAxisEvent, PointerButtonEvent, PointerMotionEvent,
    },
    input::{
        keyboard::{FilterResult, KeyboardTarget, XkbConfig},
        pointer::{AxisFrame, ButtonEvent, MotionEvent, RelativeMotionEvent},
    },
    utils::SERIAL_COUNTER,
};

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
            config.repeat_rate = if interval == 0 {
                33
            } else {
                (1000 / interval).min(i32::MAX as u32) as i32
            };
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
        match event {
            InputEvent::Keyboard { event, .. } => {
                let serial = SERIAL_COUNTER.next_serial();
                let time = Event::time(&event);
                let key_state = event.state();
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
                self.refresh_panel_visibility();
                pointer.frame(self);
            }
            InputEvent::PointerButton { event, .. } => {
                let pointer = self.seat.get_pointer().unwrap();
                let keyboard = self.seat.get_keyboard().unwrap();

                let serial = SERIAL_COUNTER.next_serial();

                let button = event.button_code();

                let button_state = event.state();

                if !self.session_locked
                    && ButtonState::Pressed == button_state
                    && !pointer.is_grabbed()
                {
                    if let Some((window, _loc)) = self
                        .space
                        .element_under(pointer.current_location())
                        .map(|(w, l)| (w.clone(), l))
                    {
                        let panel_surface = window
                            .toplevel()
                            .is_some_and(|top| self.is_panel_surface(top.wl_surface()));
                        if panel_surface {
                            self.space.raise_element(&window, false);
                        } else {
                            self.space.raise_element(&window, true);
                            self.focus_window_keyboard(&window, serial);
                        }
                        self.space.elements().for_each(|window| {
                            if let Some(toplevel) = window.toplevel() {
                                toplevel.send_pending_configure();
                            }
                        });
                    } else {
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
            _ => {}
        }
    }
}
