//! Publish a complete, private PNG without replacing an existing capture.
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::{
    fs,
    io::{BufWriter, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static NEXT_CAPTURE: AtomicU64 = AtomicU64::new(0);

/// Call on a capture worker, never on the compositor's input/render loop.
pub fn save_png(directory: &Path, image: &image::RgbaImage) -> Result<PathBuf, String> {
    if image.width() == 0
        || image.height() == 0
        || u64::from(image.width()) * u64::from(image.height()) > 32 * 1024 * 1024
    {
        return Err("Screenshot dimensions exceed the capture limit".into());
    }
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(directory)
        .map_err(|error| format!("Could not create screenshot directory: {error}"))?;
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "Could not read screenshot timestamp")?
        .as_nanos();
    let unique = format!(
        "{stamp}-{}-{}",
        std::process::id(),
        NEXT_CAPTURE.fetch_add(1, Ordering::Relaxed)
    );
    let temporary = directory.join(format!(".capture-{unique}.tmp"));
    let final_path = directory.join(format!("Screenshot-{unique}.png"));
    let file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&temporary)
        .map_err(|error| format!("Could not create screenshot file: {error}"))?;
    let result = (|| {
        let mut writer = BufWriter::new(file);
        image
            .write_to(&mut writer, image::ImageFormat::Png)
            .map_err(|error| format!("Could not encode screenshot: {error}"))?;
        writer
            .flush()
            .map_err(|error| format!("Could not finish screenshot: {error}"))?;
        writer
            .get_ref()
            .sync_all()
            .map_err(|error| format!("Could not save screenshot: {error}"))?;
        // A same-directory hard link publishes the complete inode atomically and
        // fails if the destination exists; rename could overwrite a saved image.
        fs::hard_link(&temporary, &final_path)
            .map_err(|error| format!("Could not publish screenshot: {error}"))?;
        Ok(final_path)
    })();
    let _ = fs::remove_file(&temporary);
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    #[test]
    fn publishes_complete_private_pngs_without_overwriting() {
        let directory = std::env::temp_dir().join(format!(
            "pantheon-capture-test-{}-{}",
            std::process::id(),
            NEXT_CAPTURE.fetch_add(1, Ordering::Relaxed)
        ));
        let pixels = image::RgbaImage::from_pixel(2, 2, image::Rgba([10, 20, 30, 255]));
        let first = save_png(&directory, &pixels).unwrap();
        let second = save_png(&directory, &pixels).unwrap();
        assert_ne!(first, second);
        assert_eq!(
            fs::metadata(&first).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(image::open(&first).unwrap().to_rgba8(), pixels);
        assert_eq!(fs::read_dir(&directory).unwrap().count(), 2);
        fs::remove_dir_all(directory).unwrap();
    }
}
