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

struct ReadOnlyDrmDevice(File);

impl AsFd for ReadOnlyDrmDevice {
    fn as_fd(&self) -> BorrowedFd<'_> {
        self.0.as_fd()
    }
}

impl smithay::reexports::drm::Device for ReadOnlyDrmDevice {}
impl smithay::reexports::drm::control::Device for ReadOnlyDrmDevice {}

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

    let kms_path = inspect_kms_connectors(hardware_render_path.as_deref())?;
    match (hardware_render_path, kms_path) {
        (Some(render_path), Some(kms_path)) => probe_cross_gpu_import(&render_path, &kms_path),
        _ => println!(
            "Cross-GPU GBM import: skipped (could not identify a hardware renderer and connected KMS device)."
        ),
    }

    Ok(())
}

fn inspect_kms_connectors(
    render_path: Option<&std::path::Path>,
) -> Result<Option<PathBuf>, Box<dyn std::error::Error>> {
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
            Ok(file) => ReadOnlyDrmDevice(file),
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
                        connected_kms.get_or_insert_with(|| path.clone());
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
    }

    Ok(connected_kms)
}

/// Check whether the render GPU can allocate a scanout-capable DMA-BUF that
/// the connected KMS device's GBM implementation can import. This does not
/// create a DRM framebuffer, acquire DRM master, or change an output mode.
fn probe_cross_gpu_import(render_path: &PathBuf, kms_path: &PathBuf) {
    println!("Cross-GPU GBM import preflight:");
    println!("  render node: {}", render_path.display());
    println!("  KMS device: {}", kms_path.display());

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
    let kms_file = match OpenOptions::new().read(true).write(true).open(kms_path) {
        Ok(file) => file,
        Err(error) => {
            println!("  cannot open KMS device read/write: {error}");
            return;
        }
    };
    let kms_gbm = match GbmDevice::new(kms_file) {
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
        let buffer = match allocator.create_buffer(64, 64, format, &[Modifier::Invalid]) {
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
            Ok(_) => println!(
                "  {format:?} modifier {:?}: KMS GBM import succeeded",
                dmabuf.format().modifier
            ),
            Err(error) => println!(
                "  {format:?} modifier {:?}: KMS GBM import failed: {error}",
                dmabuf.format().modifier
            ),
        }
    }
    println!("  framebuffer creation and modesetting were not attempted.");
}
