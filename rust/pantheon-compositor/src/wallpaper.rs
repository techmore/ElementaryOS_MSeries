use gio::{
    Settings, SettingsBackend, SettingsSchemaSource,
    prelude::{FileExt, SettingsExt},
};
use smithay::{
    backend::{allocator::Fourcc, renderer::element::memory::MemoryRenderBuffer},
    utils::Transform,
};

pub(crate) struct Wallpaper {
    pub buffer: MemoryRenderBuffer,
    pub picture_options: String,
    pub width: u32,
    pub height: u32,
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
        Ok((buffer, width, height, path, picture_options)) => {
            tracing::info!(path = %path.display(), width, height, "loaded configured desktop wallpaper");
            Some(Wallpaper {
                buffer,
                picture_options,
                width,
                height,
            })
        }
        Err(error) => {
            tracing::warn!(%error, "could not load configured desktop wallpaper; using solid background");
            None
        }
    }
}

fn try_load_wallpaper(
    selection: &WallpaperSelection,
) -> Result<(MemoryRenderBuffer, u32, u32, std::path::PathBuf, String), Box<dyn std::error::Error>>
{
    let file = gio::File::for_uri(&selection.uri);
    let path = file
        .path()
        .ok_or("configured wallpaper is not a local file")?;

    let mut limits = image::Limits::default();
    limits.max_image_width = Some(16_384);
    limits.max_image_height = Some(16_384);
    limits.max_alloc = Some(256 * 1024 * 1024);
    let reader = image::ImageReader::open(&path)?.with_guessed_format()?;
    let mut reader = reader;
    reader.limits(limits);
    let decoded = reader.decode()?.into_rgba8();
    let (width, height) = decoded.dimensions();
    if width == 0 || height == 0 || u64::from(width) * u64::from(height) > 64 * 1024 * 1024 {
        return Err("wallpaper dimensions exceed the 64-megapixel limit".into());
    }

    // Fourcc::Argb8888 uses BGRA byte order on little-endian machines.
    let mut pixels = decoded.into_raw();
    for pixel in pixels.chunks_exact_mut(4) {
        pixel.swap(0, 2);
    }
    let buffer = MemoryRenderBuffer::from_slice(
        &pixels,
        Fourcc::Argb8888,
        (width as i32, height as i32),
        1,
        Transform::Normal,
        None,
    );
    Ok((
        buffer,
        width,
        height,
        path,
        selection.picture_options.clone(),
    ))
}
