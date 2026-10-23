use std::{collections::HashMap, sync::Mutex};

use gio::{Settings, SettingsBackend, SettingsSchemaSource, prelude::SettingsExt};
use smithay::{
    backend::{allocator::Fourcc, renderer::element::memory::MemoryRenderBuffer},
    input::pointer::CursorIcon,
    utils::{Logical, Point, Transform},
};

use crate::cursor::default_cursor_buffer;

const DEFAULT_THEME: &str = "elementary";
const DEFAULT_SIZE: u32 = 24;
const MAX_BUFFER_SCALE: i32 = 3;

/// One decoded cursor frame at a given buffer scale. The hotspot is in
/// logical pixels so it can be subtracted from the pointer location directly.
#[derive(Clone)]
pub(crate) struct ThemedCursor {
    pub buffer: MemoryRenderBuffer,
    pub hotspot: Point<f64, Logical>,
    #[cfg(test)]
    width: u32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct CursorSelection {
    theme: String,
    size: u32,
}

/// The compositor-drawn cursor shown when no client provides a cursor surface
/// (the desktop background, window borders, the drag preview). It follows the
/// same GNOME interface settings that GTK clients use, so the pointer does not
/// change appearance when it leaves an application window.
pub(crate) struct CursorTheme {
    selection: CursorSelection,
    theme: xcursor::CursorTheme,
    images: Mutex<HashMap<(CursorIcon, i32), Option<ThemedCursor>>>,
    fallback: ThemedCursor,
}

impl CursorTheme {
    pub(crate) fn load(selection: CursorSelection) -> Self {
        tracing::info!(theme = %selection.theme, size = selection.size, "loading compositor cursor theme");
        Self {
            theme: xcursor::CursorTheme::load(&selection.theme),
            selection,
            images: Mutex::new(HashMap::new()),
            fallback: ThemedCursor {
                buffer: default_cursor_buffer(),
                hotspot: Point::default(),
                #[cfg(test)]
                width: 16,
            },
        }
    }

    pub(crate) fn selection(&self) -> &CursorSelection {
        &self.selection
    }

    /// Return the themed image for `icon` rendered for an output whose
    /// fractional scale is `output_scale`, decoding it on first use.
    pub(crate) fn image(&self, icon: CursorIcon, output_scale: f64) -> ThemedCursor {
        let buffer_scale = (output_scale.ceil() as i32).clamp(1, MAX_BUFFER_SCALE);
        let mut images = self
            .images
            .lock()
            .unwrap_or_else(|poison| poison.into_inner());
        let entry = images.entry((icon, buffer_scale)).or_insert_with(|| {
            let loaded = self.decode(icon, buffer_scale).or_else(|| {
                (icon != CursorIcon::Default)
                    .then(|| self.decode(CursorIcon::Default, buffer_scale))
                    .flatten()
            });
            if loaded.is_none() {
                tracing::warn!(theme = %self.selection.theme, ?icon, "cursor theme image unavailable; using built-in pointer");
            }
            loaded
        });
        entry.clone().unwrap_or_else(|| self.fallback.clone())
    }

    fn decode(&self, icon: CursorIcon, buffer_scale: i32) -> Option<ThemedCursor> {
        let path = std::iter::once(icon.name())
            .chain(icon.alt_names().iter().copied())
            .chain((icon == CursorIcon::Default).then_some("left_ptr"))
            .find_map(|name| self.theme.load_icon(name))?;
        let content = std::fs::read(&path).ok()?;
        let images = xcursor::parser::parse_xcursor(&content)?;
        let target = self.selection.size * buffer_scale as u32;
        // Prefer the nominal size closest to the target; ties favour the larger
        // image so the renderer scales down rather than up.
        let nominal = images
            .iter()
            .map(|image| image.size)
            .min_by_key(|size| (size.abs_diff(target), u32::MAX - size))?;
        // Animated cursors are drawn using their first frame.
        let frame = images.iter().find(|image| image.size == nominal)?;
        let buffer = MemoryRenderBuffer::from_slice(
            &frame.pixels_rgba,
            Fourcc::Abgr8888,
            (frame.width as i32, frame.height as i32),
            buffer_scale,
            Transform::Normal,
            None,
        );
        Some(ThemedCursor {
            buffer,
            hotspot: (
                frame.xhot as f64 / buffer_scale as f64,
                frame.yhot as f64 / buffer_scale as f64,
            )
                .into(),
            #[cfg(test)]
            width: frame.width,
        })
    }
}

/// Read the cursor theme and size from `org.gnome.desktop.interface`, falling
/// back to `XCURSOR_THEME`/`XCURSOR_SIZE` and then to elementary defaults.
pub(crate) fn configured_selection() -> CursorSelection {
    let settings = SettingsSchemaSource::default()
        .and_then(|source| source.lookup("org.gnome.desktop.interface", true))
        .map(|schema| Settings::new_full(&schema, None::<&SettingsBackend>, None));
    let theme = settings
        .as_ref()
        .map(|settings| settings.string("cursor-theme").to_string())
        .filter(|theme| !theme.is_empty())
        .or_else(|| {
            std::env::var("XCURSOR_THEME")
                .ok()
                .filter(|theme| !theme.is_empty())
        })
        .unwrap_or_else(|| DEFAULT_THEME.to_string());
    let size = settings
        .as_ref()
        .and_then(|settings| u32::try_from(settings.int("cursor-size")).ok())
        .filter(|size| (8..=256).contains(size))
        .or_else(|| {
            std::env::var("XCURSOR_SIZE")
                .ok()
                .and_then(|size| size.parse().ok())
        })
        .unwrap_or(DEFAULT_SIZE);
    CursorSelection { theme, size }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hidpi_outputs_get_a_higher_resolution_themed_pointer() {
        let theme = CursorTheme::load(CursorSelection {
            theme: DEFAULT_THEME.to_string(),
            size: 24,
        });
        if theme.theme.load_icon("left_ptr").is_none() {
            eprintln!("elementary cursor theme is not installed; skipping");
            return;
        }
        let normal = theme.image(CursorIcon::Default, 1.0);
        let hidpi = theme.image(CursorIcon::Default, 2.0);
        let fractional = theme.image(CursorIcon::Default, 1.5);
        assert_ne!(hidpi.width, 16, "fell back to the built-in arrow");
        assert!(hidpi.width > normal.width);
        assert_eq!(fractional.width, hidpi.width);
        assert!(hidpi.hotspot.x >= 0.0 && hidpi.hotspot.x < 24.0);
        assert_ne!(theme.image(CursorIcon::Text, 2.0).width, 16);
    }
}
