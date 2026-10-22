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
