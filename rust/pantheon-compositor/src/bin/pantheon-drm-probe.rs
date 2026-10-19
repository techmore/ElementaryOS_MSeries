use smithay::backend::egl::EGLDevice;

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

    Ok(())
}
