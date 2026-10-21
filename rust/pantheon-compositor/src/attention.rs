//! Windows that asked for the user's attention and did not get focus.
//!
//! A window lands here when the compositor declines to raise it: an
//! xdg-activation request the policy ignored, a deferred activation that gave
//! up because the user never paused typing, an X11 `_NET_WM_STATE_DEMANDS_ATTENTION`
//! request, or `WM_HINTS` urgency. The flag is cleared as soon as the window
//! gets keyboard focus (or goes away) and is published as `demands-attention`
//! in the Gala `GetWindows` reply, so the dock or taskbar can mark the app.

use std::collections::HashSet;

use smithay::{
    desktop::{Window, find_popup_root_surface},
    reexports::wayland_server::protocol::wl_surface::WlSurface,
};

use crate::PantheonCompositor;

/// The Gala window uid (`Window::id()`).
pub type WindowKey = usize;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Reason {
    /// xdg-activation request that the activation policy ignored.
    ActivationIgnored,
    /// Deferred activation whose user never stopped typing.
    ActivationGaveUp,
    /// X11 `_NET_WM_STATE_DEMANDS_ATTENTION`.
    X11Request,
    /// X11 `WM_HINTS` urgency hint.
    X11Urgency,
}

#[derive(Debug, Default)]
pub struct Attention {
    windows: HashSet<WindowKey>,
}

impl Attention {
    /// Mark `key`. A window that already has focus never needs attention.
    /// Returns whether the set changed.
    pub fn request(&mut self, key: WindowKey, focused: bool) -> bool {
        !focused && self.windows.insert(key)
    }

    /// Returns whether the set changed.
    pub fn clear(&mut self, key: WindowKey) -> bool {
        self.windows.remove(&key)
    }

    pub fn contains(&self, key: WindowKey) -> bool {
        self.windows.contains(&key)
    }
}

impl PantheonCompositor {
    pub(crate) fn request_attention(&mut self, window: &Window, reason: Reason) {
        let focused = self.focused_window().as_ref() == Some(window);
        if !self.attention.request(window.id(), focused) {
            return;
        }
        tracing::info!(uid = window.id(), ?reason, "window demands attention");
        // Urgency stays a WM_HINTS flag; everything else is mirrored into
        // _NET_WM_STATE so X11 clients see the state they asked for.
        if reason != Reason::X11Urgency
            && let Some(surface) = window.x11_surface()
            && !surface.demands_attention()
            && let Err(error) = surface.set_demands_attention(true)
        {
            tracing::debug!(?error, "could not set X11 demands-attention state");
        }
    }

    pub(crate) fn clear_attention(&mut self, window: &Window) {
        if !self.attention.clear(window.id()) {
            return;
        }
        if let Some(surface) = window.x11_surface()
            && surface.demands_attention()
            && let Err(error) = surface.set_demands_attention(false)
        {
            tracing::debug!(?error, "could not clear X11 demands-attention state");
        }
    }

    /// Keyboard focus moved to `surface` (a toplevel, subsurface or popup):
    /// its window has the user's attention now.
    pub(crate) fn clear_attention_for_focus(&mut self, surface: &WlSurface) {
        let root = self
            .popups
            .find_popup(surface)
            .and_then(|popup| find_popup_root_surface(&popup).ok())
            .unwrap_or_else(|| {
                let mut root = surface.clone();
                while let Some(parent) = smithay::wayland::compositor::get_parent(&root) {
                    root = parent;
                }
                root
            });
        if let Some(window) = self.find_window_for_surface(&root) {
            self.clear_attention(&window);
        }
    }

    /// The managed window whose toplevel is `root`, mapped or not, once it has
    /// been shown at least once. A toolkit's `present()` on a window that has
    /// not mapped yet is not a request for attention: mapping focuses it.
    pub(crate) fn workspace_window_for_root(&self, root: &WlSurface) -> Option<Window> {
        use smithay::reexports::wayland_server::Resource;
        if !self.initially_positioned.contains(&root.id()) {
            return None;
        }
        self.find_window_for_surface(root).or_else(|| {
            self.workspace_manager
                .windows()
                .into_iter()
                .find(|(window, _, _)| {
                    window
                        .toplevel()
                        .is_some_and(|toplevel| toplevel.wl_surface() == root)
                })
                .map(|(window, _, _)| window)
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_request_marks_an_unfocused_window_once() {
        let mut attention = Attention::default();
        assert!(attention.request(7, false));
        assert!(!attention.request(7, false), "already marked");
        assert!(attention.contains(7));
    }

    #[test]
    fn a_focused_window_is_never_marked() {
        let mut attention = Attention::default();
        assert!(!attention.request(3, true));
        assert!(!attention.contains(3));
    }

    #[test]
    fn focus_clears_the_mark() {
        let mut attention = Attention::default();
        attention.request(1, false);
        assert!(attention.clear(1));
        assert!(!attention.contains(1));
        assert!(!attention.clear(1), "clearing twice changes nothing");
    }
}
