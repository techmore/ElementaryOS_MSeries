use smithay::{
    backend::{
        allocator::Fourcc,
        renderer::{
            ImportAll, ImportMem, Renderer, Texture,
            element::{
                Kind, Wrap,
                memory::{MemoryRenderBuffer, MemoryRenderBufferRenderElement},
                solid::{SolidColorBuffer, SolidColorRenderElement},
                surface::{WaylandSurfaceRenderElement, render_elements_from_surface_tree},
            },
        },
    },
    input::pointer::{CursorImageAttributes, CursorImageStatus},
    render_elements,
    utils::{IsAlive, Logical, Point, Rectangle, Scale, Size, Transform},
    wayland::compositor::with_states,
};

use crate::PantheonCompositor;

render_elements! {
    pub CursorRenderElement<R> where R: ImportAll + ImportMem;
    Surface=WaylandSurfaceRenderElement<R>,
    Memory=MemoryRenderBufferRenderElement<R>,
    Solid=SolidColorRenderElement,
    WrappedSurface=Wrap<WaylandSurfaceRenderElement<R>>,
}

pub fn default_cursor_buffer() -> MemoryRenderBuffer {
    const WIDTH: usize = 16;
    const HEIGHT: usize = 20;
    let mut pixels = vec![0; WIDTH * HEIGHT * 4];

    for y in 0..HEIGHT {
        let (first_x, last_x) = match y {
            0..=12 => (0, y),
            13..=17 => (6, 9),
            _ => (6, 8),
        };
        for x in first_x..=last_x {
            // Build a black outline around the white pointer body and stem.
            let outline = x == first_x || x == last_x || y == 12 || y == 18;
            let color = if outline {
                [0, 0, 0, 255]
            } else {
                [255, 255, 255, 255]
            };
            let offset = (y * WIDTH + x) * 4;
            pixels[offset..offset + 4].copy_from_slice(&color);
        }
    }

    MemoryRenderBuffer::from_slice(
        &pixels,
        Fourcc::Argb8888,
        (WIDTH as i32, HEIGHT as i32),
        1,
        Transform::Normal,
        None,
    )
}

pub fn render_cursor_elements<R>(
    renderer: &mut R,
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Vec<CursorRenderElement<R>>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    let Some(output_geometry) = state.space.output_geometry(output) else {
        return Vec::new();
    };
    let pointer_location = state.seat.get_pointer().unwrap().current_location();
    if !output_geometry.to_f64().contains(pointer_location) {
        return Vec::new();
    }

    let scale = Scale::from(output.current_scale().fractional_scale());
    let mut elements = match &state.cursor_status {
        CursorImageStatus::Hidden => Vec::new(),
        CursorImageStatus::Surface(surface) if surface.alive() => {
            let hotspot = with_states(surface, |states| {
                states
                    .data_map
                    .get::<std::sync::Mutex<CursorImageAttributes>>()
                    .and_then(|attributes| {
                        attributes.lock().ok().map(|attributes| attributes.hotspot)
                    })
                    .unwrap_or_default()
            });
            let location = (pointer_location - output_geometry.loc.to_f64() - hotspot.to_f64())
                .to_physical(scale)
                .to_i32_round();
            render_elements_from_surface_tree::<R, CursorRenderElement<R>>(
                renderer,
                surface,
                location,
                scale,
                1.0,
                Kind::Cursor,
            )
        }
        CursorImageStatus::Surface(_) | CursorImageStatus::Named(_) => {
            let location = (pointer_location - output_geometry.loc.to_f64())
                .to_physical(scale)
                .to_i32_round();
            MemoryRenderBufferRenderElement::from_buffer(
                renderer,
                location,
                &state.default_cursor,
                None,
                None,
                None,
                Kind::Cursor,
            )
            .map(CursorRenderElement::from)
            .ok()
            .into_iter()
            .collect()
        }
    };

    if let Some(preview) = state.corner_snap_preview.as_ref()
        && preview.output.name() == output.name()
    {
        let buffer = SolidColorBuffer::new(preview.rect.size, [0.18, 0.46, 0.92, 1.0]);
        let location = (preview.rect.loc - output_geometry.loc)
            .to_f64()
            .to_physical(scale)
            .to_i32_round();
        let element =
            SolidColorRenderElement::from_buffer(&buffer, location, scale, 0.28, Kind::Unspecified);
        elements.push(element.into());
    }

    elements.extend(render_shell_osd_elements(renderer, state, output));

    elements
}

fn render_shell_osd_elements<R>(
    _renderer: &mut R,
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Vec<CursorRenderElement<R>>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    let Some(osd) = state.shell_compat.active_osd() else {
        return Vec::new();
    };
    let outputs = state.space.outputs().collect::<Vec<_>>();
    let target_name = osd
        .connector
        .as_ref()
        .filter(|connector| {
            outputs
                .iter()
                .any(|candidate| candidate.name().as_str() == connector.as_str())
        })
        .cloned()
        .or_else(|| {
            osd.monitor
                .and_then(|index| outputs.get(index as usize).map(|target| target.name()))
        })
        .or_else(|| state.primary_output().map(|target| target.name()));
    if target_name.as_deref() != Some(output.name().as_str()) {
        return Vec::new();
    }
    let Some(geometry) = state.space.output_geometry(output) else {
        return Vec::new();
    };

    let width = 304.min(geometry.size.w.saturating_sub(32).max(120));
    let height = 76.min(geometry.size.h.saturating_sub(32).max(48));
    let card = Rectangle::<i32, Logical>::new(
        Point::from((
            geometry.loc.x + (geometry.size.w - width) / 2,
            geometry.loc.y + (geometry.size.h - height) / 2,
        )),
        Size::from((width, height)),
    );
    let scale = Scale::from(output.current_scale().fractional_scale());
    let mut elements = Vec::new();
    let mut append = |rect: Rectangle<i32, Logical>, color: [f32; 4], opacity: f32| {
        let location = (rect.loc - geometry.loc)
            .to_f64()
            .to_physical(scale)
            .to_i32_round();
        let size = rect.size;
        if size.w > 0 && size.h > 0 {
            let buffer = SolidColorBuffer::new(size, color);
            let element = SolidColorRenderElement::from_buffer(
                &buffer,
                location,
                scale,
                opacity,
                Kind::Unspecified,
            );
            elements.push(element.into());
        }
    };

    append(card, [0.055, 0.065, 0.085, 1.0], 0.94);
    let icon_x = card.loc.x + 22;
    let icon_y = card.loc.y + 25;
    if osd
        .icon
        .as_deref()
        .is_some_and(|icon| icon.contains("brightness"))
    {
        // A simple sun glyph keeps the brightness OSD recognizable without
        // pulling a shell toolkit or image stack into the compositor.
        append(
            Rectangle::new((icon_x + 7, icon_y + 7).into(), (12, 12).into()),
            [1.0, 0.86, 0.49, 1.0],
            1.0,
        );
        for (x, y, w, h) in [
            (icon_x + 11, icon_y, 4, 5),
            (icon_x + 11, icon_y + 21, 4, 5),
            (icon_x, icon_y + 11, 5, 4),
            (icon_x + 21, icon_y + 11, 5, 4),
            (icon_x + 3, icon_y + 3, 4, 4),
            (icon_x + 19, icon_y + 3, 4, 4),
            (icon_x + 3, icon_y + 19, 4, 4),
            (icon_x + 19, icon_y + 19, 4, 4),
        ] {
            append(
                Rectangle::new((x, y).into(), (w, h).into()),
                [1.0, 0.86, 0.49, 1.0],
                1.0,
            );
        }
    } else {
        // The sound indicator uses the same endpoint for volume and mute.
        append(
            Rectangle::new((icon_x, icon_y + 8).into(), (8, 12).into()),
            [0.76, 0.85, 1.0, 1.0],
            1.0,
        );
        append(
            Rectangle::new((icon_x + 8, icon_y + 3).into(), (7, 22).into()),
            [0.76, 0.85, 1.0, 1.0],
            1.0,
        );
        if !osd
            .icon
            .as_deref()
            .is_some_and(|icon| icon.contains("muted"))
        {
            append(
                Rectangle::new((icon_x + 18, icon_y + 8).into(), (4, 12).into()),
                [0.76, 0.85, 1.0, 1.0],
                1.0,
            );
        }
    }

    if let Some(level) = osd.level {
        let max_level = osd.max_level.filter(|value| *value > 0.0).unwrap_or(1.0);
        if level.is_finite() && max_level.is_finite() {
            let bar_width = (width - 76).max(32);
            let bar_height = 8;
            let bar_x = card.loc.x + 62;
            let bar_y = card.loc.y + (height - bar_height) / 2;
            append(
                Rectangle::new((bar_x, bar_y).into(), (bar_width, bar_height).into()),
                [0.28, 0.31, 0.37, 1.0],
                1.0,
            );
            let fill_width =
                ((level / max_level).clamp(0.0, 1.0) * f64::from(bar_width)).round() as i32;
            if fill_width > 0 {
                append(
                    Rectangle::new((bar_x, bar_y).into(), (fill_width, bar_height).into()),
                    [0.45, 0.67, 1.0, 1.0],
                    1.0,
                );
            }
        }
    }
    elements
}

pub fn render_lock_surface_elements<R>(
    renderer: &mut R,
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Vec<CursorRenderElement<R>>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    let output_name = output.name();
    let Some(surface) = state.lock_surfaces.get(&output_name) else {
        return Vec::new();
    };
    let scale = Scale::from(output.current_scale().fractional_scale());
    render_elements_from_surface_tree::<R, CursorRenderElement<R>>(
        renderer,
        surface.wl_surface(),
        (0, 0),
        scale,
        1.0,
        Kind::Unspecified,
    )
}
