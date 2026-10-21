//! Optional early modeset of a newly connected output on a helper thread.
//!
//! The Apple DCP firmware needs ~240 ms to bring up an external display, and
//! Smithay performs that modeset as a blocking ioctl inside `initialize_output`
//! on the compositor thread (the renderer and output manager are not `Send`),
//! which stalls every output, the internal panel included. The kernel skips a
//! modeset whose CRTC, connector and mode already match (DCP logs `Already set`
//! and returns in ~5 ms), so this module performs the expensive modeset first
//! on a helper thread with a black dumb buffer, through a duplicate of the DRM
//! master fd. The compositor then only maps outputs whose modeset already
//! finished; its own commit replaces the framebuffer without a modeset.
//!
//! Off unless `PANTHEON_PREWARM_MODESET=1`. Any failure leaves the connector
//! to the normal inline path. The state machine is separated from the ioctls
//! so it can be unit tested without a display.

use std::collections::HashMap;
use std::hash::Hash;
use std::time::{Duration, Instant};

use smithay::reexports::drm::{
    buffer::DrmFourcc,
    control::{
        AtomicCommitFlags, Device, Mode, ResourceHandles, atomic::AtomicModeReq, crtc,
        dumbbuffer::DumbBuffer, framebuffer, plane, property,
    },
};

use crate::kms_props::named_property;

/// A prewarm that has not reported back after this long stops blocking the
/// connector; it is mapped inline like the unflagged path.
pub const STUCK_AFTER: Duration = Duration::from_secs(3);

/// `plane` property `type` value of a primary plane.
const PLANE_TYPE_PRIMARY: u64 = 1;

pub fn enabled() -> bool {
    std::env::var_os("PANTHEON_PREWARM_MODESET").is_some_and(|value| value == "1")
}

/// What the helper thread should program.
#[derive(Clone, Copy, Debug)]
pub struct Plan {
    pub crtc: crtc::Handle,
    pub plane: plane::Handle,
    pub mode: Mode,
    pub format: DrmFourcc,
}

/// Kernel objects left behind by a finished prewarm; released by the owner
/// once the compositor's own commit has replaced the framebuffer.
#[derive(Debug)]
pub struct Warmed {
    framebuffer: framebuffer::Handle,
    buffer: DumbBuffer,
}

/// Per-connector state. `R` is the resource kept for a finished prewarm.
#[derive(Debug)]
pub enum Slot<R> {
    InFlight { since: Instant },
    Warmed(R),
    Failed,
}

/// What the reconcile should do for one unmapped connector.
#[derive(Debug, PartialEq, Eq)]
pub enum Gate {
    /// Nothing recorded: plan a prewarm (or map inline if none is possible).
    Plan,
    /// A prewarm is running; skip the connector, its completion reconciles.
    Wait,
    /// A prewarm finished; map now.
    Ready,
    /// Prewarm failed or timed out; map inline.
    Inline,
}

#[derive(Debug)]
pub struct Slots<K, R> {
    slots: HashMap<K, Slot<R>>,
}

impl<K: Hash + Eq + Copy, R> Default for Slots<K, R> {
    fn default() -> Self {
        Self {
            slots: HashMap::new(),
        }
    }
}

impl<K: Hash + Eq + Copy, R> Slots<K, R> {
    pub fn gate(&mut self, key: K, now: Instant) -> Gate {
        match self.slots.get(&key) {
            None => Gate::Plan,
            Some(Slot::InFlight { since }) if now.duration_since(*since) < STUCK_AFTER => {
                Gate::Wait
            }
            Some(Slot::InFlight { .. }) => {
                self.slots.insert(key, Slot::Failed);
                Gate::Inline
            }
            Some(Slot::Warmed(_)) => Gate::Ready,
            Some(Slot::Failed) => Gate::Inline,
        }
    }

    pub fn started(&mut self, key: K, now: Instant) {
        self.slots.insert(key, Slot::InFlight { since: now });
    }

    /// Record a helper thread's result. Returns the resource of a result that
    /// arrives for a connector that has since been forgotten, so the caller
    /// can release it.
    pub fn finished(&mut self, key: K, result: Result<R, ()>) -> Option<R> {
        match (self.slots.get(&key), result) {
            (Some(Slot::InFlight { .. }) | Some(Slot::Failed), Ok(resource)) => {
                self.slots.insert(key, Slot::Warmed(resource));
                None
            }
            (Some(Slot::InFlight { .. }), Err(())) => {
                self.slots.insert(key, Slot::Failed);
                None
            }
            (_, Ok(resource)) => Some(resource),
            (_, Err(())) => None,
        }
    }

    /// Take the finished resource once the connector has been mapped.
    pub fn take_warmed(&mut self, key: K) -> Option<R> {
        match self.slots.remove(&key) {
            Some(Slot::Warmed(resource)) => Some(resource),
            other => {
                if let Some(slot) = other {
                    self.slots.insert(key, slot);
                }
                None
            }
        }
    }

    pub fn warmed(&self, key: K) -> Option<&R> {
        match self.slots.get(&key) {
            Some(Slot::Warmed(resource)) => Some(resource),
            _ => None,
        }
    }

    /// Forget connectors for which `keep` is false (unplugged), returning any
    /// finished resources so they can be released.
    pub fn retain(&mut self, mut keep: impl FnMut(&K) -> bool) -> Vec<R> {
        let gone = self
            .slots
            .keys()
            .filter(|key| !keep(key))
            .copied()
            .collect::<Vec<_>>();
        gone.into_iter()
            .filter_map(|key| match self.slots.remove(&key) {
                Some(Slot::Warmed(resource)) => Some(resource),
                _ => None,
            })
            .collect()
    }
}

/// Primary plane of `crtc` and a 32-bit format it can scan out, preferring
/// opaque XRGB8888 so the placeholder frame is plain black.
pub fn primary_plane<D: Device>(
    device: &D,
    resources: &ResourceHandles,
    crtc: crtc::Handle,
) -> Option<(plane::Handle, DrmFourcc)> {
    for handle in device.plane_handles().ok()? {
        let Ok(info) = device.get_plane(handle) else {
            continue;
        };
        if !resources
            .filter_crtcs(info.possible_crtcs())
            .contains(&crtc)
        {
            continue;
        }
        if named_property(device, handle, "type").map(|(_, value)| value)
            != Some(PLANE_TYPE_PRIMARY)
        {
            continue;
        }
        let format = [DrmFourcc::Xrgb8888, DrmFourcc::Argb8888]
            .into_iter()
            .find(|format| info.formats().contains(&(*format as u32)))?;
        return Some((handle, format));
    }
    None
}

fn handle_of<D: Device, H: smithay::reexports::drm::control::ResourceHandle>(
    device: &D,
    object: H,
    name: &str,
) -> Result<property::Handle, String> {
    named_property(device, object, name)
        .map(|(handle, _)| handle)
        .ok_or_else(|| format!("missing property {name}"))
}

/// Build the modeset request: bind `connector` to the CRTC with the mode and
/// scan the placeholder framebuffer out of the primary plane.
fn request<D: Device>(
    device: &D,
    connector: smithay::reexports::drm::control::connector::Handle,
    plan: &Plan,
    framebuffer: framebuffer::Handle,
    mode_blob: u64,
) -> Result<AtomicModeReq, String> {
    let (width, height) = plan.mode.size();
    let (width, height) = (u64::from(width), u64::from(height));
    let mut req = AtomicModeReq::new();
    req.add_property(
        connector,
        handle_of(device, connector, "CRTC_ID")?,
        property::Value::CRTC(Some(plan.crtc)),
    );
    req.add_property(
        plan.crtc,
        handle_of(device, plan.crtc, "MODE_ID")?,
        property::Value::Blob(mode_blob),
    );
    req.add_property(
        plan.crtc,
        handle_of(device, plan.crtc, "ACTIVE")?,
        property::Value::Boolean(true),
    );
    let plane = plan.plane;
    let set = |req: &mut AtomicModeReq, name: &str, value: property::Value| {
        handle_of(device, plane, name).map(|handle| req.add_property(plane, handle, value))
    };
    set(
        &mut req,
        "FB_ID",
        property::Value::Framebuffer(Some(framebuffer)),
    )?;
    set(&mut req, "CRTC_ID", property::Value::CRTC(Some(plan.crtc)))?;
    set(&mut req, "SRC_X", property::Value::UnsignedRange(0))?;
    set(&mut req, "SRC_Y", property::Value::UnsignedRange(0))?;
    set(
        &mut req,
        "SRC_W",
        property::Value::UnsignedRange(width << 16),
    )?;
    set(
        &mut req,
        "SRC_H",
        property::Value::UnsignedRange(height << 16),
    )?;
    set(&mut req, "CRTC_X", property::Value::SignedRange(0))?;
    set(&mut req, "CRTC_Y", property::Value::SignedRange(0))?;
    set(&mut req, "CRTC_W", property::Value::UnsignedRange(width))?;
    set(&mut req, "CRTC_H", property::Value::UnsignedRange(height))?;
    Ok(req)
}

/// Perform the modeset. Runs on the helper thread. A `TEST_ONLY` commit comes
/// first so a configuration the driver rejects changes nothing. With
/// `commit` false it stops after that test and releases everything (`None`),
/// which `pantheon-drm-probe --prewarm-dry-run` uses on real hardware.
pub fn run<D: Device>(
    device: &D,
    connector: smithay::reexports::drm::control::connector::Handle,
    plan: &Plan,
    commit: bool,
) -> Result<Option<Warmed>, String> {
    let (width, height) = plan.mode.size();
    let buffer = device
        .create_dumb_buffer((u32::from(width), u32::from(height)), plan.format, 32)
        .map_err(|error| format!("dumb buffer: {error}"))?;
    // Legacy ADDFB: a dumb buffer is not a `PlanarBuffer`; depth follows format.
    let depth = if plan.format == DrmFourcc::Argb8888 {
        32
    } else {
        24
    };
    let framebuffer = match device.add_framebuffer(&buffer, depth, 32) {
        Ok(framebuffer) => framebuffer,
        Err(error) => {
            let _ = device.destroy_dumb_buffer(buffer);
            return Err(format!("framebuffer: {error}"));
        }
    };
    let warmed = Warmed {
        framebuffer,
        buffer,
    };
    let blob = match device.create_property_blob(&plan.mode) {
        Ok(property::Value::Blob(id)) => id,
        Ok(_) => {
            release(device, warmed);
            return Err("mode blob has an unexpected type".into());
        }
        Err(error) => {
            release(device, warmed);
            return Err(format!("mode blob: {error}"));
        }
    };
    let committed = request(device, connector, plan, framebuffer, blob).and_then(|req| {
        device
            .atomic_commit(
                AtomicCommitFlags::ALLOW_MODESET | AtomicCommitFlags::TEST_ONLY,
                req.clone(),
            )
            .map_err(|error| format!("test commit: {error}"))?;
        if !commit {
            return Ok(());
        }
        device
            .atomic_commit(AtomicCommitFlags::ALLOW_MODESET, req)
            .map_err(|error| format!("commit: {error}"))
    });
    // The kernel keeps its own reference to the blob once committed.
    let _ = device.destroy_property_blob(blob);
    match committed {
        Ok(()) if commit => Ok(Some(warmed)),
        Ok(()) => {
            release(device, warmed);
            Ok(None)
        }
        Err(error) => {
            release(device, warmed);
            Err(error)
        }
    }
}

/// Free the placeholder framebuffer and buffer. Only call this once the
/// plane scans out something else (or the connector is gone): removing a
/// framebuffer that is still on screen disables its plane.
pub fn release<D: Device>(device: &D, warmed: Warmed) {
    let _ = device.destroy_framebuffer(warmed.framebuffer);
    let _ = device.destroy_dumb_buffer(warmed.buffer);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ms(n: u64) -> Duration {
        Duration::from_millis(n)
    }

    #[test]
    fn a_new_connector_is_planned_then_waits_until_the_helper_finishes() {
        let t0 = Instant::now();
        let mut slots = Slots::<u32, &str>::default();
        assert_eq!(slots.gate(1, t0), Gate::Plan);
        slots.started(1, t0);
        assert_eq!(slots.gate(1, t0 + ms(240)), Gate::Wait);
        assert!(slots.finished(1, Ok("fb")).is_none());
        assert_eq!(slots.gate(1, t0 + ms(250)), Gate::Ready);
        assert_eq!(slots.warmed(1), Some(&"fb"));
        assert_eq!(slots.take_warmed(1), Some("fb"));
        assert_eq!(slots.gate(1, t0 + ms(300)), Gate::Plan);
    }

    #[test]
    fn a_failed_prewarm_falls_back_to_inline_until_unplugged() {
        let t0 = Instant::now();
        let mut slots = Slots::<u32, &str>::default();
        slots.started(1, t0);
        assert!(slots.finished(1, Err(())).is_none());
        assert_eq!(slots.gate(1, t0), Gate::Inline);
        assert_eq!(slots.gate(1, t0 + Duration::from_secs(60)), Gate::Inline);
        assert!(slots.retain(|_| false).is_empty());
        assert_eq!(slots.gate(1, t0), Gate::Plan);
    }

    #[test]
    fn a_stuck_prewarm_stops_blocking_the_connector() {
        let t0 = Instant::now();
        let mut slots = Slots::<u32, &str>::default();
        slots.started(1, t0);
        assert_eq!(slots.gate(1, t0 + STUCK_AFTER - ms(1)), Gate::Wait);
        assert_eq!(slots.gate(1, t0 + STUCK_AFTER), Gate::Inline);
        // The late result still has somewhere to go and is not leaked.
        assert!(slots.finished(1, Ok("late")).is_none());
        assert_eq!(slots.gate(1, t0 + STUCK_AFTER), Gate::Ready);
    }

    #[test]
    fn a_result_for_an_unplugged_connector_is_handed_back_for_release() {
        let t0 = Instant::now();
        let mut slots = Slots::<u32, &str>::default();
        slots.started(7, t0);
        assert!(slots.retain(|_| false).is_empty());
        assert_eq!(slots.finished(7, Ok("orphan")), Some("orphan"));
        assert_eq!(slots.finished(7, Err(())), None);
    }

    #[test]
    fn unplugging_returns_finished_resources_only() {
        let t0 = Instant::now();
        let mut slots = Slots::<u32, &str>::default();
        slots.started(1, t0);
        slots.started(2, t0);
        slots.started(3, t0);
        slots.finished(1, Ok("one"));
        slots.finished(2, Err(()));
        let released = slots.retain(|key| *key == 3);
        assert_eq!(released, vec!["one"]);
        assert_eq!(slots.gate(3, t0), Gate::Wait);
        assert_eq!(slots.gate(1, t0), Gate::Plan);
    }
}
