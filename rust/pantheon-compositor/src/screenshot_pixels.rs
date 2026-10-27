//! Bounded readback of a renderer-owned framebuffer; no client capture API.
use smithay::backend::{
    allocator::Fourcc,
    renderer::{ExportMem, Texture, TextureMapping},
};
use smithay::utils::{Buffer, Rectangle, Size};

const MAX_PIXELS: usize = 32 * 1024 * 1024;

pub fn rgba_image(
    width: u32,
    height: u32,
    bytes: &[u8],
    bottom_up: bool,
) -> Result<image::RgbaImage, String> {
    let pixels = (width as usize)
        .checked_mul(height as usize)
        .filter(|pixels| *pixels > 0 && *pixels <= MAX_PIXELS)
        .ok_or("Screenshot dimensions exceed the capture limit")?;
    if bytes.len() != pixels * 4 {
        return Err("Screenshot pixel buffer has an unexpected size".into());
    }
    let mut image = image::RgbaImage::from_raw(width, height, bytes.to_vec())
        .ok_or("Screenshot pixel buffer is invalid")?;
    if bottom_up {
        image::imageops::flip_vertical_in_place(&mut image);
    }
    Ok(image)
}

pub fn read_framebuffer<R: ExportMem>(
    renderer: &mut R,
    framebuffer: &R::Framebuffer<'_>,
    size: Size<i32, Buffer>,
) -> Result<image::RgbaImage, String> {
    if size.w <= 0 || size.h <= 0 || i64::from(size.w) * i64::from(size.h) > MAX_PIXELS as i64 {
        return Err("Screenshot dimensions exceed the capture limit".into());
    }
    let mapping = renderer
        .copy_framebuffer(framebuffer, Rectangle::from_size(size), Fourcc::Abgr8888)
        .map_err(|error| format!("Could not read screenshot framebuffer: {error}"))?;
    if TextureMapping::format(&mapping) != Fourcc::Abgr8888 || mapping.size() != size {
        return Err("Screenshot renderer returned an unexpected pixel format or size".into());
    }
    // Smithay renders into textures y-down, so ReadPixels already returns the
    // top row first. `TextureMapping::flipped()` is a hard-coded `true` in the
    // GLES backend and must not be used here: it turned every capture upside
    // down on the hardware renderer (see `gpu_orientation`).
    let bottom_up = false;
    let bytes = renderer
        .map_texture(&mapping)
        .map_err(|error| format!("Could not map screenshot pixels: {error}"))?;
    rgba_image(size.w as u32, size.h as u32, bytes, bottom_up)
}

/// Compose an output into an owned texture rather than reading a scanout plane.
/// This is invoked only for an explicit capture request; it does no idle work.
pub fn compose_output<R>(
    renderer: &mut R,
    state: &crate::PantheonCompositor,
    output: &smithay::output::Output,
) -> Result<image::RgbaImage, String>
where
    R: smithay::backend::renderer::ImportAll
        + smithay::backend::renderer::ImportMem
        + smithay::backend::renderer::Offscreen<smithay::backend::renderer::gles::GlesTexture>
        + ExportMem
        + crate::corner_render::CornerRenderer,
    R::TextureId: Texture + Clone + Send + 'static,
{
    if state.session_locked {
        return Err("Screenshot capture is unavailable while the session is locked".into());
    }
    let mode = output
        .current_mode()
        .ok_or("Screenshot output has no active mode")?;
    let size: Size<i32, Buffer> = (mode.size.w, mode.size.h).into();
    if size.w <= 0 || size.h <= 0 || i64::from(size.w) * i64::from(size.h) > MAX_PIXELS as i64 {
        return Err("Screenshot dimensions exceed the capture limit".into());
    }
    let elements = crate::cursor::render_desktop_elements(renderer, state, output)
        .map_err(|error| format!("Could not collect screenshot surfaces: {error}"))?;
    let mut target = renderer
        .create_buffer(Fourcc::Abgr8888, size)
        .map_err(|error| format!("Could not allocate screenshot texture: {error}"))?;
    let mut framebuffer = renderer
        .bind(&mut target)
        .map_err(|error| format!("Could not bind screenshot texture: {error}"))?;
    let mut damage = smithay::backend::renderer::damage::OutputDamageTracker::from_output(output);
    let rendered = damage
        .render_output(
            renderer,
            &mut framebuffer,
            0,
            &elements,
            [0.1, 0.1, 0.1, 1.0],
        )
        .map_err(|error| format!("Could not render screenshot: {error}"))?;
    renderer
        .wait(&rendered.sync)
        .map_err(|error| format!("Could not finish screenshot rendering: {error}"))?;
    read_framebuffer(renderer, &framebuffer, size)
}

/// Crop an upright output image using global logical desktop bounds.
/// Pixel ratios come from the rendered image, avoiding integer-scale assumptions.
pub fn crop_output(
    image: &image::RgbaImage,
    output: crate::screenshot::Region,
    selection: crate::screenshot::Region,
) -> Option<image::RgbaImage> {
    if output.width == 0 || output.height == 0 {
        return None;
    }
    let left = i64::from(output.x).max(i64::from(selection.x));
    let top = i64::from(output.y).max(i64::from(selection.y));
    let right = (i64::from(output.x) + i64::from(output.width))
        .min(i64::from(selection.x) + i64::from(selection.width));
    let bottom = (i64::from(output.y) + i64::from(output.height))
        .min(i64::from(selection.y) + i64::from(selection.height));
    if right <= left || bottom <= top {
        return None;
    }
    let pixel = |coordinate: i64, origin: i32, logical: u32, physical: u32, ceil: bool| {
        let numerator = (coordinate - i64::from(origin)) as u64 * u64::from(physical);
        let value = if ceil {
            numerator.div_ceil(u64::from(logical))
        } else {
            numerator / u64::from(logical)
        };
        value.min(u64::from(physical)) as u32
    };
    let x = pixel(left, output.x, output.width, image.width(), false);
    let y = pixel(top, output.y, output.height, image.height(), false);
    let end_x = pixel(right, output.x, output.width, image.width(), true);
    let end_y = pixel(bottom, output.y, output.height, image.height(), true);
    (end_x > x && end_y > y)
        .then(|| image::imageops::crop_imm(image, x, y, end_x - x, end_y - y).to_image())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preserves_channels_and_corrects_bottom_up_rows() {
        let bytes = [255, 0, 0, 255, 0, 0, 255, 128];
        let upright = rgba_image(1, 2, &bytes, false).unwrap();
        assert_eq!(upright.get_pixel(0, 0).0, [255, 0, 0, 255]);
        let flipped = rgba_image(1, 2, &bytes, true).unwrap();
        assert_eq!(flipped.get_pixel(0, 0).0, [0, 0, 255, 128]);
        assert_eq!(flipped.get_pixel(0, 1).0, [255, 0, 0, 255]);
    }
    #[test]
    fn region_crop_handles_negative_origins_fractional_scale_and_clipping() {
        use crate::screenshot::Region;
        let image =
            image::RgbaImage::from_fn(150, 120, |x, y| image::Rgba([x as u8, y as u8, 0, 255]));
        let output = Region {
            x: -100,
            y: -80,
            width: 100,
            height: 80,
        };
        let selected = Region {
            x: -90,
            y: -70,
            width: 20,
            height: 20,
        };
        let cropped = crop_output(&image, output, selected).unwrap();
        assert_eq!(cropped.dimensions(), (30, 30));
        assert_eq!(cropped.get_pixel(0, 0).0, [15, 15, 0, 255]);
        let clipped = crop_output(
            &image,
            output,
            Region {
                x: -110,
                y: -90,
                width: 20,
                height: 20,
            },
        )
        .unwrap();
        assert_eq!(clipped.dimensions(), (15, 15));
        assert!(
            crop_output(
                &image,
                output,
                Region {
                    x: 1,
                    y: 1,
                    width: 10,
                    height: 10
                }
            )
            .is_none()
        );
    }

    #[test]
    fn rejects_empty_oversized_and_truncated_buffers() {
        assert!(rgba_image(0, 1, &[], false).is_err());
        assert!(rgba_image(u32::MAX, u32::MAX, &[], false).is_err());
        assert!(rgba_image(1, 1, &[0; 3], false).is_err());
    }
}

/// Consume one explicit request; encoding and file I/O run off the render loop.
pub fn process_request<R>(
    renderer: &mut R,
    state: &crate::PantheonCompositor,
    outputs: &[smithay::output::Output],
) where
    R: smithay::backend::renderer::ImportAll
        + smithay::backend::renderer::ImportMem
        + smithay::backend::renderer::Offscreen<smithay::backend::renderer::gles::GlesTexture>
        + ExportMem
        + crate::corner_render::CornerRenderer,
    R::TextureId: Texture + Clone + Send + 'static,
{
    use std::sync::atomic::Ordering;
    if !state.screenshot_requested.replace(false) {
        return;
    }
    if state.session_locked || state.screenshot_busy.swap(true, Ordering::AcqRel) {
        return;
    }
    let Some(home) = std::env::var_os("HOME") else {
        state.screenshot_busy.store(false, Ordering::Release);
        tracing::warn!("Screenshot unavailable: HOME is unset");
        return;
    };
    let directory = std::path::PathBuf::from(home).join("Downloads/Screenshots");
    let region = state.screenshot_region.take();
    let mut images = Vec::new();
    let mut pixels = 0_u64;
    for output in outputs {
        let result = compose_output(renderer, state, output);
        match result {
            Ok(image) => {
                let image = if let Some(region) = region {
                    let Some(bounds) = state.space.output_geometry(output) else {
                        continue;
                    };
                    let Some(cropped) = crop_output(
                        &image,
                        crate::screenshot::Region {
                            x: bounds.loc.x,
                            y: bounds.loc.y,
                            width: bounds.size.w as u32,
                            height: bounds.size.h as u32,
                        },
                        region,
                    ) else {
                        continue;
                    };
                    cropped
                } else {
                    image
                };
                pixels += u64::from(image.width()) * u64::from(image.height());
                if pixels > MAX_PIXELS as u64 {
                    state.screenshot_busy.store(false, Ordering::Release);
                    tracing::warn!("Screenshot desktop exceeds capture limit");
                    return;
                }
                images.push(image);
            }
            Err(error) => {
                state.screenshot_busy.store(false, Ordering::Release);
                tracing::warn!(%error, "Screenshot composition failed");
                return;
            }
        }
    }
    let busy = state.screenshot_busy.clone();
    let worker = std::thread::Builder::new()
        .name("screenshot-save".into())
        .spawn(move || {
            let mut saved = false;
            for image in images {
                match crate::screenshot_save::save_png(&directory, &image) {
                    Ok(_) => saved = true,
                    Err(error) => tracing::warn!(%error, "Screenshot save failed"),
                }
            }
            if saved {
                let played = std::process::Command::new("canberra-gtk-play")
                    .args(["-i", "camera-shutter"])
                    .status()
                    .is_ok_and(|status| status.success());
                if !played {
                    match std::process::Command::new("pw-play")
                        .arg("/usr/share/sounds/freedesktop/stereo/camera-shutter.oga")
                        .status()
                    {
                        Ok(status) if status.success() => {}
                        _ => tracing::warn!("Screenshot saved, but shutter sound playback failed"),
                    }
                }
            }
            busy.store(false, Ordering::Release);
        });
    if let Err(error) = worker {
        state.screenshot_busy.store(false, Ordering::Release);
        tracing::warn!(%error, "Could not start screenshot worker");
    }
}

/// Orientation through the exact renderer stack the native session uses
/// (GbmGles multi-GPU renderer, offscreen texture, damage-tracker render,
/// `read_framebuffer`). Needs a hardware render node; skipped without one.
#[cfg(all(test, feature = "native-drm"))]
mod gpu_orientation {
    use super::*;
    use smithay::{
        backend::{
            allocator::gbm::GbmDevice,
            drm::{DrmDeviceFd, DrmNode},
            egl::{EGLContext, EGLDisplay, context::ContextPriority},
            renderer::{
                Bind, Offscreen, Renderer,
                damage::OutputDamageTracker,
                element::{
                    Kind,
                    solid::{SolidColorBuffer, SolidColorRenderElement},
                },
                gles::{GlesRenderer, GlesTexture},
                multigpu::{GpuManager, gbm::GbmGlesBackend},
            },
        },
        output::{Mode, Output, PhysicalProperties, Subpixel},
        utils::{DeviceFd, Scale, Transform},
    };

    #[test]
    fn red_top_left_stays_at_the_top_through_the_native_renderer() {
        let Ok(path) = std::fs::read_dir("/dev/dri").map(|d| {
            d.flatten()
                .map(|e| e.path())
                .find(|p| p.to_string_lossy().contains("renderD"))
        }) else {
            return;
        };
        let Some(path) = path else { return };
        let Ok(file) = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(&path)
        else {
            return;
        };
        let drm_fd = DrmDeviceFd::new(DeviceFd::from(std::os::fd::OwnedFd::from(file)));
        let gbm = GbmDevice::new(drm_fd).unwrap();
        let display = unsafe { EGLDisplay::new(gbm.clone()).unwrap() };
        let node = DrmNode::from_path(&path).unwrap();
        let mut gpus = GpuManager::new(GbmGlesBackend::<GlesRenderer, DrmDeviceFd>::with_factory(
            |display| {
                let context = EGLContext::new_with_priority(display, ContextPriority::High)?;
                let capabilities = unsafe { GlesRenderer::supported_capabilities(&context)? };
                Ok(unsafe { GlesRenderer::with_capabilities(context, capabilities)? })
            },
        ))
        .unwrap();
        drop(display);
        gpus.as_mut().add_node(node, gbm).unwrap();
        let mut renderer = gpus.single_renderer(&node).unwrap();

        let output = Output::new(
            "test".into(),
            PhysicalProperties {
                size: (0, 0).into(),
                subpixel: Subpixel::Unknown,
                make: "t".into(),
                serial_number: "t".into(),
                model: "t".into(),
            },
        );
        let mode = Mode {
            size: (128, 128).into(),
            refresh: 60_000,
        };
        output.change_current_state(
            Some(mode),
            Some(Transform::Normal),
            Some(smithay::output::Scale::Integer(1)),
            Some((0, 0).into()),
        );
        output.set_preferred(mode);
        let buffer = SolidColorBuffer::new((64, 32), [1.0, 0.0, 0.0, 1.0]);
        let element = SolidColorRenderElement::from_buffer(
            &buffer,
            (0, 0),
            Scale::from(1.0),
            1.0,
            Kind::Unspecified,
        );
        let mut target = Offscreen::<GlesTexture>::create_buffer(
            &mut renderer,
            Fourcc::Abgr8888,
            (128, 128).into(),
        )
        .unwrap();
        let mut framebuffer = renderer.bind(&mut target).unwrap();
        let mut damage = OutputDamageTracker::from_output(&output);
        let rendered = damage
            .render_output(
                &mut renderer,
                &mut framebuffer,
                0,
                &[element],
                [0.0, 0.0, 1.0, 1.0],
            )
            .unwrap();
        renderer.wait(&rendered.sync).unwrap();
        let image = read_framebuffer(&mut renderer, &framebuffer, (128, 128).into()).unwrap();
        println!(
            "top-left {:?} bottom-left {:?}",
            image.get_pixel(10, 10),
            image.get_pixel(10, 120)
        );
        assert_eq!(
            image.get_pixel(10, 10).0,
            [255, 0, 0, 255],
            "red element must be at the top"
        );
        assert_eq!(image.get_pixel(10, 120).0, [0, 0, 255, 255]);
    }
}
