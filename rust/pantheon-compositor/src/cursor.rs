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
    utils::{IsAlive, Scale, Transform},
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
