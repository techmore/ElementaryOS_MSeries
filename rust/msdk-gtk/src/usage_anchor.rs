//! Candidate reusable GTK status anchor. Host placement and profile-specific
//! installation are deliberately external to this widget.
use crate::usage_control::UsageControl;
use gtk::prelude::*;
use msdk::usage::{Snapshot, SnapshotError};
use std::cell::{Cell, RefCell};
use std::path::PathBuf;
use std::rc::{Rc, Weak};
use std::time::Duration;

struct Inner {
    button: gtk::Button,
    popup: gtk::Popover,
    control: UsageControl,
    pinned: Cell<bool>,
    open_timer: RefCell<Option<gtk::glib::SourceId>>,
    close_timer: RefCell<Option<gtk::glib::SourceId>>,
}
impl Inner {
    fn cancel(timer: &RefCell<Option<gtk::glib::SourceId>>) {
        if let Some(source) = timer.borrow_mut().take() {
            source.remove();
        }
    }
    fn show(&self, interactive: bool) {
        Self::cancel(&self.close_timer);
        if self.popup.is_visible() {
            if interactive {
                self.pinned.set(true);
                self.popup.set_autohide(true);
            }
            return;
        }
        self.pinned.set(interactive);
        self.popup.set_autohide(interactive);
        let _ = self.control.open();
        self.popup.popup();
    }
    fn schedule_open(this: &Rc<Self>) {
        Self::cancel(&this.close_timer);
        if this.open_timer.borrow().is_some() || this.popup.is_visible() {
            return;
        }
        let weak = Rc::downgrade(this);
        let source = gtk::glib::timeout_add_local_once(Duration::from_millis(250), move || {
            if let Some(inner) = weak.upgrade() {
                inner.open_timer.borrow_mut().take();
                inner.show(false);
            }
        });
        *this.open_timer.borrow_mut() = Some(source);
    }
    fn schedule_close(this: &Rc<Self>) {
        Self::cancel(&this.open_timer);
        Self::cancel(&this.close_timer);
        if this.pinned.get() {
            return;
        }
        let weak = Rc::downgrade(this);
        let source = gtk::glib::timeout_add_local_once(Duration::from_millis(450), move || {
            if let Some(inner) = weak.upgrade() {
                inner.close_timer.borrow_mut().take();
                inner.popup.popdown();
            }
        });
        *this.close_timer.borrow_mut() = Some(source);
    }
    fn closed(&self) {
        self.pinned.set(false);
        Self::cancel(&self.open_timer);
        Self::cancel(&self.close_timer);
        self.control.close();
    }
}
impl Drop for Inner {
    fn drop(&mut self) {
        Self::cancel(&self.open_timer);
        Self::cancel(&self.close_timer);
        self.control.close();
        if self.popup.parent().is_some() {
            self.popup.unparent();
        }
    }
}

/// Host-owned status anchor. The profile must place `button()` in its actual
/// status area and call neither open nor refresh while it is closed. Dropping
/// this object releases timers, popup and owned read; no background polling.
pub struct UsageAnchor {
    inner: Rc<Inner>,
}
impl UsageAnchor {
    pub fn new(
        initial: &Snapshot,
        now: i64,
        executable: PathBuf,
        max_age_seconds: u64,
        position: gtk::PositionType,
    ) -> Result<Self, SnapshotError> {
        let control = UsageControl::new(initial, now, executable, max_age_seconds)?;
        let button = gtk::Button::with_label("Usage");
        button.add_css_class("flat");
        button.set_tooltip_text(Some("Usage status"));
        let popup = gtk::Popover::builder()
            .position(position)
            .autohide(false)
            .has_arrow(false)
            .child(control.widget())
            .build();
        popup.set_parent(&button);
        let inner = Rc::new(Inner {
            button,
            popup,
            control,
            pinned: Cell::new(false),
            open_timer: RefCell::new(None),
            close_timer: RefCell::new(None),
        });
        let weak = Rc::downgrade(&inner);
        inner.button.connect_clicked(move |_| {
            if let Some(inner) = weak.upgrade() {
                Inner::cancel(&inner.open_timer);
                if inner.popup.is_visible() && inner.pinned.get() {
                    inner.popup.popdown();
                } else {
                    inner.show(true);
                }
            }
        });
        let motion = gtk::EventControllerMotion::new();
        let weak = Rc::downgrade(&inner);
        motion.connect_enter(move |_, _, _| {
            if let Some(inner) = weak.upgrade() {
                Inner::schedule_open(&inner);
            }
        });
        let weak = Rc::downgrade(&inner);
        motion.connect_leave(move |_| {
            if let Some(inner) = weak.upgrade() {
                Inner::schedule_close(&inner);
            }
        });
        inner.button.add_controller(motion);
        let motion = gtk::EventControllerMotion::new();
        let weak = Rc::downgrade(&inner);
        motion.connect_enter(move |_, _, _| {
            if let Some(inner) = weak.upgrade() {
                Inner::cancel(&inner.close_timer);
            }
        });
        let weak = Rc::downgrade(&inner);
        motion.connect_leave(move |_| {
            if let Some(inner) = weak.upgrade() {
                Inner::schedule_close(&inner);
            }
        });
        inner.popup.add_controller(motion);
        let weak = Rc::downgrade(&inner);
        inner.popup.connect_closed(move |_| {
            if let Some(inner) = weak.upgrade() {
                inner.closed();
            }
        });
        let keys = gtk::EventControllerKey::new();
        let weak: Weak<Inner> = Rc::downgrade(&inner);
        keys.connect_key_pressed(move |_, key, _, _| {
            if key == gtk::gdk::Key::Escape {
                if let Some(inner) = weak.upgrade() {
                    inner.popup.popdown();
                    inner.button.grab_focus();
                }
                gtk::glib::Propagation::Stop
            } else {
                gtk::glib::Propagation::Proceed
            }
        });
        inner.popup.add_controller(keys);
        let weak = Rc::downgrade(&inner);
        inner.button.connect_unmap(move |_| {
            if let Some(inner) = weak.upgrade() {
                Inner::cancel(&inner.open_timer);
                Inner::cancel(&inner.close_timer);
                inner.popup.popdown();
                inner.closed();
            }
        });
        Ok(Self { inner })
    }
    pub fn button(&self) -> &gtk::Button {
        &self.inner.button
    }
}
