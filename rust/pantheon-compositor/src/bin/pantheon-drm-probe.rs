use std::{
    fs::File,
    os::fd::{AsFd, BorrowedFd},
};

use smithay::backend::egl::EGLDevice;

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

        println!("EGL device {index}:");
        println!("  DRM node: {drm_path}");
        println!("  render node: {render_path}");
        println!("  Smithay node selection: {render_node}");
        println!("  software renderer: {}", device.is_software());
    }

    if count == 0 {
        println!("No EGL devices found.");
    }

    inspect_kms_connectors()?;

    Ok(())
}

fn inspect_kms_connectors() -> Result<(), Box<dyn std::error::Error>> {
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

    Ok(())
}
