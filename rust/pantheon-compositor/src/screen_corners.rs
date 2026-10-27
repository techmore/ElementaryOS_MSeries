//! A lightweight output mask for rounded built-in display panels.
//!
//! This belongs in the compositor because client-side window styling cannot
//! mask the physical display. The masks are small, cached memory textures and
//! are drawn as four final scene elements; they add no polling or animation.

use std::{cell::RefCell, collections::HashMap};

use smithay::{
    backend::{
        allocator::Fourcc,
        renderer::{
            ImportAll, ImportMem, Renderer, Texture,
            element::{Kind, memory::MemoryRenderBuffer},
        },
    },
    utils::{Logical, Point, Scale, Size, Transform},
};

use crate::cursor::CursorRenderElement;

const ENV_RADIUS: &str = "PANTHEON_SCREEN_CORNER_RADIUS";
const DEFAULT_RADIUS: i32 = 20;
const MAX_RADIUS: i32 = 128;
/// Supersampling makes the curve smooth at fractional and high-DPI scales.
const BUFFER_SCALE: i32 = 4;
const COVERAGE_SAMPLES: i32 = 2;

#[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)]
enum Corner {
    TopLeft,
    TopRight,
    BottomLeft,
    BottomRight,
}

impl Corner {
    const ALL: [Self; 4] = [
        Self::TopLeft,
        Self::TopRight,
        Self::BottomLeft,
        Self::BottomRight,
    ];

    fn is_right(self) -> bool {
        matches!(self, Self::TopRight | Self::BottomRight)
    }

    fn is_bottom(self) -> bool {
        matches!(self, Self::BottomLeft | Self::BottomRight)
    }
}

/// Rounded corner support is opt-in only for recognized internal panels.
/// `PANTHEON_SCREEN_CORNER_RADIUS=0` disables it; positive values are logical
/// pixels. The default follows the existing M-series Gala mask provisionally.
pub(crate) struct ScreenCorners {
    radius: i32,
    buffers: RefCell<HashMap<(Corner, i32), MemoryRenderBuffer>>,
}

impl Default for ScreenCorners {
    fn default() -> Self {
        Self {
            radius: DEFAULT_RADIUS,
            buffers: RefCell::new(HashMap::new()),
        }
    }
}

impl ScreenCorners {
    pub(crate) fn from_environment() -> Self {
        let radius = match std::env::var(ENV_RADIUS) {
            Ok(value) => match value.parse::<i32>() {
                Ok(radius) if (0..=MAX_RADIUS).contains(&radius) => radius,
                _ => {
                    tracing::warn!(
                        value,
                        maximum = MAX_RADIUS,
                        "ignoring invalid screen-corner radius"
                    );
                    DEFAULT_RADIUS
                }
            },
            Err(std::env::VarError::NotPresent) => DEFAULT_RADIUS,
            Err(error) => {
                tracing::warn!(%error, "ignoring unreadable screen-corner radius");
                DEFAULT_RADIUS
            }
        };
        Self {
            radius,
            buffers: RefCell::new(HashMap::new()),
        }
    }

    pub(crate) fn elements<R>(
        &self,
        renderer: &mut R,
        output: &smithay::output::Output,
        output_size: Option<Size<i32, Logical>>,
    ) -> Vec<CursorRenderElement<R>>
    where
        R: Renderer + ImportAll + ImportMem,
        R::TextureId: Texture + Clone + Send + 'static,
    {
        if self.radius == 0 || !is_builtin_panel(&output.name()) {
            return Vec::new();
        }
        let Some(output_size) = output_size else {
            return Vec::new();
        };
        let radius = self.radius.min(output_size.w / 2).min(output_size.h / 2);
        if radius <= 0 {
            return Vec::new();
        }

        let scale = Scale::from(output.current_scale().fractional_scale());
        let physical_size = output_size
            .to_f64()
            .to_physical(scale)
            .to_i32_round::<i32>();
        let radius_physical = Size::from((radius, radius))
            .to_f64()
            .to_physical(scale)
            .to_i32_round::<i32>();

        let mut elements = Vec::with_capacity(4);
        for corner in Corner::ALL {
            let buffer = self.buffer(corner, radius);
            let x = if corner.is_right() {
                physical_size.w - radius_physical.w
            } else {
                0
            };
            let y = if corner.is_bottom() {
                physical_size.h - radius_physical.h
            } else {
                0
            };
            if let Ok(element) =
                smithay::backend::renderer::element::memory::MemoryRenderBufferRenderElement::from_buffer(
                    renderer,
                    Point::<i32, smithay::utils::Physical>::from((x, y)).to_f64(),
                    &buffer,
                    None,
                    None,
                    Some((radius, radius).into()),
                    Kind::Unspecified,
                )
            {
                elements.push(CursorRenderElement::from(element));
            }
        }
        elements
    }

    fn buffer(&self, corner: Corner, radius: i32) -> MemoryRenderBuffer {
        let mut buffers = self.buffers.borrow_mut();
        buffers
            .entry((corner, radius))
            .or_insert_with(|| make_corner_buffer(corner, radius))
            .clone()
    }
}

fn is_builtin_panel(name: &str) -> bool {
    let name = name.to_ascii_lowercase();
    ["edp-", "lvds-", "dsi-"]
        .iter()
        .any(|prefix| name.starts_with(prefix))
}

fn make_corner_buffer(corner: Corner, radius: i32) -> MemoryRenderBuffer {
    let pixels = make_corner_pixels(corner, radius);
    let size = (radius * BUFFER_SCALE) as usize;
    MemoryRenderBuffer::from_slice(
        &pixels,
        Fourcc::Argb8888,
        (size as i32, size as i32),
        BUFFER_SCALE,
        Transform::Normal,
        None,
    )
}

fn make_corner_pixels(corner: Corner, radius: i32) -> Vec<u8> {
    let size = (radius * BUFFER_SCALE) as usize;
    let mut pixels = vec![0; size * size * 4];
    let samples_per_pixel = COVERAGE_SAMPLES * COVERAGE_SAMPLES;

    for pixel_y in 0..size {
        for pixel_x in 0..size {
            let mut outside = 0;
            for sample_y in 0..COVERAGE_SAMPLES {
                for sample_x in 0..COVERAGE_SAMPLES {
                    let local_x = (pixel_x as f64
                        + (sample_x as f64 + 0.5) / COVERAGE_SAMPLES as f64)
                        / BUFFER_SCALE as f64;
                    let local_y = (pixel_y as f64
                        + (sample_y as f64 + 0.5) / COVERAGE_SAMPLES as f64)
                        / BUFFER_SCALE as f64;
                    let distance_x = if corner.is_right() {
                        radius as f64 - local_x
                    } else {
                        local_x
                    };
                    let distance_y = if corner.is_bottom() {
                        radius as f64 - local_y
                    } else {
                        local_y
                    };
                    if !inside_superellipse(distance_x, distance_y, radius as f64) {
                        outside += 1;
                    }
                }
            }
            let alpha = (outside * 255 / samples_per_pixel) as u8;
            let offset = (pixel_y * size + pixel_x) * 4;
            // Fourcc::Argb8888 is BGRA byte order on little-endian hosts.
            pixels[offset..offset + 4].copy_from_slice(&[0, 0, 0, alpha]);
        }
    }
    pixels
}

fn inside_superellipse(distance_x: f64, distance_y: f64, radius: f64) -> bool {
    let x = (1.0 - distance_x / radius).clamp(0.0, 1.0);
    let y = (1.0 - distance_y / radius).clamp(0.0, 1.0);
    x.powi(4) + y.powi(4) <= 1.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_internal_panel_connector_names_match() {
        for name in ["eDP-1", "LVDS-0", "DSI-1"] {
            assert!(is_builtin_panel(name));
        }
        for name in ["HDMI-A-1", "DP-1", "Virtual-1"] {
            assert!(!is_builtin_panel(name));
        }
    }

    #[test]
    fn generated_masks_mirror_the_curve_by_corner() {
        let radius = 12;
        let size = (radius * BUFFER_SCALE) as usize;
        let masks = Corner::ALL.map(|corner| make_corner_pixels(corner, radius));
        let alpha = |mask: &[u8], x: usize, y: usize| mask[(y * size + x) * 4 + 3];
        let (top_left, top_right, bottom_left, bottom_right) =
            (&masks[0], &masks[1], &masks[2], &masks[3]);

        assert!(alpha(top_left, 0, 0) > 0);
        assert_eq!(alpha(top_left, size / 2, size / 2), 0);
        for y in 0..size {
            for x in 0..size {
                assert_eq!(alpha(top_left, x, y), alpha(top_right, size - 1 - x, y));
                assert_eq!(alpha(top_left, x, y), alpha(bottom_left, x, size - 1 - y));
                assert_eq!(
                    alpha(top_left, x, y),
                    alpha(bottom_right, size - 1 - x, size - 1 - y)
                );
            }
        }
    }
}
