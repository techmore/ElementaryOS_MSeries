//! Small helper windows that float above apps without ever taking the keyboard.
//!
//! The screenshot shelf and the dictation microphone indicator must not steal focus:
//! dictation types into the app the user was in, and a click-through-free shelf would
//! interrupt typing. They are recognised by application ID.

pub const SCREENSHOT_SHELF: &str = "org.techmore.mseries.ScreenshotShelf";
pub const DICTATION_INDICATOR: &str = "org.techmore.mseries.DictationIndicator";

/// Never activated or given keyboard focus, on map or on click.
pub fn is_no_focus_overlay(app_id: Option<&str>) -> bool {
    matches!(app_id, Some(SCREENSHOT_SHELF) | Some(DICTATION_INDICATOR))
}

/// Gap between the dictation indicator and the bottom of the work area (the dock).
pub const DICTATION_INDICATOR_BOTTOM_GAP: i32 = 72;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn overlays_are_recognised() {
        assert!(is_no_focus_overlay(Some(SCREENSHOT_SHELF)));
        assert!(is_no_focus_overlay(Some(DICTATION_INDICATOR)));
        assert!(!is_no_focus_overlay(Some("io.elementary.terminal")));
        assert!(!is_no_focus_overlay(None));
    }
}
