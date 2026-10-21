//! Read-only helpers for named properties on KMS objects.
//!
//! Shared by the native backend and `pantheon-drm-probe`, which includes this
//! file by path so the probe exercises the exact code the compositor runs.

use smithay::reexports::drm::control::{Device, ResourceHandle, connector, property};

/// Raw value of a named property on a KMS object, with its property handle.
pub fn named_property<D: Device, H: ResourceHandle>(
    device: &D,
    object: H,
    wanted: &str,
) -> Option<(property::Handle, u64)> {
    let set = device.get_properties(object).ok()?;
    let (handles, values) = set.as_props_and_values();
    handles.iter().zip(values).find_map(|(handle, value)| {
        let info = device.get_property(*handle).ok()?;
        (info.name().to_str().ok()? == wanted).then_some((*handle, *value))
    })
}

/// The connector's EDID bytes and the id of the kernel blob holding them.
pub fn connector_edid<D: Device>(
    device: &D,
    connector: connector::Handle,
) -> Option<(Vec<u8>, u32)> {
    let (_, blob_id) = named_property(device, connector, "EDID")?;
    let blob_id = u32::try_from(blob_id).ok().filter(|id| *id != 0)?;
    let bytes = device.get_property_blob(u64::from(blob_id)).ok()?;
    (!bytes.is_empty()).then_some((bytes, blob_id))
}
