//! Mac-style clipboard keys in terminal emulators.
//!
//! Command is Ctrl here (`ctrl:swap_lwin_lctl`), so Cmd+C reaches a terminal as
//! Ctrl+C, which is SIGINT, not copy. For terminal windows the compositor holds
//! a synthetic Shift around the key so Cmd+C/V/A arrive as Ctrl+Shift+C/V/A
//! (the terminals' own copy/paste/select-all). A real Ctrl key is Super after
//! the swap, so Ctrl+C still interrupts.

/// evdev codes, as sent by libinput (xkb keycodes are these + 8).
pub const KEY_LEFTSHIFT: u32 = 42;
const KEY_A: u32 = 30;
const KEY_C: u32 = 46;
const KEY_V: u32 = 47;

const TERMINAL_APP_IDS: &[&str] = &[
    "io.elementary.terminal",
    "org.gnome.Terminal",
    "org.gnome.Console",
    "org.kde.konsole",
    "konsole",
    "kitty",
    "Alacritty",
    "foot",
    "xterm",
    "org.wezfurlong.wezterm",
    "com.mitchellh.ghostty",
];

pub fn is_terminal_app_id(app_id: &str) -> bool {
    TERMINAL_APP_IDS
        .iter()
        .any(|id| id.eq_ignore_ascii_case(app_id))
}

/// Whether this key press, with these modifiers, should get a synthetic Shift.
/// `ctrl` is the Command key; `logo` is the physical Ctrl key.
pub fn needs_shift(ctrl: bool, logo: bool, shift: bool, alt: bool, evdev_key: u32) -> bool {
    ctrl && !logo && !shift && !alt && matches!(evdev_key, KEY_A | KEY_C | KEY_V)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn command_c_v_a_get_shift() {
        for key in [KEY_A, KEY_C, KEY_V] {
            assert!(needs_shift(true, false, false, false, key));
        }
    }

    #[test]
    fn real_ctrl_and_other_combos_are_untouched() {
        // Physical Ctrl is Super after the swap: Ctrl+C stays an interrupt.
        assert!(!needs_shift(false, true, false, false, KEY_C));
        assert!(!needs_shift(false, false, false, false, KEY_C));
        assert!(!needs_shift(true, false, true, false, KEY_C));
        assert!(!needs_shift(true, false, false, true, KEY_C));
        assert!(!needs_shift(true, false, false, false, 45)); // X
    }

    #[test]
    fn terminal_app_ids() {
        assert!(is_terminal_app_id("io.elementary.terminal"));
        assert!(is_terminal_app_id("Alacritty"));
        assert!(!is_terminal_app_id("org.mozilla.firefox"));
    }
}
