use std::{
    cell::RefCell,
    collections::HashMap,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};

use gio::{
    Settings, SettingsBackend, SettingsSchemaSource,
    prelude::{FileExt, SettingsExt},
};
use smithay::{
    backend::{allocator::Fourcc, renderer::element::memory::MemoryRenderBuffer},
    reexports::calloop::channel::Sender,
    utils::{Buffer, Rectangle, Transform},
};

/// Distinguishes wallpaper loads, so a scaled copy finished for an old
/// wallpaper is dropped instead of shown.
static NEXT_GENERATION: AtomicU64 = AtomicU64::new(1);

pub(crate) struct Wallpaper {
    /// Full-resolution image, sampled by the GPU with a crop until a copy
    /// scaled for the output is ready. Dropped once every output has one.
    fallback: RefCell<Option<MemoryRenderBuffer>>,
    pub picture_options: String,
    pub width: u32,
    pub height: u32,
    path: PathBuf,
    opaque: bool,
    generation: u64,
    /// Copies scaled (and cropped) to an output's pixel size, drawn 1:1 so
    /// repaints sample nothing larger than the screen. `None` = being built.
    scaled: RefCell<HashMap<(i32, i32), Option<MemoryRenderBuffer>>>,
}

/// A helper thread's scaled copy for one output size.
pub(crate) struct ScaledWallpaper {
    generation: u64,
    size: (i32, i32),
    pixels: Result<Vec<u8>, String>,
}

/// What to draw for an output right now.
pub(crate) enum WallpaperBuffer {
    /// Scaled to the output: draw at its pixel size with no crop.
    Scaled(MemoryRenderBuffer),
    /// Full-size fallback: draw with this crop of the source.
    Fallback(
        MemoryRenderBuffer,
        Option<Rectangle<f64, smithay::utils::Logical>>,
    ),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct WallpaperSelection {
    uri: String,
    picture_options: String,
}

/// Load the desktop wallpaper selected by GNOME's shared background settings.
/// The decoded image is held as a CPU buffer and uploaded by Smithay's renderer
/// as needed on each output device.
pub(crate) fn configured_selection()
-> Result<Option<WallpaperSelection>, Box<dyn std::error::Error>> {
    let source = SettingsSchemaSource::default().ok_or("GSettings schemas are unavailable")?;
    let schema = source
        .lookup("org.gnome.desktop.background", true)
        .ok_or("desktop background settings schema is unavailable")?;
    let settings = Settings::new_full(&schema, None::<&SettingsBackend>, None);
    let uri = settings.string("picture-uri");
    if uri.is_empty() || uri == "file://" {
        return Ok(None);
    }
    Ok(Some(WallpaperSelection {
        uri: uri.to_string(),
        picture_options: settings.string("picture-options").to_string(),
    }))
}

pub(crate) fn load_wallpaper(selection: &WallpaperSelection) -> Option<Wallpaper> {
    match try_load_wallpaper(selection) {
        Ok(wallpaper) => {
            tracing::info!(path = %wallpaper.path.display(), width = wallpaper.width,
                height = wallpaper.height, opaque = wallpaper.opaque, "loaded configured desktop wallpaper");
            Some(wallpaper)
        }
        Err(error) => {
            tracing::warn!(%error, "could not load configured desktop wallpaper; using solid background");
            None
        }
    }
}

fn decode(path: &std::path::Path) -> Result<image::RgbaImage, Box<dyn std::error::Error>> {
    let mut limits = image::Limits::default();
    limits.max_image_width = Some(16_384);
    limits.max_image_height = Some(16_384);
    limits.max_alloc = Some(256 * 1024 * 1024);
    let mut reader = image::ImageReader::open(path)?.with_guessed_format()?;
    reader.limits(limits);
    let decoded = reader.decode()?.into_rgba8();
    let (width, height) = decoded.dimensions();
    if width == 0 || height == 0 || u64::from(width) * u64::from(height) > 64 * 1024 * 1024 {
        return Err("wallpaper dimensions exceed the 64-megapixel limit".into());
    }
    Ok(decoded)
}

/// RGBA → the BGRA byte order `Fourcc::Argb8888` uses on little-endian.
fn into_bgra(image: image::RgbaImage) -> Vec<u8> {
    let mut pixels = image.into_raw();
    for pixel in pixels.as_chunks_mut::<4>().0 {
        pixel.swap(0, 2);
    }
    pixels
}

fn memory_buffer(pixels: &[u8], width: i32, height: i32, opaque: bool) -> MemoryRenderBuffer {
    // A fully opaque wallpaper lets the damage tracker skip whatever is
    // underneath (the clear colour) instead of blending over it.
    let opaque_regions =
        opaque.then(|| vec![Rectangle::<i32, Buffer>::from_size((width, height).into())]);
    MemoryRenderBuffer::from_slice(
        pixels,
        Fourcc::Argb8888,
        (width, height),
        1,
        Transform::Normal,
        opaque_regions,
    )
}

fn try_load_wallpaper(
    selection: &WallpaperSelection,
) -> Result<Wallpaper, Box<dyn std::error::Error>> {
    let file = gio::File::for_uri(&selection.uri);
    let path = file
        .path()
        .ok_or("configured wallpaper is not a local file")?;
    let decoded = decode(&path)?;
    let (width, height) = decoded.dimensions();
    let opaque = decoded.pixels().all(|pixel| pixel[3] == u8::MAX);
    let pixels = into_bgra(decoded);
    Ok(Wallpaper {
        fallback: RefCell::new(Some(memory_buffer(
            &pixels,
            width as i32,
            height as i32,
            opaque,
        ))),
        picture_options: selection.picture_options.clone(),
        width,
        height,
        path,
        opaque,
        generation: NEXT_GENERATION.fetch_add(1, Ordering::Relaxed),
        scaled: RefCell::new(HashMap::new()),
    })
}

/// Part of a `source`-sized image shown on a `target`-shaped output: the
/// centred crop with the output's aspect for "zoom", the whole image otherwise.
pub(crate) fn zoom_crop(
    picture_options: &str,
    source: (f64, f64),
    target: (f64, f64),
) -> Option<(f64, f64, f64, f64)> {
    let ((source_w, source_h), (target_w, target_h)) = (source, target);
    if picture_options != "zoom" || target_w <= 0.0 || target_h <= 0.0 {
        return None;
    }
    let source_aspect = source_w / source_h;
    let target_aspect = target_w / target_h;
    if source_aspect > target_aspect {
        let width = source_h * target_aspect;
        Some(((source_w - width) / 2.0, 0.0, width, source_h))
    } else {
        let height = source_w / target_aspect;
        Some((0.0, (source_h - height) / 2.0, source_w, height))
    }
}

impl Wallpaper {
    /// The buffer to draw on an output `size` physical pixels large. Starts a
    /// helper thread for a scaled copy the first time a size is seen.
    pub(crate) fn buffer_for(
        &self,
        size: (i32, i32),
        ready: Option<&Sender<ScaledWallpaper>>,
    ) -> Option<WallpaperBuffer> {
        if let Some(Some(buffer)) = self.scaled.borrow().get(&size) {
            return Some(WallpaperBuffer::Scaled(buffer.clone()));
        }
        if let Some(ready) = ready
            && size.0 > 0
            && size.1 > 0
            && !self.scaled.borrow().contains_key(&size)
        {
            self.scaled.borrow_mut().insert(size, None);
            self.spawn_scale(size, ready.clone());
        }
        let crop = zoom_crop(
            &self.picture_options,
            (self.width as f64, self.height as f64),
            (size.0 as f64, size.1 as f64),
        )
        .map(|(x, y, w, h)| Rectangle::new((x, y).into(), (w, h).into()));
        self.fallback
            .borrow()
            .clone()
            .map(|buffer| WallpaperBuffer::Fallback(buffer, crop))
    }

    fn spawn_scale(&self, size: (i32, i32), ready: Sender<ScaledWallpaper>) {
        let path = self.path.clone();
        let options = self.picture_options.clone();
        let generation = self.generation;
        let spawned = std::thread::Builder::new()
            .name("wallpaper-scale".into())
            .spawn(move || {
                let started = std::time::Instant::now();
                let pixels = scale(&path, &options, size).map_err(|error| error.to_string());
                tracing::debug!(
                    ?size,
                    elapsed_ms = started.elapsed().as_millis() as u64,
                    ok = pixels.is_ok(),
                    "scaled desktop wallpaper for output"
                );
                let _ = ready.send(ScaledWallpaper {
                    generation,
                    size,
                    pixels,
                });
            });
        if let Err(error) = spawned {
            tracing::warn!(%error, "could not start the wallpaper scaling thread");
        }
    }

    /// Store a finished copy. Returns whether it belongs to this wallpaper.
    /// Once every size in `live_sizes` has a copy the full-size fallback is
    /// released.
    pub(crate) fn accept(&self, result: ScaledWallpaper, live_sizes: &[(i32, i32)]) -> bool {
        if result.generation != self.generation {
            return false;
        }
        match result.pixels {
            Ok(pixels) => {
                let buffer = memory_buffer(&pixels, result.size.0, result.size.1, self.opaque);
                self.scaled.borrow_mut().insert(result.size, Some(buffer));
            }
            Err(error) => {
                // Keep drawing the fallback for this size; do not retry.
                tracing::warn!(%error, size = ?result.size, "could not scale the desktop wallpaper");
                return true;
            }
        }
        let scaled = self.scaled.borrow();
        if live_sizes
            .iter()
            .all(|size| matches!(scaled.get(size), Some(Some(_))))
        {
            self.fallback.borrow_mut().take();
        }
        true
    }
}

/// Decode, crop and resize for one output size, off the compositor thread.
fn scale(
    path: &std::path::Path,
    picture_options: &str,
    (width, height): (i32, i32),
) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let decoded = decode(path)?;
    let (source_w, source_h) = decoded.dimensions();
    let cropped = match zoom_crop(
        picture_options,
        (source_w as f64, source_h as f64),
        (width as f64, height as f64),
    ) {
        Some((x, y, w, h)) => image::imageops::crop_imm(
            &decoded,
            x.round() as u32,
            y.round() as u32,
            (w.round() as u32).clamp(1, source_w),
            (h.round() as u32).clamp(1, source_h),
        )
        .to_image(),
        None => decoded,
    };
    let resized = image::imageops::resize(
        &cropped,
        width as u32,
        height as u32,
        image::imageops::FilterType::Triangle,
    );
    Ok(into_bgra(resized))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zoom_crops_the_long_side_to_the_output_aspect() {
        // 5000×2813 (16:9) on a 3024×1964 panel: keep full height, trim width.
        let (x, y, w, h) = zoom_crop("zoom", (5000.0, 2813.0), (3024.0, 1964.0)).unwrap();
        assert_eq!(y, 0.0);
        assert_eq!(h, 2813.0);
        assert!((w / h - 3024.0 / 1964.0).abs() < 1e-9);
        assert!((x - (5000.0 - w) / 2.0).abs() < 1e-9);
        // A tall image on a wide output trims the height instead.
        let (x, _, w, h) = zoom_crop("zoom", (1000.0, 2000.0), (1920.0, 1080.0)).unwrap();
        assert_eq!((x, w), (0.0, 1000.0));
        assert!((w / h - 1920.0 / 1080.0).abs() < 1e-9);
    }

    #[test]
    fn other_modes_show_the_whole_image() {
        assert_eq!(
            zoom_crop("stretched", (5000.0, 2813.0), (3024.0, 1964.0)),
            None
        );
        assert_eq!(zoom_crop("zoom", (5000.0, 2813.0), (0.0, 1964.0)), None);
    }

    #[test]
    fn scaled_copy_has_the_output_size_and_bgra_order() {
        let dir = std::env::temp_dir().join(format!("pantheon-wallpaper-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("red.png");
        image::RgbaImage::from_pixel(64, 36, image::Rgba([255, 0, 0, 255]))
            .save(&path)
            .unwrap();
        let pixels = scale(&path, "zoom", (30, 20)).unwrap();
        assert_eq!(pixels.len(), 30 * 20 * 4);
        assert_eq!(&pixels[..4], &[0, 0, 255, 255]);
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
