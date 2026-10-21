use std::{
    fs::{File, OpenOptions},
    os::fd::{AsFd, BorrowedFd},
    path::PathBuf,
};

use smithay::backend::{
    allocator::{
        Allocator, Buffer, Fourcc, Modifier,
        dmabuf::AsDmabuf,
        gbm::{GbmAllocator, GbmBufferFlags, GbmDevice},
    },
    egl::EGLDevice,
};
use smithay::reexports::drm::control::{Device as _, FbCmd2Flags};

// Same parsing and property code the compositor runs, so a read-only probe on
// real hardware verifies it without taking DRM master.
#[path = "../edid.rs"]
#[allow(dead_code)]
mod edid;
#[path = "../kms_props.rs"]
mod kms_props;
#[path = "../link_status.rs"]
#[allow(dead_code)]
mod link_status;
#[path = "../prewarm.rs"]
#[allow(dead_code)]
mod prewarm;

struct KmsTarget {
    path: PathBuf,
    width: u32,
    height: u32,
}

struct DrmDeviceFile(File);

impl AsFd for DrmDeviceFile {
    fn as_fd(&self) -> BorrowedFd<'_> {
        self.0.as_fd()
    }
}

impl smithay::reexports::drm::Device for DrmDeviceFile {}
impl smithay::reexports::drm::control::Device for DrmDeviceFile {}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let devices = EGLDevice::enumerate()?;
    let mut count = 0;
    let mut hardware_render_path = None;

    for (index, device) in devices.enumerate() {
        count += 1;
        let drm_path = device
            .drm_device_path()
            .map(|path| path.display().to_string())
            .unwrap_or_else(|error| format!("unavailable ({error})"));
        let render_path = device
            .render_device_path()
            .map(|path| path.display().to_string())
            .unwrap_or_else(|error| format!("unavailable ({error})"));
        let render_node = device
            .try_get_render_node()
            .map(|node| {
                node.map(|node| node.to_string())
                    .unwrap_or_else(|| "unavailable".to_owned())
            })
            .unwrap_or_else(|error| format!("unavailable ({error})"));
        if !device.is_software() {
            hardware_render_path = device.render_device_path().ok();
        }

        println!("EGL device {index}:");
        println!("  DRM node: {drm_path}");
        println!("  render node: {render_path}");
        println!("  Smithay node selection: {render_node}");
        println!("  software renderer: {}", device.is_software());
    }

    if count == 0 {
        println!("No EGL devices found.");
    }

    if std::env::args().any(|arg| arg == "--prewarm-dry-run") {
        prewarm_dry_run();
        return Ok(());
    }

    let kms_target = inspect_kms_connectors(hardware_render_path.as_deref())?;
    match (hardware_render_path, kms_target) {
        (Some(render_path), Some(kms_target)) => probe_cross_gpu_import(&render_path, &kms_target),
        _ => println!(
            "Cross-GPU GBM import: skipped (could not identify a hardware renderer and connected KMS device)."
        ),
    }

    Ok(())
}

fn inspect_kms_connectors(
    render_path: Option<&std::path::Path>,
) -> Result<Option<KmsTarget>, Box<dyn std::error::Error>> {
    use smithay::reexports::drm::control::Device as _;

    let mut cards = std::fs::read_dir("/dev/dri")?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .and_then(|name| name.strip_prefix("card"))
                .is_some_and(|suffix| {
                    !suffix.is_empty() && suffix.bytes().all(|b| b.is_ascii_digit())
                })
        })
        .collect::<Vec<_>>();
    cards.sort();
    let mut connected_kms = None;

    for path in cards {
        println!("KMS device {}:", path.display());
        let device = match File::open(&path) {
            Ok(file) => DrmDeviceFile(file),
            Err(error) => {
                println!("  cannot open read-only: {error}");
                continue;
            }
        };
        let resources = match device.resource_handles() {
            Ok(resources) => resources,
            Err(error) => {
                println!("  cannot query resources: {error}");
                continue;
            }
        };

        let mut edid_names: Vec<String> = Vec::new();
        let mut edid_candidates: Vec<edid::Candidate<usize>> = Vec::new();
        for handle in resources.connectors() {
            match device.get_connector(*handle, false) {
                Ok(connector) => {
                    println!("  {}: {:?}", connector, connector.state());
                    if connector.state()
                        == smithay::reexports::drm::control::connector::State::Connected
                    {
                        if let Some((bytes, blob_id)) =
                            kms_props::connector_edid(&device, connector.handle())
                        {
                            match edid::parse(&bytes) {
                                Some(identity) => println!(
                                    "    EDID blob {blob_id}: {}:{}:{} (unique serial: {})",
                                    identity.vendor,
                                    identity.product,
                                    identity.serial,
                                    identity.has_unique_serial
                                ),
                                None => println!("    EDID blob {blob_id}: unparseable"),
                            }
                            edid_candidates.push(edid::Candidate {
                                key: edid_names.len(),
                                edid: bytes,
                                blob_id,
                                interface_id: connector.interface_id(),
                            });
                            edid_names.push(connector.to_string());
                        }
                        if let Some((_, value)) =
                            kms_props::named_property(&device, connector.handle(), "link-status")
                        {
                            println!(
                                "    link-status: {}",
                                if value == link_status::LINK_STATUS_BAD {
                                    "Bad"
                                } else {
                                    "Good"
                                }
                            );
                        }
                    }
                    let is_separate_device = render_path.is_some_and(|render_path| {
                        smithay::backend::drm::DrmNode::from_path(render_path)
                            .ok()
                            .zip(smithay::backend::drm::DrmNode::from_path(&path).ok())
                            .is_some_and(|(render, kms)| render.dev_id() != kms.dev_id())
                    });
                    if is_separate_device
                        && connector.state()
                            == smithay::reexports::drm::control::connector::State::Connected
                    {
                        let selected_mode = connector
                            .modes()
                            .iter()
                            .find(|mode| {
                                mode.mode_type().contains(
                                    smithay::reexports::drm::control::ModeTypeFlags::PREFERRED,
                                )
                            })
                            .or_else(|| connector.modes().first());
                        if let Some(mode) = selected_mode {
                            let (width, height) = mode.size();
                            connected_kms.get_or_insert_with(|| KmsTarget {
                                path: path.clone(),
                                width: u32::from(width),
                                height: u32::from(height),
                            });
                        }
                    }
                    for mode in connector.modes().iter().take(8) {
                        let (width, height) = mode.size();
                        println!("    {width}x{height}@{}Hz", mode.vrefresh());
                    }
                    if connector.modes().len() > 8 {
                        println!("    ... {} more modes", connector.modes().len() - 8);
                    }
                }
                Err(error) => println!("  connector {:?}: {error}", handle),
            }
        }

        let stale = edid::stale_duplicates(&edid_candidates);
        if !stale.is_empty() {
            println!(
                "  stale duplicate connectors (same monitor EDID, older blob): {}",
                stale
                    .iter()
                    .map(|index| edid_names[*index].as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            );
        }

        let is_render_device = render_path.is_some_and(|render_path| {
            smithay::backend::drm::DrmNode::from_path(render_path)
                .ok()
                .zip(smithay::backend::drm::DrmNode::from_path(&path).ok())
                .is_some_and(|(render, kms)| render.dev_id() == kms.dev_id())
        });
        if !is_render_device {
            inspect_kms_planes(&device);
        }
    }

    Ok(connected_kms)
}

/// Read advertised plane formats from the KMS device. This does not change
/// plane state or attach a framebuffer.
fn inspect_kms_planes(device: &DrmDeviceFile) {
    use smithay::reexports::drm::control::Device as _;

    let plane_handles = match device.plane_handles() {
        Ok(planes) => planes,
        Err(error) => {
            println!("  cannot query KMS planes: {error}");
            return;
        }
    };

    println!("  KMS planes:");
    for handle in plane_handles {
        let plane = match device.get_plane(handle) {
            Ok(plane) => plane,
            Err(error) => {
                println!("    {handle:?}: {error}");
                continue;
            }
        };
        let supported = [
            (Fourcc::Argb2101010, "AR30"),
            (Fourcc::Abgr8888, "AB24"),
            (Fourcc::Argb8888, "AR24"),
            (Fourcc::Abgr2101010, "AB30"),
        ]
        .into_iter()
        .filter_map(|(format, name)| plane.formats().contains(&(format as u32)).then_some(name))
        .collect::<Vec<_>>();
        println!(
            "    {handle:?}: crtc={:?} framebuffer={:?}, tested formats advertised={:?} ({} total formats)",
            plane.crtc(),
            plane.framebuffer(),
            supported,
            plane.formats().len()
        );
    }
}

/// Check whether the render GPU can allocate a scanout-capable DMA-BUF that
/// the connected KMS device can import and register as a framebuffer. Created
/// framebuffers are immediately removed; no plane or mode is changed and DRM
/// master is not acquired.
fn probe_cross_gpu_import(render_path: &PathBuf, kms_target: &KmsTarget) {
    println!("Cross-GPU GBM import preflight:");
    println!("  render node: {}", render_path.display());
    println!("  KMS device: {}", kms_target.path.display());
    println!(
        "  preferred mode size: {}x{}",
        kms_target.width, kms_target.height
    );

    let render_file = match OpenOptions::new().read(true).write(true).open(render_path) {
        Ok(file) => file,
        Err(error) => {
            println!("  cannot open render node read/write: {error}");
            return;
        }
    };
    let render_gbm = match GbmDevice::new(render_file) {
        Ok(gbm) => gbm,
        Err(error) => {
            println!("  cannot create render GBM device: {error}");
            return;
        }
    };
    let kms_file = match OpenOptions::new()
        .read(true)
        .write(true)
        .open(&kms_target.path)
    {
        Ok(file) => file,
        Err(error) => {
            println!("  cannot open KMS device read/write: {error}");
            return;
        }
    };
    let kms_gbm = match GbmDevice::new(DrmDeviceFile(kms_file)) {
        Ok(gbm) => gbm,
        Err(error) => {
            println!("  cannot create KMS GBM device: {error}");
            return;
        }
    };

    let mut allocator = GbmAllocator::new(
        render_gbm,
        GbmBufferFlags::RENDERING | GbmBufferFlags::SCANOUT,
    );
    let formats = [
        Fourcc::Abgr2101010,
        Fourcc::Argb2101010,
        Fourcc::Abgr8888,
        Fourcc::Argb8888,
    ];
    for format in formats {
        let buffer = match allocator.create_buffer(
            kms_target.width,
            kms_target.height,
            format,
            &[Modifier::Invalid],
        ) {
            Ok(buffer) => buffer,
            Err(error) => {
                println!("  {format:?}: render allocation failed: {error}");
                continue;
            }
        };
        let dmabuf = match buffer.export() {
            Ok(dmabuf) => dmabuf,
            Err(error) => {
                println!("  {format:?}: DMA-BUF export failed: {error}");
                continue;
            }
        };
        match dmabuf.import_to(&kms_gbm, GbmBufferFlags::SCANOUT) {
            Ok(kms_buffer) => {
                println!(
                    "  {format:?} modifier {:?}: KMS GBM import succeeded",
                    dmabuf.format().modifier
                );
                match kms_gbm.add_planar_framebuffer(&kms_buffer, FbCmd2Flags::empty()) {
                    Ok(framebuffer) => {
                        println!("    ADDFB2 registration succeeded");
                        match kms_gbm.destroy_framebuffer(framebuffer) {
                            Ok(()) => println!("    unassigned framebuffer removed"),
                            Err(error) => println!(
                                "    framebuffer removal failed; it will be released when the KMS fd closes: {error}"
                            ),
                        }
                    }
                    Err(error) => println!("    ADDFB2 registration failed: {error}"),
                }
            }
            Err(error) => println!(
                "  {format:?} modifier {:?}: KMS GBM import failed: {error}",
                dmabuf.format().modifier
            ),
        }
    }
    println!("  No framebuffer was attached to a plane; modesetting was not attempted.");
}

/// Run the compositor's prewarm planning and request building against every
/// connected external connector, stopping at a `TEST_ONLY` atomic commit. It
/// creates and destroys a dumb buffer but changes no display state, so it is
/// safe next to a running compositor.
fn prewarm_dry_run() {
    // `--include-internal` also tests the built-in panel, the only connected
    // connector when no dock is attached.
    let include_internal = std::env::args().any(|arg| arg == "--include-internal");
    use smithay::reexports::drm::{
        ClientCapability,
        control::{ModeTypeFlags, connector},
    };

    let Ok(entries) = std::fs::read_dir("/dev/dri") else {
        println!("cannot read /dev/dri");
        return;
    };
    let mut cards = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.strip_prefix("card").is_some_and(|n| !n.is_empty()))
        })
        .collect::<Vec<_>>();
    cards.sort();
    for path in cards {
        let Ok(file) = OpenOptions::new().read(true).write(true).open(&path) else {
            continue;
        };
        let device = DrmDeviceFile(file);
        use smithay::reexports::drm::Device as _;
        let _ = device.set_client_capability(ClientCapability::UniversalPlanes, true);
        let _ = device.set_client_capability(ClientCapability::Atomic, true);
        let Ok(resources) = device.resource_handles() else {
            println!("{}: cannot query resources", path.display());
            continue;
        };
        for handle in resources.connectors() {
            let Ok(info) = device.get_connector(*handle, false) else {
                continue;
            };
            if info.state() != connector::State::Connected
                || (info.interface() == connector::Interface::EmbeddedDisplayPort
                    && !include_internal)
                || info.modes().is_empty()
            {
                continue;
            }
            println!("{}: {}", path.display(), info);
            let encoder = info
                .current_encoder()
                .and_then(|encoder| device.get_encoder(encoder).ok())
                .or_else(|| {
                    info.encoders()
                        .iter()
                        .find_map(|encoder| device.get_encoder(*encoder).ok())
                });
            let Some(crtc) = encoder.and_then(|encoder| {
                encoder.crtc().or_else(|| {
                    resources
                        .filter_crtcs(encoder.possible_crtcs())
                        .first()
                        .copied()
                })
            }) else {
                println!("  no CRTC for this connector");
                continue;
            };
            let Some(mode) = info
                .modes()
                .iter()
                .find(|mode| mode.mode_type().contains(ModeTypeFlags::PREFERRED))
                .or_else(|| info.modes().first())
                .copied()
            else {
                continue;
            };
            let Some((plane, format)) = prewarm::primary_plane(&device, &resources, crtc) else {
                println!("  no primary plane with XRGB8888/ARGB8888 for {crtc:?}");
                continue;
            };
            println!(
                "  crtc {crtc:?}, plane {plane:?}, format {format:?}, mode {}x{}@{}",
                mode.size().0,
                mode.size().1,
                mode.vrefresh()
            );
            let plan = prewarm::Plan {
                crtc,
                plane,
                mode,
                format,
            };
            match prewarm::run(&device, info.handle(), &plan, false) {
                Ok(_) => println!("  TEST_ONLY modeset commit accepted; nothing was changed"),
                Err(error) => println!("  rejected: {error}"),
            }
        }
    }
}
