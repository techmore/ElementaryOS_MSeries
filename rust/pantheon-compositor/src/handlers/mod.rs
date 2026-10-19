mod compositor;
mod xdg_shell;

use crate::PantheonCompositor;

//
// Wl Seat
//

use smithay::input::dnd::{DnDGrab, DndGrabHandler, GrabType, Source};
use smithay::input::pointer::Focus;
use smithay::input::{Seat, SeatHandler, SeatState};
use smithay::reexports::wayland_server::Resource;
use smithay::reexports::wayland_server::protocol::{wl_output::WlOutput, wl_surface::WlSurface};
use smithay::utils::{IsAlive, Serial};
use smithay::wayland::output::OutputHandler;
use smithay::wayland::pointer_constraints::PointerConstraintsHandler;
use smithay::wayland::selection::data_device::{
    DataDeviceHandler, DataDeviceState, WaylandDndGrabHandler, set_data_device_focus,
};
use smithay::wayland::selection::primary_selection::{
    PrimarySelectionHandler, PrimarySelectionState, set_primary_focus,
};
use smithay::wayland::selection::{SelectionHandler, SelectionSource, SelectionTarget};
use smithay::wayland::session_lock::{
    LockSurface, SessionLockHandler, SessionLockManagerState, SessionLocker,
};

impl SeatHandler for PantheonCompositor {
    type KeyboardFocus = WlSurface;
    type PointerFocus = WlSurface;
    type TouchFocus = WlSurface;

    fn seat_state(&mut self) -> &mut SeatState<PantheonCompositor> {
        &mut self.seat_state
    }

    fn cursor_image(
        &mut self,
        _seat: &Seat<Self>,
        image: smithay::input::pointer::CursorImageStatus,
    ) {
        self.cursor_status = image;
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    fn focus_changed(&mut self, seat: &Seat<Self>, focused: Option<&WlSurface>) {
        let dh = &self.display_handle;
        let client = focused.and_then(|s| dh.get_client(s.id()).ok());
        set_data_device_focus(dh, seat, client.clone());
        set_primary_focus(dh, seat, client);
    }
}

impl PointerConstraintsHandler for PantheonCompositor {}

//
// Wl Data Device
//

impl SelectionHandler for PantheonCompositor {
    type SelectionUserData = ();

    fn new_selection(
        &mut self,
        selection: SelectionTarget,
        source: Option<SelectionSource>,
        _seat: Seat<Self>,
    ) {
        if let Some(xwm) = self.xwm.as_mut()
            && let Err(error) =
                xwm.new_selection(selection, source.map(|source| source.mime_types()))
        {
            tracing::warn!(
                ?selection,
                ?error,
                "failed to forward Wayland selection to XWayland"
            );
        }
    }

    fn send_selection(
        &mut self,
        selection: SelectionTarget,
        mime_type: String,
        fd: std::os::fd::OwnedFd,
        _seat: Seat<Self>,
        _user_data: &Self::SelectionUserData,
    ) {
        if let Some(xwm) = self.xwm.as_mut()
            && let Err(error) = xwm.send_selection(selection, mime_type, fd)
        {
            tracing::warn!(?selection, ?error, "failed to send selection to XWayland");
        }
    }
}

impl DataDeviceHandler for PantheonCompositor {
    fn data_device_state(&mut self) -> &mut DataDeviceState {
        &mut self.data_device_state
    }
}

impl PrimarySelectionHandler for PantheonCompositor {
    fn primary_selection_state(&mut self) -> &mut PrimarySelectionState {
        &mut self.primary_selection_state
    }
}

impl DndGrabHandler for PantheonCompositor {}
impl WaylandDndGrabHandler for PantheonCompositor {
    fn dnd_requested<S: Source>(
        &mut self,
        source: S,
        _icon: Option<WlSurface>,
        seat: Seat<Self>,
        serial: Serial,
        type_: GrabType,
    ) {
        match type_ {
            GrabType::Pointer => {
                let ptr = seat.get_pointer().unwrap();
                let start_data = ptr.grab_start_data().unwrap();

                // create a dnd grab to start the operation
                let grab = DnDGrab::new_pointer(&self.display_handle, start_data, source, seat);
                ptr.set_grab(self, grab, serial, Focus::Keep);
            }
            GrabType::Touch => {
                // pantheon-compositor lacks touch handling
                source.cancel();
            }
        }
    }
}

//
// Wl Output & Xdg Output
//

impl OutputHandler for PantheonCompositor {}

impl SessionLockHandler for PantheonCompositor {
    fn lock_state(&mut self) -> &mut SessionLockManagerState {
        &mut self.session_lock_state
    }

    fn lock(&mut self, confirmation: SessionLocker) {
        if self.session_locked || self.lock_confirmation.is_some() {
            return;
        }

        let serial = smithay::utils::SERIAL_COUNTER.next_serial();
        self.seat.get_pointer().unwrap().unset_grab(
            self,
            serial,
            smithay::backend::input::InputTime::now(),
        );
        let keyboard = self.seat.get_keyboard().unwrap();
        keyboard.unset_grab(self);
        self.keyboard_focus_before_lock = keyboard.current_focus();
        self.x11_keyboard_focus_before_lock = self.x11_keyboard_focus.clone();
        self.set_x11_keyboard_focus(None, serial);
        keyboard.set_focus(self, None, serial);

        self.session_locked = true;
        self.lock_owner = Some(confirmation.ext_session_lock().id());
        self.lock_surfaces.clear();
        let pointer = self.seat.get_pointer().unwrap();
        let location = pointer.current_location();
        pointer.motion(
            self,
            None,
            &smithay::input::pointer::MotionEvent {
                location,
                serial: smithay::utils::SERIAL_COUNTER.next_serial(),
                time: smithay::backend::input::InputTime::now(),
            },
        );
        pointer.frame(self);
        self.lock_confirmation_outputs = self
            .space
            .outputs()
            .map(|output| output.name().to_string())
            .collect();
        self.lock_confirmation = Some(confirmation);
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    fn unlock(&mut self) {
        self.shell_compat.set_locked(false);
        self.session_locked = false;
        self.lock_owner = None;
        self.lock_confirmation = None;
        self.lock_confirmation_outputs.clear();
        self.lock_surfaces.clear();

        let focus = self
            .keyboard_focus_before_lock
            .take()
            .filter(|surface| surface.alive());
        let serial = smithay::utils::SERIAL_COUNTER.next_serial();
        if let Some(x11_focus) = self
            .x11_keyboard_focus_before_lock
            .take()
            .filter(IsAlive::alive)
        {
            self.set_x11_keyboard_focus(Some(x11_focus), serial);
        } else {
            self.seat
                .get_keyboard()
                .unwrap()
                .set_focus(self, focus, serial);
        }

        let pointer = self.seat.get_pointer().unwrap();
        let location = pointer.current_location();
        pointer.motion(
            self,
            self.surface_under(location),
            &smithay::input::pointer::MotionEvent {
                location,
                serial: smithay::utils::SERIAL_COUNTER.next_serial(),
                time: smithay::backend::input::InputTime::now(),
            },
        );
        pointer.frame(self);
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }

    fn new_surface(&mut self, surface: LockSurface, output: WlOutput) {
        let owner = surface.ext_session_lock().id();
        if !self.session_locked || self.lock_owner.as_ref() != Some(&owner) {
            return;
        }
        let Some(output) = smithay::output::Output::from_resource(&output) else {
            return;
        };
        let Some(geometry) = self.space.output_geometry(&output) else {
            return;
        };
        surface.with_pending_state(|pending| {
            pending.size =
                Some((geometry.size.w.max(0) as u32, geometry.size.h.max(0) as u32).into())
        });

        let output_name = output.name().to_string();
        self.lock_surfaces.insert(output_name, surface.clone());
        self.set_x11_keyboard_focus(None, smithay::utils::SERIAL_COUNTER.next_serial());
        self.seat.get_keyboard().unwrap().set_focus(
            self,
            Some(surface.wl_surface().clone()),
            smithay::utils::SERIAL_COUNTER.next_serial(),
        );
        #[cfg(feature = "native-drm")]
        self.request_native_redraw();
    }
}

smithay::delegate_dispatch2!(PantheonCompositor);
