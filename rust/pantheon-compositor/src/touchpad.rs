//! libinput device configuration from the GNOME peripheral settings.
//!
//! libinput leaves tap-to-click, natural scrolling and similar options at
//! their (non-macOS) device defaults until the compositor sets them. This
//! module reads the same `org.gnome.desktop.peripherals.*` keys that the
//! Switchboard Mouse & Touchpad plug writes and applies them when a device is
//! added and whenever a key changes.

use gio::{Settings, SettingsBackend, SettingsSchemaSource, prelude::SettingsExt};

const TOUCHPAD_SCHEMA: &str = "org.gnome.desktop.peripherals.touchpad";
const MOUSE_SCHEMA: &str = "org.gnome.desktop.peripherals.mouse";
/// Schemas whose changes re-apply [`PeripheralSettings`] to every device.
pub(crate) const SETTINGS_SCHEMAS: &[&str] = &[TOUCHPAD_SCHEMA, MOUSE_SCHEMA];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum AccelProfile {
    Default,
    Flat,
    Adaptive,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ClickMethod {
    Default,
    None,
    Areas,
    Fingers,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum SendEvents {
    Enabled,
    Disabled,
    DisabledOnExternalMouse,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct TouchpadSettings {
    pub tap_to_click: bool,
    pub tap_and_drag: bool,
    pub tap_and_drag_lock: bool,
    /// `true` maps a three-finger tap to the middle button and two to right.
    pub tap_left_right_middle: Option<bool>,
    pub natural_scroll: bool,
    pub two_finger_scrolling: bool,
    pub edge_scrolling: bool,
    pub disable_while_typing: bool,
    pub middle_click_emulation: bool,
    pub left_handed: Option<bool>,
    pub click_method: ClickMethod,
    pub speed: f64,
    pub accel_profile: AccelProfile,
    pub send_events: SendEvents,
}

impl Default for TouchpadSettings {
    /// The GNOME schema defaults, used when the schema is not installed.
    fn default() -> Self {
        Self {
            tap_to_click: false,
            tap_and_drag: true,
            tap_and_drag_lock: false,
            tap_left_right_middle: None,
            natural_scroll: true,
            two_finger_scrolling: true,
            edge_scrolling: false,
            disable_while_typing: true,
            middle_click_emulation: false,
            left_handed: None,
            click_method: ClickMethod::Default,
            speed: 0.0,
            accel_profile: AccelProfile::Default,
            send_events: SendEvents::Enabled,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct MouseSettings {
    pub natural_scroll: bool,
    pub left_handed: bool,
    pub speed: f64,
    pub accel_profile: AccelProfile,
    pub middle_click_emulation: bool,
}

impl Default for MouseSettings {
    fn default() -> Self {
        Self {
            natural_scroll: false,
            left_handed: false,
            speed: 0.0,
            accel_profile: AccelProfile::Default,
            middle_click_emulation: false,
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub(crate) struct PeripheralSettings {
    pub touchpad: TouchpadSettings,
    pub mouse: MouseSettings,
}

impl PeripheralSettings {
    pub(crate) fn load() -> Self {
        let mut config = Self::default();
        let Some(source) = SettingsSchemaSource::default() else {
            return config;
        };
        if let Some(schema) = source.lookup(MOUSE_SCHEMA, true) {
            let settings = Settings::new_full(&schema, None::<&SettingsBackend>, None);
            let has = |key: &str| schema.has_key(key);
            let mouse = &mut config.mouse;
            if has("natural-scroll") {
                mouse.natural_scroll = settings.boolean("natural-scroll");
            }
            if has("left-handed") {
                mouse.left_handed = settings.boolean("left-handed");
            }
            if has("speed") {
                mouse.speed = settings.double("speed");
            }
            if has("accel-profile") {
                mouse.accel_profile = parse_accel_profile(&settings.string("accel-profile"));
            }
            if has("middle-click-emulation") {
                mouse.middle_click_emulation = settings.boolean("middle-click-emulation");
            }
        }
        if let Some(schema) = source.lookup(TOUCHPAD_SCHEMA, true) {
            let settings = Settings::new_full(&schema, None::<&SettingsBackend>, None);
            let has = |key: &str| schema.has_key(key);
            let touchpad = &mut config.touchpad;
            for (key, slot) in [
                ("tap-to-click", &mut touchpad.tap_to_click),
                ("tap-and-drag", &mut touchpad.tap_and_drag),
                ("tap-and-drag-lock", &mut touchpad.tap_and_drag_lock),
                ("natural-scroll", &mut touchpad.natural_scroll),
                (
                    "two-finger-scrolling-enabled",
                    &mut touchpad.two_finger_scrolling,
                ),
                ("edge-scrolling-enabled", &mut touchpad.edge_scrolling),
                ("disable-while-typing", &mut touchpad.disable_while_typing),
                (
                    "middle-click-emulation",
                    &mut touchpad.middle_click_emulation,
                ),
            ] {
                if has(key) {
                    *slot = settings.boolean(key);
                }
            }
            if has("tap-button-map") {
                touchpad.tap_left_right_middle = match settings.string("tap-button-map").as_str() {
                    "lrm" => Some(true),
                    "lmr" => Some(false),
                    _ => None,
                };
            }
            if has("left-handed") {
                touchpad.left_handed = match settings.string("left-handed").as_str() {
                    "left" => Some(true),
                    "right" => Some(false),
                    // "mouse": follow the mouse setting.
                    _ => Some(config.mouse.left_handed),
                };
            }
            if has("click-method") {
                touchpad.click_method = match settings.string("click-method").as_str() {
                    "none" => ClickMethod::None,
                    "areas" => ClickMethod::Areas,
                    "fingers" => ClickMethod::Fingers,
                    _ => ClickMethod::Default,
                };
            }
            if has("speed") {
                touchpad.speed = settings.double("speed");
            }
            if has("accel-profile") {
                touchpad.accel_profile = parse_accel_profile(&settings.string("accel-profile"));
            }
            if has("send-events") {
                touchpad.send_events = match settings.string("send-events").as_str() {
                    "disabled" => SendEvents::Disabled,
                    "disabled-on-external-mouse" => SendEvents::DisabledOnExternalMouse,
                    _ => SendEvents::Enabled,
                };
            }
        }
        config
    }
}

fn parse_accel_profile(value: &str) -> AccelProfile {
    match value {
        "flat" => AccelProfile::Flat,
        "adaptive" => AccelProfile::Adaptive,
        _ => AccelProfile::Default,
    }
}

#[cfg(feature = "native-drm")]
mod libinput {
    use super::{AccelProfile, ClickMethod, PeripheralSettings, SendEvents};
    use smithay::reexports::input::{self, Device, DeviceCapability};

    /// A device with tap support is a touchpad; libinput has no other flag.
    fn is_touchpad(device: &Device) -> bool {
        device.config_tap_finger_count() > 0
    }

    fn accel_profile(device: &mut Device, profile: AccelProfile) {
        let profile = match profile {
            AccelProfile::Flat => input::AccelProfile::Flat,
            AccelProfile::Adaptive => input::AccelProfile::Adaptive,
            AccelProfile::Default => match device.config_accel_default_profile() {
                Some(profile) => profile,
                None => return,
            },
        };
        if device.config_accel_profiles().contains(&profile) {
            let _ = device.config_accel_set_profile(profile);
        }
    }

    /// Apply the settings that this device supports. libinput rejects
    /// unsupported options with an error, which is ignored deliberately.
    pub(crate) fn apply(settings: &PeripheralSettings, device: &mut Device) {
        if !device.has_capability(DeviceCapability::Pointer) {
            return;
        }
        if device.config_accel_is_available() {
            let speed = if is_touchpad(device) {
                settings.touchpad.speed
            } else {
                settings.mouse.speed
            };
            let _ = device.config_accel_set_speed(speed.clamp(-1.0, 1.0));
        }
        if !is_touchpad(device) {
            let mouse = &settings.mouse;
            if device.config_scroll_has_natural_scroll() {
                let _ = device.config_scroll_set_natural_scroll_enabled(mouse.natural_scroll);
            }
            if device.config_left_handed_is_available() {
                let _ = device.config_left_handed_set(mouse.left_handed);
            }
            if device.config_middle_emulation_is_available() {
                let _ = device.config_middle_emulation_set_enabled(mouse.middle_click_emulation);
            }
            accel_profile(device, mouse.accel_profile);
            return;
        }

        let touchpad = &settings.touchpad;
        let _ = device.config_tap_set_enabled(touchpad.tap_to_click);
        let _ = device.config_tap_set_drag_enabled(touchpad.tap_and_drag);
        // GNOME's boolean predates sticky drag lock and means the timeout mode.
        let _ = device.config_tap_set_drag_lock_enabled(if touchpad.tap_and_drag_lock {
            input::DragLockState::EnabledTimeout
        } else {
            input::DragLockState::Disabled
        });
        let button_map = match touchpad.tap_left_right_middle {
            Some(true) => Some(input::TapButtonMap::LeftRightMiddle),
            Some(false) => Some(input::TapButtonMap::LeftMiddleRight),
            None => device.config_tap_default_button_map(),
        };
        if let Some(map) = button_map {
            let _ = device.config_tap_set_button_map(map);
        }
        if device.config_scroll_has_natural_scroll() {
            let _ = device.config_scroll_set_natural_scroll_enabled(touchpad.natural_scroll);
        }
        let methods = device.config_scroll_methods();
        let scroll =
            if touchpad.two_finger_scrolling && methods.contains(&input::ScrollMethod::TwoFinger) {
                input::ScrollMethod::TwoFinger
            } else if touchpad.edge_scrolling && methods.contains(&input::ScrollMethod::Edge) {
                input::ScrollMethod::Edge
            } else {
                input::ScrollMethod::NoScroll
            };
        let _ = device.config_scroll_set_method(scroll);
        if device.config_dwt_is_available() {
            let _ = device.config_dwt_set_enabled(touchpad.disable_while_typing);
        }
        if device.config_middle_emulation_is_available() {
            let _ = device.config_middle_emulation_set_enabled(touchpad.middle_click_emulation);
        }
        if let Some(left_handed) = touchpad.left_handed
            && device.config_left_handed_is_available()
        {
            let _ = device.config_left_handed_set(left_handed);
        }
        let click = match touchpad.click_method {
            ClickMethod::Fingers => Some(input::ClickMethod::Clickfinger),
            ClickMethod::Areas => Some(input::ClickMethod::ButtonAreas),
            ClickMethod::Default => device.config_click_default_method(),
            ClickMethod::None => {
                // input 0.10's safe enum omits LIBINPUT_CONFIG_CLICK_METHOD_NONE.
                // SAFETY: this Device owns a live libinput reference and NONE is
                // the documented value for disabling software button methods.
                use input::AsRaw;
                unsafe {
                    input::ffi::libinput_device_config_click_set_method(
                        device.as_raw_mut(),
                        input::ffi::libinput_config_click_method_LIBINPUT_CONFIG_CLICK_METHOD_NONE,
                    );
                }
                None
            }
        };
        if let Some(click) = click
            && device.config_click_methods().contains(&click)
        {
            let _ = device.config_click_set_method(click);
        }
        accel_profile(device, touchpad.accel_profile);
        let mode = match touchpad.send_events {
            SendEvents::Enabled => input::SendEventsMode::ENABLED,
            SendEvents::Disabled => input::SendEventsMode::DISABLED,
            SendEvents::DisabledOnExternalMouse => {
                input::SendEventsMode::DISABLED_ON_EXTERNAL_MOUSE
            }
        };
        if device.config_send_events_modes().contains(mode) {
            let _ = device.config_send_events_set_mode(mode);
        }
    }
}

#[cfg(feature = "native-drm")]
pub(crate) use libinput::apply;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accel_profiles_parse_like_the_schema_nicks() {
        assert_eq!(parse_accel_profile("flat"), AccelProfile::Flat);
        assert_eq!(parse_accel_profile("adaptive"), AccelProfile::Adaptive);
        assert_eq!(parse_accel_profile("default"), AccelProfile::Default);
    }

    #[test]
    fn defaults_match_the_gnome_schema() {
        let settings = PeripheralSettings::default();
        assert!(!settings.touchpad.tap_to_click);
        assert!(settings.touchpad.natural_scroll);
        assert!(settings.touchpad.two_finger_scrolling);
        assert!(!settings.mouse.natural_scroll);
    }
}
