use smithay::{
    desktop::{PopupKind, PopupManager},
    utils::{Logical, Rectangle},
    wayland::{
        input_method::{InputMethodHandler, PopupSurface},
        text_input::TextInputActivation,
    },
};

use crate::PantheonCompositor;

impl TextInputActivation for PantheonCompositor {}

impl InputMethodHandler for PantheonCompositor {
    fn new_popup(&mut self, surface: PopupSurface) {
        if let Err(error) = self.popups.track_popup(PopupKind::from(surface)) {
            tracing::warn!(?error, "could not track IBus input-method popup");
        }
    }

    fn dismiss_popup(&mut self, surface: PopupSurface) {
        if let Some(parent) = surface.get_parent().map(|parent| parent.surface.clone()) {
            let _ = PopupManager::dismiss_popup(&parent, &PopupKind::from(surface));
        }
    }

    fn popup_repositioned(&mut self, _surface: PopupSurface) {
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    fn parent_geometry(
        &self,
        parent: &smithay::reexports::wayland_server::protocol::wl_surface::WlSurface,
    ) -> Rectangle<i32, Logical> {
        self.space
            .elements()
            .find_map(|window| {
                window
                    .toplevel()
                    .is_some_and(|toplevel| toplevel.wl_surface() == parent)
                    .then(|| window.geometry())
            })
            .unwrap_or_default()
    }
}
