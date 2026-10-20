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

        for handle in resources.connectors() {
            match device.get_connector(*handle, false) {
                Ok(connector) => {
                    println!("  {}: {:?}", connector, connector.state());
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
