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
    let bottom_up = !mapping.flipped();
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
        + ExportMem,
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
        + ExportMem,
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
    let mut images = Vec::new();
    let mut pixels = 0_u64;
    for output in outputs {
        let result = compose_output(renderer, state, output);
        match result {
            Ok(image) => {
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
                let _ = std::process::Command::new("canberra-gtk-play")
                    .args(["-i", "camera-shutter"])
                    .status();
            }
            busy.store(false, Ordering::Release);
        });
    if let Err(error) = worker {
        state.screenshot_busy.store(false, Ordering::Release);
        tracing::warn!(%error, "Could not start screenshot worker");
    }
}
